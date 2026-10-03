/* Independent optional NVS record; dhcp_bind_v1 remains byte-for-byte compatible.
 * Events update RAM under the bindings mutex. Only TCP/IP checkpoints write NVS.
 * Never infer activity from a snapshot, station-list refresh or ARP cache. */
#define SEEN_MIN_TIME 1704067200ULL /* 2024-01-01; unset ESP clock is 1970 */
#define SEEN_INTERVAL_US (1200LL * 1000000LL)
#define SEEN_RAM_MAX (DHCP_REMEMBERED_MAX + DHCP_OBSERVATIONS_MAX)
typedef struct { uint8_t mac[6], pad[2]; uint64_t unix_s, checkpoint_s; } seen_entry_t;
typedef struct {
    uint32_t version, checksum;
    seen_entry_t entries[DHCP_REMEMBERED_MAX];
} seen_blob_t;
_Static_assert(sizeof(seen_entry_t) == 24, "Last seen entry NVS ABI");
_Static_assert(sizeof(seen_blob_t) == 8 + 24 * DHCP_REMEMBERED_MAX, "Last seen blob NVS ABI");
typedef struct { seen_entry_t entry; int64_t attempt_us; bool attempted; } seen_ram_t;
static seen_ram_t s_seen[SEEN_RAM_MAX];
static seen_blob_t s_seen_disk;
static esp_timer_handle_t s_seen_timer;
static esp_err_t s_seen_error;

static uint32_t seen_checksum(const seen_blob_t *blob)
{
    const uint8_t *p = (const uint8_t *)blob->entries;
    uint32_t hash = 2166136261u;
    for (size_t i = 0; i < sizeof blob->entries; ++i) hash = (hash ^ p[i]) * 16777619u;
    return hash;
}
static bool seen_owned(const uint8_t mac[6]) { return binding_lookup(&s_state, mac) != 0; }
/* Mutex held. Keep all remembered owners; only transient history may be evicted. */
static seen_ram_t *seen_slot(const uint8_t mac[6], bool create)
{
    seen_ram_t *empty = NULL, *oldest = NULL;
    for (int i = 0; i < SEEN_RAM_MAX; ++i) {
        seen_ram_t *r = &s_seen[i];
        if (!memcmp(r->entry.mac, mac, 6)) return r;
        if (!binding_mac_valid(r->entry.mac)) { if (!empty) empty = r; }
        else if (!seen_owned(r->entry.mac) && (!oldest || r->entry.unix_s < oldest->entry.unix_s)) oldest = r;
    }
    if (!create) return NULL;
    seen_ram_t *r = empty ? empty : oldest;
    if (r) { memset(r, 0, sizeof(*r)); memcpy(r->entry.mac, mac, 6); }
    return r;
}
void dhcp_last_seen_activity(const uint8_t mac[6])
{
    if (!s_mutex || !binding_mac_valid(mac)) return;
    time_t now = time(NULL);
    if (now < (time_t)SEEN_MIN_TIME) return;
    LOCK();
    seen_ram_t *r = seen_slot(mac, true);
    /* A backwards clock correction must not destroy the latest known activity. */
    if (r && (uint64_t)now > r->entry.unix_s) r->entry.unix_s = (uint64_t)now;
    UNLOCK();
}
static void seen_load(void)
{
    memset(s_seen, 0, sizeof s_seen);
    memset(&s_seen_disk, 0, sizeof s_seen_disk);
    s_seen_error = ESP_OK;
    nvs_handle_t nvs;
    esp_err_t err = nvs_open(NVS_NAMESPACE, NVS_READONLY, &nvs);
    if (err == ESP_OK) {
        size_t size = sizeof s_seen_disk;
        err = nvs_get_blob(nvs, "dhcp_seen_v1", &s_seen_disk, &size);
        nvs_close(nvs);
        if (err == ESP_OK && (size != sizeof s_seen_disk || s_seen_disk.version != 1 ||
            s_seen_disk.checksum != seen_checksum(&s_seen_disk))) err = ESP_ERR_INVALID_STATE;
        if (err == ESP_OK) for (int i = 0; i < DHCP_REMEMBERED_MAX; ++i) {
            seen_entry_t *e = &s_seen_disk.entries[i];
            if (!e->unix_s) continue;
            if (!binding_mac_valid(e->mac) || e->unix_s < SEEN_MIN_TIME || e->checkpoint_s < e->unix_s) { err = ESP_ERR_INVALID_STATE; break; }
            for (int j = 0; j < i; ++j)
                if (s_seen_disk.entries[j].unix_s && !memcmp(e->mac, s_seen_disk.entries[j].mac, 6)) err = ESP_ERR_INVALID_STATE;
        }
    }
    if (err != ESP_OK) {
        memset(&s_seen_disk, 0, sizeof s_seen_disk);
        if (err != ESP_ERR_NVS_NOT_FOUND) s_seen_error = err;
    }
    for (int i = 0; i < DHCP_REMEMBERED_MAX; ++i) if (s_seen_disk.entries[i].unix_s) {
        s_seen[i].entry = s_seen_disk.entries[i];
    }
}
/* One blob transaction includes only due MACs. Non-due entries retain their
 * previous checkpoint, so another MAC cannot bypass their write throttle. */
static void seen_checkpoint(void *arg)
{
    (void)arg;
    if (!s_healthy) return;
    seen_blob_t *next = malloc(sizeof(*next));
    if (!next) return;
    *next = s_seen_disk;
    bool dirty = false;
    int64_t uptime = esp_timer_get_time();
    time_t wall = time(NULL);
    if (wall < (time_t)SEEN_MIN_TIME) { free(next); return; }
    LOCK();
    for (int i = 0; i < SEEN_RAM_MAX; ++i) {
        seen_ram_t *r = &s_seen[i];
        if (!r->entry.unix_s || !seen_owned(r->entry.mac)) continue;
        seen_entry_t *saved = NULL, *empty = NULL;
        for (int j = 0; j < DHCP_REMEMBERED_MAX; ++j) {
            seen_entry_t *e = &next->entries[j];
            if (e->unix_s && !memcmp(e->mac, r->entry.mac, 6)) saved = e;
            if ((!e->unix_s || !seen_owned(e->mac)) && !empty) empty = e;
        }
        if (saved && saved->unix_s >= r->entry.unix_s) continue;
        if (r->attempted && uptime - r->attempt_us < SEEN_INTERVAL_US) continue;
        /* Across reboot, use the saved checkpoint time conservatively as a write
         * boundary. Invalid/backwards time never accelerates flash writes. */
        if (!r->attempted && saved && (wall < (time_t)SEEN_MIN_TIME ||
            (uint64_t)wall < saved->checkpoint_s + 1200)) continue;
        seen_entry_t *target = saved ? saved : empty;
        if (!target) continue;
        r->attempted = true; r->attempt_us = uptime; /* failed writes also throttled */
        *target = r->entry;
        target->checkpoint_s = (uint64_t)wall > target->unix_s ? (uint64_t)wall : target->unix_s;
        dirty = true;
    }
    UNLOCK();
    if (dirty) {
        next->version = 1; next->checksum = seen_checksum(next);
        nvs_handle_t nvs;
        esp_err_t err = nvs_open(NVS_NAMESPACE, NVS_READWRITE, &nvs);
        if (err == ESP_OK) {
            err = nvs_set_blob(nvs, "dhcp_seen_v1", next, sizeof(*next));
            if (err == ESP_OK) err = nvs_commit(nvs);
            nvs_close(nvs);
        }
        LOCK(); s_seen_error = err; UNLOCK();
        if (err == ESP_OK) s_seen_disk = *next;
        else ESP_LOGW(TAG, "Last seen checkpoint failed: %s", esp_err_to_name(err));
    }
    free(next);
}
static void seen_timer_cb(void *arg)
{
    (void)arg;
    /* Nonblocking timer handoff; all NVS mutations remain serialized on TCP/IP. */
    (void)tcpip_callback_with_block(seen_checkpoint, NULL, 0);
}
static void seen_start(void)
{
    if (s_seen_timer) return;
    const esp_timer_create_args_t args = {.callback = seen_timer_cb, .name = "dhcp_seen"};
    esp_err_t err = esp_timer_create(&args, &s_seen_timer);
    if (err == ESP_OK) err = esp_timer_start_periodic(s_seen_timer, 60000000);
    if (err != ESP_OK) { s_seen_error = err; ESP_LOGW(TAG, "Last seen timer failed: %s", esp_err_to_name(err)); }
}
