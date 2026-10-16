"""Pinned DERP reconnect fragment with deterministic boundary doubles, not TLS runtime."""
import argparse, hashlib, json, pathlib, subprocess

ROOT = pathlib.Path(__file__).resolve().parents[2]
PIN = 'eb63b97073e529d57bc9c1deaeea25ac304034e5'
BASE = 'ed510efa72da0925cbac3d15ab353175b00c96b2'
def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args]).decode().strip()
def main():
    p = argparse.ArgumentParser()
    p.add_argument('--cc', required=True)
    p.add_argument('--upstream', type=pathlib.Path, default=ROOT/'external/microlink')
    p.add_argument('--sanitize', action='store_true')
    p.add_argument('--prepare-only', action='store_true')
    a = p.parse_args()
    assert git(ROOT, 'ls-tree', BASE, 'external/microlink').split()[2] == PIN
    assert git(a.upstream, 'rev-parse', 'HEAD') == PIN
    assert not git(a.upstream, 'status', '--porcelain', '--untracked-files=no')
    blob = (a.upstream/'components/microlink/src/ml_derp.c').read_bytes()
    text = blob.decode().replace('\r\n', '\n')
    start = '                ml->derp.connected = false;\n                for (int i = 0; i < 20'
    end = '                verbose_phase = false;'
    assert text.count(start) == 1
    tail = text[text.index(start):]
    assert end in tail
    fragment = tail[:tail.index(end)]
    # The assertion deliberately expects the current contract violation.
    harness = '''#include <assert.h>
#include <stdbool.h>
#include <stdio.h>
typedef struct { struct { bool connected; volatile bool rx_parked; } derp; } microlink_t;
static int elapsed, teardown_calls;
#define pdMS_TO_TICKS(x) (x)
static void vTaskDelay(int ms) { assert(ms == 10); elapsed += ms; }
static void ml_derp_disconnect(microlink_t *ml) { assert(!ml->derp.rx_parked); teardown_calls++; }
static void reconnect(microlink_t *ml) {
''' + fragment + '''
}
int main(void) {
 microlink_t ml = { .derp = { true, false } };
 reconnect(&ml);
 assert(elapsed == 200 && teardown_calls == 1 && !ml.derp.rx_parked);
 puts("EXPECTED CONTRACT VIOLATION: pinned DERP fragment tears down after 200ms without rx_parked");
 return 0;
}
'''
    out = ROOT/'build/lifecycle-ci'/ (a.cc + ('-san' if a.sanitize else ''))
    out.mkdir(parents=True, exist_ok=True)
    (out/'negative.c').write_text(harness, encoding='utf-8')
    result = {'base': BASE, 'pin': PIN, 'kind': 'exact source fragment; deterministic boundary doubles',
              'full_derp_runtime': False, 'source_sha256': hashlib.sha256(blob).hexdigest(),
              'fragment_sha256': hashlib.sha256(fragment.encode()).hexdigest(), 'commands': []}
    if a.prepare_only:
        result['status'] = 'PREPARED_NOT_EXECUTED'
        (out/'result.json').write_text(json.dumps(result, indent=2)+'\n')
        print(json.dumps(result, indent=2))
        return
    def run(cmd, label):
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        (out/(label+'.stdout.log')).write_text(r.stdout, encoding='utf-8')
        (out/(label+'.stderr.log')).write_text(r.stderr, encoding='utf-8')
        result['commands'].append({'argv': cmd, 'exit': r.returncode})
        (out/'result.json').write_text(json.dumps(result, indent=2)+'\n')
        print(label, r.returncode, r.stdout, r.stderr)
        assert r.returncode == 0, label
        return r.stdout
    run([a.cc, '--version'], 'compiler-version')
    flags = ['-std=c11', '-Wall', '-Wextra', '-Werror', '-UNDEBUG']
    if a.sanitize: flags += ['-fsanitize=address,undefined', '-fno-omit-frame-pointer', '-g']
    for name, src in [('smoke', ROOT/'tests/lifecycle_ci/smoke.c'), ('negative', out/'negative.c'),
                      ('control', ROOT/'tests/lifecycle_ci/control.c')]:
        exe = out/name
        run([a.cc, *flags, str(src), '-o', str(exe)], name+'-compile-link')
        stdout = run([str(exe)], name+'-execute')
        if name == 'negative': assert 'EXPECTED CONTRACT VIOLATION:' in stdout
    result['status'] = 'EXPECTED_VIOLATION_CONFIRMED_CONTROL_PASS'
    (out/'result.json').write_text(json.dumps(result, indent=2)+'\n')
if __name__ == '__main__': main()
