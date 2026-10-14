"""wgopt4: read-only TX route metrics for 40-110s throughput anomaly.

Generated component only, after wgopt2. Data packets only, after peer
output returns; no endpoint/key/pbuf modification, no per-packet logs.
"""
from derp_header_overlay import once


def apply(component):
    wgif = component / "components/wireguard_lwip/src/wireguardif.c"
    s = wgif.read_text()
    anchor = "wg_diag_peer_tx(d_peer, result != ERR_OK);"
    replacement = """wg_diag_peer_tx(d_peer, result != ERR_OK);
    /* Actual WG data egress route. DERP accepts a queue item, direct
     * accepts a raw UDP send; neither confirms remote delivery.
     * Handshake send-both is excluded (wg_mt != 4). */
    if (wg_mt == 4) {
        unsigned wg4_route_derp = (ip_addr_isany(&peer->ip) || peer->port == 0 ||
                                   device->force_derp_output) ? 1u : 0u;
        wg_diag_wg4_tx(wg4_route_derp, result, q ? q->tot_len : 0);
    }"""
    s = once(s, anchor, replacement)
    wgif.write_text(s)
