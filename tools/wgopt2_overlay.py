"""wgopt2: avoid encrypted ingress copy on complete WG data messages.

Generated-copy only; caller owns outer ciphertext until synchronous parse returns.
Decrypted plaintext remains a different owned PBUF_RAM for tcpip_input.
Handshake/cookie/malformed packets retain legacy pbuf path.
"""
from derp_header_overlay import once


def apply(component):
    backend = component / "components/wireguard_lwip/src"
    wgif = backend / "wireguardif.c"
    s = wgif.read_text()
    old = """void wireguardif_network_rx(void *arg, struct udp_pcb *pcb, struct pbuf *p, const ip_addr_t *addr, u16_t port) {
\tLWIP_ASSERT("wireguardif_network_rx: invalid arg", arg != NULL);
\tLWIP_ASSERT("wireguardif_network_rx: invalid pbuf", p != NULL);
\t// We have received a packet from the base_netif to our UDP port - process this as a possible Wireguard packet
\tstruct wireguard_device *device = (struct wireguard_device *)arg;
\tstruct wireguard_peer *peer;
\tuint8_t *data = p->payload;
\tsize_t len = p->len; // This buf, not chained ones
"""
    new = """/* The encoded WG frame is consumed synchronously. Decrypted data
 * enters tcpip_input on an independent PBUF_RAM, never on this buffer.
 * The caller retains ownership of input bytes throughout the call. */
void wireguardif_network_rx_borrowed(void *arg, uint8_t *data, size_t len,
                                     const ip_addr_t *addr, u16_t port) {
    LWIP_ASSERT("wireguardif_network_rx_borrowed: invalid arg", arg != NULL);
    LWIP_ASSERT("wireguardif_network_rx_borrowed: invalid data", data != NULL);
    struct wireguard_device *device = (struct wireguard_device *)arg;
    struct wireguard_peer *peer;
"""
    s = once(s, old, new)
    tail = """\t// Release data!
\tpbuf_free(p);
}

static err_t wireguard_start_handshake"""
    replacement = """}

/* Preserve the existing pbuf-consuming UDP entrypoint for every legacy
 * caller. Only the new method borrows its buffer without freeing it. */
void wireguardif_network_rx(void *arg, struct udp_pcb *pcb, struct pbuf *p,
                            const ip_addr_t *addr, u16_t port) {
    LWIP_ASSERT("wireguardif_network_rx: invalid arg", arg != NULL);
    LWIP_ASSERT("wireguardif_network_rx: invalid pbuf", p != NULL);
    wireguardif_network_rx_borrowed(arg, (uint8_t *)p->payload, p->len, addr, port);
    pbuf_free(p);
}

static err_t wireguard_start_handshake"""
    s = once(s, tail, replacement)
    wgif.write_text(s)

    hdr = backend / "wireguardif.h"
    s = hdr.read_text()
    s = once(s, "// Check if packet looks like a WireGuard packet (type 1-4)",
        """/* Synchronous, non-owning encrypted ingress; caller retains buffer.
 * Plaintext for asynchronous tcpip_input still has its own PBUF_RAM. */
void wireguardif_network_rx_borrowed(void *arg, uint8_t *data, size_t len,
                                     const ip_addr_t *addr, u16_t port);

// Check if packet looks like a WireGuard packet (type 1-4)""")
    hdr.write_text(s)

    manager = component / "src/ml_wg_mgr.c"
    s = manager.read_text()
    marker = "    /* Allocate PBUF_RAM and copy data so the pbuf OWNS its data."
    bypass = """    /* wgopt2: only complete canonical WG transport data uses borrowed
     * encrypted input. pkt->data lives through synchronous parse/decrypt;
     * the forwarded plaintext remains separately allocated PBUF_RAM.
     * Handshakes, cookie replies, malformed packets use the old path. */
    if (pkt->data && pkt->len >= 32 && pkt->len <= UINT16_MAX &&
        pkt->data[0] == 4 && pkt->data[1] == 0 &&
        pkt->data[2] == 0 && pkt->data[3] == 0) {
        ip_addr_t borrowed_addr;
        if (pkt->via_derp) {
            ip_addr_set_any(false, &borrowed_addr);
        } else {
            IP_SET_TYPE_VAL(borrowed_addr, IPADDR_TYPE_V4);
            ip4_addr_set_u32(ip_2_ip4(&borrowed_addr), htonl(pkt->src_ip));
        }
        wireguardif_network_rx_borrowed(device, pkt->data, pkt->len,
                                        &borrowed_addr, pkt->src_port);
        free(pkt->data);
        return;
    }

"""
    s = once(s, marker, bypass + marker)
    manager.write_text(s)
