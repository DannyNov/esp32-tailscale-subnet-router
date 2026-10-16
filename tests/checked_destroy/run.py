"""Execute actual generated lifecycle bodies with deterministic scheduler doubles."""
from pathlib import Path
import argparse
import shlex
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'tools'))
from prepare_wg_diagnostics import prepare

def function(text, signature):
    start = text.index(signature)
    brace = text.index('{', start)
    depth = 1
    end = brace + 1
    while depth:
        depth += (text[end] == '{') - (text[end] == '}')
        end += 1
    return text[start:end]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--cc', default='cc')
    parser.add_argument('--sanitize', action='store_true')
    args = parser.parse_args()
    out = ROOT/'tests/host/build/checked-destroy'
    prepare(out)
    text = (out/'microlink/src/microlink.c').read_text()
    start = text.index('    /* Create tasks */')
    end = text.index('    /* WiFi is expected', start)
    tasks = 'static int create_tasks(microlink_t *ml) {\n'+text[start:end]+'return ESP_OK;\n}'
    bodies = '\n'.join(function(text, signature) for signature in (
        'esp_err_t microlink_stop(', 'esp_err_t microlink_destroy_checked(',
        'void ml_task_exiting('))
    manager = (ROOT/'main/tailscale_manager.c').read_text(encoding='utf-8')
    connect = function(manager, 'static esp_err_t tailscale_connect_locked(')
    prior = function(connect, '    if (s_microlink) {')
    failed = function(connect, '    if (err != ESP_OK) {')
    manager_bodies = ('static int manager_prior(void) {\n'+prior+'\nreturn ESP_OK;\n}\n'
        'static int manager_start_failed(int err) {\n'+failed+'\nreturn ESP_OK;\n}\n'
        + function(manager, 'void tailscale_disconnect(')+'\n'
        + function(manager, 'bool tailscale_is_connected('))
    fixture = (Path(__file__).parent/'fixture.c').read_text()
    source = out/'lifecycle.c'
    source.write_text(fixture.replace('/* GENERATED */', bodies+'\n'+tasks)
                     .replace('/* MANAGER */', manager_bodies))
    exe = out/'lifecycle-test'
    flags = ['-std=c11', '-Wall', '-Wextra', '-Werror', '-UNDEBUG']
    if args.sanitize:
        flags += ['-fsanitize=address,undefined', '-fno-omit-frame-pointer']
    subprocess.run(shlex.split(args.cc)+flags+[str(source), '-o', str(exe)], check=True)
    subprocess.run([str(exe)], check=True)
    print('PASS generated stop/destroy/task reservation scenarios')
    sd = (ROOT/'components/sdlog/sdlog.c').read_text(encoding='utf-8')
    a = sd.index("    char coord = '-'")
    b = sd.index('    char line[256];', a)
    sample = sd[a:b]
    a = sd.index('        if (s_ml_mutex) xSemaphoreTake', sd.index('uint64_t now_ms ='))
    b = sd.index('        uint32_t coord_age =', a)
    heartbeat = sd[a:b]
    fixture = (Path(__file__).parent/'sd_fixture.c').read_text()
    source = out/'sd-reader.c'
    source.write_text(fixture.replace('/* SETTER */', function(sd,'void sdlog_set_microlink('))
        .replace('/* SAMPLE */',sample).replace('/* HEARTBEAT */',heartbeat))
    exe = out/'sd-reader-test'
    subprocess.run(shlex.split(args.cc)+flags+['-pthread',str(source),'-o',str(exe)],check=True)
    subprocess.run([str(exe)],check=True)
    print('PASS actual SD accessor blocks and setter: concurrent detach/free/attach')

if __name__ == '__main__':
    main()
