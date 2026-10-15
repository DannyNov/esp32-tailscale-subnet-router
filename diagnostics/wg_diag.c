#include "wg_diag.h"
#include "esp_log.h"
#include "esp_heap_caps.h"
#include "freertos/task.h"
#include "freertos/idf_additions.h"
#include <string.h>
#include <stdio.h>

/* All storage is bounded; no heap allocation or logging in packet hooks.
 * One instance per boot. Source labels are first-seen opaque slots, never
 * hashes or prefixes of public keys. No peer table access in producer tasks. */
#define SOURCES 16
#define ALLOCS 64
static uint32_t counts[D_PATHS][D_METRICS], allocs[ALLOCS], hwm[3];
static uint32_t depths[3], wg_stack;
static struct { uint32_t n, sum, max, slow; } times[D_TIMERS];
static uint32_t peers[32][2];
static uint32_t peer_tx[32][2], peer_tx_wire_bytes[32], wake_counts[2];
static struct { uint8_t key[32]; uint32_t ip, rx, bytes, enq, drop;
                uint16_t port; uint8_t path, used; } sources[SOURCES];
static uint32_t source_overflow;
/* wgopt4: no per-packet UART, two compact warnings per 10-second window.
 * Atomic writes protect concurrent WG TX callbacks on the tcpip thread.
 * A 10s qpeak is reset atomically each period, unlike boot-lifetime hwm. */
static uint32_t wg4_tx[2][3]; /* success, error, successful bytes */
static uint32_t wg4_qpeak[3];
/* wgopt7: one-time queue geometry, atomic direct RX allocation buckets. */
static uint32_t wg7_queue_cap, wg7_queue_item_size, wg7_rx_alloc[3];
void wg_diag_queue_config(unsigned cap, unsigned item_size) {
    __atomic_store_n(&wg7_queue_cap, cap, __ATOMIC_RELAXED);
    __atomic_store_n(&wg7_queue_item_size, item_size, __ATOMIC_RELAXED);
}
void wg_diag_rx_alloc(unsigned stage) {
    if (stage < 3) __atomic_fetch_add(&wg7_rx_alloc[stage], 1, __ATOMIC_RELAXED);
}
static portMUX_TYPE source_lock = portMUX_INITIALIZER_UNLOCKED;
static const char *const names[D_METRICS] = {
    "rx", "bytes", "enq", "drop", "deq", "tx", "tx_err", "tx_evict",
    "read_err", "decrypt_ok", "decrypt_err", "forward_ok", "forward_err",
    "replay", "policy_drop", "tx_enq", "tx_drop", "init", "response", "cookie", "data", "other" };
static const char *const timers[D_TIMERS] = {"process", "periodic", "probes", "loop", "rx_wait", "drain_gap", "loop_gap", "tx_lock", "tx_crypto", "tx_send",
    "tx_pbuf", "tx_copy", "rx_pbuf", "rx_copy", "rx_dec_pbuf",
    "rx_decrypt", "rx_lwip", "rx_handshake", "rx_data"};
/* Raw lwIP errors -16..0 plus overflow; bounded storage, no packet logs. */
static uint32_t txstage[4][18], burst_events, burst_max, burst_run;
static int64_t burst_last, drain_last, loop_last;
static uint32_t load(uint32_t *p) { return __atomic_load_n(p, __ATOMIC_RELAXED); }
static void add(uint32_t *p, uint32_t v) { __atomic_fetch_add(p, v, __ATOMIC_RELAXED); }
static void maximum(uint32_t *p, uint32_t v) {
    uint32_t old = load(p);
    while (v > old && !__atomic_compare_exchange_n(p, &old, v, 0,
            __ATOMIC_RELAXED, __ATOMIC_RELAXED)) {}
}
void wg_diag_add(unsigned p, unsigned m, uint32_t v) {
    if (p < D_PATHS && m < D_METRICS) add(&counts[p][m], v);
}
void wg_diag_wg4_tx(unsigned path, int result, uint32_t bytes) {
    if (path >= 2) return;
    add(&wg4_tx[path][result == 0 ? 0 : 1], 1);
    if (result == 0) add(&wg4_tx[path][2], bytes);
}
void wg_diag_tx(unsigned stage, int err) {
    if (stage < 4) add(&txstage[stage][err <= 0 && err >= -16 ? -err : 17], 1);
}
/* Direct producer is single-owner; runs split at acceptance or a 10ms gap.
 * Max includes an unfinished run, so continuing overload remains visible. */
void wg_diag_burst(int accepted, int64_t now) {
    if (accepted) { burst_run = 0; return; }
    if (!burst_run || now - burst_last > 10000) { add(&burst_events, 1); burst_run = 0; }
    burst_last = now;
    maximum(&burst_max, ++burst_run);
}
void wg_diag_drain(int64_t now) {
    if (drain_last) wg_diag_time(D_DRAIN_GAP, (uint32_t)(now - drain_last));
    drain_last = now;
}
void wg_diag_loop_gap(int64_t now) {
    if (loop_last) wg_diag_time(D_LOOP_GAP, (uint32_t)(now - loop_last));
    loop_last = now;
}
void wg_diag_type(unsigned path, const uint8_t *data, size_t len) {
    unsigned metric = D_OTHER;
    if (len >= 4 && data[1] == 0 && data[2] == 0 && data[3] == 0 &&
        data[0] >= 1 && data[0] <= 4) metric = D_INIT + data[0] - 1;
    wg_diag_add(path, metric, 1);
}
void wg_diag_alloc_fail(unsigned site) { if (site < ALLOCS) add(&allocs[site], 1); }
void wg_diag_time(unsigned t, uint32_t us) {
    if (t >= D_TIMERS) return;
    add(&times[t].n, 1); add(&times[t].sum, us); maximum(&times[t].max, us);
    if (us > 30000) add(&times[t].slow, 1);
}
void wg_diag_sample_queue(unsigned q, QueueHandle_t queue) {
    if (q < 3 && queue) {
        uint32_t depth = uxQueueMessagesWaiting(queue);
        maximum(&hwm[q], depth);
        maximum(&wg4_qpeak[q], depth);
        __atomic_store_n(&depths[q], depth, __ATOMIC_RELAXED);
    }
}
void wg_diag_source(unsigned path, const uint8_t key[32], uint32_t ip,
                    uint16_t port, size_t bytes, int accepted) {
    portENTER_CRITICAL(&source_lock);
    unsigned i;
    for (i = 0; i < SOURCES; i++) {
        if (!sources[i].used) {
            sources[i].used = 1; sources[i].path = path;
            sources[i].ip = ip; sources[i].port = port;
            if (key) memcpy(sources[i].key, key, 32);
            break;
        }
        if (sources[i].path == path && (path == D_DERP ?
            (key && memcmp(key, sources[i].key, 32) == 0) :
            (ip == sources[i].ip && port == sources[i].port))) break;
    }
    if (i < SOURCES) {
        sources[i].rx++; sources[i].bytes += bytes;
        if (accepted) sources[i].enq++; else sources[i].drop++;
    } else source_overflow++;
    portEXIT_CRITICAL(&source_lock);
}
void wg_diag_peer(unsigned peer, int ok) {
    if (peer < 32) add(&peers[peer][ok ? 0 : 1], 1);
}
void wg_diag_peer_tx(unsigned peer, int failed) {
    if (peer < 32) add(&peer_tx[peer][failed ? 1 : 0], 1);
}
void wg_diag_peer_tx_bytes(unsigned peer, uint32_t bytes) {
    if (peer < 32) add(&peer_tx_wire_bytes[peer], bytes);
}
void wg_diag_wake(int active) { add(&wake_counts[active ? 1 : 0], 1); }
/* User-facing, bounded diagnostic output. Existing WG_DIAG INFO lines are
 * compiled but hidden by CONFIG_LOG_DEFAULT_LEVEL_WARN=y. Keep this summary
 * at WARN so the existing /log live 16KiB ring exposes it remotely.
 * No peer keys/endpoints or per-packet printf. Rows span the same 10s bucket. */
static void wg4_report(void) {
    static uint32_t old_tx[2][3], old_n[D_TIMERS], old_sum[D_TIMERS];
    static uint32_t old_drop[D_PATHS], old_rx[D_PATHS];
    uint32_t delta_tx[2][3], delta_n[D_TIMERS], delta_sum[D_TIMERS];
    uint32_t delta_drop[D_PATHS], delta_rx[D_PATHS];
    for (unsigned p = 0; p < 2; ++p)
        for (unsigned k = 0; k < 3; ++k) {
            uint32_t v = load(&wg4_tx[p][k]);
            delta_tx[p][k] = v - old_tx[p][k];
            old_tx[p][k] = v;
        }
    for (unsigned i = 0; i < D_TIMERS; ++i) {
        uint32_t n = load(&times[i].n), sum = load(&times[i].sum);
        delta_n[i] = n - old_n[i];
        delta_sum[i] = sum - old_sum[i];
        old_n[i] = n; old_sum[i] = sum;
    }
    for (unsigned p = 0; p < D_PATHS; ++p) {
        uint32_t n = load(&counts[p][D_RX]), d = load(&counts[p][D_DROP]);
        delta_rx[p] = n - old_rx[p];
        delta_drop[p] = d - old_drop[p];
        old_rx[p] = n; old_drop[p] = d;
    }
    uint32_t peak = __atomic_exchange_n(&wg4_qpeak[0], 0, __ATOMIC_RELAXED);
    const unsigned long long t_ms = (unsigned long long)(esp_timer_get_time() / 1000);
    /* A path count is *accepted by the lower output callback*, not confirmed
     * delivery by the remote Tailscale peer. Throughput must be measured. */
    ESP_LOGW("WG4_TX",
        "t_ms=%llu direct_ok=%lu direct_err=%lu direct_bytes=%lu derp_ok=%lu derp_err=%lu derp_bytes=%lu crypto_n=%lu crypto_avg_us=%lu send_avg_us=%lu lock_avg_us=%lu",
        t_ms,
        (unsigned long)delta_tx[0][0], (unsigned long)delta_tx[0][1], (unsigned long)delta_tx[0][2],
        (unsigned long)delta_tx[1][0], (unsigned long)delta_tx[1][1], (unsigned long)delta_tx[1][2],
        (unsigned long)delta_n[D_TX_CRYPTO],
        (unsigned long)(delta_n[D_TX_CRYPTO] ? delta_sum[D_TX_CRYPTO] / delta_n[D_TX_CRYPTO] : 0),
        (unsigned long)(delta_n[D_TX_SEND] ? delta_sum[D_TX_SEND] / delta_n[D_TX_SEND] : 0),
        (unsigned long)(delta_n[D_TX_LOCK] ? delta_sum[D_TX_LOCK] / delta_n[D_TX_LOCK] : 0));
    ESP_LOGW("WG4_RX",
        "t_ms=%llu direct_rx=%lu derp_rx=%lu direct_drop=%lu derp_drop=%lu wgq_depth=%lu wgq_peak=%lu wgq_cap=128 rx_wait_avg_us=%lu periodic_avg_us=%lu probes_avg_us=%lu internal_free=%u",
        t_ms,
        (unsigned long)delta_rx[D_DIRECT], (unsigned long)delta_rx[D_DERP],
        (unsigned long)delta_drop[D_DIRECT], (unsigned long)delta_drop[D_DERP],
        (unsigned long)load(&depths[0]), (unsigned long)peak,
        (unsigned long)(delta_n[D_WAIT] ? delta_sum[D_WAIT] / delta_n[D_WAIT] : 0),
        (unsigned long)(delta_n[D_PERIODIC] ? delta_sum[D_PERIODIC] / delta_n[D_PERIODIC] : 0),
        (unsigned long)(delta_n[D_PROBES] ? delta_sum[D_PROBES] / delta_n[D_PROBES] : 0),
        (unsigned)heap_caps_get_free_size(MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT));
}

/* 10-second passive internal/PSRAM heap and direct UDP allocation report.
 * Allocation counters cover shared direct UDP ingress (WG and DISCO).
 * malloc fallback does not guarantee internal RAM placement. */
static void wg7_report(void) {
    static uint32_t previous[3];
    uint32_t delta[3];
    for (unsigned i = 0; i < 3; ++i) {
        uint32_t now = __atomic_load_n(&wg7_rx_alloc[i], __ATOMIC_RELAXED);
        delta[i] = now - previous[i];
        previous[i] = now;
    }
    const uint32_t internal = MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT;
    const uint32_t psram = MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT;
    ESP_LOGW("WG7_MEM",
        "wgq_cap=%lu wgq_item_bytes=%lu internal_free=%u internal_min=%u internal_largest=%u psram_free=%u psram_min=%u psram_largest=%u udp_psram_delta=%lu udp_fallback_delta=%lu udp_alloc_fail_delta=%lu",
        (unsigned long)__atomic_load_n(&wg7_queue_cap, __ATOMIC_RELAXED),
        (unsigned long)__atomic_load_n(&wg7_queue_item_size, __ATOMIC_RELAXED),
        (unsigned)heap_caps_get_free_size(internal),
        (unsigned)heap_caps_get_minimum_free_size(internal),
        (unsigned)heap_caps_get_largest_free_block(internal),
        (unsigned)heap_caps_get_free_size(psram),
        (unsigned)heap_caps_get_minimum_free_size(psram),
        (unsigned)heap_caps_get_largest_free_block(psram),
        (unsigned long)delta[0], (unsigned long)delta[1],
        (unsigned long)delta[2]);
}
static void reporter(void *arg) {
    (void)arg;
    for (;;) {
        vTaskDelay(pdMS_TO_TICKS(10000));
        wg_diag_report();
        wg4_report();
        wg5_report();
        wg7_report();
    }
}
void wg_diag_start(void) {
    static uint32_t started;
    uint32_t zero = 0;
    if (__atomic_compare_exchange_n(&started, &zero, 1, 0, __ATOMIC_RELAXED, __ATOMIC_RELAXED)) {
        if (xTaskCreateWithCaps(reporter, "wg_diag", 6144, NULL, 1, NULL, MALLOC_CAP_SPIRAM) != pdPASS) {
            wg_diag_alloc_fail(63);
            ESP_LOGW("WG_DIAG", "Reporter creation failed; counters remain active");
        }
    }
    wg_diag_stack_sample();
}
void wg_diag_stack_sample(void) {
    __atomic_store_n(&wg_stack, uxTaskGetStackHighWaterMark(NULL), __ATOMIC_RELAXED);
}
void wg_diag_report(void) {
    static uint32_t ptprev[32][2], ptbytes_prev[32], wake_prev[2];
    for (unsigned i = 0; i < 32; i++) {
        uint32_t ok = load(&peer_tx[i][0]), err = load(&peer_tx[i][1]);
        uint32_t bytes = load(&peer_tx_wire_bytes[i]);
        if (ok != ptprev[i][0] || err != ptprev[i][1] || bytes != ptbytes_prev[i]) ESP_LOGI("WG_DIAG", "wgi=%u direction=tx ok_delta=%lu fail_delta=%lu wire_bytes_delta=%lu", i, (unsigned long)(ok - ptprev[i][0]), (unsigned long)(err - ptprev[i][1]), (unsigned long)(bytes - ptbytes_prev[i]));
        ptbytes_prev[i] = bytes;
        ptprev[i][0] = ok; ptprev[i][1] = err;
    }
    uint32_t idle = load(&wake_counts[0]), busy = load(&wake_counts[1]);
    ESP_LOGI("WG_DIAG", "rx_schedule sleep_idle10_delta=%lu sleep_active2_delta=%lu",
        (unsigned long)(idle - wake_prev[0]), (unsigned long)(busy - wake_prev[1]));
    wake_prev[0] = idle; wake_prev[1] = busy;
    static uint32_t txprev[4][18], burst_prev;
    static const char *const stages[] = {"internal_wrapper", "psram_payload", "custom_pbuf", "udp_sendto"};
    for (unsigned st = 0; st < 4; st++) for (unsigned e = 0; e < 18; e++) {
        uint32_t n = load(&txstage[st][e]);
        if (n != txprev[st][e]) ESP_LOGI("WG_DIAG", "tx_stage=%s raw_err=%d delta=%lu", stages[st], e == 17 ? 127 : -(int)e, (unsigned long)(n - txprev[st][e]));
        txprev[st][e] = n;
    }
    uint32_t bursts = load(&burst_events);
    ESP_LOGI("WG_DIAG", "direct_drop_runs_delta=%lu run_max_boot=%lu gap_split_us=10000", (unsigned long)(bursts - burst_prev), (unsigned long)load(&burst_max));
    burst_prev = bursts;
    static uint32_t previous[D_PATHS][D_METRICS], aprev[ALLOCS];
    static uint32_t pn[D_TIMERS], ps[D_TIMERS], pslow[D_TIMERS], pp[32][2];
    static uint32_t sr[SOURCES], se[SOURCES], sd[SOURCES], sb[SOURCES];
    static int64_t last;
    int64_t now = esp_timer_get_time();
    uint32_t elapsed = last ? (uint32_t)((now - last) / 1000) : (uint32_t)(now / 1000);
    last = now;
    ESP_LOGI("WG_DIAG", "window_ms=%lu uptime_ms=%llu internal_free=%u internal_min=%u largest=%u stack_wg_sample=%lu stack_reporter=%u",
        (unsigned long)elapsed, (unsigned long long)(now / 1000),
        (unsigned)heap_caps_get_free_size(MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT),
        (unsigned)heap_caps_get_minimum_free_size(MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT),
        (unsigned)heap_caps_get_largest_free_block(MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT),
        (unsigned long)load(&wg_stack), (unsigned)uxTaskGetStackHighWaterMark(NULL));
    for (unsigned p = 0; p < D_PATHS; p++) {
        /* Fixed stack buffer; one line per path, all metrics have deltas. */
        char line[1024]; size_t used = 0;
        for (unsigned m = 0; m < D_METRICS; m++) {
            uint32_t v = load(&counts[p][m]);
            int n = snprintf(line + used, sizeof(line) - used, " %s=%lu(+%lu)",
                names[m], (unsigned long)v, (unsigned long)(v - previous[p][m]));
            previous[p][m] = v;
            if (n < 0 || (size_t)n >= sizeof(line) - used) break;
            used += n;
        }
        ESP_LOGI("WG_DIAG", "path=%s%s", p ? "derp" : "direct", line);
    }
    for (unsigned q = 0; q < 3; q++) {
        ESP_LOGI("WG_DIAG", "q=%u depth=%u sampled_hwm=%lu", q,
            (unsigned)load(&depths[q]), (unsigned long)load(&hwm[q]));
    }
    for (unsigned t = 0; t < D_TIMERS; t++) {
        uint32_t n = load(&times[t].n), s = load(&times[t].sum), slow = load(&times[t].slow);
        ESP_LOGI("WG_DIAG", "timer=%s n_delta=%lu us_sum_delta=%lu us_max_boot=%lu slow30_delta=%lu",
            timers[t], (unsigned long)(n - pn[t]), (unsigned long)(s - ps[t]),
            (unsigned long)load(&times[t].max), (unsigned long)(slow - pslow[t]));
        pn[t] = n; ps[t] = s; pslow[t] = slow;
    }
    for (unsigned i = 0; i < ALLOCS; i++) {
        uint32_t v = load(&allocs[i]);
        if (v != aprev[i]) ESP_LOGI("WG_DIAG", "alloc_site=%u failures=%lu delta=%lu", i,
            (unsigned long)v, (unsigned long)(v - aprev[i]));
        aprev[i] = v;
    }
    for (unsigned i = 0; i < SOURCES; i++) {
        uint32_t r, e, d, b; unsigned path;
        portENTER_CRITICAL(&source_lock);
        r = sources[i].rx; e = sources[i].enq; d = sources[i].drop;
        b = sources[i].bytes; path = sources[i].path;
        portEXIT_CRITICAL(&source_lock);
        if (r != sr[i]) ESP_LOGI("WG_DIAG", "source=S%u path=%s rx_delta=%lu bytes_delta=%lu enq_delta=%lu drop_delta=%lu",
            i, path ? "derp" : "direct", (unsigned long)(r - sr[i]),
            (unsigned long)(b - sb[i]), (unsigned long)(e - se[i]), (unsigned long)(d - sd[i]));
        sr[i] = r; se[i] = e; sd[i] = d; sb[i] = b;
    }
    for (unsigned i = 0; i < 32; i++) {
        uint32_t ok = load(&peers[i][0]), err = load(&peers[i][1]);
        if (ok != pp[i][0] || err != pp[i][1]) ESP_LOGI("WG_DIAG", "wgi=%u decrypt_ok_delta=%lu decrypt_err_delta=%lu", i,
            (unsigned long)(ok - pp[i][0]), (unsigned long)(err - pp[i][1]));
        pp[i][0] = ok; pp[i][1] = err;
    }
    portENTER_CRITICAL(&source_lock);
    uint32_t overflow = source_overflow;
    portEXIT_CRITICAL(&source_lock);
    if (overflow) ESP_LOGI("WG_DIAG", "source_table_overflow=%lu", (unsigned long)overflow);
}
