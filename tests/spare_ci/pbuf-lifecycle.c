/* Host-only ownership contract tests. Does not emulate real lwIP. */
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <string.h>

typedef struct { unsigned refs; bool freed; uint8_t data[16]; } pbuf_mock;
typedef struct { bool up; unsigned sends; } netif_mock;
static unsigned releases;
static void retain(pbuf_mock *p) { assert(p && !p->freed && p->refs); ++p->refs; }
static void release(pbuf_mock *p) { assert(p && !p->freed && p->refs); if (!--p->refs) { p->freed=true; ++releases; } }
/* Contract under test: only an exclusively owned outgoing buffer can be mutated. */
static bool encode_and_send(netif_mock *n, pbuf_mock *p) {
    if (!n || !n->up || !p || p->freed || p->refs != 1) return false;
    p->data[0] ^= 0x5a;
    ++n->sends;
    return true;
}
static bool copy_and_send(netif_mock *n, const pbuf_mock *src, bool allocation_ok) {
    if (!allocation_ok || !src || src->freed || !src->refs) return false;
    pbuf_mock own = { .refs=1 };
    memcpy(own.data, src->data, sizeof(own.data));
    bool ok = encode_and_send(n, &own);
    release(&own);
    return ok;
}
int main(void) {
    netif_mock n={.up=true};
    pbuf_mock sole={.refs=1};
    assert(encode_and_send(&n,&sole) && n.sends==1);
    release(&sole); assert(sole.freed && releases==1);

    pbuf_mock shared={.refs=1}; retain(&shared);
    assert(shared.refs==2 && !encode_and_send(&n,&shared));
    assert(copy_and_send(&n,&shared,true) && shared.refs==2 && !shared.freed);
    assert(!copy_and_send(&n,&shared,false));
    release(&shared); assert(shared.refs==1 && !shared.freed);
    release(&shared); assert(shared.freed && releases==3);

    pbuf_mock pending={.refs=1};
    n.up=false;
    assert(!encode_and_send(&n,&pending));
    n.up=true;
    assert(encode_and_send(&n,&pending));
    release(&pending); assert(pending.freed && releases==4);
    assert(!encode_and_send(&n,&pending));
    assert(!encode_and_send(NULL,&pending));
    return 0;
}
