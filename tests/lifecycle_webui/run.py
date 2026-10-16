"""Run the actual manager adapters and Web UI snapshot sections with host doubles.

Uses the real pinned public microlink.h and the integrated snapshot header.
Does not claim coverage of the entire ESP-IDF TU or internal writer tasks.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
PILOT = HERE/'pilot'

def between(s, start, stop):
    assert s.count(start) == 1 and s.count(stop) == 1
    return s[s.index(start):s.index(stop)]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--cc', required=True, choices=['gcc', 'clang'])
    parser.add_argument('--sanitize', action='store_true')
    parser.add_argument('--prepare-only', action='store_true')
    a = parser.parse_args()
    out = ROOT/'build/lifecycle-webui'/ (a.cc + ('-san' if a.sanitize else ''))
    out.mkdir(parents=True, exist_ok=True)
    manager = (ROOT/'main/tailscale_manager.c').read_text(encoding='utf-8')
    functions = between(manager, 'static bool snapshot_try_lock(void)', 'void tailscale_set_subnet(')
    (out/'generated_snapshot_functions.c').write_text(functions, encoding='utf-8')
    stubs = (PILOT/'tests/host_stubs.h').read_text(encoding='utf-8')
    start = stubs.index('typedef struct { int online;')
    stop = stubs.index('static pthread_mutex_t master_mu')
    stubs = stubs[:start] + '''#include "tailscale_snapshot.h"
struct microlink_s {
    uint32_t serial;
    bool connected;
    microlink_peer_info_t peer;
    char region[64];
};
static bool test_diag_error, test_peer_error;
static int test_rtt_count = -1;
''' + stubs[stop:]
    import re
    stubs = re.sub(r'^static ([^\n]+\bmicrolink_\w+\()', r'\1', stubs, flags=re.M)
    stubs = stubs.replace('.online=ml->connected', '.connected=ml->connected')
    stubs = stubs.replace('*out=(microlink_diag_t)', 'if (test_diag_error) { memset(out, 0xa5, sizeof(*out)); return ESP_ERR_INVALID_STATE; }\n    *out=(microlink_diag_t)')
    stubs = stubs.replace('if(i!=0)', 'if(test_peer_error) { memset(out, 0xa5, sizeof(*out)); return ESP_ERR_INVALID_STATE; }\n    if(i!=0)')
    stubs = stubs.replace('return 1;\n}', 'return test_rtt_count >= 0 ? test_rtt_count : 1;\n}')
    (out/'host_stubs.h').write_text(stubs, encoding='utf-8')
    (out/'esp_err.h').write_text('typedef int esp_err_t;\n#define ESP_OK 0\n#define ESP_ERR_INVALID_STATE 0x103\n#define ESP_ERR_NO_MEM 0x101\n', encoding='utf-8')
    test = (PILOT/'tests/test_snapshot.c').read_text(encoding='utf-8')
    extra = (HERE/'snapshot_errors.inc').read_text(encoding='utf-8')
    test = test.replace('int main(void) {', extra+'\nint main(void) {\n    error_tests();')
    (out/'test_snapshot.c').write_text(test, encoding='utf-8')
    web = (ROOT/'main/web_ui.c').read_text(encoding='utf-8')
    support = between(web, '#define SNAPSHOT_JSON_CHECK(expression)', '/* index.html is generated')
    ipfn = between(web, 'static void ip4_hbo_to_str(', 'static esp_err_t tailscale_handler(')
    status = between(web, '    /* Tailscale (microlink) — task-context lifetime-safe snapshot. */', '    /* Telemetry summary')
    runtime = between(web, '    /* Runtime: standalone copy, never a borrowed microlink pointer. */', '    /* MTU / MSS / PMTU manager')
    peers = between(web, '    /* Peer snapshots are copies; generation check avoids mixing old/new instances. */', '    /* Accepted-routes table')
    json_test = (HERE/'json_errors.inc').read_text(encoding='utf-8')
    json_test = json_test.replace('/* SUPPORT */', support+ipfn)
    json_test = json_test.replace('/* STATUS */', status).replace('/* RUNTIME_PEERS */', runtime+peers)
    (out/'test_json.c').write_text(json_test, encoding='utf-8')
    if a.prepare_only:
        print('PREPARED_NOT_COMPILED: integrated functions and real headers; Web UI sections extracted')
        return
    flags = ['-std=c11', '-O1', '-g', '-Wall', '-Wextra', '-Werror', '-UNDEBUG', '-pthread']
    if a.sanitize: flags += ['-fsanitize=address,undefined', '-fno-omit-frame-pointer']
    includes = ['-I'+str(out), '-I'+str(ROOT/'main'), '-I'+str(ROOT/'external/microlink/components/microlink/include')]
    result = {'cc': a.cc, 'sanitize': a.sanitize, 'functions_sha256': hashlib.sha256(functions.encode()).hexdigest(), 'commands': []}
    def run(command, label):
        print('+', ' '.join(map(str, command)), flush=True)
        r = subprocess.run(command, capture_output=True, text=True, timeout=120)
        (out/(label+'.log')).write_text(r.stdout+r.stderr, encoding='utf-8')
        print(r.stdout+r.stderr, flush=True)
        print(label, 'exit', r.returncode, flush=True)
        result['commands'].append({'argv':list(map(str,command)), 'exit':r.returncode})
        (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
        if r.returncode: raise SystemExit(r.returncode)
    run([a.cc, '--version'], 'version')
    for name in ['snapshot', 'json']:
        exe = out/name
        libraries = subprocess.check_output(['pkg-config','--cflags','--libs','libcjson'],text=True).split() if name=='json' else []
        run([a.cc, *flags, *includes, str(out/('test_'+name+'.c')), '-o',str(exe), *libraries], name+'-compile')
        run([str(exe)], name+'-run')

if __name__=='__main__': main()
