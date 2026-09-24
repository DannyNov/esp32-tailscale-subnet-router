/* Included in the framework etharp translation unit by CMake, without changing
 * the installed SDK. Use lwIP's own queue/state handling with an explicit netif. */
#if LWIP_IPV4 && LWIP_ARP && ETHARP_SUPPORT_STATIC_ENTRIES
err_t tsr_etharp_add_static_entry(struct netif *netif, const ip4_addr_t *ip, const struct eth_addr *mac)
{
    LWIP_ASSERT_CORE_LOCKED();
    if (!netif || !ip || !mac) return ERR_ARG;
    return etharp_update_arp_entry(netif, ip, mac, ETHARP_FLAG_TRY_HARD | ETHARP_FLAG_STATIC_ENTRY);
}
err_t tsr_etharp_remove_static_entry(struct netif *netif, const ip4_addr_t *ip)
{
    LWIP_ASSERT_CORE_LOCKED();
    if (!netif || !ip) return ERR_ARG;
    for (int i = 0; i < ARP_TABLE_SIZE; ++i) {
        if (arp_table[i].state == ETHARP_STATE_STATIC && arp_table[i].netif == netif &&
            ip4_addr_eq(ip, &arp_table[i].ipaddr)) {
            etharp_free_entry(i);
            return ERR_OK;
        }
    }
    return ERR_MEM;
}
#else
#error "Persistent AP bindings require IPv4 ARP static entries"
#endif
