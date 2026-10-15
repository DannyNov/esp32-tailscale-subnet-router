"""Fail closed on partition size and build/source provenance."""
from pathlib import Path
import hashlib
import json
import os
import subprocess
from prepare_wg_diagnostics import PIN

def git(*args):
    return subprocess.check_output(['git', *args], text=True).strip()

image = Path('artifacts/firmware-0.1.35-tuya-wgopt11-esp32-s3-ota.bin')
size = image.stat().st_size
assert 0 < size <= 1966080, f'OTA size {size} exceeds partition'
assert image.read_bytes()[0] == 0xE9, 'Invalid ESP image magic'
assert git('-C', 'external/microlink', 'rev-parse', 'HEAD') == PIN
assert not git('status', '--porcelain', '--untracked-files=no'), 'Dirty source'
config = Path('artifacts/sdkconfig-built.txt').read_text()
for flag in ('CONFIG_ESPTOOLPY_FLASHSIZE_4MB=y', 'CONFIG_SPIRAM=y',
             'CONFIG_SPIRAM_MODE_OCT=y', 'CONFIG_SPIRAM_XIP_FROM_PSRAM=y'):
    assert flag in config, flag
assert 'CONFIG_ML_ZERO_COPY_WG=y' not in config, 'Untested receive path'
for flag in ('CONFIG_ESP_WIFI_STATIC_TX_BUFFER=y',
             'CONFIG_ESP_WIFI_STATIC_TX_BUFFER_NUM=36',
             'CONFIG_ESP_WIFI_CACHE_TX_BUFFER_NUM=32',
             'CONFIG_SPIRAM_TRY_ALLOCATE_WIFI_LWIP=y'):
    assert flag in config, 'Effective Wi-Fi TX config mismatch: ' + flag
data = {'version': '0.1.35-tuya-wgopt11', 'source_commit': git('rev-parse', 'HEAD'),
        'microlink': PIN, 'base_commit': '44220ec080e5688c896855d41a90f69cd0fcff26',
        'ota_bytes': size, 'partition_bytes': 1966080, 'headroom_bytes': 1966080 - size,
        'sha256': hashlib.sha256(image.read_bytes()).hexdigest(),
        'workflow_url': 'https://github.com/' + os.environ['GITHUB_REPOSITORY'] + '/actions/runs/' + os.environ['GITHUB_RUN_ID'],
        'static_tx_buffers': 36, 'cache_tx_buffers': 32,
        'static_tx_delta_vs_wgopt10': 4, 'predicted_static_internal_ram_delta_bytes': 6400,
        'hardware_acceptance': 'pending', 'flashed': False}
Path('artifacts/provenance.json').write_text(json.dumps(data, indent=2) + '\n')
print(json.dumps(data, indent=2))
