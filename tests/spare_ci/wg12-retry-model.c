/* Synthetic retry/lifetime tests for the archived WG12 algorithm.
 * This does not compile production lwIP and does not reproduce the live PANIC.
 */
#include <assert.h>
#include <stdbool.h>
#include <stdio.h>

typedef struct { unsigned refs; bool dead; } pbuf_mock;
typedef struct { pbuf_mock *p; bool queued; unsigned tries; } wg_queue;
typedef enum { SEND_OK, SEND_ERR_MEM } send_result;
static unsigned freed;
static void ref(pbuf_mock *p) { assert(p && !p->dead && p->refs); ++p->refs; }
static void unref(pbuf_mock *p) {
    assert(p && !p->dead && p->refs);
    if (--p->refs == 0) { p->dead=true; ++freed; }
}
static void enqueue(wg_queue *q, pbuf_mock *p) {
    assert(!q->queued);
    ref(p); q->p=p; q->queued=true; q->tries=0;
}
static bool can_prepend_ipv4(const pbuf_mock *p) {
    return p && !p->dead && p->refs == 1;
}
/* Model the archived WG12 retry policy: keep queue's reference on ERR_MEM. */
static void complete(wg_queue *q, send_result result, bool permit_retry) {
    assert(q->queued && q->p);
    if (result == SEND_ERR_MEM && permit_retry && q->tries < 1) {
        ++q->tries;
        return;  /* FIFO owns its original reference */
    }
    unref(q->p);
    q->p=NULL; q->queued=false;
}
int main(void) {
    /* Normal ERR_MEM, lower layer does not retain the pbuf. */
    pbuf_mock normal={.refs=1};
    wg_queue q={0};
    enqueue(&q,&normal);
    unref(&normal);                  /* caller's reference released */
    assert(can_prepend_ipv4(q.p));
    complete(&q,SEND_ERR_MEM,true);
    assert(q.queued && q.tries==1 && can_prepend_ipv4(q.p));
    complete(&q,SEND_OK,true);
    assert(normal.dead && freed==1);

    /* Hypothetical ERR_MEM after downstream has retained a reference:
     * a second send would violate the exclusive-pbuf requirement.
     * The model detects it; it does not assert ESP-IDF behaves this way.
     */
    pbuf_mock held={.refs=1};
    wg_queue q2={0};
    enqueue(&q2,&held);
    unref(&held);
    ref(&held);                      /* hypothetical downstream retention */
    assert(held.refs==2 && !can_prepend_ipv4(&held));
    complete(&q2,SEND_ERR_MEM,true);
    assert(q2.queued && !can_prepend_ipv4(q2.p));
    complete(&q2,SEND_ERR_MEM,false); /* stop instead of unsafe reuse */
    assert(!held.dead && held.refs==1);
    unref(&held);
    assert(held.dead && freed==2);

    /* A distinct exclusive copy can meet the contract while the original
     * remains shared. This is a model, not a proposed production patch.
     */
    pbuf_mock original={.refs=2}, copy={.refs=1};
    assert(!can_prepend_ipv4(&original));
    assert(can_prepend_ipv4(&copy));
    unref(&copy);
    unref(&original); unref(&original);
    assert(freed==4);
    puts("WG12 retry model: exclusive=PASS, retained-on-error=DETECTED, copy=PASS");
    return 0;
}
