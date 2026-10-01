#pragma once
#include <stdint.h>
struct pbuf { const void *payload; uint16_t len, tot_len; struct pbuf *next; };
uint16_t pbuf_copy_partial(const struct pbuf *, void *, uint16_t, uint16_t);
