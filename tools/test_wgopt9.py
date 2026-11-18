"""wgopt9: read-only host integration check of the precise ERR_MEM attribution.

No behavioral or transmit buffer changes relative to wgopt8.
"""
from pathlib import Path
from tempfile import TemporaryDirectory
from prepare_wg_diagnostics import ROOT, prepare

with TemporaryDirectory(prefix="wgopt9-") as td:
    out = Path(td)
    prepare(out)
    mgr = (out / "microlink/src/ml_wg_mgr.c").read_text()
    begin = mgr.index("static err_t wg_udp_pbuf_output_cb(uint32_t dest_ip, uint16_t dest_port, struct pbuf *p, void *ctx) {")
    end = mgr.index("static err_t wg_udp_output_cb(", begin)
    borrowed = mgr[begin:end]
    assert borrowed.count("wg9_direct_udp_begin();") == 1
    assert borrowed.count("wg9_direct_udp_end(err);") == 1
    assert borrowed.index("wg9_direct_udp_begin();") < borrowed.index(
        "wg_udp_sendto_tcpip(p, &dst, dest_port)") < borrowed.index(
        "wg9_direct_udp_end(err);")
    assert borrowed.count("wg_diag_tx(3, err);") == 1
    assert "wg_send_both_relay(ml, dest_ip, data, len);" in borrowed
    assert "return err;" in borrowed
    assert '#define ML_WG_RX_QUEUE_DEPTH    128' in (out / "microlink/include/microlink_internal.h").read_text()
    diag = (out / "microlink/components/wireguard_lwip/src/wg_diag.c").read_text()
    assert "WG9_TXPATH" in diag and "MALLOC_CAP_DMA" in diag
    assert "WG9_STA_ERRMEM" in diag and "WG9_NO_STA_OUTPUT" in diag
    assert "xTaskGetCurrentTaskHandle()" in diag
    hooks = (ROOT / "main/netif_hooks.c").read_text()
    assert "wg9_sta_link_result(tx_result);" in hooks
    assert "return tx_result;" in hooks
    assert "return original_ap_linkoutput ? original_ap_linkoutput(netif, p) : ERR_VAL;" in hooks
    print("PASS: wgopt9 scoped diagnostics, preserved direct TX behavior and 128-slot queue")
