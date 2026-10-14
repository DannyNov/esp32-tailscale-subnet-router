"""Fail closed on partition size and build/source provenance."""
from pathlib import Path
import hashlib
import json
import os
import subprocess
from prepare_wg_diagnostics import PIN

def git(*args):
    return subprocess.check_output(['git', *args], text=True).strip()

image = Path('artifacts/firmware-0.1.35-tuya-wgdiag2-esp32-s3-ota.bin')
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
data = {'version': '0.1.35-tuya-wgdiag2', 'source_commit': git('rev-parse', 'HEAD'),
        'microlink': PIN, 'base_commit': '3bd26480a4fb82aeb14cf2483bae9d3f2b9c2beb',
        'ota_bytes': size, 'partition_bytes': 1966080, 'headroom_bytes': 1966080 - size,
        'sha256': hashlib.sha256(image.read_bytes()).hexdigest(),
        'workflow_url': 'https://github.com/' + os.environ['GITHUB_REPOSITORY'] + '/actions/runs/' + os.environ['GITHUB_RUN_ID'],
        'hardware_acceptance': 'pending', 'flashed': False}
Path('artifacts/provenance.json').write_text(json.dumps(data, indent=2) + '\n')
print(json.dumps(data, indent=2))
