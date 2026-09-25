#include "dhcp_bindings.h"
#include <string.h>

bool binding_parse_ipv4(const uint8_t *h, size_t copied, size_t frame_size,
                        uint8_t mac[6], uint32_t *ip)
{
    if (!h || copied < 34 || h[12] != 8 || h[13] != 0 || (h[14] >> 4) != 4)
        return false;
    size_t ihl = (h[14] & 15) * 4u;
    size_t total = ((size_t)h[16] << 8) | h[17];
    if (ihl < 20 || copied < 14 + ihl || total < ihl || frame_size < 14 + total ||
        !binding_mac_valid(h + 6)) return false;
    unsigned sum = 0;
    for (size_t i = 14; i < 14 + ihl; i += 2) sum += ((unsigned)h[i] << 8) | h[i+1];
    while (sum >> 16) sum = (sum & 65535) + (sum >> 16);
    if (sum != 65535) return false;
    memcpy(mac, h + 6, 6);
    memcpy(ip, h + 26, 4); /* wire order, no unaligned loads */
    return true;
}

bool binding_mac_valid(const uint8_t mac[6])
{
    static const uint8_t zero[6];
    return mac && !(mac[0] & 1) && memcmp(mac, zero, 6);
}
uint32_t binding_sticky(const dhcp_bindings_t *s, const uint8_t mac[6])
{
    for (int i = 0; i < DHCP_STICKY_MAX; ++i)
        if (s->sticky[i].ip && !memcmp(s->sticky[i].mac, mac, 6)) return s->sticky[i].ip;
    return 0;
}
uint32_t binding_lookup(const dhcp_bindings_t *s, const uint8_t mac[6])
{
    for (int i = 0; i < DHCP_RESERVATIONS_MAX; ++i)
        if (s->manual[i].valid && !memcmp(s->manual[i].mac, mac, 6)) return s->manual[i].ip;
    return binding_sticky(s, mac);
}
bool binding_owned_by_other(const dhcp_bindings_t *s, const uint8_t mac[6], uint32_t ip)
{
    for (int i = 0; i < DHCP_RESERVATIONS_MAX; ++i)
        if (s->manual[i].valid && s->manual[i].ip == ip && memcmp(s->manual[i].mac, mac, 6)) return true;
    for (int i = 0; i < DHCP_STICKY_MAX; ++i)
        if (s->sticky[i].ip == ip && ip && memcmp(s->sticky[i].mac, mac, 6)) return true;
    return false;
}
bool binding_remember(dhcp_bindings_t *s, const uint8_t mac[6], uint32_t ip)
{
    if (!ip || !binding_mac_valid(mac) || binding_owned_by_other(s, mac, ip)) return false;
    uint32_t known = binding_lookup(s, mac);
    if (known && known != ip) return false; /* Never silently reassign a live client. */
    if (binding_sticky(s, mac)) return true;
    for (int i = 0; i < DHCP_STICKY_MAX; ++i) if (!s->sticky[i].ip) {
        memcpy(s->sticky[i].mac, mac, 6);
        s->sticky[i].ip = ip;
        return true;
    }
    return false; /* No eviction: offline/sleeping clients still own their IP. */
}
bool binding_replace_manual(dhcp_bindings_t *s, const dhcp_reservation_t *r, int count)
{
    if (count < 0 || count > DHCP_RESERVATIONS_MAX || (count && !r)) return false;
    dhcp_reservation_t next[DHCP_RESERVATIONS_MAX] = {0};
    for (int i = 0; i < count; ++i) {
        if (!r[i].ip || !binding_mac_valid(r[i].mac)) return false;
        next[i] = r[i];
        next[i].valid = 1;
        next[i].name[DHCP_RESERVATION_NAME_LEN - 1] = 0;
        /* Reserve the address the device actually holds, never the typed replacement. */
        uint32_t held = binding_sticky(s, r[i].mac);
        if (held) next[i].ip = held;
        for (int j = 0; j < i; ++j)
            if (next[j].ip == next[i].ip || !memcmp(next[j].mac, next[i].mac, 6)) return false;
        for (int j = 0; j < DHCP_STICKY_MAX; ++j)
            if (s->sticky[j].ip == next[i].ip && memcmp(s->sticky[j].mac, next[i].mac, 6)) return false;
    }
    memcpy(s->manual, next, sizeof next);
    return true;
}
static uint32_t checksum(const dhcp_bindings_t *s)
{
    const uint8_t *p = (const uint8_t *)s;
    uint32_t h = 2166136261u;
    for (size_t i = 0; i < offsetof(dhcp_bindings_t, checksum); ++i) h = (h ^ p[i]) * 16777619u;
    return h;
}
void binding_seal(dhcp_bindings_t *s) { s->version = 1; s->checksum = checksum(s); }
bool binding_valid(const dhcp_bindings_t *s)
{
    if (s->version != 1 || s->enabled > 1 || s->checksum != checksum(s)) return false;
    for (int i = 0; i < DHCP_RESERVATIONS_MAX; ++i) if (s->manual[i].valid) {
        const dhcp_reservation_t *r = &s->manual[i];
        if (!binding_mac_valid(r->mac) || !r->ip || r->name[DHCP_RESERVATION_NAME_LEN - 1]) return false;
        if (binding_owned_by_other(s, r->mac, r->ip)) return false;
        uint32_t held = binding_sticky(s, r->mac);
        if (held && held != r->ip) return false;
        for (int j = 0; j < i; ++j)
            if (s->manual[j].valid && !memcmp(s->manual[j].mac, r->mac, 6)) return false;
    }
    for (int i = 0; i < DHCP_STICKY_MAX; ++i) if (s->sticky[i].ip) {
        const dhcp_sticky_t *r = &s->sticky[i];
        if (!binding_mac_valid(r->mac) || binding_owned_by_other(s, r->mac, r->ip)) return false;
        for (int j = 0; j < i; ++j)
            if (s->sticky[j].ip && !memcmp(s->sticky[j].mac, r->mac, 6)) return false;
    }
    return true;
}
