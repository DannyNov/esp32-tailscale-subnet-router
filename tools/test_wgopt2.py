"""wgopt2: generated-copy contracts plus executable exact fast-path ownership test.

This test compiles the actual borrowed-ingress decision block extracted from
the instrumented production source against small host mocks. This verifies
control/malformed fallback and ownership on the direct and DERP data paths.
"""
from pathlib import Path
from tempfile import TemporaryDirectory
from prepare_wg_diagnostics import prepare
import os
import subprocess
import shutil

with TemporaryDirectory(prefix="wgopt2-") as temp:
    root = Path(temp)
    prepare(root)
    component = root / "microlink"
    mgr = (component / "src/ml_wg_mgr.c").read_text()
    wgif = (component / "components/wireguard_lwip/src/wireguardif.c").read_text()
    hdr = (component / "components/wireguard_lwip/src/wireguardif.h").read_text()

    handler_start = wgif.index("void wireguardif_network_rx_borrowed(")
    wrapper_start = wgif.index("void wireguardif_network_rx(", handler_start)
    handler = wgif[handler_start:wrapper_start]
    wrapper = wgif[wrapper_start:wgif.index("static err_t wireguard_start_handshake", wrapper_start)]
    assert "pbuf_alloc(" not in handler and "pbuf_free(" not in handler
    assert "wireguardif_process_data_message(" in handler
    assert "wireguardif_network_rx_borrowed(arg, (uint8_t *)p->payload, p->len, addr, port);" in wrapper
    assert wrapper.count("pbuf_free(p);") == 1
    assert "void wireguardif_network_rx_borrowed" in hdr
    assert "pbuf = D_ALLOC(" in wgif and "PBUF_TRANSPORT, src_len - WIREGUARD_AUTHTAG_LEN, PBUF_RAM" in wgif
    assert "device->netif->input(pbuf, device->netif)" in wgif

    start = mgr.index("    /* wgopt2: only complete canonical WG transport data uses borrowed")
    end = mgr.index("    /* Allocate PBUF_RAM and copy data so the pbuf OWNS its data.", start)
    fast = mgr[start:end]
    assert mgr.index("    if (!ml->wg_netif)") < start < mgr.index("    struct pbuf *p = D_ALLOC", start)
    assert "wireguardif_network_rx_borrowed(device, pkt->data, pkt->len," in fast
    assert "pkt->len >= 32" in fast and "pkt->len <= UINT16_MAX" in fast
    assert "pkt->data[0] == 4" in fast and "pkt->data[3] == 0" in fast
    assert "free(pkt->data);" in fast and "return;" in fast

    c_source = r"""
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifdef _WIN32
#include <winsock2.h>
#else
#include <arpa/inet.h>
#endif
typedef struct { int t; uint32_t u_addr; } ip_addr_t;
#define IPADDR_TYPE_V4 4
#define IP_SET_TYPE_VAL(addr, type) ((addr).t = (type))
#define ip_addr_set_any(ipv6, addr) do { (addr)->t=0; (addr)->u_addr=0; } while (0)
#define ip_2_ip4(addr) (&(addr)->u_addr)
#define ip4_addr_set_u32(ptr,v) (*(ptr)=(v))
typedef struct {
    uint8_t *data;
    size_t len;
    uint32_t src_ip;
    uint16_t src_port;
    int via_derp;
} packet_t;
static int borrow_count=0, frees=0, fallback=0, derp_seen=-1;
static void *seen_device;
static uint8_t *seen_buffer;
static size_t seen_len;
static uint16_t seen_port;
static void tracked_free(void *p) { frees++; free(p); }
#define free tracked_free
static void wireguardif_network_rx_borrowed(void *device, uint8_t *data,
        size_t len, const ip_addr_t *addr, uint16_t port) {
    borrow_count++;
    seen_device=device; seen_buffer=data; seen_len=len; seen_port=port;
    derp_seen=addr->t;
    assert(data[0] == 4);
}
static void tested(const packet_t *pkt, void *device) {
""" + fast + r"""
    fallback++;
}
static void check_data(int derp) {
    packet_t pkt={0};
    pkt.data=malloc(64); pkt.len=64; pkt.src_ip=0xc0a80001;
    pkt.src_port=51820; pkt.via_derp=derp;
    memset(pkt.data,0,64);pkt.data[0]=4;
    uint8_t *ptr=pkt.data;int initial_free=frees;
    tested(&pkt,(void *)0x1234);
    assert(borrow_count==1 && fallback==0 && frees==initial_free+1);
    assert(seen_device==(void *)0x1234 && seen_buffer==ptr);
    assert(seen_len==64 && seen_port==51820);
    assert(derp_seen==(derp?0:4));
}
static void check_fallback(uint8_t type,size_t len,int reserved) {
    packet_t pkt={0};
    pkt.data=malloc(len); pkt.len=len; memset(pkt.data,0,len);
    pkt.data[0]=type;pkt.data[1]=reserved;
    int b=borrow_count,f=frees;
    tested(&pkt,(void*)0x1234);
    assert(borrow_count==b && fallback>0 && frees==f);
    tracked_free(pkt.data);
}
int main(void) {
    check_data(0);borrow_count=0;fallback=0;
    check_data(1);borrow_count=0;fallback=0;
    check_fallback(1,64,0);check_fallback(2,64,0);
    check_fallback(3,64,0);check_fallback(4,16,0);
    check_fallback(4,64,1);check_fallback(0,64,0);
    puts("PASS: exact wgopt2 fast path borrowed ownership, DERP/direct endpoint and malformed/control fallback");
    return 0;
}
"""
    source = root / "wgopt2_host.c"
    exe = root / ("wgopt2_host.exe" if os.name == "nt" else "wgopt2_host")
    source.write_text(c_source)
    cc = shutil.which("cc")
    assert cc, "Host C compiler is required for wgopt2 acceptance tests"
    subprocess.run([cc,"-std=c11","-Wall","-Wextra","-Werror",str(source),"-o",str(exe)]+(['-lws2_32'] if os.name=='nt' else []),check=True)
    subprocess.run([str(exe)],check=True)

print("PASS: wgopt2 generated-copy and ingress/forwarding ownership contracts")
