"""Pinned upstream source contracts; these are not device/runtime tests."""
from pathlib import Path
import subprocess
import re

root = Path(__file__).resolve().parents[1]
ml = root / 'external/microlink'
assert subprocess.check_output(['git', '-C', str(ml), 'rev-parse', 'HEAD'], text=True).strip() == 'eb63b97073e529d57bc9c1deaeea25ac304034e5'
src = ml / 'components/microlink/src'
wg = (src / 'ml_wg_mgr.c').read_text()
for line in ['WG UDP TX:', 'WG RX:']:
    assert re.search(r'ESP_LOGD\(TAG, "' + re.escape(line), wg)
for marker in ['[WG_SNAP]', '[WG_SNAP_SUM]']:
    assert re.search(r'ESP_LOGI\(TAG,\s*"' + re.escape(marker), wg)
derp = (src / 'ml_derp.c').read_text()
assert 'while (ml->derp_tx_queue && xQueueReceive' in derp
coord = (src / 'ml_coord.c').read_text()
assert 'ML_EVT_DERP_CONNECTED | ML_EVT_SHUTDOWN_REQUEST' in coord
assert 'if (derp_wb & ML_EVT_SHUTDOWN_REQUEST)' in coord
print('PASS: pinned microlink logging/OOM/shutdown source contracts; runtime and throughput pending hardware')
