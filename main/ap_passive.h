#pragma once
struct pbuf;
struct netif;
/* Nonblocking, bounded handoff from the WIFI_AP_DEF input hook. */
void ap_passive_observe(struct pbuf *p, struct netif *netif);
void ap_passive_init(void);
/* Schedule reconciliation against the current association list after Wi-Fi events. */
void ap_passive_associations_changed(void);
