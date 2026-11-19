/* Host model of lwIP 2.2.0-esp UDP + IPv4 header prepend behavior.
 * Audited against public esp-lwip 2.2.0-esp:
 * udp_sendto_if_src: pbuf_add_header(UDP_HLEN), ip_output_if_src,
 * ip4_output_if_opt_src: pbuf_add_header(IP_HLEN);
 * successful header additions are NOT undone by either function.
 *
 * NOT the installed ESP-IDF 6.1 SDK, not an ESP32 build or a device PANIC
 * reproduction. Tests the specific reusable-pbuf contract violation.
 */
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
enum { UDP_HLEN=8, IP_HLEN=20, DATA_LEN=1312, SPACE=96 };
typedef struct {
    uint8_t mem[SPACE+DATA_LEN];
    uint8_t *payload;
    unsigned len, tot_len, refs;
} pbuf;
static void init(pbuf *p) {
    memset(p,0,sizeof *p);
    p->payload=p->mem+SPACE; p->len=p->tot_len=DATA_LEN; p->refs=1;
    p->payload[0]=4; /* WG DATA type */
}
static bool add_header(pbuf *p,unsigned n) {
    if ((unsigned)(p->payload-p->mem)<n) return false;
    p->payload-=n; p->len+=n; p->tot_len+=n;
    return true;
}
static bool send_model(pbuf *p, bool wifi_nomem) {
    /* Same exclusive refcount predicate as IPv4 TX, before IP header. */
    assert(add_header(p,UDP_HLEN));
    if(p->refs!=1) return false; /* would trigger lwIP assert */
    assert(add_header(p,IP_HLEN));
    memset(p->payload,0x45,IP_HLEN); /* generated IPv4 header */
    return !wifi_nomem;
}
int main(void) {
    pbuf p;
    init(&p);
    uint8_t *start=p.payload;
    assert(p.payload[0]==4);
    assert(!send_model(&p,true)); /* lower layer ERR_MEM */
    assert(p.payload==start-28 && p.tot_len==DATA_LEN+28);
    /* WG12 retries the SAME pointer and does not reset its header. */
    assert(send_model(&p,false));
    assert(p.payload==start-56 && p.tot_len==DATA_LEN+56);
    /* A new distinct buffer starts at its initial offset on retry. */
    pbuf independent;
    init(&independent);
    assert(send_model(&independent,false));
    assert(independent.tot_len==DATA_LEN+28);
    /* A shared queue pbuf would violate refcount predicate. */
    pbuf shared;
    init(&shared);
    shared.refs=2;
    assert(!send_model(&shared,false));
    puts("Header model PASS: after ERR_MEM reused pbuf carries two header sets; new pbuf one");
    return 0;
}
