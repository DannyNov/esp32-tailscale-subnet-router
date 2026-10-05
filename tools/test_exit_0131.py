"""Production exit-mode and DNS parsing host regressions; no ESP required."""
from pathlib import Path
import argparse
import re
import shlex
import subprocess

root = Path(__file__).resolve().parents[1]
p = argparse.ArgumentParser()
p.add_argument('--cc', default='cc')
a = p.parse_args()
manager = (root / 'main/tailscale_manager.c').read_text()
dns = (root / 'main/peer_dns.c').read_text()

def extract(source, name):
    m = re.search(r'^(?:static )?(?:bool|int|size_t) ' + name + r'\([^;]*?\)\s*\{', source, re.M)
    assert m, name
    end = m.end()
    depth = 1
    while depth:
        if source[end] == '{': depth += 1
        if source[end] == '}': depth -= 1
        end += 1
    return source[m.start():end]

source = '''#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include <assert.h>
#include <stdio.h>
#define PEER_DNS_MAX_MESSAGE 4096
#define PEER_DNS_MAX_B64 (((PEER_DNS_MAX_MESSAGE + 2U) / 3U) * 4U)
int tailscale_enabled, tailscale_advertise_exit_node;
uint32_t tailscale_exit_node_ip;
'''
source += '\n'.join(extract(manager, n) for n in ['tailscale_exit_server_active', 'routes_append_unique'])
source += '\n' + '\n'.join(extract(dns, n) for n in ['dns_query_valid', 'base64url_value', 'decode_base64url'])
source += r'''
int main(void) {
 assert(!tailscale_exit_server_active());
 tailscale_enabled=1; assert(!tailscale_exit_server_active());
 tailscale_advertise_exit_node=1; assert(tailscale_exit_server_active());
 tailscale_exit_node_ip=1;assert(!tailscale_exit_server_active());
 tailscale_exit_node_ip=0;tailscale_enabled=0;assert(!tailscale_exit_server_active());
 char routes[80]="10.71.0.0/24";
 size_t n=strlen(routes);n=routes_append_unique(routes,sizeof(routes),n,"0.0.0.0/0");
 n=routes_append_unique(routes,sizeof(routes),n,"::/0");
 assert(!strcmp(routes,"10.71.0.0/24\n0.0.0.0/0\n::/0"));
 assert(routes_append_unique(routes,sizeof(routes),n,"0.0.0.0/0")==n);
 char small[4]="abc";assert(routes_append_unique(small,sizeof(small),3,"::/0")==3);
 assert(!strcmp(small,"abc"));
 uint8_t query[4097]={0};assert(dns_query_valid(query,12));
 assert(dns_query_valid(query,4096));assert(!dns_query_valid(query,4097));
 assert(!dns_query_valid(query,11));assert(!dns_query_valid(NULL,12));
 query[2]=0x80;assert(!dns_query_valid(query,12));
 uint8_t out[8];size_t len=0;
 assert(decode_base64url("AA",2,out,sizeof(out),&len)&&len==1&&out[0]==0);
 assert(decode_base64url("_-4",3,out,sizeof(out),&len)&&len==2&&out[0]==255&&out[1]==238);
 assert(!decode_base64url("AB",2,out,sizeof(out),&len));
 assert(!decode_base64url("AA=",3,out,sizeof(out),&len));
 assert(!decode_base64url("A",1,out,sizeof(out),&len));
 assert(!decode_base64url("AA",2,out,0,&len));
 puts("PASS: production exit-mode exclusion/defaults, AP/default route dedup/bounds, DNS query/base64url validation");
}
'''
build = root / 'tests/host/build'
build.mkdir(exist_ok=True)
path = build / 'exit_0131.c'
path.write_text(source)
exe = build / 'exit_0131.exe'
subprocess.run(shlex.split(a.cc) + ['-std=c11', '-Wall', '-Wextra', '-Werror', str(path), '-o', str(exe)], check=True)
subprocess.run([str(exe)], check=True)
lease = dns.split('static bool peer_request_allowed(httpd_req_t *req)', 1)[1].split('static bool dns_query_valid', 1)[0]
assert lease.index('tailscale_lifecycle_try_acquire()') < lease.index('peer_request_allowed_locked(req)') < lease.index('tailscale_lifecycle_release()')
assert 'local_ip != own_ip' in dns and 'peer.vpn_ip == remote_ip' in dns
assert 'if (server || !tailscale_exit_server_active()) return;' in dns
web = (root / 'main/web_ui.c').read_text()
save = web.split('static esp_err_t tailscale_save_handler', 1)[1]
assert save.index('if (adv && exit_hbo)') < save.index('nvs_save_int(')
assert 'peer_dns' in (root / 'main/CMakeLists.txt').read_text()
ml = (root / 'external/microlink/components/microlink/src/ml_net_io.c').read_text()
assert 'uint8_t *pkt_data = ml_psram_malloc(n);' in ml
print('PASS: DNS lifecycle lease/access gates, no conflicting save writes, PSRAM queue source contracts; device load/reconnect pending')
