/* Address ownership policy shared by firmware and host tests. SPDX-License-Identifier: MIT */
#pragma once
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#define DHCP_RESERVATIONS_MAX 16
#define DHCP_RESERVATION_NAME_LEN 32
#define DHCP_STICKY_MAX 128
typedef struct {
    uint8_t mac[6], _pad0[2];
    uint32_t ip; /* network byte order */
    char name[DHCP_RESERVATION_NAME_LEN];
    uint8_t valid, _reserved[7];
} dhcp_reservation_t; /* Preserve the legacy NVS layout. */
typedef struct { uint8_t mac[6], pad[2]; uint32_t ip; } dhcp_sticky_t;
typedef struct {
    uint32_t version, enabled;
    dhcp_reservation_t manual[DHCP_RESERVATIONS_MAX];
    dhcp_sticky_t sticky[DHCP_STICKY_MAX];
    uint32_t checksum;
} dhcp_bindings_t;
bool binding_mac_valid(const uint8_t mac[6]);
uint32_t binding_lookup(const dhcp_bindings_t *s, const uint8_t mac[6]);
uint32_t binding_sticky(const dhcp_bindings_t *s, const uint8_t mac[6]);
bool binding_owned_by_other(const dhcp_bindings_t *s, const uint8_t mac[6], uint32_t ip);
bool binding_remember(dhcp_bindings_t *s, const uint8_t mac[6], uint32_t ip);
bool binding_replace_manual(dhcp_bindings_t *s, const dhcp_reservation_t *r, int count);
void binding_seal(dhcp_bindings_t *s);
bool binding_valid(const dhcp_bindings_t *s);
/* Parse a copied Ethernet + IPv4 header; frame_size includes all pbuf segments. */
bool binding_parse_ipv4(const uint8_t *header, size_t copied, size_t frame_size,
                        uint8_t mac[6], uint32_t *ip);
