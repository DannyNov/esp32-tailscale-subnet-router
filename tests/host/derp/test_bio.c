#include <assert.h>
#include <stdint.h>
#include <stddef.h>
#include <errno.h>
#include <stdio.h>
#define MBEDTLS_ERR_SSL_WANT_READ -2
#define MBEDTLS_ERR_SSL_TIMEOUT -4
#define MBEDTLS_ERR_NET_INVALID_CONTEXT -5
#define MBEDTLS_ERR_NET_CONN_RESET -6
#define MBEDTLS_ERR_NET_RECV_FAILED -7
#define DERP_CONNECT_TIMEOUT_MS 10000
#define SOL_SOCKET 1
#define SO_RCVTIMEO 2
struct timeval { long tv_sec, tv_usec; };
static int result;
static long timeout_ms;
static int ml_setsockopt(int fd,int level,int opt,const struct timeval *tv,size_t len) {
    (void)fd;(void)level;(void)opt;(void)len; timeout_ms=tv->tv_sec*1000+tv->tv_usec/1000;return 0;
}
static int ml_read_sock(int fd,unsigned char *buf,size_t len) {
    (void)fd;(void)buf;(void)len;return result;
}
#include "bio_under_test.inc"
int main(void) {
    int fd=1; unsigned char b[5]; result=-1;
    errno=EAGAIN; assert(ml_derp_bio_recv_timeout(&fd,b,5,20)==-2); assert(timeout_ms==20);
    errno=EWOULDBLOCK; assert(ml_derp_bio_recv_timeout(&fd,b,5,20)==-2);
    errno=EAGAIN; assert(ml_derp_bio_recv_timeout(&fd,b,5,10000)==-4);
    assert(ml_derp_bio_recv_timeout(&fd,b,5,0)==-4); assert(timeout_ms==10000);
    errno=EINTR; assert(ml_derp_bio_recv_timeout(&fd,b,5,20)==-2);
    errno=ECONNRESET; assert(ml_derp_bio_recv_timeout(&fd,b,5,20)==-6);
    errno=EPIPE; assert(ml_derp_bio_recv_timeout(&fd,b,5,20)==-6);
    errno=EINVAL; assert(ml_derp_bio_recv_timeout(&fd,b,5,20)==-7);
    result=0; assert(ml_derp_bio_recv_timeout(&fd,b,5,20)==0);
    result=1; assert(ml_derp_bio_recv_timeout(&fd,b,5,20)==1);
    fd=-1; assert(ml_derp_bio_recv_timeout(&fd,b,5,20)==-5);
    puts("PASS: 11 production BIO wait/handshake-timeout/EOF/error cases");
}
