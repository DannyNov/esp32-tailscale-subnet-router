"""Host contracts for wgopt1 direct-pbuf TX on immutable pinned microlink."""
from pathlib import Path
from tempfile import TemporaryDirectory
from prepare_wg_diagnostics import prepare

with TemporaryDirectory(prefix="wgopt1-contract-") as tmp:
    out = Path(tmp)
    prepare(out)
    root = out / "microlink"
    mgr = (root / "src/ml_wg_mgr.c").read_text()
    src = (root / "components/wireguard_lwip/src/wireguardif.c").read_text()
    header = (root / "components/wireguard_lwip/src/wireguard.h").read_text()
    public = (root / "components/wireguard_lwip/src/wireguardif.h").read_text()

    # The shortcut executes ONLY for the direct magicsock path, after DERP
    # selection, before old PSRAM linearisation; chained buffers fall back.
    i_derp = src.index("if (ip_addr_isany(&peer->ip) || peer->port == 0 || device->force_derp_output)")
    i_direct = src.index("if (device->udp_output_fn)", i_derp)
    i_short = src.index("if (device->udp_pbuf_output_fn && q &&", i_direct)
    i_fallback = src.index("// Linearize pbuf chain and send via callback", i_short)
    assert "WG_OUT_ALLOC(q->tot_len)" in src[i_fallback:src.index("// Convert lwIP IP address", i_fallback)]
    assert i_derp < i_direct < i_short < i_fallback
    assert "q->len == q->tot_len" in src[i_short:i_fallback]
    assert "result = device->udp_pbuf_output_fn(dest_ip, peer->port, q," in src[i_short:i_fallback]
    assert "goto done;" in src[i_short:i_fallback]
    assert "pbuf = D_ALLOC(" in src and "PBUF_TRANSPORT, header_len + padded_len + WIREGUARD_AUTHTAG_LEN, PBUF_RAM" in src
    assert "wireguard_udp_pbuf_output_fn udp_pbuf_output_fn;" in header
    assert "wireguardif_set_udp_pbuf_output" in public
    assert "device->udp_pbuf_output_fn = fn;" in src

    # Borrowing contract: no alloc, pbuf_free, ref/deferred retention,
    # or change in encrypted data; UDP send is synchronous.
    fn = mgr.split("static err_t wgopt1_udp_pbuf_output_cb(", 1)[1].split("static err_t wg_udp_output_cb(", 1)[0]
    for forbidden in ("malloc(", "free(", "memcpy(", "pbuf_alloc(", "pbuf_free(", "pbuf_ref(", "tcpip_callback("):
        assert forbidden not in fn, forbidden
    assert "udp_sendto(s_wg_output_pcb, p, &dst, dest_port)" in fn
    assert fn.count("wg_diag_tx(3, err);") == 1
    assert fn.index("udp_sendto(") < fn.index("wg_diag_tx(3, err);") < fn.index("return err;")
    assert "wgopt1_send_both(ml, dest_ip, packet_data, packet_len)" in fn
    assert "p->len != p->tot_len" in fn
    assert "if (!ml || !s_wg_output_pcb) return ERR_CONN" in fn

    # The legacy byte callback and both-path handshake logic remain.
    assert "static err_t wg_udp_output_cb(" in mgr
    assert "wireguardif_set_udp_output(netif, wg_udp_output_cb, ml);" in mgr
    assert "wireguardif_set_udp_pbuf_output(netif, wgopt1_udp_pbuf_output_cb, ml);" in mgr
    assert mgr.count("wgopt1_send_both(ml, dest_ip,") == 2
    helper = mgr.split("static void wgopt1_send_both(", 1)[1].split("static err_t wgopt1_udp_pbuf_output_cb(", 1)[0]
    for marker in ("data[0] == 0x01", "data[0] == 0x02", "data[0] == 0x03",
                   "ml_derp_queue_send(ml, pr->public_key, data, len)",
                   "htonl(pr->best_ip) == dest_ip"):
        assert marker in helper, marker

print("PASS: borrowed original PBUF_RAM, no copies on direct callback, chained fallback, DERP send-both, immutable pinned component")
