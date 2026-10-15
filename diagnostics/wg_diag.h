#pragma once
#include <stdint.h>
#include <stddef.h>
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "esp_timer.h"

enum { D_DIRECT, D_DERP, D_PATHS };
enum { D_RX, D_BYTES, D_ENQUEUE, D_DROP, D_DEQUEUE, D_TX, D_TX_ERROR,
       D_TX_EVICT, D_READ_ERROR, D_DECRYPT_OK, D_DECRYPT_ERROR,
       D_FORWARD_OK, D_FORWARD_ERROR, D_REPLAY, D_POLICY_DROP,
       D_TX_ENQUEUE, D_TX_DROP, D_INIT, D_RESPONSE, D_COOKIE, D_DATA,
       D_OTHER, D_METRICS };
enum { D_PROCESS, D_PERIODIC, D_PROBES, D_LOOP, D_WAIT, D_DRAIN_GAP, D_LOOP_GAP, D_TX_LOCK, D_TX_CRYPTO, D_TX_SEND,
       D_TX_PBUF, D_TX_COPY, D_RX_PBUF, D_RX_COPY, D_RX_DEC_PBUF,
       D_RX_DECRYPT, D_RX_LWIP, D_RX_HS, D_RX_DATA, D_TIMERS };
void wg_diag_tx(unsigned stage, int err);
void wg_diag_burst(int accepted, int64_t now);
void wg_diag_drain(int64_t now);
void wg_diag_loop_gap(int64_t now);
void wg_diag_add(unsigned path, unsigned metric, uint32_t value);
void wg_diag_type(unsigned path, const uint8_t *data, size_t len);
void wg_diag_stack_sample(void);
void wg_diag_alloc_fail(unsigned site);
void wg_diag_time(unsigned timer, uint32_t us);
void wg_diag_source(unsigned path, const uint8_t key[32], uint32_t ip,
                    uint16_t port, size_t bytes, int accepted);
void wg_diag_peer(unsigned peer, int decrypt_ok);
void wg_diag_peer_tx(unsigned peer, int failed);
void wg_diag_peer_tx_bytes(unsigned peer, uint32_t bytes);
void wg_diag_wake(int active);
void wg_diag_sample_queue(unsigned q, QueueHandle_t queue);
/* wgopt4: only canonical transport DATA egress attempts, indexed by path.
 * path: 0 = direct UDP; 1 = DERP. Error is lwIP err_t (ERR_OK == 0).
 * Call is nonblocking and never retains packet bytes or sensitive keys. */
void wg_diag_wg4_tx(unsigned path, int result, uint32_t bytes);
void wg_diag_rx_alloc(unsigned stage);
void wg_diag_queue_config(unsigned cap, unsigned item_size);
/* wgopt9 scoped, passive direct-UDP to STA linkoutput error attribution. */
void wg9_direct_udp_begin(void);
void wg9_direct_udp_end(int err);
void wg9_sta_link_result(int err);
/* wgopt10: called only from raw Wi-Fi TX wraps / STA shape observation. */
void wg10_sta_pbuf_shape(int chained);
void wg10_wifi_driver_result(int raw_err, int by_ref);
int wg10_wifi_nomem_in_scope(void);
enum { WG12_ENQ, WG12_DONE, WG12_NOMEM, WG12_DROP, WG12_FULL,
       WG12_STOP, WG12_POSTFAIL, WG12_BACKLOG, WG12_COUNTERS };
void wg12_diag_add(unsigned event);
void wg_diag_start(void);
void wg_diag_report(void);
/* wgopt5: low-rate Wi-Fi + task profiling. Called from reporter only. */
void wg5_report(void);
/* GNU C: evaluates the original allocation once and preserves its type. */
#define D_ALLOC(site, expression) ({ __auto_type d_result = (expression); \
    if (!d_result) { wg_diag_alloc_fail(site); } d_result; })
