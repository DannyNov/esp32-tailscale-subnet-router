static uint64_t last_seen_for(const uint8_t mac[6]) {
    dhcp_remembered_t rows[DHCP_REMEMBERED_MAX];
    int n=dhcp_remembered_snapshot(rows,DHCP_REMEMBERED_MAX);
    for(int i=0;i<n;++i)if(!memcmp(rows[i].mac,mac,6))return rows[i].last_seen;
    return 0;
}
static void test_last_seen(void) {
    passive_reset();
    dhcp_reservation_t r=reservation(a,IP(4));
    assert(dhcp_reservations_save(&r,1,0)==ESP_OK);
    assert(!last_seen_for(a)); /* old dhcp_bind_v1 with no optional record */
    reboot();assert(!last_seen_for(a));
    wall_s=SEEN_MIN_TIME+100000;
    dhcp_last_seen_activity(a); /* same RAM-only function used by association */
    assert(last_seen_for(a)==(uint64_t)wall_s&&!seen_writes);
    seen_timer_cb(NULL);drain();assert(seen_writes==1&&seen_present);
    uint64_t saved=last_seen_for(a);
    wall_s+=60;observe(IP(4));assert(last_seen_for(a)==(uint64_t)wall_s);
    for(int i=0;i<100;++i) { ++wall_s;observe(IP(4));seen_checkpoint(NULL); }
    assert(seen_writes==1&&seen_disk.entries[0].unix_s==saved);
    /* UI/client resolve/ARP and station-cache refresh do not mark activity. */
    uint64_t before=last_seen_for(a);wall_s+=60;
    const char *source;bool conflict;
    dhcp_client_resolve(a,IP(4),IP(4),&source,&conflict);
    ap_passive_associations_changed();assert(last_seen_for(a)==before);
    associated_stations.num=0;observe(IP(4));assert(last_seen_for(a)==before);
    associated_stations.num=1;observe(IP(5));assert(last_seen_for(a)==before);
    arp_conflict=true;observe(IP(4));assert(last_seen_for(a)==before);arp_conflict=false;
    uint8_t h[74];make_frame(h,a,IP(4),20);h[22]^=1;
    struct pbuf invalid={h,34,34,NULL};clock_us+=1000000;
    ap_passive_observe(&invalid,&ap_netif);drain();assert(last_seen_for(a)==before);
    wall_s=0;observe(IP(4));assert(last_seen_for(a)==before); /* unset wall clock */
    wall_s=(time_t)saved+1201;clock_us+=SEEN_INTERVAL_US;
    observe(IP(4));seen_checkpoint(NULL);assert(seen_writes==2);
    saved=last_seen_for(a);reboot();associated_stations.num=0;
    assert(last_seen_for(a)==saved); /* offline API source, no DHCP/ARP/association */
    wall_s=0;dhcp_last_seen_activity(a);seen_checkpoint(NULL);
    assert(last_seen_for(a)==saved&&seen_writes==2);
    wall_s=(time_t)saved+30;dhcp_last_seen_activity(a);seen_checkpoint(NULL);
    assert(last_seen_for(a)==(uint64_t)wall_s&&seen_writes==2); /* reboot throttle */
    wall_s=(time_t)saved+1201;clock_us+=SEEN_INTERVAL_US;
    dhcp_last_seen_activity(a);seen_checkpoint(NULL);assert(seen_writes==3);
    saved=last_seen_for(a);wall_s=(time_t)saved-10;dhcp_last_seen_activity(a);
    assert(last_seen_for(a)==saved); /* backward correction */
    assert(binding_remember(&s_state,a,IP(4))); /* manual+sticky still one row */
    dhcp_remembered_t rows[DHCP_REMEMBERED_MAX];
    assert(dhcp_remembered_snapshot(rows,DHCP_REMEMBERED_MAX)==1&&rows[0].last_seen==saved);
    assert(dhcp_reservations_save(&r,1,0)==ESP_OK);reboot();assert(last_seen_for(a)==saved);
    /* Failed checkpoint retries are throttled; persistence never corrupts ownership. */
    wall_s=(time_t)saved+1300;clock_us+=SEEN_INTERVAL_US;dhcp_last_seen_activity(a);
    fail_commit=true;seen_checkpoint(NULL);unsigned w=seen_writes;
    fail_commit=false;seen_checkpoint(NULL);assert(seen_writes==w);
    reboot();assert(last_seen_for(a)==saved&&dhcp_reservations_lookup(a)==IP(4));
    seen_disk.checksum^=1;reboot();assert(!last_seen_for(a)&&s_healthy);
    /* Another MAC becoming due must not flush this MAC inside its window.
     * Checkpoint time (not activity time) governs the boundary after reboot. */
    passive_reset();r=reservation(a,IP(4));
    assert(dhcp_reservations_save(&r,1,0)==ESP_OK);
    wall_s=SEEN_MIN_TIME+100000;dhcp_last_seen_activity(a);
    saved=(uint64_t)wall_s;wall_s+=300;seen_checkpoint(NULL);assert(seen_writes==1);
    r=reservation(b,IP(5));dhcp_reservation_t pair[2]={reservation(a,IP(4)),r};
    assert(dhcp_reservations_save(pair,2,0)==ESP_OK);
    wall_s+=60;dhcp_last_seen_activity(a);dhcp_last_seen_activity(b);
    seen_checkpoint(NULL);assert(seen_writes==2);
    assert(seen_disk.entries[0].unix_s==saved);
    reboot();wall_s=(time_t)saved+1201;dhcp_last_seen_activity(a);
    seen_checkpoint(NULL);assert(seen_writes==2); /* save happened 300s after activity */
    wall_s=(time_t)saved+1501;dhcp_last_seen_activity(a);
    seen_checkpoint(NULL);assert(seen_writes==3);
    /* Full remembered capacity, plus transient churn: owners are never evicted. */
    passive_reset();assert(dhcp_reservations_save(NULL,0,1)==ESP_OK);
    wall_s=SEEN_MIN_TIME+200000;
    for(int i=0;i<DHCP_STICKY_MAX;++i) {
        uint8_t m[6]={2,0,0,0,1,(uint8_t)i};assert(ack_cb(m,IP(i+2)));dhcp_last_seen_activity(m);
    }
    dhcp_reservation_t manual[DHCP_RESERVATIONS_MAX];
    for(int i=0;i<DHCP_RESERVATIONS_MAX;++i) {
        uint8_t m[6]={2,0,0,0,2,(uint8_t)i};manual[i]=reservation(m,IP(i+150));
    }
    assert(dhcp_reservations_save(manual,DHCP_RESERVATIONS_MAX,0)==ESP_OK);
    for(int i=0;i<DHCP_RESERVATIONS_MAX;++i)dhcp_last_seen_activity(manual[i].mac);
    for(int i=0;i<100;++i) { uint8_t m[6]={2,0,0,0,3,(uint8_t)i};dhcp_last_seen_activity(m); }
    assert(dhcp_remembered_snapshot(rows,DHCP_REMEMBERED_MAX)==DHCP_REMEMBERED_MAX);
    for(int i=0;i<DHCP_REMEMBERED_MAX;++i)assert(rows[i].last_seen==(uint64_t)wall_s);
    seen_checkpoint(NULL);assert(seen_writes==1);reboot();
    assert(dhcp_remembered_snapshot(rows,DHCP_REMEMBERED_MAX)==DHCP_REMEMBERED_MAX);
    for(int i=0;i<DHCP_REMEMBERED_MAX;++i)assert(rows[i].last_seen==(uint64_t)wall_s);
    puts("PASS: Last seen association/passive RAM, stale/invalid rejection, throttle, reboot, unknown clock/recovery, OFF/manual/dedup, old/corrupt NVS, failures and bounded capacity");
}
