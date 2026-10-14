"""wgopt1 — direct WireGuard PBUF_RAM to UDP, build-copy only.

The WireGuard TX caller owns a contiguous encrypted PBUF_TRANSPORT buffer.
The existing magicsock path copied it into PSRAM, then again into a second
SPIRAM custom pbuf with UDP header space, allocating three temporary objects.
The optional callback here borrows that original pbuf synchronously for
udp_sendto and must neither free nor retain it.

Preserve existing byte callback as fallback for chained buffers and legacy
device-output/cookie routes; preserve DERP fallback and send-both handshake.
All modifications fail closed against pinned-source anchors.
"""
from derp_header_overlay import once


def apply(component):
    backend = component / "components/wireguard_lwip/src"

    h = backend / "wireguard.h"
    s = h.read_text()
    s = once(s,
        "typedef err_t (*wireguard_udp_output_fn)(uint32_t dest_ip, uint16_t dest_port, const uint8_t *data, size_t len, void *ctx);",
        """typedef err_t (*wireguard_udp_output_fn)(uint32_t dest_ip, uint16_t dest_port, const uint8_t *data, size_t len, void *ctx);
/* Optional borrowed-pbuf callback. Caller retains ownership; callback is
 * synchronous and may not retain/free the pbuf. In magicsock mode the
 * source is already a contiguous, encrypted PBUF_TRANSPORT/PBUF_RAM. */
typedef err_t (*wireguard_udp_pbuf_output_fn)(uint32_t dest_ip, uint16_t dest_port, struct pbuf *p, void *ctx);""")
    s = once(s,
        "\twireguard_udp_output_fn udp_output_fn;\n\tvoid *udp_output_ctx;",
        """\twireguard_udp_output_fn udp_output_fn;
\tvoid *udp_output_ctx;
\twireguard_udp_pbuf_output_fn udp_pbuf_output_fn;
\tvoid *udp_pbuf_output_ctx;""")
    h.write_text(s)

    h = backend / "wireguardif.h"
    s = h.read_text()
    s = once(s,
        "void wireguardif_set_udp_output(struct netif *netif, wireguard_udp_output_fn fn, void *ctx);",
        """void wireguardif_set_udp_output(struct netif *netif, wireguard_udp_output_fn fn, void *ctx);
/* Optional synchronous zero-extra-copy direct UDP output for owned WG pbufs. */
void wireguardif_set_udp_pbuf_output(struct netif *netif, wireguard_udp_pbuf_output_fn fn, void *ctx);""")
    h.write_text(s)

    w = backend / "wireguardif.c"
    s = w.read_text()
    s = once(s,
        "\t\t// Linearize pbuf chain and send via callback",
        """        /* wgopt1: the encrypted output pbuf is already contiguous and
         * allocated with PBUF_TRANSPORT headroom. Reuse it for raw UDP
         * rather than copying to TWO separate PSRAM scratch buffers.
         * The callback borrows it only through synchronous udp_sendto;
         * the parent still owns/frees pbuf after this call returns.
         * For chained pbufs, use the unchanged byte-copy fallback. */
        if (device->udp_pbuf_output_fn && q &&
            q->len == q->tot_len) {
            uint32_t dest_ip = ip4_addr_get_u32(ip_2_ip4(&peer->ip));
            result = device->udp_pbuf_output_fn(dest_ip, peer->port, q,
                                                device->udp_pbuf_output_ctx);
            goto done;
        }

\t\t// Linearize pbuf chain and send via callback""")
    setter = """void wireguardif_set_udp_pbuf_output(struct netif *netif, wireguard_udp_pbuf_output_fn fn, void *ctx) {
    LWIP_ASSERT("netif != NULL", (netif != NULL));
    LWIP_ASSERT("state != NULL", (netif->state != NULL));
    struct wireguard_device *device = (struct wireguard_device *)netif->state;
    if (device->valid) {
        device->udp_pbuf_output_fn = fn;
        device->udp_pbuf_output_ctx = ctx;
    }
}

"""
    s = once(s,
        "void wireguardif_force_derp_output(struct netif *netif, bool force) {",
        setter + "void wireguardif_force_derp_output(struct netif *netif, bool force) {")
    w.write_text(s)

    mgr = component / "src/ml_wg_mgr.c"
    s = mgr.read_text()
    begin = '    /* tailscale "send both" (wgengine/magicsock/endpoint.go send):'
    end = '\n    return err;\n}\n\n/* ============================================================================'
    if s.count(begin) != 1 or s.count(end) < 1:
        raise RuntimeError("wgopt1 handshake send-both source changed")
    start = s.index(begin)
    finish = s.index(end, start)
    body = s[start:finish]
    for required in ("data[0] == 0x01", "data[0] == 0x02",
                     "data[0] == 0x03", "ml_derp_queue_send(ml, pr->public_key, data, len)"):
        if required not in body:
            raise RuntimeError("wgopt1 send-both protocol guard missing: " + required)
    s = once(s, body, "    wgopt1_send_both(ml, dest_ip, data, len);\n")
    fn = """/* Shared by the borrowed-pbuf direct path and legacy byte callback.
 * Retains the original handshake send-both semantics and endpoint lookup. */
static void wgopt1_send_both(microlink_t *ml, uint32_t dest_ip,
                             const uint8_t *data, size_t len) {
""" + body + """
}

/* Synchronous direct UDP transport: borrow the original encrypted
 * PBUF_RAM allocated by wireguardif_output_to_peer(PBUF_TRANSPORT).
 * udp_sendto may temporarily adjust the pbuf header but restores it
 * before return; keep the payload pointer/length from before the call
 * for the optional handshake DERP duplicate. Do not take ownership. */
static err_t wgopt1_udp_pbuf_output_cb(uint32_t dest_ip, uint16_t dest_port,
                                       struct pbuf *p, void *ctx) {
    microlink_t *ml = (microlink_t *)ctx;
    if (!ml || !s_wg_output_pcb) return ERR_CONN;
    if (!p || !p->payload || p->len != p->tot_len) return ERR_VAL;
    const uint8_t *packet_data = (const uint8_t *)p->payload;
    size_t packet_len = p->tot_len;

    ip_addr_t dst;
    IP_SET_TYPE_VAL(dst, IPADDR_TYPE_V4);
    ip4_addr_set_u32(ip_2_ip4(&dst), dest_ip);
    err_t err = udp_sendto(s_wg_output_pcb, p, &dst, dest_port);
    /* Type 4 bulk data never goes to DERP duplicate; exact same helper
     * as legacy direct callback handles type 1..3 handshake messages. */
    wgopt1_send_both(ml, dest_ip, packet_data, packet_len);
    return err;
}

"""
    s = once(s, "static err_t wg_udp_output_cb(", fn + "static err_t wg_udp_output_cb(")
    s = once(s,
        "    wireguardif_set_udp_output(netif, wg_udp_output_cb, ml);",
        """    wireguardif_set_udp_output(netif, wg_udp_output_cb, ml);
    wireguardif_set_udp_pbuf_output(netif, wgopt1_udp_pbuf_output_cb, ml);
    ESP_LOGI(TAG, "WGOPT1: direct UDP uses borrowed encrypted PBUF_RAM (fallback and DERP retained)");""")
    mgr.write_text(s)
