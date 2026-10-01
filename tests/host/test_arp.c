#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#define LWIP_IPV4 1
#define LWIP_ARP 1
#define ETHARP_SUPPORT_STATIC_ENTRIES 1
#define LWIP_ASSERT_CORE_LOCKED() ((void)0)
#define ETHARP_FLAG_TRY_HARD 1
#define ETHARP_FLAG_STATIC_ENTRY 4
#define ETHARP_STATE_STATIC 5
#define ARP_TABLE_SIZE 4
#define ERR_OK 0
#define ERR_ARG -1
#define ERR_MEM -2
typedef int err_t;
typedef struct { uint32_t addr; } ip4_addr_t;
struct netif { int id; };
struct eth_addr { uint8_t addr[6]; };
static struct { int state; struct netif *netif; ip4_addr_t ipaddr; } arp_table[ARP_TABLE_SIZE];
static struct netif *last_netif;
static err_t etharp_update_arp_entry(struct netif *n,const ip4_addr_t *a,const struct eth_addr *mac,int flags) {
    (void)a;(void)mac;assert(flags==(ETHARP_FLAG_TRY_HARD|ETHARP_FLAG_STATIC_ENTRY));last_netif=n;return ERR_OK;
}
#define ip4_addr_eq(a,b) ((a)->addr==(b)->addr)
static void etharp_free_entry(int i) { arp_table[i].state=0; }
#include "../../components/dhcpserver/etharp_netif.inc"
int main(void) {
    struct netif ap={1},sta={2};ip4_addr_t ip={4};struct eth_addr mac={{2,0,0,0,0,1}};
    assert(tsr_etharp_add_static_entry(&ap,&ip,&mac)==ERR_OK);assert(last_netif==&ap);
    assert(tsr_etharp_add_static_entry(NULL,&ip,&mac)==ERR_ARG);
    arp_table[0].state=arp_table[1].state=ETHARP_STATE_STATIC;
    arp_table[0].netif=&sta;arp_table[1].netif=&ap;arp_table[0].ipaddr=arp_table[1].ipaddr=ip;
    assert(tsr_etharp_remove_static_entry(&ap,&ip)==ERR_OK);
    assert(arp_table[0].state==ETHARP_STATE_STATIC);assert(arp_table[1].state==0);
    puts("PASS: explicit AP netif ARP add/removal, independent of route selection");return 0;
}
