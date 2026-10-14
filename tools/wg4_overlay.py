"""wgdiag4: stage timing and reduced synchronous handshake logging.

Generated-copy only. Fail-closed anchors; no modification of WG key state,
handshake cadence, security, routing, packet ownership or submodule.
"""
import re
from derp_header_overlay import once

def exact_sub(text, pattern, replacement, expected=1):
    result, n = re.subn(pattern, replacement, text, flags=re.MULTILINE)
    if n != expected:
        raise RuntimeError(f"wgdiag4 source anchor drift: {pattern[:90]} count={n} expected={expected}")
    return result

def apply(component):
    manager = component / "src/ml_wg_mgr.c"
    s = manager.read_text()
    # Match only the PBUF_RAW packet-copy allocation: another PBUF_REF
    # allocation elsewhere in this file must remain untouched.
    s = exact_sub(s,
        r"(?m)^(    struct pbuf \*p = D_ALLOC\(\d+, pbuf_alloc\(PBUF_RAW, pkt->len, PBUF_RAM\)\);)$",
        r"    int64_t d_rx_pbuf_us = esp_timer_get_time();\n\1\n    wg_diag_time(D_RX_PBUF, (uint32_t)(esp_timer_get_time() - d_rx_pbuf_us));")
    s = once(s, "    pbuf_take(p, pkt->data, pkt->len);",
             "    int64_t d_rx_copy_us = esp_timer_get_time();\n    pbuf_take(p, pkt->data, pkt->len);\n    wg_diag_time(D_RX_COPY, (uint32_t)(esp_timer_get_time() - d_rx_copy_us));")
    target = "            process_wg_packet(ml, &wg_pkt);"
    if s.count(target) != 2:
        raise RuntimeError("WG RX drain changed; refuse to patch")
    s = s.replace(target, """            uint8_t d_wg_type = (wg_pkt.len >= 4 && wg_pkt.data) ? wg_pkt.data[0] : 0;
            int64_t d_wg_start_us = esp_timer_get_time();
            process_wg_packet(ml, &wg_pkt);
            wg_diag_time((d_wg_type >= 1 && d_wg_type <= 3) ? D_RX_HS : D_RX_DATA,
                         (uint32_t)(esp_timer_get_time() - d_wg_start_us));""")
    s = once(s, 'ESP_LOGI(TAG, "WG send-both: handshake type=%d also relayed via DERP to %s",',
             'ESP_LOGD(TAG, "WG send-both: handshake type=%d also relayed via DERP to %s",')
    manager.write_text(s)

    netio = component / "src/ml_net_io.c"
    n = netio.read_text()
    n = once(n, 'ESP_LOGW(TAG, "WG-RX(direct) queue full: dropped %lu",',
             'ESP_LOGD(TAG, "WG-RX(direct) queue full: dropped %lu",')
    netio.write_text(n)

    file = component / "components/wireguard_lwip/src/wireguardif.c"
    s = file.read_text()
    success_patterns = [
        "[WG_RX] Handshake INITIATION from peer",
        "[WG_RX] Initiation MAC check PASSED",
        "[WG_RX] Initiation processed OK, sending response",
        "[WG_RX] Handshake RESPONSE!",
        "[WG_RX] Response MAC check PASSED",
        "[WG_RX] Peer found for handshake, processing response",
        "[WG] *** HANDSHAKE COMPLETE!",
        "[WG] Session started, sending keepalive",
        "[WG] *** WIREGUARD SESSION ESTABLISHED",
    ]
    for p in success_patterns:
        s = once(s, 'ESP_LOGW(TAG, "' + p, 'ESP_LOGD(TAG, "' + p)

    s = exact_sub(s,
        r"(?m)^(\s*)pbuf = D_ALLOC\((\d+), (pbuf_alloc\(PBUF_TRANSPORT, header_len \+ padded_len \+ WIREGUARD_AUTHTAG_LEN, PBUF_RAM\))\);$",
        r"\1int64_t d_tx_pbuf_us = esp_timer_get_time();\n\1pbuf = D_ALLOC(\2, \3);\n\1wg_diag_time(D_TX_PBUF, (uint32_t)(esp_timer_get_time() - d_tx_pbuf_us));")
    s = once(s, '\t\t\t\t\tpbuf_copy_partial(q, dst, unpadded_len, 0);',
            "\t\t\t\t\tint64_t d_tx_copy_us = esp_timer_get_time();\n\t\t\t\t\tpbuf_copy_partial(q, dst, unpadded_len, 0);\n\t\t\t\t\twg_diag_time(D_TX_COPY, (uint32_t)(esp_timer_get_time() - d_tx_copy_us));")
    s = exact_sub(s,
        r"(?m)^(\s*)pbuf = D_ALLOC\((\d+), (pbuf_alloc\(PBUF_TRANSPORT, src_len - WIREGUARD_AUTHTAG_LEN, PBUF_RAM\))\);$",
        r"\1int64_t d_rx_dec_pbuf_us = esp_timer_get_time();\n\1pbuf = D_ALLOC(\2, \3);\n\1wg_diag_time(D_RX_DEC_PBUF, (uint32_t)(esp_timer_get_time() - d_rx_dec_pbuf_us));")
    s = once(s,
        'bool decrypt_ok = wireguard_decrypt_packet_diag(pbuf->payload, src, src_len, nonce, keypair, (ip_addr_isany(addr) ? D_DERP : D_DIRECT));',
        "int64_t d_rx_decrypt_us = esp_timer_get_time();\n                bool decrypt_ok = wireguard_decrypt_packet_diag(pbuf->payload, src, src_len, nonce, keypair, (ip_addr_isany(addr) ? D_DERP : D_DIRECT));\n                wg_diag_time(D_RX_DECRYPT, (uint32_t)(esp_timer_get_time() - d_rx_decrypt_us));")
    s = once(s,
        'err_t d_forward = device->netif->input(pbuf, device->netif);',
        "int64_t d_rx_lwip_us = esp_timer_get_time();\n                                    err_t d_forward = device->netif->input(pbuf, device->netif);\n                                    wg_diag_time(D_RX_LWIP, (uint32_t)(esp_timer_get_time() - d_rx_lwip_us));")
    file.write_text(s)
