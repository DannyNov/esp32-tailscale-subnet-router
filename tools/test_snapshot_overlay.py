"""Compile exact periodic consumer block; preserve DERP production regressions."""
import argparse
from pathlib import Path
import shlex
import subprocess
from prepare_wg_diagnostics import ROOT, prepare

p = argparse.ArgumentParser()
p.add_argument('--cc', default='cc')
a = p.parse_args()
out = ROOT / 'build/snapshot-test'
prepare(out)
mgr = (out / 'microlink/src/ml_wg_mgr.c').read_text()
start = mgr.index('        /* Throughput-collapse diag: full state snapshot every 10 s. */')
end = mgr.index('        /* Yield - 10ms loop rate', start)
block = mgr[start:end]
# A snapshot reference fails compilation: no declaration, no peer/netif objects.
c = '''#include <assert.h>
#include <stdint.h>
#define TAG "test"
#define ESP_LOGI(...) ((void)0)
static unsigned samples;
static void wg_diag_stack_sample(void) { samples++; }
int main(void) {
    uint64_t last_snapshot_ms = 0;
    uint32_t disco_rx_10s = 1, budget_hits_10s = 1;
    for (uint64_t now = 0; now <= 100000000; now += 1) {
''' + block + '''
        assert(last_snapshot_ms <= now);
        if (now >= 10000) assert(disco_rx_10s == 0 && budget_hits_10s == 0);
    }
    assert(samples == 10000);
    return 0;
}
'''
build = ROOT / 'tests/host/build'
build.mkdir(exist_ok=True)
(build / 'snapshot_block.c').write_text(c)
derp = (out / 'microlink/src/ml_derp.c').read_text()
for function, filename, stop in [('ml_derp_bio_recv_timeout', 'bio_under_test.inc', '\n/**'),
                                 ('poll_derp_read', 'poll_under_test.inc', '\n/* ===')]:
    begin = derp.index('static int ' + function + '(')
    (build / filename).write_text(derp[begin:derp.index(stop, begin)])
sources = [build / 'snapshot_block.c'] + [ROOT / 'tests/host/derp' / ('test_' + n + '.c') for n in ('header', 'bio', 'poll')]
for source in sources:
    exe = build / (source.stem + '.exe')
    subprocess.run(shlex.split(a.cc) + ['-std=c11', '-Wall', '-Wextra', '-Werror',
                   '-I' + str(build), str(source), '-o', str(exe)], check=True)
    subprocess.run([str(exe)], check=True)
print('PASS: exact snapshot block, 10000 windows without peer pointers; DERP header/BIO/poll regressions')
