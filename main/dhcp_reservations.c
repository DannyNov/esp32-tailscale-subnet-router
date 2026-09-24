/* Persistent ownership: mutations are serialized on the TCP/IP task. */
#include <string.h>
#include <stdlib.h>
#include "esp_log.h"
#include "nvs.h"
#include "nvs_params.h"
#include "dhcps_ext.h"
#include "dhcp_reservations.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "lwip/tcpip.h"
static const char *TAG = "dhcp_bindings";
static dhcp_bindings_t s_state;
static SemaphoreHandle_t s_mutex;
static bool s_healthy;
static esp_err_t s_error;
#define LOCK() xSemaphoreTake(s_mutex, portMAX_DELAY)
#define UNLOCK() xSemaphoreGive(s_mutex)

static esp_err_t commit(dhcp_bindings_t *next)
{
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
    return err;
}
static bool address_available(const uint8_t mac[6], uint32_t ip)
{
    LOCK(); bool ok = s_healthy && !binding_owned_by_other(&s_state, mac, ip); UNLOCK();
    return ok;
}
static bool prepare_ack(const uint8_t mac[6], uint32_t ip)
{
    LOCK();
    bool ok = s_healthy && !binding_owned_by_other(&s_state, mac, ip);
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
void dhcp_reservations_init(void)
{
    if (s_mutex) return;
    s_mutex = xSemaphoreCreateMutex();
    configASSERT(s_mutex);
    memset(&s_state, 0, sizeof s_state); /* opt-in; ordinary DHCP by default */
    nvs_handle_t nvs;
    esp_err_t err = nvs_open(NVS_NAMESPACE, NVS_READONLY, &nvs);
    if (err == ESP_ERR_NVS_NOT_FOUND) s_healthy = true;
    else if (err == ESP_OK) {
        size_t size = sizeof s_state;
        err = nvs_get_blob(nvs, "dhcp_bind_v1", &s_state, &size);
        if (err == ESP_ERR_NVS_NOT_FOUND) {
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
    dhcps_set_reservation_lookup(dhcp_reservations_lookup);
    dhcps_set_address_policy(address_available, prepare_ack);
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
    r->result = ESP_ERR_INVALID_STATE;
    if (!s_healthy) goto done;
    dhcp_bindings_t *next = malloc(sizeof(*next));
    if (!next) { r->result = ESP_ERR_NO_MEM; goto done; }
    LOCK(); *next = s_state; UNLOCK();
    if (r->enabled >= 0) next->enabled = !!r->enabled;
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
            dhcps_address_in_use(next->manual[i].mac, next->manual[i].ip)) goto invalid;
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
