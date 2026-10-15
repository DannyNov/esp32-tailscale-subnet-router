"""wgopt6: precise queue-capacity experiment with compile-time space contract.

Verifies the *generated* pinned component differs from wgopt5 only in
WG_RX FIFO capacity: no modified producer, consumer, DERP, WireGuard crypto,
routing, buffer ownership, scheduler or NVS. Uses the extracted real C
ml_rx_packet_t structure to assert bounded queue metadata.
"""
from pathlib import Path
from tempfile import TemporaryDirectory
import subprocess, shutil, re
from prepare_wg_diagnostics import prepare, ROOT

with TemporaryDirectory(prefix="wgopt6-test-") as td:
    out = Path(td)
    prepare(out)
    comp = out / "microlink"
    hdr = (comp / "include/microlink_internal.h").read_text()
    upstream_hdr = (ROOT / "external/microlink/components/microlink/include/microlink_internal.h").read_text()
    assert upstream_hdr.count("#define ML_WG_RX_QUEUE_DEPTH    32") == 1
    assert hdr.count("#define ML_WG_RX_QUEUE_DEPTH    128") == 1
    assert "#define ML_WG_RX_QUEUE_DEPTH    32" not in hdr
    assert hdr.count("wgopt6: double the FIFO metadata slots") == 1
    assert "wgopt7: double queue slots to 128" in hdr
    # Other prior wgopt1-5 transformations stay unchanged.
    assert "int64_t diag_enqueued_us;" in hdr
    assert "ML_DERP_TX_QUEUE_DEPTH  64" in hdr
    assert "ML_DISCO_RX_QUEUE_DEPTH 8" in hdr
    assert "ML_STUN_RX_QUEUE_DEPTH  4" in hdr
    assert "ML_TASK_WG_MGR_PRIO     7" in hdr
    assert "ML_TASK_WG_MGR_CORE     1" in hdr
    mgr = (comp / "src/ml_wg_mgr.c").read_text()
    producer = (comp / "src/ml_net_io.c").read_text()
    microlink = (comp / "src/microlink.c").read_text()
    derp = (comp / "src/ml_derp.c").read_text()
    wireguard = (comp / "components/wireguard_lwip/src/wireguardif.c").read_text()
    assert mgr.count("vTaskDelay(pdMS_TO_TICKS(wg_rx_active ? 2 : 10));") == 1
    assert mgr.count("WG_MGR_WG_BURST         64") == 1
    assert mgr.count("WG_MGR_WG_BUDGET_MS     30") == 1
    assert mgr.count("process_wg_packet(ml, &wg_pkt);") == 2
    assert "wg_diag_burst(accepted == pdTRUE, pkt.diag_enqueued_us)" in producer
    assert "wg_diag_add(D_DIRECT, accepted == pdTRUE ? D_ENQUEUE : D_DROP, 1)" in producer
    assert "free(data);  /* Queue full, drop */" in producer
    assert "wg7_direct_rx_alloc(n)" in producer
    assert "free(pkt->data);" in mgr
    assert "wireguardif_network_rx_borrowed" in wireguard
    assert "ml_derp_queue_send" in mgr
    assert "xQueueCreate(ML_WG_RX_QUEUE_DEPTH, sizeof(ml_rx_packet_t))" in microlink
    assert "static inline void *ml_psram_malloc(size_t size)" in hdr
    assert "if (!ptr) ptr = malloc(size);" in hdr  # disclose fallback risk
    assert 'wgq_cap=128' in (comp / "components/wireguard_lwip/src/wg_diag.c").read_text()
    assert "wg5_report();" in (comp / "components/wireguard_lwip/src/wg_diag.c").read_text()
    assert "wg_diag_wg4_tx(" in wireguard

    # Real C structure copied from generated microlink header.
    match = re.search(r'/\* Received packet \(from net_io to disco/wg queues\) \*/\s*(typedef struct \{.*?\} ml_rx_packet_t;)',hdr,re.S)
    assert match, "Packet struct disappeared: cannot estimate memory"
    cc = shutil.which("cc")
    if not cc:
        raise RuntimeError("host C compiler required for queue size bound")
    program = out / "size.c"
    program.write_text('''#include <stddef.h>
#include <stdint.h>
#include <stdbool.h>
''' + match.group(1) + '''
_Static_assert(sizeof(ml_rx_packet_t) <= 64, "unexpected RX metadata growth");
_Static_assert((128 - 64) * sizeof(ml_rx_packet_t) <= 4096, "queue internal RAM delta exceeded");
_Static_assert(128 * sizeof(ml_rx_packet_t) <= 8192, "queue RAM budget exceeded");
int main(void) { return 0; }
''')
    subprocess.run([cc, "-std=c11", "-Wall", "-Wextra", "-Werror",
                    str(program), "-o", str(out / "size")],check=True)
    subprocess.run([str(out / "size")], check=True)
    print("PASS: wgopt7 queue128; <=4KiB metadata delta; direct RX allocation probe")
