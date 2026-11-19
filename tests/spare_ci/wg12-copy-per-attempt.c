/* Host-only alternative ownership design, based on attested SPARE wg12 flow.
 * Payload queue owns bytes; every retry owns a *new* packet buffer.
 * Neither real ESP-IDF Wi-Fi driver behavior nor deployed SPARE is simulated.
 */
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>

typedef struct {
    unsigned refs;
    bool freed;
    uint8_t bytes[64];
} packet;
typedef struct {
    uint8_t bytes[64];
    bool pending;
    unsigned tries;
} queue;
static unsigned destroyed;
static packet *packet_new(const uint8_t data[64], bool available) {
    if (!available) return NULL;
    packet *p = calloc(1, sizeof *p);
    if (p) { p->refs=1; memcpy(p->bytes,data,64); }
    return p;
}
static void unref(packet *p) {
    assert(p && p->refs && !p->freed);
    if (--p->refs == 0) { p->freed=true; ++destroyed; free(p); }
}
static bool admit(queue *q, const uint8_t payload[64]) {
    if (q->pending) return false;
    memcpy(q->bytes,payload,64);
    q->pending=true;
    q->tries=0;
    return true;
}
enum outcome { OK, OOM, SHARED_AFTER_SEND };
/* Model only: on SHARED_AFTER_SEND, a lower layer acquired a reference. */
static enum outcome attempt(queue *q, bool available, bool retain_in_driver) {
    assert(q->pending);
    packet *p=packet_new(q->bytes,available);
    if (!p) return OOM;
    assert(p->refs == 1); /* no caller/queue reference to transmission pbuf */
    if (retain_in_driver) ++p->refs;
    unref(p); /* return from udp_sendto; caller releases its only reference */
    if (retain_in_driver) {
        /* Simulated later lower-layer completion. This attempt is independent
         * of the next, so an ERR_MEM/retry never reuses this pbuf. */
        unref(p);
        return SHARED_AFTER_SEND;
    }
    return OK;
}
int main(void) {
    uint8_t bytes[64]={4,0,0,0};
    queue q={0};
    assert(admit(&q,bytes));
    assert(!admit(&q,bytes)); /* queue full */
    assert(attempt(&q,false,false)==OOM);
    assert(q.pending && q.tries==0);
    ++q.tries;
    assert(attempt(&q,true,true)==SHARED_AFTER_SEND);
    assert(q.pending && q.tries==1);
    assert(attempt(&q,true,false)==OK);
    q.pending=false;
    assert(destroyed==2);
    for (unsigned i=0;i<200;i++) {
        bytes[4]=(uint8_t)i;
        assert(admit(&q,bytes));
        assert(attempt(&q,true,i%3==0)==(i%3==0?SHARED_AFTER_SEND:OK));
        q.pending=false;
    }
    assert(destroyed==202);
    puts("WG12 model alternative ownership: 202 distinct transmissions, no borrowed TX pbuf");
    return 0;
}
