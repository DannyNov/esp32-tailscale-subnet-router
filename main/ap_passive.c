/* Incoming frames may execute on the Wi-Fi task, not the TCP/IP task.
 * Copy only validated headers; never retain a pbuf or write flash in the hook.
 * A fixed pool coalesces traffic and limits retries to once/second per MAC. */
#include <string.h>
#include "esp_wifi.h"
#include "esp_netif.h"
#include "esp_netif_net_stack.h"
#include "esp_timer.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "lwip/pbuf.h"
#include "lwip/netif.h"
#include "lwip/tcpip.h"
#include "dhcps_ext.h"
#include "dhcp_reservations.h"
#include "mac_deny.h"
#include "ap_passive.h"

typedef struct {
    uint8_t mac[6];
    uint32_t ip;
    struct netif *netif;
    bool used, pending;
    int64_t attempted;
} observation_t;
static observation_t s_pending[16];
static portMUX_TYPE s_lock = portMUX_INITIALIZER_UNLOCKED;

static void reconcile(struct netif *n, const wifi_sta_list_t *stations)
{
    for (int i = 0; i < DHCP_OBSERVATIONS_MAX; ++i) {
        dhcp_observation_t o;
        if (!dhcp_observation_get(i, &o)) continue;
        bool present = false;
        for (int j = 0; j < stations->num; ++j)
            if (!memcmp(stations->sta[j].mac, o.mac, 6)) present = true;
        if (present && (!o.ip || dhcps_address_valid(o.ip)) && !mac_deny_is_blocked(o.mac)) continue;
        (void)dhcp_observation_forget(o.mac);
        /* Never remove another owner's ARP entry while discarding stale RAM. */
        ip4_addr_t ip = {.addr = o.ip};
        struct eth_addr *owner = NULL; const ip4_addr_t *found = NULL;
        if (n && o.ip && etharp_find_addr(n, &ip, &owner, &found) >= 0 &&
            owner && !memcmp(owner->addr, o.mac, 6))
            (void)tsr_etharp_remove_static_entry(n, &ip);
    }
}
static void refresh_on_tcpip(void)
{
    esp_netif_t *ap = esp_netif_get_handle_from_ifkey("WIFI_AP_DEF");
    struct netif *n = ap ? esp_netif_get_netif_impl(ap) : NULL;
    wifi_sta_list_t stations = {0};
    /* A failed station query is not evidence that a live owner went away. */
    if (n && esp_wifi_ap_get_sta_list(&stations) != ESP_OK) return;
    reconcile(n, &stations);
}
static void associations_changed_cb(void *arg) { (void)arg; refresh_on_tcpip(); }
void ap_passive_associations_changed(void)
{
    (void)tcpip_callback(associations_changed_cb, NULL);
}
void ap_passive_init(void) { dhcp_observations_set_refresh(refresh_on_tcpip); }

static void learn_on_tcpip(void *arg)
{
    observation_t *o = arg; /* immutable until pending is cleared */
    esp_netif_t *ap = esp_netif_get_handle_from_ifkey("WIFI_AP_DEF");
    struct netif *n = ap ? esp_netif_get_netif_impl(ap) : NULL;
    wifi_sta_list_t stations = {0};
    bool associated = false;
    if (n && n == o->netif &&
        esp_wifi_ap_get_sta_list(&stations) == ESP_OK) {
        reconcile(n, &stations);
        for (int i = 0; i < stations.num; ++i)
            if (!memcmp(stations.sta[i].mac, o->mac, 6) && !mac_deny_is_blocked(o->mac)) associated = true;
    }
    /* A live ARP owner also counts, even without a DHCP lease. */
    if (associated) {
        ip4_addr_t ip = {.addr = o->ip};
        struct eth_addr *owner = NULL;
        const ip4_addr_t *found_ip = NULL;
        if (etharp_find_addr(n, &ip, &owner, &found_ip) >= 0 &&
            owner && memcmp(owner->addr, o->mac, 6)) {
            associated = false;
            ESP_LOGW("ap_passive", "ARP owner conflict; observation rejected");
        }
    }
    uint32_t previous = dhcp_clients_lookup(o->mac);
    if (dhcp_reservations_observe(o->mac, o->ip, associated)) {
        ip4_addr_t ip = {.addr = o->ip};
        struct eth_addr mac;
        memcpy(mac.addr, o->mac, 6);
        err_t err = tsr_etharp_add_static_entry(n, &ip, &mac);
        if (!previous) ESP_LOGW("ap_passive", "observed %02x:%02x:%02x:%02x:%02x:%02x -> "
                               IPSTR " (persistent=%d, AP ARP result=%d)",
                               o->mac[0], o->mac[1], o->mac[2], o->mac[3], o->mac[4], o->mac[5],
                               IP2STR(&ip), dhcp_reservations_lookup(o->mac) == o->ip, (int)err);
    }
    portENTER_CRITICAL(&s_lock);
    o->pending = false;
    portEXIT_CRITICAL(&s_lock);
}

void ap_passive_observe(struct pbuf *p, struct netif *netif)
{
    if (!p || !netif) return;
    uint8_t header[74], mac[6];
    uint32_t ip;
    size_t copied = pbuf_copy_partial(p, header, sizeof header, 0);
    if (!binding_parse_ipv4(header, copied, p->tot_len, mac, &ip)) return;
    /* Cheap prefilter; DHCP's current subnet and ownership are rechecked in
     * the TCP/IP callback. Also reject initial DHCP frames (source 0.0.0.0). */
    if (!ip) return;
    int64_t now = esp_timer_get_time();
    observation_t *slot = NULL;
    portENTER_CRITICAL(&s_lock);
    for (unsigned i = 0; i < sizeof s_pending / sizeof s_pending[0]; ++i) {
        observation_t *o = &s_pending[i];
        if (o->used && !memcmp(o->mac, mac, 6)) {
            if (!o->pending && now - o->attempted >= 1000000) slot = o;
            goto selected;
        }
    }
    for (unsigned i = 0; i < sizeof s_pending / sizeof s_pending[0]; ++i) {
        observation_t *o = &s_pending[i];
        if (!o->pending && (!o->used || now - o->attempted >= 1000000)) {
            slot = o;
            break;
        }
    }
selected:
    if (slot) {
        memcpy(slot->mac, mac, 6);
        slot->ip = ip;
        slot->netif = netif;
        slot->used = slot->pending = true;
        slot->attempted = now;
    }
    portEXIT_CRITICAL(&s_lock);
    if (slot && tcpip_callback_with_block(learn_on_tcpip, slot, 0) != ERR_OK) {
        portENTER_CRITICAL(&s_lock);
        slot->pending = false;
        portEXIT_CRITICAL(&s_lock);
    }
}
