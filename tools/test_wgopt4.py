"""Source/host acceptance for wgopt4 low-rate path telemetry.

Uses generated component source to detect silent anchor drift; the existing
test_wg_diagnostics.py compiles and executes the actual updated wg_diag.c.
No new runtime path modifications, no source-code patching in external/.
"""
from pathlib import Path
from tempfile import TemporaryDirectory
from prepare_wg_diagnostics import prepare, ROOT

with TemporaryDirectory(prefix="wgopt4-host-") as tmp:
    root = Path(tmp)
    prepare(root)
    backend = root / "microlink/components/wireguard_lwip/src"
    output = (backend / "wireguardif.c").read_text()
    hdr = (backend / "wg_diag.h").read_text()
    source = (backend / "wg_diag.c").read_text()
    original = (ROOT / "external/microlink/components/microlink/components/wireguard_lwip/src/wireguardif.c").read_text()
    assert "wg_diag_wg4_tx" not in original
    assert output.count("wg_diag_wg4_tx(wg4_route_derp, result, q ? q->tot_len : 0);") == 1
    assert output.count("if (wg_mt == 4)") == 1
    pos = output.index("wg_diag_wg4_tx(wg4_route_derp")
    assert output.rfind("wg_diag_peer_tx(d_peer",0,pos) >= 0
    assert output.index("if (result != ERR_OK)",pos) > pos
    assert output.count("wireguard_encrypt_packet(dst, dst, padded_len, keypair);") == 1
    assert "wireguardif_network_rx_borrowed" in output
    assert "unsigned wg4_route_derp = (ip_addr_isany(&peer->ip) || peer->port == 0 ||" in output
    assert "device->force_derp_output) ? 1u : 0u;" in output
    assert "void wg_diag_wg4_tx(unsigned path, int result, uint32_t bytes);" in hdr
    assert 'ESP_LOGW("WG4_TX"' in source and 'ESP_LOGW("WG4_RX"' in source
    assert "wg4_report();" in source and "pdMS_TO_TICKS(10000)" in source
    assert "__atomic_exchange_n(&wg4_qpeak[0], 0, __ATOMIC_RELAXED)" in source
    assert "memcpy(" not in source[source.index("void wg_diag_wg4_tx("):source.index("void wg_diag_tx(")]
    assert "ESP_LOG" not in source[source.index("void wg_diag_wg4_tx("):source.index("void wg_diag_tx(")]
    assert "static uint32_t wg4_tx[2][3];" in source
    assert "delta_drop" in source and "D_TX_CRYPTO" in source and "D_TX_SEND" in source
    assert "D_PERIODIC" in source and "D_PROBES" in source and "D_WAIT" in source
    assert "heap_caps_get_free_size(MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT)" in source
    # No extra polling or payload retention in generated WG data path.
    block = output[output.index("/* Actual WG data egress route."):pos+len("wg_diag_wg4_tx(wg4_route_derp, result, q ? q->tot_len : 0);")]
    for forbidden in ("malloc(", "free(", "pbuf_ref(", "ESP_LOG", "vTaskDelay(", "memcpy(", "wireguardif_update_endpoint"):
        assert forbidden not in block, forbidden
print("PASS: wgopt4 route attribution, 10s WARN web-log windows, bounded/atomic counters, no data-path behavior changes")
