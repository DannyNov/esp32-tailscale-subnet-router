"""Execute production CGNAT exception with host netif/DNS/DHCP stubs.

Lifecycle checks below are source contracts, not concurrency or heap tests.
"""
from pathlib import Path
import argparse
import shlex
import subprocess

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--cc', default='cc')
args = parser.parse_args()
route = (root / 'main/lwip_route_hook.c').read_text(encoding='utf-8')
function = route.split('static struct netif *cgnat_local_exception', 1)[1].split('\nstatic struct netif *s_original_default', 1)[0]
harness = r'''
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <assert.h>
#include <stdio.h>
typedef unsigned char u8_t;
typedef struct { uint32_t addr; } ip4_addr_t;
typedef ip4_addr_t ip_addr_t;
struct dhcp { ip_addr_t server_ip_addr; };
struct netif { struct netif *next; bool wg, up, link; ip4_addr_t addr, mask; struct dhcp dhcp; };
struct netif *netif_list, *uplink, *wg;
static ip_addr_t dns[2];
static uint32_t peer;
#define DNS_MAX_SERVERS 2
#define lwip_htonl(x) __builtin_bswap32(x)
#define netif_is_wg(n) ((n)->wg)
#define netif_is_up(n) ((n)->up)
#define netif_is_link_up(n) ((n)->link)
#define netif_ip4_addr(n) (&(n)->addr)
#define netif_ip4_netmask(n) (&(n)->mask)
#define ip4_addr_isany_val(x) (!(x).addr)
#define ip_addr_isany_val(x) (!(x).addr)
#define ip_addr_isany(x) (!(x)->addr)
#define ip4_addr_netcmp(d,a,m) (((d)->addr & (m)->addr)==((a)->addr & (m)->addr))
#define IP_IS_V4(x) true
#define ip_2_ip4(x) (x)
#define ip4_addr_get_u32(x) ((x)->addr)
#define netif_dhcp_data(n) (&(n)->dhcp)
static struct netif *find_sta_netif(void) { return uplink; }
static struct netif *find_wg_netif(void) { return wg; }
static bool microlink_wg_has_peer_ip(struct netif *n, uint32_t ip) { return n && peer && ip==peer; }
static const ip_addr_t *dns_getserver(u8_t i) { return &dns[i]; }
'''
harness += 'static struct netif *cgnat_local_exception' + function
harness += r'''
int main(void) {
 struct netif tunnel={.wg=true,.up=true,.link=true}, sta={.up=true,.link=true}, ap={.up=true,.link=true};
 tunnel.next=&sta; sta.next=&ap; netif_list=&tunnel; wg=&tunnel; uplink=&sta;
 sta.addr.addr=lwip_htonl(0x64400102);sta.mask.addr=lwip_htonl(0xffc00000);
 assert(cgnat_local_exception(0x64400405,NULL)==&sta);
 peer=lwip_htonl(0x64400405);
 assert(cgnat_local_exception(0x64400405,NULL)==NULL); /* peer /32 wins over /10 */
 dns[0].addr=peer;sta.dhcp.server_ip_addr.addr=peer;
 assert(cgnat_local_exception(0x64400405,NULL)==NULL); /* peer beats resolver/server */
 peer=0;sta.mask.addr=lwip_htonl(0xffffff00);
 assert(cgnat_local_exception(0x64400405,NULL)==&sta); /* off-link DNS */
 dns[0].addr=0;
 assert(cgnat_local_exception(0x64400405,NULL)==&sta); /* off-link DHCP */
 sta.dhcp.server_ip_addr.addr=0;
 assert(cgnat_local_exception(0x64400405,NULL)==NULL); /* other CGNAT uses tunnel */
 ap.addr.addr=lwip_htonl(0x64400401);ap.mask.addr=lwip_htonl(0xffffff00);
 assert(cgnat_local_exception(0x64400405,NULL)==&ap); /* AP on-link */
 ap.link=false;assert(cgnat_local_exception(0x64400405,NULL)==NULL);
 ap.link=true;ap.up=false;assert(cgnat_local_exception(0x64400405,NULL)==NULL);
 puts("PASS: production CGNAT on-link/DNS/DHCP/AP exceptions, peer priority, down-interface exclusion");
}
'''
build = root / 'tests/host/build'
build.mkdir(exist_ok=True)
source = build / 'routes_0130.c'
source.write_text(harness, encoding='utf-8')
exe = build / 'routes_0130.exe'
subprocess.run(shlex.split(args.cc) + ['-std=c11', '-Wall', '-Wextra', '-Werror', str(source), '-o', str(exe)], check=True, cwd=root)
subprocess.run([str(exe)], check=True)
supervisor = route.split('static void route_supervisor_task', 1)[1].split('/* ----', 1)[0]
assert supervisor.index('tailscale_lifecycle_try_acquire()') < supervisor.index('tailscale_get_microlink()')
assert 'tcpip_callback_wait(supervisor_netifs_cb' in supervisor
assert 'tcpip_callback_wait(publish_routes_cb' in supervisor
assert 'pin_wg_output_sync(ml' in supervisor
assert supervisor.index('tcpip_callback_wait(publish_routes_cb') < supervisor.rindex('tailscale_lifecycle_release()')
netcheck = (root / 'external/microlink/components/microlink/src/ml_netcheck.c').read_text()
assert netcheck.count('netcheck_stop_requested(ml)') >= 4
assert 'if (remain > 250000ULL) remain = 250000ULL;' in netcheck
ml = (root / 'external/microlink/components/microlink/src/microlink.c').read_text()
assert 'ml->stop_incomplete = false;' in ml.split('All tasks exited', 1)[1]
print('PASS: supervisor lease/callback and netcheck cancellation source contracts; hardware concurrency/heap pending')
