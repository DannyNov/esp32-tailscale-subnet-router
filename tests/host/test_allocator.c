/* This adapter supplies only platform types/I/O. Production functions are
 * extracted verbatim by run_host_tests.py, not reimplemented in this test. */
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#include "dhcp_bindings.h"
#include "dhcps_ext.h"
typedef uint8_t u8_t;typedef uint16_t u16_t;typedef uint32_t u32_t;typedef int16_t s16_t;
typedef struct { uint32_t addr; } ip4_addr_t;
static uint32_t swap32(uint32_t x) { return (x<<24)|((x&0xff00)<<8)|((x>>8)&0xff00)|(x>>24); }
#define htonl swap32
#define ntohl swap32
#define IP(n) htonl(0x0a470000u+(n))
#define DHCPS_COARSE_TIMER_SECS 1
#define DHCPS_LEASE_UNIT 60
#define DHCPS_MAX_HOSTNAME_LEN 32
#define DHCPS_STATE_IDLE 0
#define DHCPS_STATE_OFFER 1
#define DHCPS_STATE_DECLINE 2
#define DHCPS_STATE_ACK 3
#define DHCPS_STATE_NAK 4
#define DHCPS_STATE_RELEASE 5
#define DHCPDISCOVER 1
#define DHCPREQUEST 3
#define DHCPDECLINE 4
#define DHCPRELEASE 7
#define DHCP_OPTION_PAD 0
#define DHCP_OPTION_END 255
#define DHCP_OPTION_MSG_TYPE 53
#define DHCP_OPTION_HOSTNAME 12
#define DHCP_OPTION_REQ_IPADDR 50
#define mem_calloc calloc
struct dhcps_state { int state; };
struct dhcps_msg { uint8_t options[312], chaddr[16], ciaddr[4]; };
struct dhcps_pool { bool acknowledged; ip4_addr_t ip;uint8_t mac[6];uint32_t lease_timer;char hostname[32]; };
typedef struct list_node { struct dhcps_pool *pnode;struct list_node *pnext; } list_node;
struct netif { ip4_addr_t ip, mask; };
#define netif_ip4_addr(n) (&(n)->ip)
#define netif_ip4_netmask(n) (&(n)->mask)
#define ip4_addr_ismulticast(a) ((ntohl((a)->addr)&0xf0000000)==0xe0000000)
#define ip4_addr_isbroadcast(a,n) (((a)->addr|((n)->mask.addr))==UINT32_MAX)
#define ip4_addr_net_eq(a,b,m) (((a)->addr & (m)->addr)==((b)->addr & (m)->addr))
typedef struct { list_node *plist;struct netif *dhcps_netif;uint32_t dhcps_lease_time;struct { ip4_addr_t start_ip,end_ip; } dhcps_poll;ip4_addr_t client_address;bool renew,has_declined_ip;uint32_t declined_ip;char current_hostname[32]; } dhcps_t;
static dhcps_t *g_dhcps_instance;
static uint32_t magic_cookie=0x63538263;
static dhcp_bindings_t owners;
static uint32_t lookup(const uint8_t mac[6]) { return binding_lookup(&owners,mac); }
static bool available(const uint8_t mac[6],uint32_t ip) { return !binding_owned_by_other(&owners,mac,ip); }
static dhcps_reservation_lookup_fn s_reservation_lookup=lookup;
static dhcps_address_policy_fn s_available=available;
static void node_insert_to_list(list_node **list,list_node *node) { node->pnext=*list;*list=node; }
static void node_remove_from_list(list_node **list,list_node *node) { while(*list&&*list!=node)list=&(*list)->pnext;if(*list)*list=node->pnext; }
#include "allocator_under_test.inc"
static const uint8_t a[6]={0xa0,0x92,8,0x51,0xdc,0xd6},b[6]={2,0,0,0,0,2},c[6]={2,0,0,0,0,3};
static void clear_leases(dhcps_t *s) { while(s->plist) { list_node *p=s->plist;s->plist=p->pnext;free(p->pnode);free(p); } }
static int packet(dhcps_t *s,const uint8_t mac[6],int type,uint32_t req,uint32_t ciaddr) {
    struct dhcps_msg m={0};memcpy(m.chaddr,mac,6);memcpy(m.ciaddr,&ciaddr,4);memcpy(m.options,&magic_cookie,4);
    int i=4;m.options[i++]=53;m.options[i++]=1;m.options[i++]=(uint8_t)type;
    if(req) { m.options[i++]=50;m.options[i++]=4;memcpy(m.options+i,&req,4);i+=4; }
    m.options[i++]=255;return parse_msg(s,&m,i-4);
}
int main(void) {
    struct netif ap={.ip={IP(1)},.mask={htonl(0xffffff00)}};
    dhcps_t s={.dhcps_netif=&ap,.dhcps_lease_time=120,.dhcps_poll={{IP(2)},{IP(10)}}};g_dhcps_instance=&s;
    assert(packet(&s,a,DHCPDISCOVER,0,0)==DHCPS_STATE_OFFER);assert(s.client_address.addr==IP(2));
    assert(packet(&s,a,DHCPREQUEST,IP(2),0)==DHCPS_STATE_ACK);
    clear_leases(&s);memset(&owners,0,sizeof owners);
    dhcp_reservation_t r={.ip=IP(2),.valid=1};memcpy(r.mac,a,6);assert(binding_replace_manual(&owners,&r,1));
    assert(packet(&s,b,DHCPDISCOVER,0,0)==DHCPS_STATE_OFFER);assert(s.client_address.addr==IP(3));
    assert(packet(&s,a,DHCPDISCOVER,0,0)==DHCPS_STATE_OFFER);assert(s.client_address.addr==IP(2));
    clear_leases(&s);memset(&owners,0,sizeof owners);assert(binding_remember(&owners,a,IP(4)));
    /* After reboot empty leases: known renewal without Option 50 is ACKed. */
    assert(packet(&s,a,DHCPREQUEST,0,IP(4))==DHCPS_STATE_ACK);assert(s.client_address.addr==IP(4));
    assert(packet(&s,b,DHCPREQUEST,IP(4),0)==DHCPS_STATE_NAK);
    assert(packet(&s,a,DHCPREQUEST,0,IP(3))==DHCPS_STATE_NAK);
    /* Existing RAM lease may not bypass a reservation belonging to another MAC. */
    clear_leases(&s);memset(&owners,0,sizeof owners);
    assert(packet(&s,b,DHCPDISCOVER,0,0)==DHCPS_STATE_OFFER);
    assert(binding_replace_manual(&owners,&r,1));
    assert(packet(&s,b,DHCPREQUEST,IP(2),0)==DHCPS_STATE_NAK);
    assert(packet(&s,c,DHCPDISCOVER,0,0)==DHCPS_STATE_OFFER);assert(s.client_address.addr==IP(3));
    /* Valid reservation outside the dynamic range is supported; network/gateway aren't. */
    clear_leases(&s);memset(&owners,0,sizeof owners);r.ip=IP(50);assert(binding_replace_manual(&owners,&r,1));
    assert(packet(&s,a,DHCPDISCOVER,0,0)==DHCPS_STATE_OFFER);assert(s.client_address.addr==IP(50));
    assert(!dhcps_address_valid(IP(0)));assert(!dhcps_address_valid(IP(1)));assert(!dhcps_address_valid(IP(255)));
    assert(!dhcps_address_valid(htonl(0x0a480004)));
    /* Exhaustion yields no OFFER, and a declined address is not immediately reused. */
    clear_leases(&s);memset(&owners,0,sizeof owners);s.dhcps_poll.end_ip.addr=IP(2);
    assert(packet(&s,a,DHCPDISCOVER,0,0)==DHCPS_STATE_OFFER);
    assert(packet(&s,b,DHCPDISCOVER,0,0)==DHCPS_STATE_IDLE);
    assert(packet(&s,a,DHCPDECLINE,IP(2),0)==DHCPS_STATE_DECLINE);
    assert(packet(&s,b,DHCPDISCOVER,0,0)==DHCPS_STATE_IDLE);
    clear_leases(&s);puts("PASS: production DHCP parser/allocator, fresh/reboot, exclusions, conflicts, exhaustion");return 0;
}
