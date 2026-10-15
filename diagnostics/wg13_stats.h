#pragma once
#include <stdint.h>
/* Single WG consumer owns the live accumulator. No packet storage/allocations. */
enum { WG13_COUNT, WG13_TIME, WG13_EMPTY };
enum { WG13_WORK, WG13_CYCLE, WG13_CONTROL_PRE, WG13_CONTROL_MID,
       WG13_PEERS, WG13_ACTIVE, WG13_IDLE, WG13_TIMERS };
typedef struct { uint64_t n, sum, max; } wg13_timer_t;
typedef struct {
    int64_t start_us, end_us;
    uint64_t exits[2][3], wait[7], invalid_wait;
    wg13_timer_t timer[WG13_TIMERS];
} wg13_stats_t;
static inline void wg13_time(wg13_stats_t *s, unsigned t, int64_t start, int64_t end) {
    if (end < start) return;
    uint64_t us = (uint64_t)(end - start);
    wg13_timer_t *v = &s->timer[t];
    v->n++; v->sum += us; if (us > v->max) v->max = us;
}
static inline void wg13_wait(wg13_stats_t *s, int64_t enqueued, int64_t now) {
    if (enqueued <= 0 || now < enqueued) { s->invalid_wait++; return; }
    uint64_t us = (uint64_t)(now - enqueued);
    unsigned b = us < 1000 ? 0 : us < 4000 ? 1 : us < 10000 ? 2 :
                 us < 20000 ? 3 : us < 40000 ? 4 : us < 80000 ? 5 : 6;
    s->wait[b]++;
}
static inline void wg13_exit(wg13_stats_t *s, unsigned drain, int n, int cap, int budget_left) {
    /* Same precedence as the original short-circuit condition; no recheck. */
    s->exits[drain][n >= cap ? WG13_COUNT : !budget_left ? WG13_TIME : WG13_EMPTY]++;
}
