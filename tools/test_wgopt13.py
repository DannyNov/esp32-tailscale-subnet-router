"""Compile exact diagnostic helpers/report and generated drain predicates with mocks."""
from pathlib import Path
from tempfile import TemporaryDirectory
import os, shlex, subprocess
import prepare_wg_diagnostics as prep
from wgopt13_overlay import apply, REPORT

with TemporaryDirectory(prefix='wg13-') as tmp:
    out = Path(tmp)
    prep.prepare(out)
    mgr = (out/'microlink/src/ml_wg_mgr.c').read_text()
    backend = (out/'microlink/components/wireguard_lwip/src/wireguardif.c').read_bytes()
    original_apply = prep.apply_wgopt13
    prep.apply_wgopt13 = lambda c: None
    prep.prepare(out/'baseline')
    prep.apply_wgopt13 = original_apply
    base = out/'baseline/microlink'
    assert backend == (base/'components/wireguard_lwip/src/wireguardif.c').read_bytes()
    for rel in ('src/ml_net_io.c', 'src/ml_derp.c', 'include/microlink_internal.h'):
        assert (out/'microlink'/rel).read_bytes() == (base/rel).read_bytes(), rel
    baseline = (base/'src/ml_wg_mgr.c').read_text()
    # All non-task functions (including TX retry and packet ownership) identical.
    start = baseline.index('static struct udp_pcb *s_wg_output_pcb = NULL;')
    end = baseline.index('    wg_diag_start();')
    common = baseline[start:end]
    assert common in mgr
    assert mgr.count('vTaskDelay(pdMS_TO_TICKS(wg_rx_active ? 2 : 10));') == 1
    assert mgr.count('wg13_wait(&wg13_live, wg_pkt.diag_enqueued_us, d_start);') == 2
    assert mgr.count('wg13_exit(&wg13_live,') == 2
    assert 'wg13_live.end_us = wg13_end;' in mgr
    for forbidden in ('malloc(', 'pbuf_', 'xTaskNotify', 'xQueueSend', 'free('):
        assert forbidden not in REPORT
    # Idempotence/anchor mismatch must fail closed.
    try:
        apply(out/'microlink')
    except (RuntimeError, AssertionError):
        pass
    else:
        raise AssertionError('reapplying overlay should fail')
    header = (prep.ROOT/'diagnostics/wg13_stats.h').read_text()
    prefix = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdarg.h>
#include <stdio.h>
#include <string.h>
static int locked, rows;
typedef int portMUX_TYPE;
#define portMUX_INITIALIZER_UNLOCKED 0
#define portENTER_CRITICAL(p) ((void)(p), assert(!locked), locked=1)
#define portEXIT_CRITICAL(p) ((void)(p), assert(locked), locked=0)
#ifndef HZ
#define HZ 100
#endif
#define configTICK_RATE_HZ HZ
#define pdMS_TO_TICKS(ms) ((ms)*HZ/1000)
static void logrow(const char *tag, const char *fmt, ...) {
    assert(!locked && !strcmp(tag,"WG13")); rows++;
    char line[512]; va_list ap; va_start(ap,fmt);
    int n=vsnprintf(line,sizeof(line),fmt,ap); va_end(ap);
    assert(n>0 && n<(int)sizeof(line));
}
#define ESP_LOGW(...) logrow(__VA_ARGS__)
static int64_t now_us;
static int budget_calls, queue_calls, remaining, processed;
#define WG_MGR_WG_BURST 64
#define WG_MGR_WG_BUDGET_MS 30
#define WG_MGR_BUDGET_LEFT(ms) (++budget_calls, now_us/1000 < (ms))
#define pdTRUE 1
static int xQueueReceive(int q, int *p, int wait) {
    assert(q==1 && p && wait==0); queue_calls++;
    if (!remaining) return 0; remaining--; return 1;
}
'''
    loops = ''
    for d in range(2):
        start = mgr.index(f'        int wg13_n_{d} = 0;')
        body = mgr.index('            int64_t d_start', start)
        finish = mgr.index(f'        wg13_exit(&wg13_live, {d}', body)
        exit_end = mgr.index(';', finish)+1
        predicate = mgr[start:body].replace('ml->wg_rx_queue', '1')
        loops += f'\nstatic void drain{d}(int cost) {{\nint wg_pkt; wg13_stats_t wg13_live={{0}};\n'
        loops += predicate + 'processed++; now_us += cost;\n        }\n' + mgr[finish:exit_end]
        loops += f'\nresult=wg13_live.exits[{d}][0] ? 0 : wg13_live.exits[{d}][1] ? 1 : 2;\n}}\n'
    begin = mgr.index('        int64_t wg13_delay_start = esp_timer_get_time();')
    end = mgr.index('\n    }\n    #undef WG_MGR_BUDGET_LEFT', begin)
    delay_mock = r'''
static int64_t mock_delay_elapsed;
static unsigned requested_ticks;
static int64_t esp_timer_get_time(void) { return now_us; }
static void vTaskDelay(unsigned ticks) { requested_ticks=ticks; now_us+=mock_delay_elapsed; }
static wg13_stats_t cycle(bool wg_rx_active) {
    wg13_stats_t wg13_live={.start_us=1};
    int64_t d_loop_start=now_us-50;
''' + mgr[begin:end] + '\nreturn wg13_live;\n}\n'
    suffix = r'''
int main(void) {
    wg13_stats_t s={0};
    int bounds[]={0,999,1000,3999,4000,9999,10000,19999,20000,39999,40000,79999,80000};
    for(unsigned i=0;i<sizeof(bounds)/sizeof(bounds[0]);i++) wg13_wait(&s,1,1+bounds[i]);
    for(int b=0;b<6;b++) assert(s.wait[b]==2);
    assert(s.wait[6]==1);
    wg13_wait(&s,0,100); wg13_wait(&s,100,99); assert(s.invalid_wait==2);
    wg13_time(&s,WG13_ACTIVE,100,100); wg13_time(&s,WG13_ACTIVE,100,400);
    assert(s.timer[WG13_ACTIVE].n==2 && s.timer[WG13_ACTIVE].sum==300 && s.timer[WG13_ACTIVE].max==300);
    wg13_time(&s,WG13_IDLE,500,499); assert(s.timer[WG13_IDLE].n==0);
    wg13_time(&s,WG13_IDLE,1,5000000001LL); assert(s.timer[WG13_IDLE].sum==5000000000ULL);
    assert(pdMS_TO_TICKS(2)==(HZ==100?0:2));
    assert(pdMS_TO_TICKS(10)==(HZ==100?1:10));
    now_us=100; mock_delay_elapsed=0; s=cycle(true);
    assert(requested_ticks==pdMS_TO_TICKS(2) && s.timer[WG13_ACTIVE].sum==0 && s.timer[WG13_CYCLE].sum==50);
    now_us=100; mock_delay_elapsed=12345; s=cycle(false);
    assert(requested_ticks==pdMS_TO_TICKS(10) && s.timer[WG13_IDLE].sum==12345 && s.timer[WG13_CYCLE].sum==12395);
    now_us=10000001; mock_delay_elapsed=100; s=cycle(true);
    assert(wg13_published.end_us==10000101 && wg13_published.timer[WG13_ACTIVE].sum==100);
    assert(s.start_us==10000101 && !s.timer[WG13_CYCLE].n);
    wg13_published=(wg13_stats_t){0};
    for(int d=0;d<2;d++) for(int scenario=0;scenario<5;scenario++) {
        now_us=budget_calls=queue_calls=processed=0;
        remaining=scenario==0?0:scenario==1?3:100;
        int cost=scenario==3?10000:scenario==4?40000:0;
        if(d) drain1(cost); else drain0(cost);
        if(scenario==0) assert(result==2 && processed==0 && queue_calls==1);
        if(scenario==1) assert(result==2 && processed==3 && queue_calls==4);
        if(scenario==2) assert(result==0 && processed==64 && budget_calls==64 && queue_calls==64);
        if(scenario==3) assert(result==1 && processed==3 && budget_calls==4 && queue_calls==3);
        if(scenario==4) assert(result==1 && processed==1 && budget_calls==2 && queue_calls==1);
    }
    wg13_exit(&s,0,64,64,0); assert(s.exits[0][WG13_COUNT]==1);
    wg13_report(); assert(!rows);
    s.start_us=1; s.end_us=10000001; wg13_published=s;
    wg13_report(); assert(rows==11); wg13_report(); assert(rows==11);
    s.end_us++; wg13_published=s; wg13_report(); assert(rows==22);
    puts("PASS wgopt13: exact predicates, time/count precedence, overshoot, bins, timers, snapshot reporter");
}
'''
    c = out/'mock.c'
    c.write_text(header.replace('#pragma once','')+prefix+REPORT+'\nstatic int result;\n'+loops+delay_mock+suffix)
    cc = shlex.split(os.environ.get('WG13_CC','gcc'), posix=os.name!='nt')
    cc = [arg.strip('"') for arg in cc]
    for hz in (100,1000):
        exe=out/f'mock{hz}.exe'
        subprocess.run(cc+['-std=c11','-Wall','-Wextra','-Werror','-Wno-misleading-indentation',f'-DHZ={hz}',str(c),'-o',str(exe)],check=True)
        subprocess.run([str(exe)],check=True)
print('PASS wgopt13: unchanged producers/backend/TX/ownership and fail-closed overlay')
