"""Upstream v0.1.38 supersedes wgopt1 with encrypted SPIRAM pbuf TX.
Keep its TCPIP-safe output and allocation hooks rather than duplicate the API.
"""
def apply(component):
    mgr = (component/'src/ml_wg_mgr.c').read_text()
    backend = (component/'components/wireguard_lwip/src/wireguardif.c').read_text()
    for anchor in ('wg_udp_sendto_tcpip(p, &dst, dest_port)', 'wg_send_both_relay(', 'wireguardif_set_tx_pbuf_output('):
        if anchor not in mgr: raise RuntimeError('Upstream TX contract missing: '+anchor)
    if 'tx_dev->tx_pbuf_alloc_fn(out_len, tx_dev->tx_pbuf_ctx)' not in backend:
        raise RuntimeError('Upstream in-place TX allocator missing')
