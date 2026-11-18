"""Upstream replacement for office wgopt1: in-place encryption and safe output."""
from pathlib import Path
from tempfile import TemporaryDirectory
from prepare_wg_diagnostics import prepare
with TemporaryDirectory(prefix='wgopt1-upstream-') as tmp:
    out=Path(tmp);prepare(out);root=out/'microlink'
    mgr=(root/'src/ml_wg_mgr.c').read_text()
    src=(root/'components/wireguard_lwip/src/wireguardif.c').read_text()
    derp=src.index('if (ip_addr_isany(&peer->ip) || peer->port == 0 || device->force_derp_output)')
    direct=src.index('if (device->udp_output_fn)',derp)
    short=src.index('device->udp_pbuf_output_fn',direct)
    fallback=src.index('// Linearize pbuf chain and send via callback',short)
    assert derp<direct<short<fallback
    assert 'q->len == q->tot_len' in src[short:fallback]
    assert 'tx_dev->tx_pbuf_alloc_fn(out_len, tx_dev->tx_pbuf_ctx)' in src
    assert 'pbuf_alloc(PBUF_TRANSPORT, out_len, PBUF_RAM)' in src
    assert 'wireguard_encrypt_packet(dst, dst, padded_len, keypair)' in src
    begin=mgr.index('static err_t wg_udp_pbuf_output_cb(uint32_t dest_ip, uint16_t dest_port, struct pbuf *p, void *ctx) {')
    fn=mgr[begin:mgr.index('static err_t wg_udp_output_cb(',begin)]
    assert 'wg_udp_sendto_tcpip(p, &dst, dest_port)' in fn
    assert 'udp_sendto(s_wg_output_pcb' not in fn
    assert fn.count('wg_diag_tx(3, err);')==1
    assert 'wg_send_both_relay(ml, dest_ip, data, len)' in fn
    helper=mgr[mgr.index('static void wg_send_both_relay('):mgr.index('esp_err_t ml_wg_set_tx_copyfree(')]
    for marker in ['data[0] == 0x01','data[0] == 0x02','data[0] == 0x03','ml_derp_queue_send(ml, pr->public_key, data, len)']:
        assert marker in helper
print('PASS: upstream in-place encrypted SPIRAM TX, chained/DERP fallback and TCPIP-safe send-both')
