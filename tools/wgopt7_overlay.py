"""wgopt7: 64->128 slots and passive memory probes, in generated microlink only.

No packet ownership, crypto, route, DERP or scheduler changes.
"""
import re
from derp_header_overlay import once

def apply(component):
    header = component / "include/microlink_internal.h"
    s = header.read_text()
    s = once(s, "#define ML_WG_RX_QUEUE_DEPTH    64",
             "/* wgopt7: double queue slots to 128; ciphertext PSRAM-first. */\n#define ML_WG_RX_QUEUE_DEPTH    128")
    header.write_text(s)

    init = component / "src/microlink.c"
    s = init.read_text()
    s = '#include "wg_diag.h"\n' + s
    s = once(s, "    ml->wg_rx_queue = xQueueCreate(ML_WG_RX_QUEUE_DEPTH, sizeof(ml_rx_packet_t));",
             "    ml->wg_rx_queue = xQueueCreate(ML_WG_RX_QUEUE_DEPTH, sizeof(ml_rx_packet_t));\n"
             "    wg_diag_queue_config(ML_WG_RX_QUEUE_DEPTH, sizeof(ml_rx_packet_t));")
    init.write_text(s)

    netio = component / "src/ml_net_io.c"
    s = netio.read_text()
    helper = """/* Observational equivalent of ml_psram_malloc for direct UDP RX.
 * Both allocate via PSRAM-first then malloc fallback; caller owns free(). */
static void *wg7_direct_rx_alloc(size_t size) {
    void *ptr = heap_caps_malloc(size, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
    if (ptr) { wg_diag_rx_alloc(0); return ptr; }
    ptr = malloc(size);
    wg_diag_rx_alloc(ptr ? 1 : 2);
    return ptr;
}

"""
    s = once(s, 'static const char *TAG = "ml_net_io";\n',
             'static const char *TAG = "ml_net_io";\n\n' + helper)
    s, count = re.subn(r'D_ALLOC\((\d+), ml_psram_malloc\(n\)\)',
                       r'D_ALLOC(\1, wg7_direct_rx_alloc(n))', s)
    if count != 1:
        raise RuntimeError(f"wgopt7 UDP RX allocation anchor count={count}")
    netio.write_text(s)
