/* Compile the production storage module against deterministic NVS/RTOS adapters. */
#include <stdio.h>
#include <assert.h>
#include <string.h>
#include "../../main/dhcp_reservations.c"
static unsigned char disk[sizeof(dhcp_bindings_t)], pending[sizeof(dhcp_bindings_t)];
static dhcp_reservation_t legacy[DHCP_RESERVATIONS_MAX];
static bool present, have_legacy, fail_write, fail_commit;
static size_t disk_size;
static unsigned writes;
static dhcps_address_policy_fn available_cb, ack_cb;
static dhcp_lease_info_t live[16];
static int live_count;
static const uint8_t a[6] = {0xa0,0x92,8,0x51,0xdc,0xd6};
static const uint8_t b[6] = {2,0,0,0,0,2};
#define IP(n) (0x0047000au | ((uint32_t)(n)<<24))
esp_err_t nvs_open(const char *s, int mode, nvs_handle_t *h) { (void)s;(void)mode;*h=1;return ESP_OK; }
esp_err_t nvs_get_blob(nvs_handle_t h, const char *key, void *out, size_t *size) {
    (void)h;
    if (!strcmp(key,"dhcp_res")) {
        if (!have_legacy) return ESP_ERR_NVS_NOT_FOUND;
        memcpy(out,legacy,sizeof legacy); *size=sizeof legacy; return ESP_OK;
    }
    if (!present) return ESP_ERR_NVS_NOT_FOUND;
    if (*size<disk_size) return ESP_ERR_INVALID_SIZE;
    memcpy(out,disk,disk_size); *size=disk_size; return ESP_OK;
}
esp_err_t nvs_set_blob(nvs_handle_t h,const char *key,const void *p,size_t n) {
    (void)h;(void)key; ++writes;
    if (fail_write) return ESP_FAIL;
    assert(n==sizeof pending);memcpy(pending,p,n);return ESP_OK;
}
esp_err_t nvs_commit(nvs_handle_t h) {
    (void)h;if (fail_commit) return ESP_FAIL;
    memcpy(disk,pending,sizeof disk);disk_size=sizeof disk;present=true;return ESP_OK;
}
void nvs_close(nvs_handle_t h) { (void)h; }
void dhcps_set_reservation_lookup(dhcps_reservation_lookup_fn cb) { (void)cb; }
void dhcps_set_address_policy(dhcps_address_policy_fn a_cb,dhcps_address_policy_fn p_cb) { available_cb=a_cb;ack_cb=p_cb; }
int dhcps_get_active_leases(dhcp_lease_info_t *out,int max) { int n=live_count<max?live_count:max;memcpy(out,live,n*sizeof(*out));return n; }
bool dhcps_address_valid(uint32_t ip) { return (ip&0x00ffffff)==(IP(0)&0x00ffffff) && (ip>>24)>1 && (ip>>24)<255; }
bool dhcps_address_in_use(const uint8_t mac[6],uint32_t ip) {
    for(int i=0;i<live_count;++i) if(live[i].ip==ip&&memcmp(live[i].mac,mac,6))return true;return false;
}
static void reboot(void) { vSemaphoreDelete(s_mutex);s_mutex=NULL;s_healthy=false;live_count=0;memset(&s_state,0,sizeof s_state);dhcp_reservations_init(); }
static void fresh(void) { present=have_legacy=fail_write=fail_commit=false;writes=0;memset(legacy,0,sizeof legacy);reboot(); }
static dhcp_reservation_t reservation(const uint8_t mac[6],uint32_t ip) { dhcp_reservation_t r={.ip=ip,.valid=1};memcpy(r.mac,mac,6);return r; }
#include "test_passive.inc"
#include "test_remembered.inc"
int main(void) {
    test_passive();
    test_remembered();
    fresh();assert(s_healthy);assert(!s_state.enabled);
    assert(ack_cb(a,IP(4)));assert(writes==0); /* ordinary DHCP unchanged */
    assert(dhcp_reservations_save(NULL,0,1)==ESP_OK);
    unsigned w=writes;assert(ack_cb(a,IP(4)));assert(writes==w+1);
    assert(ack_cb(a,IP(4)));assert(writes==w+1); /* no write on renewal */
    reboot();assert(dhcp_reservations_lookup(a)==IP(4)); /* no DHCP needed */
    assert(!available_cb(b,IP(4)));assert(available_cb(b,IP(3)));
    dhcp_reservation_t r=reservation(a,IP(3));
    assert(dhcp_reservations_save(&r,1,-1)==ESP_OK);
    dhcp_reservation_t got;assert(dhcp_reservations_get(0,&got));assert(got.ip==IP(4));
    r=reservation(b,IP(4));assert(dhcp_reservations_save(&r,1,-1)==ESP_ERR_INVALID_ARG);
    assert(dhcp_reservations_lookup(a)==IP(4));
    r=reservation(b,IP(3));assert(dhcp_reservations_save(&r,1,-1)==ESP_OK);
    assert(!available_cb(a,IP(3)));reboot();assert(!available_cb(a,IP(3)));
    dhcp_reservation_t dup[2]={r,r};assert(dhcp_reservations_save(dup,2,-1)==ESP_ERR_INVALID_ARG);
    assert(dhcp_reservations_save(&r,1,0)==ESP_OK);reboot();
    assert(!s_state.enabled);assert(dhcp_reservations_lookup(a)==IP(4));assert(!available_cb(b,IP(4)));
    /* Failed writes/commit leave RAM and committed NVS intact. */
    fresh();assert(dhcp_reservations_save(NULL,0,1)==ESP_OK);
    fail_write=true;assert(!ack_cb(a,IP(4)));assert(!dhcp_reservations_lookup(a));fail_write=false;
    fail_commit=true;assert(!ack_cb(a,IP(4)));assert(!dhcp_reservations_lookup(a));fail_commit=false;
    reboot();assert(!dhcp_reservations_lookup(a));assert(ack_cb(a,IP(4)));reboot();assert(dhcp_reservations_lookup(a)==IP(4));
    disk[30]^=1;reboot();assert(!s_healthy);assert(!available_cb(b,IP(3)));assert(!ack_cb(b,IP(3)));
    assert(dhcp_reservations_save(NULL,0,1)==ESP_ERR_INVALID_STATE);
    fresh();assert(dhcp_reservations_save(NULL,0,1)==ESP_OK);disk_size=5;reboot();assert(!s_healthy);
    /* Migration from old reservations; no fabricated sticky lease. */
    fresh();legacy[0]=reservation(a,IP(4));have_legacy=true;reboot();assert(s_healthy);assert(dhcp_reservations_lookup(a)==IP(4));assert(!available_cb(b,IP(4)));
    assert(ack_cb(a,IP(4)));reboot();assert(binding_sticky(&s_state,a)==IP(4));
    /* Live ACKed client becomes sticky when enabling mode. */
    fresh();live[0]=(dhcp_lease_info_t){.ip=IP(4),.acknowledged=true};memcpy(live[0].mac,a,6);live_count=1;
    r=reservation(a,IP(3));assert(dhcp_reservations_save(&r,1,1)==ESP_OK);assert(dhcp_reservations_lookup(a)==IP(4));
    r=reservation(b,IP(4));assert(dhcp_reservations_save(&r,1,1)==ESP_ERR_INVALID_ARG);
    /* Capacity refuses new ownership, never evicts an offline device. */
    fresh();assert(dhcp_reservations_save(NULL,0,1)==ESP_OK);
    for(int i=0;i<DHCP_STICKY_MAX;++i) { uint8_t mac[6]={2,0,0,0,1,(uint8_t)i};assert(ack_cb(mac,IP(i+2))); }
    assert(!ack_cb(a,IP(200)));reboot();assert(!available_cb(a,IP(2)));
    vSemaphoreDelete(s_mutex);puts("PASS: persistent ownership, conflicts, manual adoption, migration, failure/recovery, capacity");
    return 0;
}
