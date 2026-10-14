"""wgopt6 — controlled 32 -> 64 WG RX queue capacity only.

Apply solely to a copied pinned microlink component after wgopt5.
No changes to packet processing order, FreeRTOS task priorities,
2/10 ms adaptive sleep, crypto, DERP or buffer ownership.
"""
from derp_header_overlay import once

def apply(component):
    header = component / "include/microlink_internal.h"
    src = header.read_text()
    src = once(src, "#define ML_WG_RX_QUEUE_DEPTH    32", """/* wgopt6: double the FIFO metadata slots to absorb measured ~29-packet
 * direct-RX overflow bursts without changing consume cadence or ownership.
 * Packet payloads are still allocated upstream by ml_psram_malloc().
 * Bounded size: 64 slots * sizeof(ml_rx_packet_t) (64 B on ESP32-S3),
 * i.e. +2048 B for queue metadata versus wgopt5, plus FreeRTOS overhead.
 * Extra in-flight ciphertext is PSRAM-first (fallback to malloc if full).
 * This is a candidate to A/B with wgopt5, NOT a proven TCP-speed fix. */
#define ML_WG_RX_QUEUE_DEPTH    64""")
    header.write_text(src)
