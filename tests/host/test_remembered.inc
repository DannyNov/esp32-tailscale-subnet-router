static void test_remembered(void) {
    _Static_assert(sizeof(dhcp_bindings_t)==2380,"tuya6 NVS ABI changed");
    dhcp_remembered_t rows[DHCP_REMEMBERED_MAX];
    const char *source;bool conflict;
    passive_reset();observe(IP(4));
    assert(dhcp_remembered_snapshot(rows,DHCP_REMEMBERED_MAX)==0);
    assert(!available_cb(b,IP(4))); /* transient protects active owner */
    dhcp_reservation_t r=reservation(a,IP(9));strcpy(r.name,"Kitchen");
    assert(dhcp_reservations_save(&r,1,0)==ESP_OK); /* Reserve adopts actual IP even OFF */
    assert(dhcp_reservations_lookup(a)==IP(4));
    assert(dhcp_remembered_snapshot(rows,DHCP_REMEMBERED_MAX)==1);
    assert(rows[0].manual&&rows[0].ip==IP(4)&&!strcmp(rows[0].name,"Kitchen"));
    reboot();associated_stations.num=0;
    assert(dhcp_remembered_snapshot(rows,DHCP_REMEMBERED_MAX)==1); /* no leases/ARP/stations */
    assert(rows[0].manual&&rows[0].ip==IP(4));
    assert(dhcp_client_resolve(a,IP(7),IP(8),&source,&conflict)==IP(4));
    assert(conflict&&!strcmp(source,"persistent"));
    r.ip=IP(9);strcpy(r.name,"Renamed");
    assert(dhcp_reservations_save(&r,1,0)==ESP_OK);
    assert(dhcp_reservations_lookup(a)==IP(4)); /* name edit cannot reassign */
    assert(dhcp_remembered_snapshot(rows,1)==1&&!strcmp(rows[0].name,"Renamed"));

    passive_reset();assert(dhcp_reservations_save(NULL,0,1)==ESP_OK);observe(IP(4));
    assert(dhcp_remembered_snapshot(rows,DHCP_REMEMBERED_MAX)==1);
    assert(!rows[0].manual&&!rows[0].name[0]);
    assert(dhcp_reservations_save(NULL,0,0)==ESP_OK);reboot();
    assert(dhcp_remembered_snapshot(rows,DHCP_REMEMBERED_MAX)==1&&rows[0].ip==IP(4));
    assert(dhcp_client_resolve(a,0,0,&source,&conflict)==rows[0].ip&&!conflict);

    passive_reset();observe(IP(4));associated_stations.num=0;
    ap_passive_associations_changed();assert(!dhcp_clients_lookup(a));
    assert(available_cb(b,IP(4))); /* disconnected transient expires */
    associated_stations.num=1;observe(IP(5));assert(dhcp_clients_lookup(a)==IP(5));
    assert(dhcp_reservations_save(NULL,0,1)==ESP_OK); /* enable imports current observation */
    reboot();assert(dhcp_reservations_lookup(a)==IP(5));

    passive_reset();observe(IP(4));
    /* Fault-injected stale cache cannot override a confirmed persistent owner. */
    assert(binding_remember(&s_state,b,IP(4)));
    assert(!dhcp_clients_lookup(a));
    assert(!dhcp_client_resolve(a,IP(4),IP(4),&source,&conflict)&&conflict);
    assert(dhcp_clients_lookup(b)==IP(4));
    passive_reset();
    for(int i=0;i<DHCP_OBSERVATIONS_MAX;++i) {
        uint8_t m[6]={2,0,0,0,1,(uint8_t)i};
        assert(dhcp_reservations_observe(m,IP(i+2),true));
    }
    assert(!dhcp_reservations_observe(a,IP(50),true));
    assert(!writes); /* bounded RAM cache does not evict or spill to flash */
    puts("PASS: remembered offline/reboot/dedup/name/Reserve, immutable IP, OFF retention, disconnect/reconnect, stale cache priority");
}
