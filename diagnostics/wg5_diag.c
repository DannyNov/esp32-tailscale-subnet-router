/* wgopt5: passive, low-rate radio + FreeRTOS runtime sampling.
 *
 * Production data-plane and Wi-Fi configuration are NOT touched. Only the
 * existing 10-second WG diagnostic reporter calls this function. The public
 * ESP-IDF Wi-Fi API offers station RSSI/channel and power-save configuration,
 * not a reliable count of MAC retry/ACK failures. Do not label udp_sendto
 * acceptance as Wi-Fi delivery or invent a retry metric.
 */
#include "esp_wifi.h"
#include "esp_log.h"
#include "esp_heap_caps.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include <stdint.h>
#include <stdbool.h>
#include <string.h>

#define WG5_MAX_TASKS 64
enum { IDLE0, IDLE1, WIFI_TASK, TCPIP_TASK, WG_TASK, NETIO_TASK, TRACKED };
static const char *const tracked[TRACKED] = {
    "IDLE0", "IDLE1", "wifi", "tiT", "ml_wg_mgr", "ml_net_io"
};
/* One PSRAM allocation for the reporter's lifetime, no allocations in any
 * packet path. A 64-entry cap avoids unbounded stack/heap use. */
static TaskStatus_t *taskbuf;
static uint32_t old_total, old_ticks[TRACKED];
static bool old_present[TRACKED], seeded;

/* Only compare counters for tasks observed in consecutive snapshots.
 * A disappeared/recreated task cannot produce a meaningful interval rate.
 * Overflowed run-time clock: mark this window unknown, re-seed next window. */
static int pct_delta(uint32_t cur, uint32_t old, uint32_t total_delta) {
    if (cur < old || total_delta == 0) return -1;
    uint32_t delta = cur - old;
    if (delta > total_delta) return -1;
    return (int)((uint64_t)delta * 100u / total_delta);
}

void wg5_report(void) {
    int sta = 0, rssi = -127, channel = -1, phy11n = -1, ps = -1;
    wifi_ap_record_t ap;
    if (esp_wifi_sta_get_ap_info(&ap) == ESP_OK) {
        sta = 1; rssi = ap.rssi; channel = ap.primary;
        phy11n = ap.phy_11n ? 1 : 0;
    }
    wifi_ps_type_t wifi_ps;
    if (esp_wifi_get_ps(&wifi_ps) == ESP_OK) ps = (int)wifi_ps;

    int cpu[TRACKED];
    for (unsigned i = 0; i < TRACKED; ++i) cpu[i] = -1;
    unsigned tasks = uxTaskGetNumberOfTasks();
    bool sampled = false;
    if (!taskbuf) {
        taskbuf = heap_caps_malloc(sizeof(*taskbuf) * WG5_MAX_TASKS,
                                   MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
    }
    if (taskbuf && tasks > 0 && tasks <= WG5_MAX_TASKS) {
        uint32_t total = 0;
        UBaseType_t got = uxTaskGetSystemState(taskbuf, WG5_MAX_TASKS, &total);
        if (got > 0 && got <= WG5_MAX_TASKS && total > 0) {
            bool present[TRACKED] = {false};
            uint32_t now[TRACKED] = {0};
            for (UBaseType_t j = 0; j < got; ++j) {
                if (!taskbuf[j].pcTaskName) continue;
                for (unsigned k = 0; k < TRACKED; ++k) {
                    if (strcmp(taskbuf[j].pcTaskName, tracked[k]) == 0) {
                        now[k] = taskbuf[j].ulRunTimeCounter;
                        present[k] = true;
                    }
                }
            }
            /* Avoid claiming 0% when tasks are missing or when counter
             * continuity cannot be established. */
            uint32_t denom = (seeded && total > old_total)
                                ? total - old_total : 0;
            for (unsigned k = 0; k < TRACKED; ++k) {
                if (present[k] && old_present[k] && denom)
                    cpu[k] = pct_delta(now[k], old_ticks[k], denom);
                old_ticks[k] = now[k];
                old_present[k] = present[k];
            }
            old_total = total;
            seeded = true;
            sampled = true;
        }
    }
    if (!sampled) seeded = false;

    /* IDLE tasks on separate cores: a value of -1 means not measured.
     * Task percentages are shares of the run-time-statistics timebase,
     * not proof of scheduler or Wi-Fi-driver bottlenecks. */
    int busy0 = cpu[IDLE0] < 0 ? -1 : 100 - cpu[IDLE0];
    int busy1 = cpu[IDLE1] < 0 ? -1 : 100 - cpu[IDLE1];
    ESP_LOGW("WG5_SYS",
             "t_ms=%llu sta=%d rssi=%d ch=%d phy11n=%d ps=%d "
             "cpu0_busy=%d cpu1_busy=%d wifi_task=%d tcpip_task=%d "
             "wg_task=%d netio_task=%d tasks=%u prof=%d",
             (unsigned long long)(esp_timer_get_time() / 1000),
             sta, rssi, channel, phy11n, ps,
             busy0, busy1, cpu[WIFI_TASK], cpu[TCPIP_TASK],
             cpu[WG_TASK], cpu[NETIO_TASK], tasks, sampled ? 1 : 0);
}
