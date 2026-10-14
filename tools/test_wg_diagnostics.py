"""Overlay integrity and executable telemetry tests (host mocks, no device)."""
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from prepare_wg_diagnostics import ROOT, prepare, replace

(ROOT / 'build').mkdir(exist_ok=True)
with tempfile.TemporaryDirectory(dir=ROOT / 'build', prefix='diag-test-') as temporary:
    out = Path(temporary)
    prepare(out)
    before = {str(p.relative_to(out)): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in out.rglob('*') if p.is_file()}
    prepare(out)
    after = {str(p.relative_to(out)): hashlib.sha256(p.read_bytes()).hexdigest()
             for p in out.rglob('*') if p.is_file()}
    assert before == after, 'Overlay must be reproducible and idempotent'
    try:
        replace('missing anchor', 'expected', 'changed')
    except RuntimeError:
        pass
    else:
        raise AssertionError('Anchor drift did not abort')
    sites = json.loads((out / 'allocation-sites.json').read_text())
    assert len(sites) == 25 and len({s['site'] for s in sites}) == 25
    assert any(s['expression'].startswith('WG_OUT_ALLOC(') for s in sites)
    assert any(s['expression'].startswith('mem_malloc(') for s in sites)
    assert sum('pbuf_alloc(' in s['expression'] for s in sites) == 7
    # The only production files changed in the copy are the four instrumented
    # sources and backend CMake plus the two new telemetry files.
    upstream = ROOT / 'external/microlink/components/microlink'
    allowed = {'src/ml_net_io.c', 'src/ml_derp.c', 'src/ml_wg_mgr.c',
               'components/wireguard_lwip/src/wireguardif.c',
               'components/wireguard_lwip/CMakeLists.txt',
               'components/wireguard_lwip/src/wireguard.c',
               'components/wireguard_lwip/src/wireguard.h', 'include/microlink_internal.h'}
    changed = set()
    for f in upstream.rglob('*'):
        if f.is_file():
            rel = f.relative_to(upstream)
            if f.read_bytes() != (out / 'microlink' / rel).read_bytes():
                changed.add(rel.as_posix())
    assert changed == allowed, changed
    mgr = (out / 'microlink/src/ml_wg_mgr.c').read_text()
    task = mgr[mgr.index('void ml_wg_mgr_task('):]
    assert 'dump_wg_state_snapshot(ml);' not in task
    assert 'wg_diag_stack_sample();' in task
    assert task.count('vTaskDelay(pdMS_TO_TICKS(10));') == 1
    assert task.count('process_wg_packet(ml, &wg_pkt);') == 2
    assert 'WG_MGR_WG_BUDGET_MS     30' in task
    assert 'WG_MGR_WG_BURST         64' in task
    assert task.count('wg_diag_time(D_WAIT,') == 2
    assert all(('wg_diag_tx(%u,' % i) in mgr for i in range(4))
    wgif = (out / 'microlink/components/wireguard_lwip/src/wireguardif.c').read_text()
    assert 'wg_diag_peer_tx(wireguard_peer_index(device, peer)' in wgif
    assert 'ESP_LOGW(TAG, "[WG_OUT_FAIL]' not in wgif
    derp = (out / 'microlink/src/ml_derp.c').read_text()
    assert 'derp_poll_header(ml, header)' in derp
    assert 'return n == 0 ? -1 : n;' in derp
    print('PASS: no snapshot call in consumer; stack/queue/counter probes and yield retained; derphdr1 retained')
    print('PASS: pinned immutable submodule, reproducible overlay, fail-closed anchors, allocation coverage')
    cc = shutil.which(os.environ.get('CC', 'cc'))
    if not cc:
        if os.name == 'nt':
            print('SKIP: executable C test locally (no C compiler); mandatory in Linux CI')
        else:
            raise RuntimeError('C compiler required')
    else:
        stub = out / 'stubs'
        (stub / 'freertos').mkdir(parents=True)
        (stub / 'freertos/FreeRTOS.h').write_text('''#pragma once
#include <stdint.h>
#include <pthread.h>
typedef pthread_mutex_t portMUX_TYPE;
#define portMUX_INITIALIZER_UNLOCKED PTHREAD_MUTEX_INITIALIZER
#define portENTER_CRITICAL(p) pthread_mutex_lock(p)
#define portEXIT_CRITICAL(p) pthread_mutex_unlock(p)
#define pdMS_TO_TICKS(x) (x)
#define pdPASS 1
''')
        (stub / 'freertos/queue.h').write_text('''#pragma once
typedef void *QueueHandle_t;
static inline unsigned uxQueueMessagesWaiting(void *q) { return *(unsigned *)q; }
''')
        (stub / 'freertos/task.h').write_text('''#pragma once
static inline void vTaskDelay(unsigned n) { (void)n; }
static inline unsigned uxTaskGetStackHighWaterMark(void *p) { (void)p; return 2048; }
''')
        (stub / 'freertos/idf_additions.h').write_text('''#pragma once
static inline int xTaskCreateWithCaps(void (*fn)(void *), const char *name,
    unsigned size, void *arg, unsigned priority, void *handle, unsigned caps) {
    (void)fn; (void)name; (void)size; (void)arg; (void)priority; (void)handle; (void)caps;
    return 1;
}
''')
        (stub / 'esp_timer.h').write_text('''#pragma once
#include <stdint.h>
static inline int64_t esp_timer_get_time(void) { return 10000000; }
''')
        (stub / 'esp_log.h').write_text('''#pragma once
#include <stdio.h>
#define ESP_LOGI(tag, fmt, ...) printf("%s " fmt "\\n", tag, ##__VA_ARGS__)
#define ESP_LOGW ESP_LOGI
''')
        (stub / 'esp_heap_caps.h').write_text('''#pragma once
#define MALLOC_CAP_INTERNAL 1
#define MALLOC_CAP_8BIT 2
#define MALLOC_CAP_SPIRAM 4
static inline unsigned heap_caps_get_free_size(unsigned c) { (void)c; return 40000; }
static inline unsigned heap_caps_get_minimum_free_size(unsigned c) { (void)c; return 2800; }
static inline unsigned heap_caps_get_largest_free_block(unsigned c) { (void)c; return 20000; }
''')
        test = out / 'test.c'
        test.write_text('''#include <assert.h>
#include "wg_diag.c"
static void *worker(void *arg) {
    (void)arg;
    for (unsigned i=0; i<10000; i++) {
        wg_diag_add(D_DIRECT, D_RX, 1);
        wg_diag_time(D_PROCESS, i % 100);
        uint8_t key[32] = {1};
        wg_diag_source(D_DERP, key, 0, 0, 1200, 1);
    }
    return NULL;
}
static unsigned calls;
static void *allocation(void) { calls++; return NULL; }
int main(void) {
    pthread_t threads[4];
    for (unsigned i=0; i<4; i++) assert(!pthread_create(&threads[i], NULL, worker, NULL));
    for (unsigned i=0; i<4; i++) assert(!pthread_join(threads[i], NULL));
    assert(load(&counts[D_DIRECT][D_RX])==40000);
    assert(times[D_PROCESS].n==40000 && times[D_PROCESS].max==99);
    assert(sources[0].rx==40000 && sources[0].enq==40000 && sources[0].bytes==48000000);
    for (unsigned i=2; i<20; i++) {
        uint8_t key[32] = {0}; key[0]=i;
        wg_diag_source(D_DERP, key, 0, 0, 1200, 0);
    }
    assert(source_overflow==3);
    void *p = D_ALLOC(3, allocation());
    assert(!p && calls==1 && allocs[3]==1);
    uint8_t data[4]={4,0,0,0}; wg_diag_type(D_DERP,data,4);
    assert(counts[D_DERP][D_DATA]==1);
    unsigned q=32; wg_diag_sample_queue(0,&q); q=0; wg_diag_sample_queue(0,&q);
    assert(hwm[0]==32 && depths[0]==0);
    wg_diag_peer(2,1); wg_diag_peer(2,0);
    assert(peers[2][0]==1 && peers[2][1]==1);
    wg_diag_peer_tx(2,0); wg_diag_peer_tx(2,1);
    assert(peer_tx[2][0]==1 && peer_tx[2][1]==1);
    wg_diag_add(D_DIRECT, D_TX, UINT32_MAX); wg_diag_add(D_DIRECT, D_TX, 2);
    assert(counts[D_DIRECT][D_TX]==1);
    wg_diag_tx(0,-1); wg_diag_tx(1,-1); wg_diag_tx(2,-1);
    wg_diag_tx(3,-1); wg_diag_tx(3,-4); wg_diag_tx(3,0);
    assert(txstage[0][1]==1 && txstage[1][1]==1 && txstage[2][1]==1);
    assert(txstage[3][1]==1 && txstage[3][4]==1 && txstage[3][0]==1);
    wg_diag_burst(0,100); wg_diag_burst(0,200); wg_diag_burst(1,300);
    wg_diag_burst(0,400); wg_diag_burst(0,20000);
    assert(burst_events==3 && burst_max==2);
    wg_diag_drain(100); wg_diag_drain(50100);
    wg_diag_loop_gap(100); wg_diag_loop_gap(40100);
    wg_diag_time(D_WAIT,31000);
    assert(times[D_DRAIN_GAP].max==50000 && times[D_LOOP_GAP].max==40000);
    assert(times[D_WAIT].slow==1);
    wg_diag_start(); wg_diag_report(); wg_diag_report();
    puts("PASS: concurrent counters, source isolation/overflow, allocation once, HWM, peer slots, wraparound");
    return 0;
}
''')
        exe = out / 'test'
        subprocess.run([cc, '-std=gnu11', '-Wall', '-Wextra', '-Werror', '-pthread',
                        '-I' + str(stub), '-I' + str(ROOT / 'diagnostics'),
                        str(test), '-o', str(exe)], check=True)
        result = subprocess.check_output([str(exe)], text=True)
        assert 'source=S0 path=derp rx_delta=40000' in result
        assert 'rx=40000(+0)' in result
        print(result.splitlines()[-1])
