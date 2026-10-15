"""Passive WG-consumer diagnostics. Original predicates/calls retain their order."""
import shutil
from pathlib import Path
from derp_header_overlay import once

REPORT = r'''
/* Live counters are task-owned; only complete 10s snapshots cross cores. */
static wg13_stats_t wg13_published;
static portMUX_TYPE wg13_mux = portMUX_INITIALIZER_UNLOCKED;
void wg13_report(void) {
    wg13_stats_t v;
    static int64_t last_end;
    portENTER_CRITICAL(&wg13_mux);
    v = wg13_published;
    portEXIT_CRITICAL(&wg13_mux);
    if (!v.end_us || v.end_us == last_end) return;
    last_end = v.end_us;
    const unsigned long long end = (unsigned long long)v.end_us;
    ESP_LOGW("WG13", "end_us=%llu window_us=%llu hz=%u active_ticks=%u idle_ticks=%u invalid_wait=%llu",
        end, (unsigned long long)(v.end_us-v.start_us), (unsigned)configTICK_RATE_HZ,
        (unsigned)pdMS_TO_TICKS(2), (unsigned)pdMS_TO_TICKS(10),
        (unsigned long long)v.invalid_wait);
    for (unsigned d=0; d<2; d++)
        ESP_LOGW("WG13", "end_us=%llu drain=%u count=%llu time=%llu empty=%llu", end, d+1,
            (unsigned long long)v.exits[d][0], (unsigned long long)v.exits[d][1],
            (unsigned long long)v.exits[d][2]);
    static const char *const names[] = {"work", "cycle", "control_pre", "control_mid", "peers", "active_elapsed", "idle_elapsed"};
    for (unsigned t=0; t<WG13_TIMERS; t++)
        ESP_LOGW("WG13", "end_us=%llu timer=%s n=%llu avg_us=%llu max_us=%llu", end, names[t],
            (unsigned long long)v.timer[t].n,
            (unsigned long long)(v.timer[t].n ? v.timer[t].sum/v.timer[t].n : 0),
            (unsigned long long)v.timer[t].max);
    ESP_LOGW("WG13", "end_us=%llu wait_us_lt_1k_4k_10k_20k_40k_80k_ge80k=%llu,%llu,%llu,%llu,%llu,%llu,%llu", end,
        (unsigned long long)v.wait[0], (unsigned long long)v.wait[1], (unsigned long long)v.wait[2],
        (unsigned long long)v.wait[3], (unsigned long long)v.wait[4], (unsigned long long)v.wait[5],
        (unsigned long long)v.wait[6]);
}
'''

def apply(component):
    root = Path(__file__).resolve().parents[1]
    shutil.copyfile(root/'diagnostics/wg13_stats.h', component/'components/wireguard_lwip/src/wg13_stats.h')
    f = component/'src/ml_wg_mgr.c'
    s = f.read_text()
    s = once(s, '#include "wg_diag.h"', '#include "wg_diag.h"\n#include "wg13_stats.h"')
    s = once(s, 'static struct udp_pcb *s_wg_output_pcb = NULL;', REPORT+'\nstatic struct udp_pcb *s_wg_output_pcb = NULL;')
    s = once(s, '    wg_diag_start();', '    wg13_stats_t wg13_live = {0};\n    wg_diag_start();')
    s = once(s, '        wg_diag_loop_gap(d_loop_start);', '        if (!wg13_live.start_us) wg13_live.start_us = d_loop_start;\n        wg_diag_loop_gap(d_loop_start);')
    s = once(s, '        process_peer_updates(ml);', '''        int64_t wg13_peer_start = esp_timer_get_time();
        process_peer_updates(ml);
        wg13_time(&wg13_live, WG13_PEERS, wg13_peer_start, esp_timer_get_time());''')
    old = '''        for (int n = 0; n < WG_MGR_WG_BURST && WG_MGR_BUDGET_LEFT(WG_MGR_WG_BUDGET_MS) &&
                        xQueueReceive(ml->wg_rx_queue, &wg_pkt, 0) == pdTRUE; n++) {'''
    assert s.count(old) == 2
    # Capture the result of the SAME time predicate, never call it after exit.
    new = '''        int wg13_n_D = 0;
        bool wg13_left_D = true;
        for (; wg13_n_D < WG_MGR_WG_BURST && (wg13_left_D = WG_MGR_BUDGET_LEFT(WG_MGR_WG_BUDGET_MS)) &&
                        xQueueReceive(ml->wg_rx_queue, &wg_pkt, 0) == pdTRUE; wg13_n_D++) {'''
    for d in range(2):
        pos = s.index(old)
        s = s[:pos]+s[pos:].replace(old, new.replace('_D', '_'+str(d)), 1)
        end = s.index('\n        }', pos)+len('\n        }')
        s = s[:end]+f'\n        wg13_exit(&wg13_live, {d}, wg13_n_{d}, WG_MGR_WG_BURST, wg13_left_{d});'+s[end:]
    anchor = '            wg_diag_drain(d_start);'
    assert s.count(anchor) == 2
    s = s.replace(anchor, '            wg13_wait(&wg13_live, wg_pkt.diag_enqueued_us, d_start);\n'+anchor)
    s = once(s, '        /* Process WireGuard packets */', '''        wg13_time(&wg13_live, WG13_CONTROL_PRE, d_loop_start, esp_timer_get_time());
        /* Process WireGuard packets */''')
    s = once(s, '        /* Run WireGuard periodic processing', '        int64_t wg13_mid_start = esp_timer_get_time();\n        /* Run WireGuard periodic processing')
    s = once(s, '        /* Re-drain WG RX', '        wg13_time(&wg13_live, WG13_CONTROL_MID, wg13_mid_start, esp_timer_get_time());\n        /* Re-drain WG RX')
    delay = '        vTaskDelay(pdMS_TO_TICKS(wg_rx_active ? 2 : 10));'
    s = once(s, delay, '''        int64_t wg13_delay_start = esp_timer_get_time();
'''+delay+'''
        int64_t wg13_end = esp_timer_get_time();
        wg13_time(&wg13_live, WG13_WORK, d_loop_start, wg13_delay_start);
        wg13_time(&wg13_live, wg_rx_active ? WG13_ACTIVE : WG13_IDLE, wg13_delay_start, wg13_end);
        wg13_time(&wg13_live, WG13_CYCLE, d_loop_start, wg13_end);
        if (wg13_end - wg13_live.start_us >= 10000000LL) {
            wg13_live.end_us = wg13_end;
            portENTER_CRITICAL(&wg13_mux);
            wg13_published = wg13_live;
            portEXIT_CRITICAL(&wg13_mux);
            wg13_live = (wg13_stats_t){.start_us = wg13_end};
        }''')
    # Correct inherited claims without modifying scheduling.
    s = s.replace('2ms active / 10ms idle: always yield to lower-priority tasks.',
                  '2/10ms requested: at 100Hz active yields with 0 ticks, idle blocks 1 tick.')
    s = s.replace('empty at this exact instant. Never spin while a peer floods us.',
                  'empty at this exact instant. Active yield does not guarantee lower-priority fairness.')
    s = s.replace('This sleep is what hands the core to lower-priority tasks; the\n         * budgets above guarantee it is reached every iteration (#46).',
                  'Idle blocks; active may only yield. The two drain budgets\n         * do not bound peer/control work or guarantee lower-priority fairness.')
    f.write_text(s)
    f = component/'components/wireguard_lwip/src/wg_diag.c'
    s = once(f.read_text(), '        wg12_report();', '        wg12_report();\n        wg13_report();')
    f.write_text('extern void wg13_report(void);\n'+s)
