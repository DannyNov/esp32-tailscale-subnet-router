"""wgopt12: bounded deferred retry of Wi-Fi driver NO_MEM on direct WG DATA.

Overlay touches only generated pinned-microlink copy. It holds one additional
pbuf reference (no payload copy); the WireGuard caller may release its own
reference immediately after returning from the output callback.
"""
from derp_header_overlay import once

RETRY_IMPL = r"""
/* wgopt12: no waits, allocations or logs on the hot data path.
 * Only direct WG DATA is deferred. The original encrypted PBUF_RAM is
 * pbuf_ref'd, queued at most 8 deep and released on all completion paths.
 * A soft timer posts a bounded, nonblocking resend to the TCPIP task.
 * New DATA follows FIFO during backlog, avoiding bypass/overtaking. */
#define WG12_QCAP 8u
#define WG12_DELAY_US 3000u
#define WG12_TTL_US 50000LL
#define WG12_MAX_TRIES 2u
typedef struct {
    struct pbuf *p;
    uint32_t ip;
    uint16_t port;
    uint8_t tries;
    int64_t since_us;
} wg12_entry_t;
static wg12_entry_t wg12_q[WG12_QCAP];
static uint8_t wg12_head, wg12_count;
static bool wg12_running, wg12_enabled;
static esp_timer_handle_t wg12_timer;
static portMUX_TYPE wg12_mux = portMUX_INITIALIZER_UNLOCKED;
static void wg12_flush_cb(void *arg);

static void wg12_arm(void) {
    if (!wg12_timer || !__atomic_load_n(&wg12_enabled, __ATOMIC_ACQUIRE)) return;
    esp_err_t e = esp_timer_start_once(wg12_timer, WG12_DELAY_US);
    if (e != ESP_OK && e != ESP_ERR_INVALID_STATE) {
        wg12_diag_add(WG12_POSTFAIL);
        /* Never strand a reference if a timer cannot be scheduled. */
        if (tcpip_callback(wg12_flush_cb, NULL) != ERR_OK)
            wg12_diag_add(WG12_POSTFAIL);
    }
}
static bool wg12_backlogged(void) {
    bool found;
    portENTER_CRITICAL(&wg12_mux);
    found = wg12_enabled && (wg12_count > 0 || wg12_running);
    portEXIT_CRITICAL(&wg12_mux);
    return found;
}
static bool wg12_enqueue(struct pbuf *p, uint32_t ip, uint16_t port, bool behind) {
    if (!p || !wg12_timer) return false;
    const int64_t now = esp_timer_get_time();
    bool accepted = false;
    portENTER_CRITICAL(&wg12_mux);
    if (wg12_enabled && wg12_count < WG12_QCAP) {
        uint8_t tail = (uint8_t)((wg12_head + wg12_count) % WG12_QCAP);
        pbuf_ref(p); /* acquire exactly one queue-owned reference */
        wg12_q[tail] = (wg12_entry_t){
            .p = p, .ip = ip, .port = port, .tries = 0, .since_us = now
        };
        wg12_count++;
        accepted = true;
    }
    portEXIT_CRITICAL(&wg12_mux);
    if (accepted) {
        wg12_diag_add(WG12_ENQ);
        if (behind) wg12_diag_add(WG12_BACKLOG);
        wg12_arm();
    } else {
        wg12_diag_add(WG12_FULL);
    }
    return accepted;
}
/* Called on the TCPIP thread, one packet per callback (no burst drain). */
static void wg12_flush_cb(void *arg) {
    (void)arg;
    wg12_entry_t e = {0};
    portENTER_CRITICAL(&wg12_mux);
    if (wg12_enabled && !wg12_running && wg12_count) {
        e = wg12_q[wg12_head];
        wg12_q[wg12_head].p = NULL;
        wg12_head = (uint8_t)((wg12_head + 1u) % WG12_QCAP);
        wg12_count--;
        wg12_running = true;
    }
    portEXIT_CRITICAL(&wg12_mux);
    if (!e.p) return;

    err_t result = ERR_MEM;
    bool tried = false;
    if (wg12_enabled && s_wg_output_pcb &&
        esp_timer_get_time() - e.since_us <= WG12_TTL_US) {
        ip_addr_t dest;
        IP_SET_TYPE_VAL(dest, IPADDR_TYPE_V4);
        ip4_addr_set_u32(ip_2_ip4(&dest), e.ip);
        result = udp_sendto(s_wg_output_pcb, e.p, &dest, e.port);
        tried = true;
    }

    bool retained = false;
    if (tried && result == ERR_MEM && e.tries + 1u < WG12_MAX_TRIES &&
        esp_timer_get_time() - e.since_us <= WG12_TTL_US) {
        e.tries++;
        portENTER_CRITICAL(&wg12_mux);
        if (wg12_enabled && wg12_count < WG12_QCAP) {
            wg12_head = (uint8_t)((wg12_head + WG12_QCAP - 1u) % WG12_QCAP);
            wg12_q[wg12_head] = e; /* oldest back to head */
            wg12_count++;
            retained = true;
        }
        portEXIT_CRITICAL(&wg12_mux);
        wg12_diag_add(WG12_NOMEM);
    }
    if (!retained) {
        wg12_diag_add(tried && result == ERR_OK ? WG12_DONE : WG12_DROP);
        pbuf_free(e.p); /* release our reference; driver may hold another */
    }
    portENTER_CRITICAL(&wg12_mux);
    wg12_running = false;
    const bool pending = wg12_enabled && wg12_count != 0;
    portEXIT_CRITICAL(&wg12_mux);
    if (pending) wg12_arm();
}
static void wg12_timer_cb(void *arg) {
    (void)arg;
    if (!__atomic_load_n(&wg12_enabled, __ATOMIC_ACQUIRE)) return;
    if (tcpip_callback(wg12_flush_cb, NULL) != ERR_OK) {
        wg12_diag_add(WG12_POSTFAIL);
        wg12_arm();
    }
}
static void wg12_start(void) {
    if (!wg12_timer) {
        const esp_timer_create_args_t args = {
            .callback = wg12_timer_cb, .name = "wg12_retry"
        };
        if (esp_timer_create(&args, &wg12_timer) != ESP_OK) {
            ESP_LOGW("WG12_TX", "Timer unavailable: direct retry disabled");
            return;
        }
    }
    portENTER_CRITICAL(&wg12_mux);
    wg12_enabled = true;
    portEXIT_CRITICAL(&wg12_mux);
}
/* Stop barrier on TCPIP thread: no posted flush can race draining refs. */
static void wg12_discard_cb(void *arg) {
    (void)arg;
    for (;;) {
        struct pbuf *p = NULL;
        portENTER_CRITICAL(&wg12_mux);
        if (wg12_count) {
            p = wg12_q[wg12_head].p;
            wg12_q[wg12_head].p = NULL;
            wg12_head = (uint8_t)((wg12_head + 1u) % WG12_QCAP);
            wg12_count--;
        }
        portEXIT_CRITICAL(&wg12_mux);
        if (!p) break;
        wg12_diag_add(WG12_STOP);
        pbuf_free(p);
    }
}
static void wg12_stop(void) {
    portENTER_CRITICAL(&wg12_mux);
    wg12_enabled = false;
    portEXIT_CRITICAL(&wg12_mux);
    if (wg12_timer) esp_timer_stop(wg12_timer);
    if (tcpip_callback_with_block(wg12_discard_cb, NULL, 1) != ERR_OK)
        wg12_discard_cb(NULL);
}
"""

def apply(component):
    mgr = component / "src/ml_wg_mgr.c"
    s = mgr.read_text()
    s = once(s, '#include "esp_heap_caps.h"',
             '#include "esp_heap_caps.h"\n#include "esp_timer.h"')
    s = once(s, 'static struct udp_pcb *s_wg_output_pcb = NULL;',
             'static struct udp_pcb *s_wg_output_pcb = NULL;\n' + RETRY_IMPL)
    s = once(s, '    wireguardif_set_derp_output(netif, wg_derp_output_cb, ml);',
             '    wg12_start();\n    wireguardif_set_derp_output(netif, wg_derp_output_cb, ml);')
    s = once(s, '    /* Shutdown WireGuard interface. ml->wg_netif goes NULL first',
             '    wg12_stop();\n    /* Shutdown WireGuard interface. ml->wg_netif goes NULL first')

    begin = s.index('static err_t wgopt1_udp_pbuf_output_cb(')
    end = s.index('static err_t wg_udp_output_cb(', begin)
    body = s[begin:end]
    anchor = '    err_t err = udp_sendto(s_wg_output_pcb, p, &dst, dest_port);'
    pre = """    const bool data_packet = packet_len >= 4 && packet_data[0] == 4 &&
        packet_data[1] == 0 && packet_data[2] == 0 && packet_data[3] == 0;
    if (data_packet && wg12_backlogged())
        return wg12_enqueue(p, dest_ip, dest_port, true) ? ERR_OK : ERR_MEM;
"""
    body = once(body, '    wg9_direct_udp_begin();', pre + '    wg9_direct_udp_begin();')
    body = once(body, '    wg9_direct_udp_end(err);',
        """    const bool driver_nomem = err == ERR_MEM && wg10_wifi_nomem_in_scope();
    wg9_direct_udp_end(err);
    if (driver_nomem && data_packet && wg12_enqueue(p, dest_ip, dest_port, false))
        err = ERR_OK; /* Queue-accepted, not yet accepted by Wi-Fi. */""")
    s = s[:begin] + body + s[end:]
    mgr.write_text(s)
