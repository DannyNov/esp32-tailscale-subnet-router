#include "host_stubs.h"
#include <assert.h>
#include <stdlib.h>
#include <stdatomic.h>
#include <sched.h>

/* generated_snapshot_functions.c is the EXACT FUNCTIONS string in apply_patch.py */
#include "generated_snapshot_functions.c"

static microlink_t *new_ml(unsigned serial) {
    microlink_t *ml = calloc(1, sizeof(*ml));
    assert(ml);
    ml->serial=serial;
    ml->connected=true;
    ml->peer.vpn_ip=0x0a00000a;
    ml->peer.online=true;
    ml->peer.derp_region=5;
    ml->peer.subnet_route_count=1;
    ml->peer.subnet_routes[0]=(microlink_route_t){.network=0xc0000200,.prefix_len=24};
    snprintf(ml->peer.hostname,sizeof ml->peer.hostname,"peer-%u",serial);
    snprintf(ml->region,sizeof ml->region,"city-%u",serial);
    return ml;
}

static void basic_tests(void) {
    microlink_diag_t d={0};
    tailscale_status_snapshot_t stat;
    tailscale_peer_snapshot_t peer;
    microlink_derp_rtt_t rtts[4];
    char region[64] = "placeholder";
    assert(!tailscale_snapshot_diag(NULL));
    assert(!tailscale_snapshot_status(&stat));
    assert(stat.peer_count==0);
    assert(!tailscale_snapshot_region_name(1,5,region,sizeof region));
    assert(region[0]==0);
    assert(!tailscale_snapshot_peer(1,0,&peer));
    assert(!tailscale_snapshot_derp_rtts(1,rtts,4));
    s_life_mux=NULL;
    assert(!tailscale_snapshot_diag(&d));
    s_life_mux=&master_mu;
    assert(!pthread_mutex_lock(&master_mu));
    assert(!tailscale_snapshot_status(&stat));
    assert(!pthread_mutex_unlock(&master_mu));
    s_microlink=new_ml(23);
    s_life_generation=9;
    assert(tailscale_snapshot_diag(&d));
    assert(d.vpn_ip==0x0a00000a);
    assert(tailscale_snapshot_status(&stat));
    assert(stat.generation==9 && stat.connected && stat.peer_count==1 && stat.peers_online==1);
    assert(!tailscale_snapshot_peer(8,0,&peer));
    assert(tailscale_snapshot_peer(9,0,&peer));
    assert(!strcmp(peer.derp_region_name,"city-23"));
    assert(tailscale_snapshot_derp_rtts(9,rtts,4)==1 && rtts[0].rtt_ms==42);
    assert(tailscale_snapshot_region_name(9,5,region,sizeof region) && !strcmp(region,"city-23"));
    assert(!tailscale_snapshot_region_name(9,0,region,sizeof region));
    assert(!tailscale_snapshot_region_name(9,5,region,0));
    assert(!pthread_mutex_lock(&master_mu));
    microlink_t *old=s_microlink;
    s_microlink=NULL;
    s_life_generation++;
    free(old);
    assert(!pthread_mutex_unlock(&master_mu));
    assert(!strcmp(peer.derp_region_name,"city-23"));
    assert(!strcmp(peer.peer.hostname,"peer-23"));
    assert(!tailscale_snapshot_peer(9,0,&peer));
    assert(peer.derp_region_name[0]==0);
}

static atomic_int active_readers=0;
static void *reader(void *unused) {
    (void)unused;
    for(int i=0;i<18000;i++) {
        tailscale_status_snapshot_t stat;
        if(tailscale_snapshot_status(&stat)) {
            tailscale_peer_snapshot_t peer;
            if(tailscale_snapshot_peer(stat.generation,0,&peer)) {
                assert(peer.peer.vpn_ip==0x0a00000a);
                assert(peer.derp_region_name[0]=='c');
            }
        }
        microlink_diag_t d;
        (void)tailscale_snapshot_diag(&d);
    }
    atomic_fetch_sub(&active_readers,1);
    return NULL;
}
static void concurrency_tests(void) {
    pthread_t threads[6];
    atomic_store(&active_readers,6);
    for(int i=0;i<6;i++) assert(!pthread_create(&threads[i],NULL,reader,NULL));
    for(int i=0;i<10000;i++) {
        assert(!pthread_mutex_lock(&master_mu));
        microlink_t *prev=s_microlink;
        s_microlink=new_ml(i+1);
        s_life_generation++;
        free(prev);
        assert(!pthread_mutex_unlock(&master_mu));
        if((i&63)==0) sched_yield();
    }
    for(int i=0;i<6;i++) assert(!pthread_join(threads[i],NULL));
    assert(atomic_load(&active_readers)==0);
    assert(!pthread_mutex_lock(&master_mu));
    free(s_microlink);s_microlink=NULL;
    assert(!pthread_mutex_unlock(&master_mu));
}
int main(void) {
    basic_tests();
    concurrency_tests();
    puts("PASS: pinned snapshot candidate, lifetime-safe under manager mutex; 6 readers + 10000 replacements");
}
