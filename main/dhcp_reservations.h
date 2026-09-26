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
/* TCP/IP task only. Caller verifies association and AP frame provenance. */
bool dhcp_reservations_observe(const uint8_t mac[6], uint32_t ip, bool associated);

#define DHCP_OBSERVATIONS_MAX 16
#define DHCP_REMEMBERED_MAX (DHCP_STICKY_MAX + DHCP_RESERVATIONS_MAX)
typedef struct { uint8_t mac[6]; uint32_t ip; bool conflict; } dhcp_observation_t;
typedef struct {
    uint8_t mac[6]; uint32_t ip;
    char name[DHCP_RESERVATION_NAME_LEN];
    bool manual;
} dhcp_remembered_t;
/* RAM only. Mutations/pruning on TCP/IP; all snapshots use the state mutex. */
bool dhcp_observation_get(int i, dhcp_observation_t *out);
uint32_t dhcp_observation_forget(const uint8_t mac[6]);
uint32_t dhcp_clients_lookup(const uint8_t mac[6]);
uint32_t dhcp_client_resolve(const uint8_t mac[6], uint32_t dhcp_ip, uint32_t arp_ip,
                             const char **source, bool *conflict);
/* Persistent rows only, one per MAC, independent of all runtime network state. */
int dhcp_remembered_snapshot(dhcp_remembered_t *out, int max);
void dhcp_observations_set_refresh(void (*refresh)(void));
