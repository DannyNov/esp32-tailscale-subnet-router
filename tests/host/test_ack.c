/* Production ACK sender with deterministic UDP, pbuf and persistence adapters. */
#include <assert.h>
#include <stdint.h>
#include <stdbool.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
typedef uint8_t u8_t;typedef uint16_t u16_t;typedef int err_t;
#define ERR_OK 0
#define DHCPACK 5
#define DHCPS_CLIENT_PORT 68
#define IPADDR4_INIT(x) {x}
#define LWIP_HOOK_DHCPS_POST_APPEND_OPTS(a,b,c,d)
typedef struct { uint32_t addr; } ip_addr_t;
#define ip_2_ip4(x) (x)
struct dhcps_msg { uint8_t options[312],yiaddr[4],chaddr[16]; };
struct pbuf { void *payload;uint16_t len,tot_len,ref;struct pbuf *next; };
struct dhcps_pool { bool acknowledged; uint8_t mac[6]; };
typedef struct list_node { struct dhcps_pool *pnode; struct list_node *pnext; } list_node;
typedef struct { ip_addr_t client_address; void *dhcps_pcb; list_node *plist; void (*dhcps_cb)(void*,void*,void*);void *dhcps_cb_arg; } dhcps_t;
static bool durable,fail_store,fail_alloc,fail_udp;
static unsigned sends,notices;
static bool prepare(const uint8_t mac[6],uint32_t ip) { (void)mac;(void)ip;if(fail_store)return false;durable=true;return true; }
static bool (*s_prepare_ack)(const uint8_t[6],uint32_t)=prepare;
static void create_msg(dhcps_t *d,struct dhcps_msg *m) { memcpy(m->yiaddr,&d->client_address.addr,4); }
static uint8_t *add_msg_type(uint8_t *p,int type) { (void)type;return p; }
static uint8_t *add_offer_options(dhcps_t *d,uint8_t *p) { (void)d;return p; }
static uint8_t *add_end(uint8_t *p) { return p; }
static struct pbuf *dhcps_pbuf_alloc(uint16_t len) { if(fail_alloc)return NULL;struct pbuf *p=calloc(1,sizeof(*p));p->payload=calloc(1,len);p->len=p->tot_len=len;p->ref=1;return p; }
static void pbuf_free(struct pbuf *p) { free(p->payload);free(p); }
static void dhcps_response_ip_set(dhcps_t *d,struct dhcps_msg *m,ip_addr_t *a) { (void)d;(void)m;(void)a; }
static int udp_sendto(void *pcb,struct pbuf *p,ip_addr_t *ip,int port) { (void)pcb;(void)p;(void)ip;assert(port==68);assert(durable);++sends;return fail_udp?-1:0; }
static void notice(void *arg,void *ip,void *mac) { (void)arg;(void)ip;(void)mac;++notices; }
#include "ack_under_test.inc"
int main(void) {
    struct dhcps_pool lease={.mac={2,0,0,0,0,1}};list_node node={.pnode=&lease};
    dhcps_t d={.client_address={4},.plist=&node,.dhcps_cb=notice};struct dhcps_msg m={0};memcpy(m.chaddr,lease.mac,6);
    fail_store=true;send_ack(&d,&m,sizeof m);assert(!sends&&!lease.acknowledged&&!notices);
    fail_store=false;fail_alloc=true;send_ack(&d,&m,sizeof m);assert(durable&&!sends&&!lease.acknowledged);
    fail_alloc=false;fail_udp=true;send_ack(&d,&m,sizeof m);assert(sends==1&&!lease.acknowledged&&!notices);
    fail_udp=false;send_ack(&d,&m,sizeof m);assert(sends==2&&lease.acknowledged&&notices==1);
    puts("PASS: production ACK sender persists before UDP, rejects storage/allocation/send failures");return 0;
}
