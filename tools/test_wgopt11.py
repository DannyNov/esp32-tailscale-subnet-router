"""wgopt11 invariant tests: one controlled static TX buffer-count change.

Verify runtime build flags separately in validate_snapshot_image.py.
Run on checked-out branch head with git history (CI fetch-depth:0).
"""
import subprocess
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
base = subprocess.check_output(
    ['git', 'show', '44220ec080e5688c896855d41a90f69cd0fcff26:sdkconfig.defaults'],
    cwd=ROOT, text=True)
new = (ROOT / 'sdkconfig.defaults').read_text()
oldline = 'CONFIG_ESP_WIFI_STATIC_TX_BUFFER_NUM=32'
newline = 'CONFIG_ESP_WIFI_STATIC_TX_BUFFER_NUM=36'
assert base.count(oldline) == 1
assert new.count(newline) == 1
def active(s):
    return [line.strip() for line in s.splitlines() if line.strip() and not line.lstrip().startswith('#')]
assert active(new) == [newline if x == oldline else x for x in active(base)], 'Unexpected Kconfig change'
for x in ['CONFIG_ESP_WIFI_CACHE_TX_BUFFER_NUM=32',
          'CONFIG_ESP_WIFI_AMPDU_TX_ENABLED=y',
          'CONFIG_ESP_WIFI_AMPDU_RX_ENABLED=y',
          'CONFIG_SPIRAM_TRY_ALLOCATE_WIFI_LWIP=y',
          'CONFIG_ESP_WIFI_DYNAMIC_TX_BUFFER_NUM=48']:
    assert x in active(new), x
assert 'wgopt11' not in (ROOT / 'main/wg10_wifi_tx.c').read_text(), 'Data plane should be unchanged'
namefiles = subprocess.check_output(
    ['git', 'diff', '--name-only', '44220ec080e5688c896855d41a90f69cd0fcff26', 'HEAD'],
    cwd=ROOT, text=True).splitlines()
allowed = {
    'sdkconfig.defaults','CMakeLists.txt',
    'tools/validate_snapshot_image.py','tools/diagnostic_provenance.py',
    '.github/workflows/build-wg-diagnostics.yml','tools/test_integration.py',
    'tools/test_wgopt11.py','docs/WGOPT11-STATIC-TX36-RU.md'
}
assert set(namefiles) <= allowed, 'Unexpected changed file(s): ' + repr(set(namefiles)-allowed)
assert 'sdkconfig.defaults' in namefiles
print('PASS: wgopt11 single Kconfig delta 32->36, CACHE_TX32/PSRAM retained; unchanged data plane')
