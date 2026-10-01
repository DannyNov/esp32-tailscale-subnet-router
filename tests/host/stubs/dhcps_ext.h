#pragma once
#include "dhcp_diagnostics.h"
#include <stdint.h>
#include <stdbool.h>
typedef uint32_t (*dhcps_reservation_lookup_fn)(const uint8_t[6]);
typedef bool (*dhcps_address_policy_fn)(const uint8_t[6], uint32_t);
typedef struct { uint8_t mac[6]; uint32_t ip; bool acknowledged;
    dhcp_forcerenew_t forcerenew; uint32_t lease_timer; char hostname[32]; } dhcp_lease_info_t;
void dhcps_set_reservation_lookup(dhcps_reservation_lookup_fn);
void dhcps_set_address_policy(dhcps_address_policy_fn, dhcps_address_policy_fn);
int dhcps_get_active_leases(dhcp_lease_info_t*, int);
bool dhcps_address_valid(uint32_t);
bool dhcps_address_in_use(const uint8_t[6], uint32_t);
