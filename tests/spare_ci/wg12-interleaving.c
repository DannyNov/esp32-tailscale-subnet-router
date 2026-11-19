/* Synthetic ordering test based on archived WG12 queue ownership pattern.
 * Not extracted from the installed November 17 SPARE firmware.
 */
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>

typedef struct { unsigned refs; bool freed; } pbuf_mock;
typedef struct { pbuf_mock *p; bool pending; } queue_mock;

static void pbuf_ref_mock(pbuf_mock *p) { assert(p && !p->freed && p->refs > 0); p->refs++; }
static void pbuf_free_mock(pbuf_mock *p) {
    assert(p && !p->freed && p->refs > 0);
    if (--p->refs == 0) p->freed = true;
}
static void wg12_enqueue_mock(queue_mock *q, pbuf_mock *p) {
    assert(!q->pending);
    pbuf_ref_mock(p); /* queue acquires its own reference */
    q->p = p;
    q->pending = true;
}
static bool udp_sendto_ipv4_mock(pbuf_mock *p) {
    /* Historical ip4 output assert requires exclusive ownership. */
    return p && !p->freed && p->refs == 1;
}
static bool wg12_flush_mock(queue_mock *q) {
    assert(q->pending && q->p);
    pbuf_mock *p = q->p;
    q->p = 0;
    q->pending = false;
    bool accepted = udp_sendto_ipv4_mock(p);
    pbuf_free_mock(p); /* release queue-owned reference */
    return accepted;
}
int main(void) {
    /* Positive: original caller releases its ref before TCPIP callback. */
    pbuf_mock normal = {.refs = 1};
    queue_mock q1 = {0};
    wg12_enqueue_mock(&q1, &normal);
    assert(normal.refs == 2);
    pbuf_free_mock(&normal);
    assert(normal.refs == 1);
    assert(wg12_flush_mock(&q1));
    assert(normal.freed);

    /* Negative: TCPIP callback executes before caller drops its ref.
     * This demonstrates an ordering-dependent violation of ref == 1,
     * NOT proof the device executed in this order.
     */
    pbuf_mock overlap = {.refs = 1};
    queue_mock q2 = {0};
    wg12_enqueue_mock(&q2, &overlap);
    assert(overlap.refs == 2);
    assert(!wg12_flush_mock(&q2)); /* exclusive-ownership requirement fails */
    assert(!overlap.freed && overlap.refs == 1);
    pbuf_free_mock(&overlap);
    assert(overlap.freed);

    /* Extra independent borrower also prevents exclusive send. */
    pbuf_mock borrowed = {.refs = 1};
    queue_mock q3 = {0};
    wg12_enqueue_mock(&q3, &borrowed);
    pbuf_free_mock(&borrowed); /* caller drops its ref */
    pbuf_ref_mock(&borrowed);  /* another borrower retains a ref */
    assert(borrowed.refs == 2);
    assert(!wg12_flush_mock(&q3));
    assert(!borrowed.freed && borrowed.refs == 1);
    pbuf_free_mock(&borrowed);
    assert(borrowed.freed);

    puts("WG12 modeled ordering: normal=PASS, overlap=DETECTED, shared=DETECTED");
    return 0;
}
