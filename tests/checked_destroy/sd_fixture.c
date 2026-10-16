#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdlib.h>
#include <stdatomic.h>
#ifdef _WIN32
#include <windows.h>
typedef CRITICAL_SECTION mutex_t;
static void lock(mutex_t *m) { EnterCriticalSection(m); }
static void unlock(mutex_t *m) { LeaveCriticalSection(m); }
#else
#include <pthread.h>
typedef pthread_mutex_t mutex_t;
static void lock(mutex_t *m) { assert(!pthread_mutex_lock(m)); }
static void unlock(mutex_t *m) { assert(!pthread_mutex_unlock(m)); }
#endif
static mutex_t mutex;
static mutex_t *s_ml_mutex;
#define portMAX_DELAY 0
static void xSemaphoreTake(mutex_t *m, int timeout) { (void)timeout; lock(m); }
static void xSemaphoreGive(mutex_t *m) { unlock(m); }
typedef struct { unsigned live; } microlink_t;
typedef struct { int coord, derp_tx, wg_mgr, net_io; } microlink_task_states_t;
typedef struct { int state, peer_count, peer_online; } microlink_diag_t;
static microlink_t *s_ml;
static atomic_bool done;
#define ESP_OK 0
static void check(microlink_t *ml) { assert(ml && ml->live==123); }
static char task_state_char(int state) { (void)state; return 'R'; }
static void microlink_get_task_states(microlink_t *ml, microlink_task_states_t *ts) {
    check(ml); *ts=(microlink_task_states_t){0};
}
static int microlink_get_diag(microlink_t *ml, microlink_diag_t *d) {
    check(ml); *d=(microlink_diag_t){0}; return ESP_OK;
}
static uint64_t microlink_get_last_derp_heartbeat_ms(microlink_t *ml) { check(ml); return 1; }
static uint64_t microlink_get_ctrl_last_rx_ms(microlink_t *ml) { check(ml); return 2; }
/* SETTER */
static void sample(void) {
    uint64_t now_ms=100;
    /* SAMPLE */
    /* HEARTBEAT */
    (void)coord; (void)derp; (void)wg; (void)netio;
    (void)ml_st; (void)peers; (void)online; (void)hb; (void)hb_age; (void)cr;
}
#ifdef _WIN32
static DWORD WINAPI reader(void *arg) {
#else
static void *reader(void *arg) {
#endif
    (void)arg;
    do { sample(); } while(!atomic_load(&done));
    return 0;
}
int main(void) {
    sdlog_set_microlink((void *)1); assert(!s_ml); /* pre-init fails closed */
#ifdef _WIN32
    InitializeCriticalSection(&mutex);
#else
    assert(!pthread_mutex_init(&mutex,NULL));
#endif
    s_ml_mutex=&mutex;
#ifdef _WIN32
    HANDLE thread=CreateThread(NULL,0,reader,NULL,0,NULL); assert(thread);
#else
    pthread_t thread; assert(!pthread_create(&thread,NULL,reader,NULL));
#endif
    for(int i=0;i<10000;i++) {
        microlink_t *ml=malloc(sizeof(*ml)); assert(ml); ml->live=123;
        sdlog_set_microlink(ml);
        sample();
        sdlog_set_microlink(NULL); /* must drain every in-flight read */
        ml->live=0; free(ml);
    }
    atomic_store(&done,1);
#ifdef _WIN32
    assert(WaitForSingleObject(thread,INFINITE)==WAIT_OBJECT_0); CloseHandle(thread);
    DeleteCriticalSection(&mutex);
#else
    assert(!pthread_join(thread,NULL)); assert(!pthread_mutex_destroy(&mutex));
#endif
    return 0;
}
