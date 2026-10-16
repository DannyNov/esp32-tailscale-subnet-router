static void assert_zero(const void *p, size_t n) {
    const unsigned char *b = p;
    for (size_t i=0; i<n; i++) assert(b[i]==0);
}
static void error_tests(void) {
    s_microlink=new_ml(1); s_life_generation=7;
    microlink_derp_rtt_t rtts[4];
    microlink_diag_t diag;
    tailscale_status_snapshot_t status;
    tailscale_peer_snapshot_t peer;
    char name[4];
    assert(!tailscale_snapshot_status(NULL));
    assert(!tailscale_snapshot_peer(7,0,NULL));
    assert(!tailscale_snapshot_region_name(7,5,NULL,1));
    assert(!tailscale_snapshot_derp_rtts(7,NULL,4));
    memset(rtts,0xa5,sizeof(rtts));
    assert(!tailscale_snapshot_derp_rtts(6,rtts,4)); assert_zero(rtts,sizeof(rtts));
    test_rtt_count=5;
    assert(!tailscale_snapshot_derp_rtts(7,rtts,4)); assert_zero(rtts,sizeof(rtts));
    test_rtt_count=-1;
    test_diag_error=true;
    assert(!tailscale_snapshot_diag(&diag)); assert_zero(&diag,sizeof(diag));
    assert(!tailscale_snapshot_status(&status)); assert_zero(&status,sizeof(status));
    test_diag_error=false; test_peer_error=true;
    assert(!tailscale_snapshot_peer(7,0,&peer)); assert_zero(&peer,sizeof(peer));
    test_peer_error=false;
    memset(s_microlink->peer.hostname,'x',sizeof(s_microlink->peer.hostname));
    assert(tailscale_snapshot_peer(7,0,&peer)); assert(peer.peer.hostname[63]==0);
    assert(tailscale_snapshot_region_name(7,5,name,sizeof(name))); assert(name[3]==0);
    assert(!tailscale_snapshot_peer(7,-1,&peer));
    assert(!tailscale_snapshot_peer(7,64,&peer));
    assert(!pthread_mutex_lock(&master_mu));
    memset(rtts,0xa5,sizeof(rtts));
    assert(!tailscale_snapshot_derp_rtts(7,rtts,4)); assert_zero(rtts,sizeof(rtts));
    assert(!tailscale_snapshot_diag(&diag)); assert_zero(&diag,sizeof(diag));
    assert(!tailscale_snapshot_peer(7,0,&peer)); assert_zero(&peer,sizeof(peer));
    assert(!tailscale_snapshot_region_name(7,5,name,sizeof(name))); assert(name[0]==0);
    assert(!pthread_mutex_unlock(&master_mu));
    free(s_microlink); s_microlink=NULL;
    puts("PASS integrated errors: stale generation, contention, getter errors, bounded strings and zero outputs");
}
