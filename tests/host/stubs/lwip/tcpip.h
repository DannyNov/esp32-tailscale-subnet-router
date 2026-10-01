#pragma once
typedef int err_t;
#define ERR_OK 0
static inline err_t tcpip_callback(void (*cb)(void*), void *arg) { cb(arg); return ERR_OK; }
err_t tcpip_callback_with_block(void (*cb)(void*), void *arg, int block);
