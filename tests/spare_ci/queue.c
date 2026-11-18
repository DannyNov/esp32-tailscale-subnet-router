/* Real MicroLink classification/dispatch, host FIFO/clock/diagnostic doubles. */
#include <pthread.h>
#include <time.h>
#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdlib.h>
#include <string.h>
#include <assert.h>
#include <stdio.h>
typedef int BaseType_t;
#define pdTRUE 1
#define ESP_LOGD(...) ((void)0)
enum{D_DIRECT,D_RX,D_BYTES,D_ENQUEUE,D_DROP};
typedef struct {uint8_t *data;size_t len;uint32_t src_ip;uint16_t src_port;bool via_derp;int64_t diag_enqueued_us;int diag;}ml_rx_packet_t;
typedef struct { pthread_mutex_t lock;unsigned read,write,count,peak;ml_rx_packet_t slots[128];} fifo;
typedef struct {fifo *stun_rx_queue,*disco_rx_queue,*wg_rx_queue;unsigned dq_udp_attempt,dq_udp_drop;}microlink_t;
static uint64_t diag[5],released,received,lat_total,lat_max;static uint64_t lat_hist[5];
static int64_t virtual_us;
static int64_t esp_timer_get_time(void){return virtual_us;}
static void tracked_free(void *p){if(p)__atomic_add_fetch(&released,1,__ATOMIC_RELAXED);free(p);}
static BaseType_t xQueueSend(void *opaque,const void *item,unsigned ticks){
 fifo*q=opaque;assert(ticks==0);pthread_mutex_lock(&q->lock);
 if(q->count==128){pthread_mutex_unlock(&q->lock);return 0;}
 q->slots[q->write]=*(const ml_rx_packet_t*)item;q->write=(q->write+1)%128;q->count++;if(q->count>q->peak)q->peak=q->count;
 pthread_mutex_unlock(&q->lock);return pdTRUE;
}
static bool pop(fifo*q,ml_rx_packet_t*out){pthread_mutex_lock(&q->lock);bool ok=q->count!=0;
 if(ok){*out=q->slots[q->read];q->read=(q->read+1)%128;q->count--;}pthread_mutex_unlock(&q->lock);return ok;}
static void wg_diag_type(int d,const uint8_t*p,size_t n){(void)d;(void)p;(void)n;}
static int dp_start(int x){return x;}
static void wg_diag_burst(bool ok,int64_t t){(void)ok;(void)t;}
static void wg_diag_add(int d,int key,uint64_t n){(void)d;diag[key]+=n;}
static void wg_diag_sample_queue(int d,void*q){(void)d;(void)q;}
static void wg_diag_source(int d,void*p,uint32_t ip,uint16_t port,size_t n,bool ok){(void)d;(void)p;(void)ip;(void)port;(void)n;(void)ok;}
#define free tracked_free
static const uint8_t DISCO_MAGIC[6] = { 'T', 'S', 0xf0, 0x9f, 0x92, 0xac };

/* Packet classification */
typedef enum {
    PKT_DISCO,
    PKT_STUN,
    PKT_WIREGUARD,
    PKT_UNKNOWN,
} pkt_type_t;

static pkt_type_t classify_packet(const uint8_t *data, size_t len) {
    /* STUN: starts with 0x00 0x01 (binding request) or 0x01 0x01 (binding response) */
    if (len >= 20 && (data[0] == 0x00 || data[0] == 0x01) && data[1] == 0x01) {
        return PKT_STUN;
    }
    /* DISCO: starts with 6-byte magic */
    if (len >= 62 && memcmp(data, DISCO_MAGIC, 6) == 0) {
        return PKT_DISCO;
    }
    /* Everything else is WireGuard */
    if (len >= 4) {
        return PKT_WIREGUARD;
    }
    return PKT_UNKNOWN;
}

static void route_udp_packet(microlink_t *ml, uint8_t *data, size_t len,
                              uint32_t src_ip, uint16_t src_port) {
    pkt_type_t type = classify_packet(data, len);

    /* Log ALL direct UDP packets for debugging */
    ESP_LOGD(TAG, "UDP RX: %d bytes from %d.%d.%d.%d:%d type=%s hdr=%02x",
             (int)len,
             (int)((src_ip >> 24) & 0xFF), (int)((src_ip >> 16) & 0xFF),
             (int)((src_ip >> 8) & 0xFF), (int)(src_ip & 0xFF),
             (int)src_port,
             type == PKT_DISCO ? "DISCO" : type == PKT_STUN ? "STUN" :
             type == PKT_WIREGUARD ? "WG" : "UNK",
             len > 0 ? data[0] : 0xFF);

    ml_rx_packet_t pkt = {
        .data = data,
        .len = len,
        .src_ip = src_ip,
        .src_port = src_port,
        .via_derp = false,
    };

    switch (type) {
    case PKT_STUN:
        if (xQueueSend(ml->stun_rx_queue, &pkt, 0) != pdTRUE) {
            free(data);  /* Queue full, drop */
        }
        break;
    case PKT_DISCO:
        __atomic_add_fetch(&ml->dq_udp_attempt, 1, __ATOMIC_RELAXED); /* attempts */
        if (xQueueSend(ml->disco_rx_queue, &pkt, 0) != pdTRUE) {
            __atomic_add_fetch(&ml->dq_udp_drop, 1, __ATOMIC_RELAXED);
            free(data);
        }
        break;
    case PKT_WIREGUARD: {
        wg_diag_type(D_DIRECT, data, len);
        pkt.diag_enqueued_us = esp_timer_get_time();
        if(len>=32 && data[0]==4 && !data[1] && !data[2] && !data[3])pkt.diag=dp_start(0);
        BaseType_t accepted = xQueueSend(ml->wg_rx_queue, &pkt, 0);
        wg_diag_burst(accepted == pdTRUE, pkt.diag_enqueued_us);
        wg_diag_add(D_DIRECT, D_RX, 1);
        wg_diag_add(D_DIRECT, D_BYTES, len);
        wg_diag_add(D_DIRECT, accepted == pdTRUE ? D_ENQUEUE : D_DROP, 1);
        wg_diag_sample_queue(0, ml->wg_rx_queue);
        wg_diag_source(D_DIRECT, NULL, src_ip, src_port, len, accepted == pdTRUE);
        if (accepted != pdTRUE) {
            static uint32_t wg_rx_drops = 0;
            if ((++wg_rx_drops & 0x1F) == 1)
                ESP_LOGD(TAG, "WG-RX(direct) queue full: dropped %lu",
                         (unsigned long)wg_rx_drops);
            free(data);  /* Queue full, drop */
        }
        break;
    }
    default:
        free(data);
        break;
    }
}

#undef free

static fifo wg,disco,stun;static microlink_t ctx;static int initialized;
void reset(void){
 if(initialized){assert(wg.count==0&&disco.count==0&&stun.count==0);pthread_mutex_destroy(&wg.lock);pthread_mutex_destroy(&disco.lock);pthread_mutex_destroy(&stun.lock);}
 memset(&wg,0,sizeof wg);memset(&disco,0,sizeof disco);memset(&stun,0,sizeof stun);
 memset(diag,0,sizeof diag);released=0;
 pthread_mutex_init(&wg.lock,0);pthread_mutex_init(&disco.lock,0);pthread_mutex_init(&stun.lock,0);
 ctx=(microlink_t){&stun,&disco,&wg,0,0};initialized=1;
}
int offer(unsigned char *data,int n,long long now){
 virtual_us=now;unsigned old=wg.count;uint8_t*p=malloc(n);assert(p);memcpy(p,data,n);
 route_udp_packet(&ctx,p,n,1,2);return wg.count==old+1;
}
int take(unsigned char *data,int n){
 ml_rx_packet_t p;if(!pop(&wg,&p))return 0;assert(p.len==(size_t)n);
 memcpy(data,p.data,n);tracked_free(p.data);return 1;
}
int depth(void){return wg.count;}
int freed(void){return released;}

#include "queue-main.inc"
