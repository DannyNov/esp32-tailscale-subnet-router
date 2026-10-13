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
static struct { uint8_t key[32]; uint32_t ip, rx, bytes, enq, drop;
                uint16_t port; uint8_t path, used; } sources[SOURCES];
static uint32_t source_overflow;
static portMUX_TYPE source_lock = portMUX_INITIALIZER_UNLOCKED;
static const char *const names[D_METRICS] = {
    "rx", "bytes", "enq", "drop", "deq", "tx", "tx_err", "tx_evict",
    "read_err", "decrypt_ok", "decrypt_err", "forward_ok", "forward_err",
    "replay", "policy_drop", "tx_enq", "tx_drop", "init", "response", "cookie", "data", "other" };
static const char *const timers[D_TIMERS] = {"process", "periodic", "probes", "loop"};
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
static void reporter(void *arg) {
    (void)arg;
    for (;;) {
        vTaskDelay(pdMS_TO_TICKS(10000));
        wg_diag_report();
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
