"""wgopt12: generated-overlay and executable reference-ownership regression."""
from pathlib import Path
from tempfile import TemporaryDirectory
import subprocess
import os
import shlex
from prepare_wg_diagnostics import ROOT, prepare
from wgopt12_overlay import RETRY_IMPL

with TemporaryDirectory(prefix="wgopt12-") as tmp:
    output = Path(tmp)
    prepare(output)
    mgr = (output / "microlink/src/ml_wg_mgr.c").read_text()
    src = mgr.split("static err_t wgopt1_udp_pbuf_output_cb(", 1)[1].split(
        "static err_t wg_udp_output_cb(", 1)[0]
    diag = (output / "microlink/components/wireguard_lwip/src/wg_diag.c").read_text()
    hdr = (output / "microlink/components/wireguard_lwip/src/wg_diag.h").read_text()
    # Scope remains balanced even when backlog redirects before udp_sendto.
    assert src.index("wg12_backlogged()") < src.index("wg9_direct_udp_begin()")
    assert src.index("wg9_direct_udp_begin()") < src.index("udp_sendto(")
    assert src.index("udp_sendto(") < src.index("wg10_wifi_nomem_in_scope()")
    assert src.index("wg10_wifi_nomem_in_scope()") < src.index("wg9_direct_udp_end(err)")
    assert src.count("wg9_direct_udp_end(err)") == 1
    assert "packet_data[0] == 4" in src and "driver_nomem && data_packet" in src
    assert "wgopt1_send_both(ml, dest_ip, packet_data, packet_len);" in src
    assert "wireguardif_set_udp_pbuf_output(netif, wgopt1_udp_pbuf_output_cb, ml);" in mgr
    assert mgr.index("wg12_stop();") < mgr.index("wireguardif_shutdown(netif)")
    assert "wg12_start();" in mgr
    assert "int wg10_wifi_nomem_in_scope(void)" in diag
    assert "wg12_report();" in diag and "WG12_TX" in diag
    assert "WG12_BACKLOG" in hdr
    assert "CONFIG_ESP_WIFI_STATIC_TX_BUFFER_NUM=32" in (ROOT / "sdkconfig.defaults").read_text()
    assert "CONFIG_ESP_WIFI_CACHE_TX_BUFFER_NUM=32" in (ROOT / "sdkconfig.defaults").read_text()
    assert "#define WG12_QCAP 8u" in RETRY_IMPL
    assert "#define WG12_TTL_US 50000LL" in RETRY_IMPL
    assert "#define WG12_MAX_TRIES 2u" in RETRY_IMPL
    assert "pbuf_ref(p);" in RETRY_IMPL
    assert "pbuf_free(e.p);" in RETRY_IMPL
    assert "tcpip_try_callback(wg12_flush_cb" in RETRY_IMPL
    assert "esp_timer_start_periodic" in RETRY_IMPL
    assert "__atomic_load" not in RETRY_IMPL
    assert "vTaskDelay(" not in RETRY_IMPL
    assert "heap_caps_malloc(" not in RETRY_IMPL
    assert "malloc(" not in RETRY_IMPL

    # Compile/run the EXACT injected C queue code with deterministic fake
    # timer, tcpip scheduler, pbuf reference counts and Wi-Fi return codes.
    prefix = r"""
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
typedef int err_t;
typedef int esp_err_t;
#define ESP_OK 0
#define ERR_OK 0
#define ERR_MEM (-1)
#define ESP_ERR_INVALID_STATE 259
#define IPADDR_TYPE_V4 0
typedef struct { uint32_t addr; } ip4_addr_t;
typedef struct { int type; ip4_addr_t ip4; } ip_addr_t;
#define IP_SET_TYPE_VAL(dst, tp) ((dst).type=(tp))
#define ip_2_ip4(p) (&(p)->ip4)
static void ip4_addr_set_u32(ip4_addr_t *a, uint32_t value) { a->addr = value; }
typedef struct pbuf { int ref, freed, id; } pbuf_t;
static void pbuf_ref(struct pbuf *p) { assert(p->ref > 0); ++p->ref; }
static void pbuf_free(struct pbuf *p) { assert(p->ref > 0); if (--p->ref == 0) ++p->freed; }
struct udp_pcb { int unused; };
static struct udp_pcb mock_pcb;
static struct udp_pcb *s_wg_output_pcb = &mock_pcb;
static int replies[64], sent_ids[64], sent_n, reply_n;
static err_t udp_sendto(struct udp_pcb *pcb, struct pbuf *p,
                        const ip_addr_t *dst, uint16_t port) {
    assert(pcb && dst && port);
    assert(p->ref > 0 && sent_n < 64);
    sent_ids[sent_n++] = p->id;
    return replies[reply_n++];
}
typedef int portMUX_TYPE;
#define portMUX_INITIALIZER_UNLOCKED 0
#define portENTER_CRITICAL(p) ((void)(p))
#define portEXIT_CRITICAL(p) ((void)(p))
typedef struct fake_timer {
    void (*cb)(void *);
    bool running;
} *esp_timer_handle_t;
static struct fake_timer timer_storage;
typedef struct {
    void (*callback)(void *);
    const char *name;
} esp_timer_create_args_t;
static int64_t mock_us;
static int64_t esp_timer_get_time(void) { return mock_us; }
static esp_err_t esp_timer_create(const esp_timer_create_args_t *a,
                                   esp_timer_handle_t *h) {
    assert(a && a->callback);
    timer_storage.cb = a->callback; *h = &timer_storage; return ESP_OK;
}
static esp_err_t esp_timer_start_periodic(esp_timer_handle_t h, uint64_t us) {
    assert(us > 0);
    if (h->running) return ESP_ERR_INVALID_STATE;
    h->running = true; return ESP_OK;
}
static esp_err_t esp_timer_stop(esp_timer_handle_t h) {
    h->running = false; return ESP_OK;
}
static void (*posted_cb)(void *);
static void *posted_arg;
static bool fail_post, fail_wait;
static err_t tcpip_try_callback(void (*cb)(void *), void *arg) {
    if (fail_post) return ERR_MEM;
    assert(!posted_cb);
    posted_cb = cb; posted_arg = arg; return ERR_OK;
}
static void dispatch(void) {
    if (!posted_cb) return;
    void (*cb)(void *) = posted_cb;
    void *arg = posted_arg;
    posted_cb = NULL;
    cb(arg);
}
static err_t tcpip_callback_wait(void (*cb)(void *), void *arg) {
    if (fail_wait) return ERR_MEM;
    dispatch(); cb(arg); return ERR_OK;
}
enum { WG12_ENQ, WG12_DONE, WG12_NOMEM, WG12_DROP, WG12_FULL,
       WG12_STOP, WG12_POSTFAIL, WG12_BACKLOG, WG12_COUNTERS };
static unsigned metrics[WG12_COUNTERS];
static void wg12_diag_add(unsigned event) {
    assert(event < WG12_COUNTERS); ++metrics[event];
}
#define ESP_LOGW(tag, fmt, ...) ((void)0)
"""
    suffix = r"""
static void fire(void) {
    assert(timer_storage.running && timer_storage.cb);
    mock_us += 3000;
    timer_storage.cb(NULL);
    dispatch();
}
int main(void) {
    wg12_start();
    /* Deferred packets stay alive past the caller's pbuf_free. */
    struct pbuf a = {.ref=1, .id=1}, b = {.ref=1, .id=2};
    assert(wg12_enqueue(&a, 0x01020304, 51820, false));
    pbuf_free(&a);
    assert(a.ref == 1 && a.freed == 0);
    assert(wg12_backlogged());
    assert(wg12_enqueue(&b, 0x01020304, 51820, true));
    pbuf_free(&b);
    assert(b.ref == 1);
    replies[0] = ERR_OK; replies[1] = ERR_OK;
    fire(); fire();
    assert(a.freed == 1 && b.freed == 1);
    assert(sent_n == 2 && sent_ids[0] == 1 && sent_ids[1] == 2);
    assert(!wg12_backlogged());
    /* One Wi-Fi NOMEM, then success: exactly one queue ref released. */
    struct pbuf c = {.ref=1, .id=3};
    assert(wg12_enqueue(&c, 0x01020304, 51820, false));
    pbuf_free(&c);
    replies[2] = ERR_MEM; replies[3] = ERR_OK;
    fire();
    assert(c.ref == 1 && c.freed == 0);
    fire();
    assert(c.ref == 0 && c.freed == 1 && metrics[WG12_NOMEM] == 1);
    /* Expiration never submits a stale packet. */
    struct pbuf d = {.ref=1, .id=4};
    assert(wg12_enqueue(&d, 0x01020304, 51820, false));
    pbuf_free(&d);
    mock_us += 60000;
    fire();
    assert(d.ref == 0 && d.freed == 1 && sent_n == 4);
    /* Mailbox failure leaves one ref; next periodic tick recovers. */
    struct pbuf f = {.ref=1, .id=5};
    assert(wg12_enqueue(&f, 0x01020304, 51820, false));
    pbuf_free(&f);
    fail_post = true; fire();
    assert(f.ref == 1 && metrics[WG12_POSTFAIL] == 1);
    fail_post = false;
    timer_storage.cb(NULL);
    assert(posted_cb && wg12_posted);
    timer_storage.cb(NULL); /* at most one pending callback */
    dispatch();
    assert(f.freed == 1);
    /* Callback already posted when shutdown begins must not transmit. */
    struct pbuf g = {.ref=1, .id=6};
    assert(wg12_enqueue(&g, 0x01020304, 51820, false));
    pbuf_free(&g);
    timer_storage.cb(NULL);
    int before_stop = sent_n;
    wg12_stop();
    assert(g.freed == 1 && sent_n == before_stop && !posted_cb);
    wg12_start();
    /* Both deferred attempts fail: bounded retries, exactly one release. */
    struct pbuf h = {.ref=1, .id=7};
    assert(wg12_enqueue(&h, 0x01020304, 51820, false));
    pbuf_free(&h);
    replies[reply_n] = ERR_MEM; replies[reply_n+1] = ERR_MEM;
    fire(); fire();
    assert(h.freed == 1 && !wg12_backlogged());
    /* Stop fallback drains queued refs even if barrier allocation fails.
     * A late callback sees disabled state and cannot send or double-free. */
    struct pbuf i = {.ref=1, .id=8};
    assert(wg12_enqueue(&i, 0x01020304, 51820, false));
    pbuf_free(&i); timer_storage.cb(NULL);
    before_stop = sent_n; fail_wait = true;
    wg12_stop(); dispatch(); fail_wait = false;
    assert(i.freed == 1 && sent_n == before_stop);
    wg12_start();
    /* Capacity is exactly eight; failure doesn't acquire a reference. */
    struct pbuf q[9] = {0};
    for (int i = 0; i < 9; i++) { q[i].id=10+i; q[i].ref=1; }
    for (int i = 0; i < 8; i++) {
        assert(wg12_enqueue(&q[i], 0x01020304, 51820, true));
        pbuf_free(&q[i]);
        assert(q[i].ref == 1);
    }
    assert(!wg12_enqueue(&q[8], 0x01020304, 51820, true));
    assert(q[8].ref == 1);
    wg12_stop();
    for (int i = 0; i < 8; i++) assert(q[i].freed == 1);
    assert(!timer_storage.running && !wg12_backlogged());
    assert(metrics[WG12_STOP] == 10);
    puts("PASS: actual wgopt12 queue, refcounts, FIFO, retry, expiry, overflow, shutdown");
    return 0;
}
"""
    f = output / "wgopt12_mock.c"
    exe = output / "wgopt12_mock"
    f.write_text(prefix + RETRY_IMPL + suffix)
    subprocess.run(shlex.split(os.environ.get("CC", "gcc")) + ["-std=c11", "-Wall", "-Wextra", "-UNDEBUG", "-o", str(exe), str(f)],
                   check=True)
    subprocess.run([str(exe)], check=True)
print("PASS: wgopt12 generated source contracts and deterministic host C replay")
