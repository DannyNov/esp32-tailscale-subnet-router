"""wgopt10: no changes to packets, routes or config. Verify raw Wi-Fi wrappers.

Probe requires exact return codes and tracks whether Wi-Fi function executed;
without it a STA ERR_MEM could equally be a temporary pbuf failure.
"""
from pathlib import Path
from tempfile import TemporaryDirectory
from prepare_wg_diagnostics import ROOT, prepare
with TemporaryDirectory(prefix="wgopt10-") as tmp:
    out = Path(tmp)
    prepare(out)
    h = (out / 'microlink/include/microlink_internal.h').read_text()
    assert '#define ML_WG_RX_QUEUE_DEPTH    128' in h
    mgr = (out / 'microlink/src/ml_wg_mgr.c').read_text()
    assert 'wg9_direct_udp_begin();' in mgr and 'wg9_direct_udp_end(err);' in mgr
    assert mgr.count('err_t err = udp_sendto(s_wg_output_pcb, p, &dst, dest_port);') >= 1
    code = (ROOT / 'main/wg10_wifi_tx.c').read_text()
    for name,mode in (('esp_wifi_internal_tx_by_ref','1'),('esp_wifi_internal_tx','0')):
        assert '__real_' + name in code
        assert '__wrap_' + name in code
        assert 'wg10_wifi_driver_result(raw, ' + mode + ');' in code
    assert code.count('return raw;') == 2
    diag = (ROOT / 'diagnostics/wg_diag.c').read_text()
    assert 'WG10_WIFI_TX' in diag and 'WG10_DRIVER_NOMEM' in diag
    assert 'WG10_NO_DRIVER_CHAIN' in diag and 'WG10_REF_CALLS' in diag
    assert 'wg10_report();' in diag
    assert 'WG9_TXPATH' in diag
    assert (ROOT / 'sdkconfig.defaults').read_text().count('CONFIG_ESP_WIFI_CACHE_TX_BUFFER_NUM=32') == 1
    print('PASS: wgopt10 raw driver return, scoped linkoutput chain detection, unchanged RX128 and buffer settings')
