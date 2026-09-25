#pragma once
#include "lwip/tcpip.h"
#include <stdint.h>
typedef struct { uint32_t addr; } ip4_addr_t;
#define IPSTR "%u"
#define IP2STR(ip) ((unsigned)(ip)->addr)
struct netif { int id; };
struct eth_addr { uint8_t addr[6]; };
typedef struct { struct netif *impl; } esp_netif_t;
esp_netif_t *esp_netif_get_handle_from_ifkey(const char *);
void *esp_netif_get_netif_impl(esp_netif_t *);
err_t tsr_etharp_add_static_entry(struct netif *, const ip4_addr_t *, const struct eth_addr *);
int etharp_find_addr(struct netif *, const ip4_addr_t *, struct eth_addr **, const ip4_addr_t **);
