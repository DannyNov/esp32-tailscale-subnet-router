#pragma once
#include "dhcp_bindings.h"
#include "esp_err.h"
/* Initialize before AP start. Cache reads use a mutex, mutations run on TCP/IP. */
void dhcp_reservations_init(void);
int dhcp_reservations_count(void);
bool dhcp_reservations_get(int i, dhcp_reservation_t *out);
uint32_t dhcp_reservations_lookup(const uint8_t mac[6]);
bool dhcp_reservations_is_manual(const uint8_t mac[6]);
void dhcp_reservations_name(const uint8_t mac[6], char out[DHCP_RESERVATION_NAME_LEN]);
/* enabled = -1 preserves mode; 0/1 changes it in the same atomic record. */
esp_err_t dhcp_reservations_save(const dhcp_reservation_t *arr, int count, int enabled);
void dhcp_sticky_status(bool *enabled, int *count, esp_err_t *error);
