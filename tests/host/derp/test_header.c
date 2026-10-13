#include <assert.h>
#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include <stdio.h>
#define MBEDTLS_ERR_SSL_WANT_READ -2
#define MBEDTLS_ERR_SSL_WANT_WRITE -3
#define MBEDTLS_ERR_SSL_TIMEOUT -4
typedef struct { struct { int connected, sockfd, ssl; } derp; } microlink_t;
static uint64_t now;
static int events[32], pos, count, sleeps, calls;
static size_t offset;
static const uint8_t wire[] = {5, 0, 0, 0, 82, 0xaa};
static uint64_t ml_get_time_ms(void) { return now; }
static void vTaskDelay(int ticks) { assert(ticks >= 1); sleeps++; now += 10; }
static int mbedtls_ssl_read(int *ssl, unsigned char *buf, size_t len) {
    (void)ssl; calls++;
    int n = pos < count ? events[pos++] : MBEDTLS_ERR_SSL_WANT_READ;
    if (n > 0) { assert((size_t)n <= len); memcpy(buf, wire + offset, n); offset += n; }
    return n;
}
#include "../../../tools/derp_read_header.inc"
static void run(const int *seq, int len, int expected, int wait) {
    memcpy(events, seq, len * sizeof(int)); count=len; pos=0; offset=0; now=0; sleeps=0; calls=0;
    microlink_t ml = {.derp={.connected=1,.sockfd=1}};
    uint8_t header[5]={0};
    assert(derp_poll_header(&ml, header) == expected);
    if (expected == 1) { assert(!memcmp(header, wire, 5)); assert(offset==5); }
    assert((sleeps > 0) == wait);
    assert(calls <= 503); /* finite retry bound with mock 10 ms ticks */
}
#define CASE(expect, wait, ...) do { int s[]={__VA_ARGS__}; run(s,sizeof(s)/sizeof(s[0]),expect,wait); } while(0)
int main(void) {
    CASE(1,0,5); CASE(1,0,1,4); CASE(1,0,2,3); CASE(1,0,1,1,3);
    CASE(1,1,1,-2,4); CASE(1,1,2,-3,-2,3);
    CASE(0,0,-2); CASE(0,0,-3);
    CASE(-1,0,0); CASE(-1,0,1,0);
    CASE(-8,0,-8); CASE(-8,0,2,-8); /* close_notify/fatal */
    CASE(-4,0,-4); CASE(-4,0,1,-4); /* TLS TIMEOUT terminal */
    CASE(-1,1,1); /* perpetual WANT: absolute 5-second deadline */
    microlink_t ml={.derp={.connected=0,.sockfd=1}}; uint8_t h[5];
    assert(derp_poll_header(&ml,h)==-1);
    ml.derp.connected=1; ml.derp.sockfd=-1; assert(derp_poll_header(&ml,h)==-1);
    puts("PASS: 17 header fragmentation/wait/EOF/error/deadline/disconnect cases");
}
