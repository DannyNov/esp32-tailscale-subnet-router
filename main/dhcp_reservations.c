/* Persistent ownership: mutations are serialized on the TCP/IP task. */
#include <string.h>
#include <stdlib.h>
#include "esp_log.h"
#include "nvs.h"
#include "nvs_params.h"
#include "dhcps_ext.h"
#include "dhcp_reservations.h"
#include "boot_timing.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "lwip/tcpip.h"
static const char *TAG = "dhcp_bindings";
static dhcp_bindings_t s_state;
static dhcp_observation_t s_observed[DHCP_OBSERVATIONS_MAX];
static SemaphoreHandle_t s_mutex;
static bool s_healthy;
static esp_err_t s_error;
static void (*s_refresh_observations)(void);
void dhcp_observations_set_refresh(void (*refresh)(void)) { s_refresh_observations = refresh; }
#define LOCK() xSemaphoreTake(s_mutex, portMAX_DELAY)
#define UNLOCK() xSemaphoreGive(s_mutex)

static esp_err_t commit(dhcp_bindings_t *next)
{
    BOOT_MARK("bindings NVS commit begin");
    binding_seal(next);
    nvs_handle_t nvs;
    esp_err_t err = nvs_open(NVS_NAMESPACE, NVS_READWRITE, &nvs);
    if (err == ESP_OK) {
        err = nvs_set_blob(nvs, "dhcp_bind_v1", next, sizeof(*next));
        if (err == ESP_OK) err = nvs_commit(nvs);
        nvs_close(nvs);
    }
    LOCK();
    s_error = err;
    if (err == ESP_OK) s_state = *next;
    UNLOCK();
    if (err != ESP_OK) ESP_LOGE(TAG, "binding not committed; ACK/settings refused: %s", esp_err_to_name(err));
    BOOT_MARK("bindings NVS commit end");
    return err;
}
/* Called with s_mutex held. Transient claims last only for this association. */
static dhcp_observation_t *observation(const uint8_t mac[6], bool create)
{
    dhcp_observation_t *empty = NULL;
    for (int i = 0; i < DHCP_OBSERVATIONS_MAX; ++i) {
        if (!memcmp(s_observed[i].mac, mac, 6)) return &s_observed[i];
        if (!binding_mac_valid(s_observed[i].mac) && !empty) empty = &s_observed[i];
    }
    if (create && empty) memcpy(empty->mac, mac, 6);
    return create ? empty : NULL;
}
static bool observed_other(const uint8_t mac[6], uint32_t ip)
{
    for (int i = 0; i < DHCP_OBSERVATIONS_MAX; ++i)
        if (ip && s_observed[i].ip == ip && memcmp(s_observed[i].mac, mac, 6) &&
            !binding_owned_by_other(&s_state, s_observed[i].mac, ip)) return true;
    return false;
}
static bool address_available(const uint8_t mac[6], uint32_t ip)
{
    LOCK();
    bool ok = s_healthy && !binding_owned_by_other(&s_state, mac, ip) && !observed_other(mac, ip);
    UNLOCK();
    return ok;
}
bool dhcp_observation_get(int i, dhcp_observation_t *out)
{
    if (!s_mutex || !out || i < 0 || i >= DHCP_OBSERVATIONS_MAX) return false;
    LOCK(); *out = s_observed[i]; UNLOCK();
    return binding_mac_valid(out->mac);
}
uint32_t dhcp_observation_forget(const uint8_t mac[6])
{
    LOCK();
    dhcp_observation_t *o = observation(mac, false);
    uint32_t ip = o ? o->ip : 0;
    if (o) memset(o, 0, sizeof(*o));
    UNLOCK();
    return ip;
}
uint32_t dhcp_clients_lookup(const uint8_t mac[6])
{
    if (!s_mutex || !binding_mac_valid(mac)) return 0;
    LOCK();
    uint32_t ip = s_healthy ? binding_lookup(&s_state, mac) : 0;
    dhcp_observation_t *o = observation(mac, false);
    if (!ip && s_healthy && o && !binding_owned_by_other(&s_state, mac, o->ip)) ip = o->ip;
    UNLOCK(); return ip;
}
uint32_t dhcp_client_resolve(const uint8_t mac[6], uint32_t dhcp_ip, uint32_t arp_ip,
                             const char **source, bool *conflict)
{
    *source = ""; *conflict = false;
    if (!s_mutex || !binding_mac_valid(mac)) return 0;
    LOCK();
    uint32_t ip = s_healthy ? binding_lookup(&s_state, mac) : 0;
    dhcp_observation_t *o = observation(mac, false);
    if (ip) *source = "persistent";
    else if (s_healthy && o && o->ip && !binding_owned_by_other(&s_state, mac, o->ip)) {
        ip = o->ip; *source = "observed";
    }
    if (o && o->conflict) *conflict = true;
    uint32_t candidates[2] = {dhcp_ip, arp_ip};
    for (int i = 0; i < 2; ++i) if (candidates[i]) {
        if (!s_healthy || binding_owned_by_other(&s_state, mac, candidates[i]) ||
            observed_other(mac, candidates[i]) || (ip && ip != candidates[i])) *conflict = true;
        else if (!ip) { ip = candidates[i]; *source = i ? "arp" : "dhcp"; }
    }
    UNLOCK();
    return ip;
}
int dhcp_remembered_snapshot(dhcp_remembered_t *out, int max)
{
    if (!s_mutex || !out || max <= 0) return 0;
    int count = 0;
    LOCK();
    if (s_healthy) {
        for (int i = 0; i < DHCP_RESERVATIONS_MAX && count < max; ++i) if (s_state.manual[i].valid) {
            dhcp_reservation_t *r = &s_state.manual[i];
            dhcp_remembered_t *v = &out[count++]; memset(v, 0, sizeof(*v));
            memcpy(v->mac, r->mac, 6); v->ip = r->ip; v->manual = true;
            memcpy(v->name, r->name, sizeof v->name);
        }
        for (int i = 0; i < DHCP_STICKY_MAX && count < max; ++i) if (s_state.sticky[i].ip) {
            dhcp_sticky_t *r = &s_state.sticky[i]; bool duplicate = false;
            for (int j = 0; j < count; ++j) if (!memcmp(out[j].mac, r->mac, 6)) duplicate = true;
            if (duplicate) continue;
            dhcp_remembered_t *v = &out[count++]; memset(v, 0, sizeof(*v));
            memcpy(v->mac, r->mac, 6); v->ip = r->ip;
        }
    }
    UNLOCK(); return count;
}
static bool prepare_ack(const uint8_t mac[6], uint32_t ip)
{
    LOCK();
    bool ok = s_healthy && !binding_owned_by_other(&s_state, mac, ip) && !observed_other(mac, ip);
    bool save = s_state.enabled || binding_lookup(&s_state, mac);
    bool known = binding_sticky(&s_state, mac) == ip;
    UNLOCK();
    if (!ok) return false;
    if (!save || known) return true;
    dhcp_bindings_t *next = malloc(sizeof(*next));
    if (!next) return false;
    LOCK(); *next = s_state; UNLOCK();
    ok = binding_remember(next, mac, ip);
    if (ok) ok = commit(next) == ESP_OK;
    else ESP_LOGE(TAG, "sticky capacity/conflict: refusing new ACK (no eviction)");
    free(next);
    return ok;
}
bool dhcp_reservations_observe(const uint8_t mac[6], uint32_t ip, bool associated)
{
    if (!s_mutex || !associated || !binding_mac_valid(mac) || !dhcps_address_valid(ip)) return false;
    bool live_conflict = dhcps_address_in_use(mac, ip);
    LOCK();
    uint32_t known = binding_lookup(&s_state, mac);
    dhcp_observation_t *o = observation(mac, true);
    bool ok = s_healthy && o && !live_conflict && !observed_other(mac, ip) &&
              !binding_owned_by_other(&s_state, mac, ip) && (!known || known == ip) &&
              (!o->ip || o->ip == ip);
    bool report = !ok && o && !o->conflict;
    if (o) {
        o->conflict = !ok;
        if (ok) o->ip = ip;
    }
    bool enabled = s_state.enabled;
    UNLOCK();
    if (report) ESP_LOGW(TAG, "passive IP conflict; preserving confirmed owner for %02x:%02x:%02x:%02x:%02x:%02x",
                        mac[0], mac[1], mac[2], mac[3], mac[4], mac[5]);
    if (!ok) return false;
    /* Observation survives persistence failure in RAM, never masquerades as sticky.
     * OFF only disables automatic persistence, not validated discovery/ARP. */
    if (enabled && !known) (void)prepare_ack(mac, ip);
    return true;
}
void dhcp_reservations_init(void)
{
    if (s_mutex) return;
    s_mutex = xSemaphoreCreateMutex();
    configASSERT(s_mutex);
    memset(s_observed, 0, sizeof s_observed);
    memset(&s_state, 0, sizeof s_state); /* opt-in; ordinary DHCP by default */
    nvs_handle_t nvs;
    esp_err_t err = nvs_open(NVS_NAMESPACE, NVS_READONLY, &nvs);
    if (err == ESP_ERR_NVS_NOT_FOUND) s_healthy = true;
    else if (err == ESP_OK) {
        size_t size = sizeof s_state;
        err = nvs_get_blob(nvs, "dhcp_bind_v1", &s_state, &size);
        if (err == ESP_ERR_NVS_NOT_FOUND) {
            BOOT_MARK("bindings legacy migration (RAM, persisted on next mutation)");
            memset(&s_state, 0, sizeof s_state);
            size = sizeof s_state.manual;
            err = nvs_get_blob(nvs, "dhcp_res", s_state.manual, &size);
            if (err == ESP_ERR_NVS_NOT_FOUND) { err = ESP_OK; memset(s_state.manual, 0, sizeof s_state.manual); }
            else if (err == ESP_OK && size != sizeof s_state.manual) err = ESP_ERR_INVALID_SIZE;
            binding_seal(&s_state);
        } else if (err == ESP_OK && size != sizeof s_state) err = ESP_ERR_INVALID_SIZE;
        s_healthy = err == ESP_OK && binding_valid(&s_state);
        nvs_close(nvs);
    }
    s_error = s_healthy ? ESP_OK : (err == ESP_OK ? ESP_ERR_INVALID_STATE : err);
    if (!s_healthy) {
        memset(&s_state, 0, sizeof s_state);
        ESP_LOGE(TAG, "Invalid/unreadable NVS bindings: DHCP allocation disabled; preserve NVS for recovery");
    }
    dhcps_set_reservation_lookup(dhcp_clients_lookup);
    dhcps_set_address_policy(address_available, prepare_ack);
    BOOT_MARK(s_healthy ? "sticky bindings loaded / validated" : "sticky bindings load FAILED");
}
uint32_t dhcp_reservations_lookup(const uint8_t mac[6])
{
    if (!s_mutex || !mac) return 0;
    LOCK(); uint32_t ip = s_healthy ? binding_lookup(&s_state, mac) : 0; UNLOCK();
    return ip;
}
bool dhcp_reservations_get(int i, dhcp_reservation_t *out)
{
    if (!s_mutex || !out || i < 0 || i >= DHCP_RESERVATIONS_MAX) return false;
    LOCK(); *out = s_state.manual[i]; UNLOCK();
    return out->valid != 0;
}
int dhcp_reservations_count(void)
{
    int n = 0;
    LOCK(); for (int i = 0; i < DHCP_RESERVATIONS_MAX; ++i) n += !!s_state.manual[i].valid; UNLOCK();
    return n;
}
bool dhcp_reservations_is_manual(const uint8_t mac[6])
{
    bool found = false;
    LOCK();
    for (int i = 0; i < DHCP_RESERVATIONS_MAX; ++i)
        if (s_state.manual[i].valid && !memcmp(s_state.manual[i].mac, mac, 6)) found = true;
    UNLOCK();
    return found;
}
void dhcp_reservations_name(const uint8_t mac[6], char out[DHCP_RESERVATION_NAME_LEN])
{
    out[0] = 0;
    LOCK();
    for (int i = 0; i < DHCP_RESERVATIONS_MAX; ++i)
        if (s_state.manual[i].valid && !memcmp(s_state.manual[i].mac, mac, 6))
            memcpy(out, s_state.manual[i].name, DHCP_RESERVATION_NAME_LEN);
    UNLOCK();
}
void dhcp_sticky_status(bool *enabled, int *count, esp_err_t *error)
{
    LOCK();
    *enabled = s_state.enabled; *count = 0; *error = s_error;
    for (int i = 0; i < DHCP_STICKY_MAX; ++i) *count += !!s_state.sticky[i].ip;
    UNLOCK();
}
typedef struct {
    const dhcp_reservation_t *arr;
    int count, enabled;
    esp_err_t result;
    SemaphoreHandle_t done;
} save_request_t;
static void save_on_tcpip(void *arg)
{
    save_request_t *r = arg;
    if (s_refresh_observations) s_refresh_observations();
    r->result = ESP_ERR_INVALID_STATE;
    if (!s_healthy) goto done;
    dhcp_bindings_t *next = malloc(sizeof(*next));
    if (!next) { r->result = ESP_ERR_NO_MEM; goto done; }
    LOCK(); *next = s_state; UNLOCK();
    if (r->enabled >= 0) next->enabled = !!r->enabled;
    /* Adopt the actual validated transient address for explicit Reserve, also OFF.
     * Enabling Sticky imports associated observations without waiting for traffic. */
    for (int i = 0; i < DHCP_OBSERVATIONS_MAX; ++i) {
        dhcp_observation_t *o = &s_observed[i];
        if (!o->ip) continue;
        bool requested = false;
        for (int j = 0; j < r->count; ++j) if (!memcmp(r->arr[j].mac, o->mac, 6)) requested = true;
        if (next->enabled || requested) {
            if (!dhcps_address_valid(o->ip) || dhcps_address_in_use(o->mac, o->ip) ||
                !binding_remember(next, o->mac, o->ip)) goto invalid;
        }
    }
    /* Capture ACKed addresses before changing ownership. Serialized with DHCP. */
    dhcp_lease_info_t leases[DHCP_RESERVATIONS_MAX];
    int n = dhcps_get_active_leases(leases, DHCP_RESERVATIONS_MAX);
    for (int i = 0; i < n; ++i) {
        bool requested = false;
        for (int j = 0; j < r->count; ++j) if (!memcmp(r->arr[j].mac, leases[i].mac, 6)) requested = true;
        if (leases[i].acknowledged && (next->enabled || requested)) {
            if (!binding_sticky(next, leases[i].mac)) {
                /* A legacy manual target may differ from a still-active lease.
                 * The ACKed address is the evidence; adopt it before migration. */
                for (int j = 0; j < DHCP_RESERVATIONS_MAX; ++j)
                    if (next->manual[j].valid && !memcmp(next->manual[j].mac, leases[i].mac, 6))
                        next->manual[j].ip = leases[i].ip;
            }
            if (!binding_remember(next, leases[i].mac, leases[i].ip)) goto invalid;
        }
    }
    if (!binding_replace_manual(next, r->arr, r->count)) goto invalid;
    for (int i = 0; i < DHCP_RESERVATIONS_MAX; ++i) if (next->manual[i].valid) {
        if (!dhcps_address_valid(next->manual[i].ip) ||
            dhcps_address_in_use(next->manual[i].mac, next->manual[i].ip) ||
            observed_other(next->manual[i].mac, next->manual[i].ip)) goto invalid;
    }
    r->result = commit(next);
    free(next);
    goto done;
invalid:
    r->result = ESP_ERR_INVALID_ARG;
    free(next);
done:
    xSemaphoreGive(r->done);
}
esp_err_t dhcp_reservations_save(const dhcp_reservation_t *arr, int count, int enabled)
{
    if (count < 0 || count > DHCP_RESERVATIONS_MAX || (count && !arr)) return ESP_ERR_INVALID_ARG;
    save_request_t r = {.arr = arr, .count = count, .enabled = enabled};
    r.done = xSemaphoreCreateBinary();
    if (!r.done) return ESP_ERR_NO_MEM;
    err_t err = tcpip_callback(save_on_tcpip, &r);
    if (err == ERR_OK) xSemaphoreTake(r.done, portMAX_DELAY);
    vSemaphoreDelete(r.done);
    return err == ERR_OK ? r.result : ESP_FAIL;
}
