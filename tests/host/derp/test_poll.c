#include <assert.h>
#include <stdint.h>
#include <stddef.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#define MBEDTLS_ERR_SSL_WANT_READ -2
#define MBEDTLS_ERR_SSL_WANT_WRITE -3
#define MBEDTLS_ERR_SSL_TIMEOUT -4
#define DERP_FRAME_RECV_PACKET 5
#define ESP_LOGW(...) ((void)0)
#define pdMS_TO_TICKS(ms) ((ms)/10)
#define D_ALLOC(site,expr) (expr)
#define ml_psram_malloc malloc
typedef struct { struct { int connected,sockfd,ssl; } derp; } microlink_t;
static uint64_t now;
static int events[32],count,pos,dispatched,sleeps;
static size_t cursor;
static uint8_t wire[128];
static uint64_t ml_get_time_ms(void) { return now; }
static void vTaskDelay(int ticks) { assert(ticks>=1); sleeps++; now+=ticks*10; }
static int mbedtls_ssl_read(int *ssl,unsigned char *buf,size_t len) {
    (void)ssl; int n=pos<count?events[pos++]:MBEDTLS_ERR_SSL_WANT_READ;
    if(n>0) { assert((size_t)n<=len); memcpy(buf,wire+cursor,n);cursor+=n; }
    return n;
}
static void dispatch_derp_frame(microlink_t *ml,uint8_t type,uint8_t *key,uint8_t *payload,size_t len) {
    (void)ml;(void)type;(void)key;(void)len;dispatched++;free(payload);
}
#include "../../../tools/derp_read_header.inc"
#include "poll_under_test.inc"
static void run(uint32_t size,const int *seq,int n,int result,int dispatch) {
    now=0;pos=0;count=n;cursor=0;dispatched=0;sleeps=0;memcpy(events,seq,n*sizeof(int));
    memset(wire,0,sizeof(wire));wire[0]=6;
    wire[1]=(uint8_t)(size>>24);wire[2]=(uint8_t)(size>>16);wire[3]=(uint8_t)(size>>8);wire[4]=(uint8_t)size;
    microlink_t ml={.derp={.connected=1,.sockfd=1}};
    assert(poll_derp_read(&ml)==result);assert(dispatched==dispatch);
}
#define CASE(size,ret,d,...) do { int s[]={__VA_ARGS__};run(size,s,sizeof(s)/sizeof(s[0]),ret,d); } while(0)
int main(void) {
    CASE(0,1,1,1,1,3); /* fragmented zero-length keepalive */
    CASE(3,1,1,1,-2,4,1,-3,2); /* header and payload fragmentation */
    CASE(3,-1,0,5,0); /* EOF payload must reconnect, never idle */
    CASE(3,-8,0,5,1,-8);
    CASE(3,-4,0,5,-4);
    CASE(3,-1,0,5); /* perpetual payload WANT, bounded and sleeping */
    assert(sleeps>0);
    CASE(65537,-1,0,5);
    CASE(0x80000000u,-1,0,5); /* BE32 high bit, no signed shift */
    CASE(3,0,0,-2); /* idle before header */
    puts("PASS: 9 production poll fragmentation/payload/EOF/error/deadline/length cases");
}
