/* Real parser -> bounded handoff -> association/owners -> real NVS module -> ARP.
 * Only platform I/O is mocked. Queued callbacks deliberately run after input. */
#include "../../main/ap_passive.c"
static struct netif ap_netif = {1}, sta_netif = {2};
static esp_netif_t ap_handle = {&ap_netif};
static wifi_sta_list_t associated_stations;
static bool queue_fail, deny_mac, arp_conflict;
static unsigned queued, arp_calls;
static int64_t clock_us;
static struct { void (*fn)(void *); void *arg; } callbacks[16];
int64_t esp_timer_get_time(void) { return clock_us; }
esp_netif_t *esp_netif_get_handle_from_ifkey(const char *key) {
    assert(!strcmp(key,"WIFI_AP_DEF"));return &ap_handle;
}
void *esp_netif_get_netif_impl(esp_netif_t *n) { return n->impl; }
esp_err_t esp_wifi_ap_get_sta_list(wifi_sta_list_t *out) { *out=associated_stations;return ESP_OK; }
bool mac_deny_is_blocked(const uint8_t mac[6]) { (void)mac;return deny_mac; }
err_t tcpip_callback_with_block(void (*cb)(void *),void *arg,int block) {
    assert(!block);if(queue_fail)return -1;assert(queued<16);
    callbacks[queued].fn=cb;callbacks[queued++].arg=arg;return ERR_OK;
}
int etharp_find_addr(struct netif *n,const ip4_addr_t *ip,struct eth_addr **mac,const ip4_addr_t **out) {
    static struct eth_addr owner={{2,0,0,0,0,2}};
    assert(n==&ap_netif);(void)ip;(void)out;*mac=&owner;return arp_conflict?0:-1;
}
err_t tsr_etharp_add_static_entry(struct netif *n,const ip4_addr_t *ip,const struct eth_addr *mac) {
    assert(n==&ap_netif);assert(present); /* commit precedes ARP */
    dhcp_bindings_t persisted;memcpy(&persisted,disk,sizeof persisted);
    assert(binding_lookup(&persisted,mac->addr)==ip->addr);
    ++arp_calls;return ERR_OK;
}
uint16_t pbuf_copy_partial(const struct pbuf *p,void *out,uint16_t len,uint16_t offset) {
    assert(!offset);uint16_t copied=0;
    for(;p&&copied<len;p=p->next) {
        uint16_t n=p->len<len-copied?p->len:len-copied;
        memcpy((uint8_t*)out+copied,p->payload,n);copied+=n;
    }
    return copied;
}
static void drain(void) {
    for(unsigned i=0;i<queued;++i)callbacks[i].fn(callbacks[i].arg);
    queued=0;
}
static void passive_reset(void) {
    fresh();memset(s_pending,0,sizeof s_pending);memset(&associated_stations,0,sizeof associated_stations);
    associated_stations.num=1;memcpy(associated_stations.sta[0].mac,a,6);
    queued=arp_calls=0;queue_fail=deny_mac=arp_conflict=false;clock_us=0;
}
static void make_frame(uint8_t h[74],const uint8_t mac[6],uint32_t ip,unsigned ihl) {
    memset(h,0,74);memcpy(h+6,mac,6);h[12]=8;h[14]=(uint8_t)(0x40+ihl/4);
    h[17]=(uint8_t)ihl;h[22]=64;h[23]=17;memcpy(h+26,&ip,4);
    unsigned sum=0;for(unsigned i=14;i<14+ihl;i+=2)sum+=((unsigned)h[i]<<8)|h[i+1];
    while(sum>>16)sum=(sum&65535)+(sum>>16);sum=~sum;
    h[24]=(uint8_t)(sum>>8);h[25]=(uint8_t)sum;
}
static void feed(const uint8_t mac[6],uint32_t ip,struct netif *netif) {
    uint8_t h[74];make_frame(h,mac,ip,20);
    /* split inside Ethernet source; exercises pbuf_copy_partial integration */
    struct pbuf tail={h+9,25,25,NULL},head={h,9,34,&tail};
    ap_passive_observe(&head,netif);
}
static void observe(uint32_t ip) { clock_us+=1000000;feed(a,ip,&ap_netif);drain(); }
static void test_passive(void) {
    passive_reset();observe(IP(4));assert(!writes&&!dhcp_reservations_lookup(a)&&!arp_calls); /* OFF */
    assert(dhcp_reservations_save(NULL,0,1)==ESP_OK);unsigned w=writes;
    feed(a,IP(4),&ap_netif);assert(!queued); /* bounded retries */
    clock_us+=1000000;feed(a,IP(4),&ap_netif);assert(queued==1&&writes==w);
    for(int i=0;i<1000;++i)feed(a,IP(4),&ap_netif);
    assert(queued==1);drain();assert(writes==w+1&&arp_calls==1&&dhcp_reservations_lookup(a)==IP(4));
    observe(IP(4));assert(writes==w+1&&arp_calls==2); /* duplicate restores ARP, never flash */
    observe(IP(5));assert(writes==w+1&&dhcp_reservations_lookup(a)==IP(4)&&arp_calls==2);
    reboot();assert(dhcp_reservations_lookup(a)==IP(4));observe(IP(4));assert(writes==w+1);
    assert(dhcp_reservations_save(NULL,0,0)==ESP_OK);w=writes;
    observe(IP(4));assert(writes==w); /* known mapping remains restorable with OFF */

    passive_reset();assert(dhcp_reservations_save(NULL,0,1)==ESP_OK);w=writes;
    uint32_t invalid[]={0,IP(0),IP(1),IP(255),0xffffffffu,0x0400480au,0x010000e0u};
    for(unsigned i=0;i<sizeof invalid/sizeof invalid[0];++i)observe(invalid[i]);
    assert(writes==w&&!arp_calls);
    associated_stations.num=0;observe(IP(4));assert(writes==w&&!arp_calls);
    associated_stations.num=1;deny_mac=true;observe(IP(4));assert(writes==w);deny_mac=false;
    clock_us+=1000000;feed(a,IP(4),&sta_netif);drain();assert(writes==w&&!arp_calls); /* provenance */
    clock_us+=1000000;feed(a,IP(4),&ap_netif);associated_stations.num=0;drain();assert(writes==w); /* left before callback */
    associated_stations.num=1;
    live[0]=(dhcp_lease_info_t){.ip=IP(4),.acknowledged=true};memcpy(live[0].mac,b,6);live_count=1;
    observe(IP(4));assert(writes==w&&!arp_calls);live_count=0;
    arp_conflict=true;observe(IP(4));assert(writes==w&&!arp_calls);arp_conflict=false;
    assert(ack_cb(b,IP(4)));w=writes;observe(IP(4));assert(writes==w&&!arp_calls); /* sticky owner */
    dhcp_reservation_t r=reservation(b,IP(4));assert(dhcp_reservations_save(&r,1,-1)==ESP_OK);
    w=writes;observe(IP(4));assert(writes==w&&!arp_calls); /* manual owner */
    passive_reset();r=reservation(a,IP(5));assert(dhcp_reservations_save(&r,1,1)==ESP_OK);
    w=writes;observe(IP(4));assert(writes==w&&dhcp_reservations_lookup(a)==IP(5)&&!arp_calls);
    observe(IP(5));assert(writes==w&&arp_calls==1); /* manual priority */

    passive_reset();assert(dhcp_reservations_save(NULL,0,1)==ESP_OK);w=writes;
    queue_fail=true;observe(IP(4));assert(writes==w&&!arp_calls);queue_fail=false;
    fail_write=true;observe(IP(4));assert(!dhcp_reservations_lookup(a)&&!arp_calls);fail_write=false;
    fail_commit=true;observe(IP(4));assert(!dhcp_reservations_lookup(a)&&!arp_calls);fail_commit=false;
    reboot();assert(!dhcp_reservations_lookup(a));observe(IP(4));assert(arp_calls==1);
    /* Configuration/conflict rechecked after enqueue, before commit. */
    passive_reset();assert(dhcp_reservations_save(NULL,0,1)==ESP_OK);feed(a,IP(4),&ap_netif);
    assert(dhcp_reservations_save(NULL,0,0)==ESP_OK);w=writes;drain();assert(writes==w&&!arp_calls);
    passive_reset();assert(dhcp_reservations_save(NULL,0,1)==ESP_OK);feed(a,IP(4),&ap_netif);
    assert(ack_cb(b,IP(4)));w=writes;drain();assert(writes==w&&!arp_calls);

    /* Parser rejects runt, non-IPv4, bad checksum, lengths, invalid MAC.
     * IP options and long payloads need only their complete header copied. */
    uint8_t h[74],mac[6];uint32_t ip;
    make_frame(h,a,IP(4),60);assert(binding_parse_ipv4(h,74,74,mac,&ip));assert(ip==IP(4)&&!memcmp(mac,a,6));
    assert(!binding_parse_ipv4(h,73,74,mac,&ip));assert(!binding_parse_ipv4(h,74,73,mac,&ip));
    make_frame(h,a,IP(4),20);h[12]=0x86;assert(!binding_parse_ipv4(h,34,34,mac,&ip));
    make_frame(h,a,IP(4),20);h[14]=0x44;assert(!binding_parse_ipv4(h,34,34,mac,&ip));
    make_frame(h,a,IP(4),20);h[22]^=1;assert(!binding_parse_ipv4(h,34,34,mac,&ip));
    make_frame(h,a,IP(4),20);memset(h+6,0,6);assert(!binding_parse_ipv4(h,34,34,mac,&ip));
    make_frame(h,a,IP(4),20);h[6]|=1;assert(!binding_parse_ipv4(h,34,34,mac,&ip));
    for(unsigned len=0;len<34;++len)assert(!binding_parse_ipv4(h,len,len,mac,&ip));
    /* Fixed memory under a burst: a 17th distinct observation is dropped. */
    passive_reset();
    for(int i=0;i<17;++i) { uint8_t m[6]={2,0,0,0,0,(uint8_t)i};feed(m,IP(4),&ap_netif); }
    assert(queued==16);drain();assert(!writes&&!arp_calls);
    puts("PASS: passive frame learning, provenance, association, conflicts, NVS order/failures, OFF, reboot, bounded handoff");
}
