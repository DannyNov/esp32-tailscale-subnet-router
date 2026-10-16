#pragma once
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>
#include <pthread.h>

typedef int esp_err_t;
#define ESP_OK 0
#define ESP_ERR_INVALID_STATE 0x103
#define pdTRUE 1

typedef pthread_mutex_t * SemaphoreHandle_t;
typedef struct { int online; int state; uint32_t vpn_ip; char identity[16]; } microlink_diag_t;
typedef struct { uint32_t network; uint8_t prefix_len; } microlink_route_t;
#define MICROLINK_MAX_PEER_ROUTES 8
typedef struct {
   uint32_t vpn_ip;
   char hostname[64];
   bool online, direct_path, is_exit_node;
   uint16_t derp_region;
   microlink_route_t subnet_routes[MICROLINK_MAX_PEER_ROUTES];
   uint8_t subnet_route_count;
} microlink_peer_info_t;
typedef struct {uint16_t region_id;uint16_t rtt_ms;} microlink_derp_rtt_t;
typedef struct {
    uint32_t serial;
    bool connected;
    microlink_peer_info_t peer;
    char region[64];
} microlink_t;
typedef struct {
    microlink_diag_t diag;
    bool connected;
    uint32_t vpn_ip;
    uint32_t generation;
    int peer_count, peers_online;
} tailscale_status_snapshot_t;
typedef struct {
    microlink_peer_info_t peer;
    char derp_region_name[64];
} tailscale_peer_snapshot_t;
static pthread_mutex_t master_mu = PTHREAD_MUTEX_INITIALIZER;
static SemaphoreHandle_t s_life_mux = &master_mu;
static microlink_t *s_microlink = NULL;
static uint32_t s_life_generation = 1;
static int xSemaphoreTake(SemaphoreHandle_t sem, unsigned timeout) {
    (void)timeout;
    return (pthread_mutex_trylock(sem) == 0) ? pdTRUE : 0;
}
static void xSemaphoreGive(SemaphoreHandle_t sem) { pthread_mutex_unlock(sem); }
static esp_err_t microlink_get_diag(const microlink_t *ml, microlink_diag_t *out) {
    if (!ml || !out) return ESP_ERR_INVALID_STATE;
    *out=(microlink_diag_t){.online=ml->connected,.state=2,.vpn_ip=ml->peer.vpn_ip};
    return ESP_OK;
}
static bool microlink_is_connected(const microlink_t *ml) {return ml->connected;}
static uint32_t microlink_get_vpn_ip(const microlink_t *ml) {return ml->peer.vpn_ip;}
static int microlink_get_peer_count(const microlink_t *ml) {(void)ml;return 1;}
static esp_err_t microlink_get_peer_info(const microlink_t *ml,int i,microlink_peer_info_t *out) {
    if(i!=0) return ESP_ERR_INVALID_STATE;
    *out=ml->peer;return ESP_OK;
}
static const char* microlink_get_derp_region_name(const microlink_t *ml,uint16_t region){return region==5 ? ml->region : NULL;}
static int microlink_get_derp_rtts(const microlink_t *ml,microlink_derp_rtt_t *out,int cap){
    (void)ml;
    if(cap<1)return 0;
    out[0]=(microlink_derp_rtt_t){.region_id=5,.rtt_ms=42};return 1;
}
