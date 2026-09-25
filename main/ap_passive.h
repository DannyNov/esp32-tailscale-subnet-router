#pragma once
struct pbuf;
struct netif;
/* Nonblocking, bounded handoff from the WIFI_AP_DEF input hook. */
void ap_passive_observe(struct pbuf *p, struct netif *netif);
