static unsigned acl_calls, driver_calls;
static err_t acl_input(struct pbuf *p, struct netif *n) {
  (void)p; (void)n; acl_calls++; return 7;
}
static err_t driver_tx(struct netif *n, struct pbuf *p) {
  (void)n; (void)p; driver_calls++; return 8;
}
static err_t l3_tx(struct netif *n, struct pbuf *p, const ip4_addr_t *a) {
  (void)n; (void)p; (void)a; driver_calls++; return 9;
}
int main(void) {
  struct netif sta={.name={'s','t'},.input=acl_input,.linkoutput=driver_tx,.output=l3_tx};
  struct netif wg={.name={'w','g'},.input=acl_input,.output=l3_tx};
  struct pbuf packet={.tot_len=123};
  ip4_addr_t address={0};
  netif_list=&sta; assert(find_ts_netif()==NULL);
  sta.next=&wg; assert(find_ts_netif()==&wg);
  hook_netif(IF_WIFI,&sta); hook_netif(IF_WIFI,&sta); /* periodic rescan */
  assert(sta.input(&packet,&sta)==7 && acl_calls==1);
  assert(sta.linkoutput(&sta,&packet)==8 && driver_calls==1);
  assert(sta.output==l3_tx); /* only L2 TX counted */
  assert(s_traf[IF_WIFI].rx_octets==123 && s_traf[IF_WIFI].tx_octets==123);
  hook_netif(IF_TS,&wg); hook_netif(IF_TS,&wg);
  assert(wg.output(&wg,&packet,&address)==9 && driver_calls==2);
  assert(s_traf[IF_TS].tx_octets==123);
  unhook_netif(IF_WIFI,&sta); unhook_netif(IF_TS,&wg);
  assert(sta.input==acl_input && sta.linkoutput==driver_tx && sta.output==l3_tx);
  assert(wg.input==acl_input && wg.output==l3_tx);
  hook_netif(IF_WIFI,&sta); unhook_netif(IF_WIFI,&sta); /* enable again */
  assert(sta.input==acl_input);
  hook_netif(IF_TS,NULL); unhook_netif(IF_TS,NULL); /* missing tunnel */
  struct netif replacement={.name={'w','g'},.input=acl_input,.output=l3_tx};
  sta.next=&replacement; hook_netif(IF_TS,find_ts_netif());
  assert(replacement.output(&replacement,&packet,&address)==9);
  unhook_netif(IF_TS,&replacement); assert(replacement.output==l3_tx);
  puts("PASS: production SNMP hooks preserve ACL, rescan idempotence, L2/L3 counters, disable/reenable, absent and rebuilt wg tunnel");
  return 0;
}
