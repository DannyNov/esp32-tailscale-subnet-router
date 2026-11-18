"""Execute exact generated v0.1.39 dispatch; validate upgrade invariants, no device IO."""
import os,re,shlex,subprocess,tempfile
from pathlib import Path
from prepare_wg_diagnostics import ROOT,prepare

def function(s,name):
    m=re.search(r'^static (?:err_t|void) '+name+r'\([^;]*?\)\s*\{',s,re.M)
    assert m,name
    i=m.end();depth=1
    while depth:
        depth+=(s[i]=='{')-(s[i]=='}');i+=1
    return s[m.start():i]
with tempfile.TemporaryDirectory(prefix='office-0139-') as tmp:
    out=Path(tmp);prepare(out);c=out/'microlink';mgr=(c/'src/ml_wg_mgr.c').read_text()
    wif=(c/'components/wireguard_lwip/src/wireguardif.c').read_text()
    coord=(c/'src/ml_coord.c').read_text();ml=(c/'src/microlink.c').read_text()
    assert 'esp_netif_tcpip_exec(wg_tcpip_exec_wrap, &c)' in mgr
    for step in ['wg_netif_init_cb','wg_netif_bring_up_cb','wg_udp_pcb_create_cb','wg_netif_take_down_cb']:
        assert 'wg_tcpip_sync('+step in mgr or 'wg_tcpip_sync('+step+', ' in mgr
    assert 'wg_stamp_age_ms(wp->last_rx_direct)' in mgr
    assert 'bool data_flowing = (direct_rx_age_ms < 30000);' in mgr
    assert 'if (trust_expired || kept_endpoint)' in mgr
    assert 'peer->last_rx_direct = wireguard_sys_now();' in wif
    assert '#define ML_COORD_PARTIAL_READ_MS 5000' in coord
    assert 'errno = ETIMEDOUT;' in coord
    assert 'ML_STATE_ERROR' in ml[ml.index('esp_err_t microlink_stop('):]
    # Office settings and identity persistence sources must remain byte-identical.
    for path in ['partitions.csv','sdkconfig.defaults','platformio.ini','main/nvs_params.c','main/nvs_params.h','main/tailscale_config.h','main/dhcp_bindings.c','main/dhcp_last_seen.inc','main/dhcp_reservations.c','main/index.html','components/dhcpserver/dhcpserver.c','main/wg10_wifi_tx.c']:
        p=ROOT/path
        assert p.is_file(), path
        old=subprocess.check_output(['git','show','ed510efa72da0925cbac3d15ab353175b00c96b2:'+path],cwd=ROOT)
        assert old.replace(b'\r\n',b'\n')==p.read_bytes().replace(b'\r\n',b'\n'),path
    prefix=r'''
#include <assert.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
typedef int err_t; typedef unsigned short u16_t;
typedef struct { unsigned addr; } ip_addr_t;
struct pbuf { void *payload; u16_t tot_len; int ref; };
struct udp_pcb { int unused; };
static struct udp_pcb pcb, *s_wg_output_pcb=&pcb;
static void *s_tcpip_task=(void*)1, *current=(void*)1;
static void *xTaskGetCurrentTaskHandle(void) { return current; }
#define ERR_OK 0
#define ERR_MEM (-1)
#define D_ALLOC(i,x) (x)
#define TAG "test"
#define ESP_LOGW(...) ((void)0)
static int alloc_fail, post_fail, sends, freed, live;
static void (*posted_fn)(void*); static void *posted_arg;
static struct pbuf *ml_spiram_pbuf_new(u16_t n) {
 if(alloc_fail) return NULL;
 struct pbuf *p=calloc(1,sizeof(*p));assert(p);p->payload=malloc(n);assert(p->payload);
 p->tot_len=n;p->ref=1;live++;return p;
}
static void pbuf_free(struct pbuf *p) { assert(p->ref==1);free(p->payload);free(p);live--;freed++; }
static void pbuf_copy_partial(struct pbuf *p,void *dst,u16_t n,int off) {memcpy(dst,(char*)p->payload+off,n);}
static unsigned char sent[8];
static err_t udp_sendto(struct udp_pcb *p,struct pbuf *b,const ip_addr_t *d,u16_t port) {
 assert(current==s_tcpip_task);assert(p==&pcb&&d->addr==42&&port==123);assert(b->ref==1);
 assert(b->tot_len==8);memcpy(sent,b->payload,8);sends++;return ERR_OK;
}
static err_t tcpip_callback(void (*fn)(void*),void *arg) {
 if(post_fail)return ERR_MEM;assert(!posted_fn);posted_fn=fn;posted_arg=arg;return ERR_OK;
}
struct wg_udp_send_msg {struct pbuf *p;ip_addr_t dst;u16_t port;};
'''
    suffix=r'''
static void drain(void) {void (*f)(void*)=posted_fn;void *a=posted_arg;posted_fn=NULL;current=s_tcpip_task;f(a);}
int main(void) {
 ip_addr_t dst={42};struct pbuf *p=ml_spiram_pbuf_new(8);memset(p->payload,7,8);
 assert(wg_udp_sendto_tcpip(p,&dst,123)==ERR_OK&&sends==1&&p->ref==1);pbuf_free(p);
 current=(void*)2;p=ml_spiram_pbuf_new(8);memset(p->payload,9,8);
 assert(wg_udp_sendto_tcpip(p,&dst,123)==ERR_OK&&sends==1&&posted_fn);
 assert(((struct wg_udp_send_msg*)posted_arg)->p!=p);
 memset(p->payload,0,8);pbuf_free(p);drain();assert(sends==2&&sent[0]==9&&live==0);
 current=(void*)2;p=ml_spiram_pbuf_new(8);alloc_fail=1;
 assert(wg_udp_sendto_tcpip(p,&dst,123)==ERR_MEM&&!posted_fn&&live==1);alloc_fail=0;
 post_fail=1;assert(wg_udp_sendto_tcpip(p,&dst,123)==ERR_MEM&&!posted_fn&&live==1);post_fail=0;
 assert(p->ref==1);pbuf_free(p);assert(live==0);
 current=(void*)2;p=ml_spiram_pbuf_new(8);assert(wg_udp_sendto_tcpip(p,&dst,123)==ERR_OK);
 pbuf_free(p);s_wg_output_pcb=NULL;drain();assert(sends==2&&live==0);
 puts("PASS: TCPIP direct send, private async copy, caller-release race, OOM/post failure, detached PCB cleanup");
 return 0;
}
'''
    source=out/'dispatch.c';source.write_text(prefix+function(mgr,'wg_udp_send_on_tcpip_cb')+'\n'+function(mgr,'wg_udp_sendto_tcpip')+suffix)
    exe=out/('dispatch.exe' if os.name=='nt' else 'dispatch')
    subprocess.run(shlex.split(os.environ.get('CC','cc'))+['-std=c11','-Wall','-Wextra','-Werror','-Wno-misleading-indentation',str(source),'-o',str(exe)],check=True)
    subprocess.run([str(exe)],check=True)
print('PASS: v0.1.36-39 source guards and unchanged office configuration/storage/identity inputs')
