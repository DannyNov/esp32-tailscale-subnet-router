#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#define ESP_OK 0
#define ESP_FAIL -1
#define ESP_ERR_INVALID_ARG -2
#define ESP_ERR_TIMEOUT -3
#define pdPASS 1
#define pdTRUE 1
#define SHUT_RDWR 2
#define ML_EVT_SHUTDOWN_REQUEST 1
#define ML_CMD_DISCONNECT 2
#define ML_STATE_IDLE 0
#define ESP_LOGI(...) ((void)0)
#define ESP_LOGE(...) ((void)0)
#define ESP_LOGW(...) ((void)0)
#define TAG "test"
#define pdMS_TO_TICKS(x) (x)
typedef int esp_err_t;
typedef int BaseType_t;
typedef int ml_coord_cmd_t;
typedef void *QueueHandle_t;
typedef struct { void *data; } ml_rx_packet_t;
typedef struct { int unused; } ml_peer_update_t;
typedef struct microlink_s {
    int tasks_alive, state, disco_sock4, stun_sock, stun_sock6, coord_sock;
    bool stop_incomplete;
    struct { int sockfd; } derp;
    void *coord_tls, *events, *config_httpd;
    void *net_io_task, *derp_tx_task, *derp_rx_task, *coord_task, *wg_mgr_task;
    QueueHandle_t derp_tx_queue, disco_rx_queue, wg_rx_queue, stun_rx_queue;
    QueueHandle_t coord_cmd_queue, peer_update_queue;
    void *h2_acc, *lp_acc;
    int h2_acc_len, lp_acc_len;
    char machine_private_key[32], wg_private_key[32], disco_private_key[32];
} microlink_t;
static int freed, cleanup, delays, exit_after, created, fail_at, immediate;
static microlink_t *active;
void ml_task_exiting(microlink_t *ml);
static int shutdown(int fd, int how) { (void)fd; (void)how; return 0; }
static int esp_tls_get_conn_sockfd(void *tls, int *fd) { (void)tls; *fd=-1; return 0; }
static void xEventGroupSetBits(void *ev, int bits) { assert(ev); (void)bits; }
static int xQueueSend(void *q, void *p, int wait) { (void)q; (void)p; (void)wait; return 1; }
static void vTaskDelay(int ms) {
    (void)ms; delays++;
    if (exit_after && delays == exit_after) active->tasks_alive=0;
}
static void ml_config_httpd_stop(void *h) { (void)h; cleanup++; }
static void ml_config_httpd_deinit(void *h) { (void)h; cleanup++; }
static void ml_close_sock(int fd) { assert(fd>=0); cleanup++; }
static void ml_derp_disconnect(microlink_t *ml) { assert(ml->tasks_alive==0); cleanup++; }
static void ml_peer_nvs_deinit(void) { cleanup++; }
static int xQueueReceive(void *q, void *p, int wait) { (void)q; (void)p; (void)wait; return 0; }
static void vQueueDelete(void *q) { assert(q); cleanup++; }
static void vEventGroupDelete(void *q) { assert(q); cleanup++; }
static void counted_free(void *p) { if(p) freed++; free(p); }
#define free counted_free
#define ML_TASK_NET_IO_STACK 1
#define ML_TASK_NET_IO_PRIO 1
#define ML_TASK_NET_IO_CORE 1
#define ML_TASK_DERP_TX_STACK 1
#define ML_TASK_DERP_TX_PRIO 1
#define ML_TASK_DERP_TX_CORE 1
#define ML_TASK_COORD_STACK 1
#define ML_TASK_COORD_PRIO 1
#define ML_TASK_COORD_CORE 1
#define ML_TASK_WG_MGR_STACK 1
#define ML_TASK_WG_MGR_PRIO 1
#define ML_TASK_WG_MGR_CORE 1
#define ml_net_io_task 1
#define ml_derp_tx_task 2
#define ml_derp_rx_task 3
#define ml_coord_task 4
#define ml_wg_mgr_task 5
static int xTaskCreatePinnedToCore(int task, const char *name, int stack,
        microlink_t *ml, int priority, void **handle, int core) {
    (void)task; (void)name; (void)stack; (void)priority; (void)core;
    created++;
    assert(ml->tasks_alive>0); /* reservation exists even before return */
    if(created==fail_at) return 0;
    *handle=(void *)(uintptr_t)created;
    if(immediate) ml_task_exiting(ml);
    return pdPASS;
}
/* GENERATED */
static microlink_t *s_microlink;
static bool tailscale_connected;
static unsigned s_life_generation, tailscale_tunnel_ip;
static int held, detached;
static void life_lock(void) { assert(!held); held=1; }
static void life_unlock(void) { assert(held); held=0; }
static void sdlog_set_microlink(void *ml) { assert(!ml); detached++; }
/* MANAGER */
static microlink_t *instance(void) {
    microlink_t *ml=calloc(1,sizeof(*ml)); assert(ml);
    ml->events=(void *)1;
    ml->disco_sock4=10; ml->stun_sock=11; ml->stun_sock6=12;
    ml->coord_sock=-1; ml->derp.sockfd=-1;
    ml->config_httpd=(void *)1;
    ml->net_io_task=(void *)1;
    active=ml; freed=cleanup=delays=exit_after=created=fail_at=immediate=0;
    return ml;
}
int main(void) {
    assert(microlink_stop(NULL)==ESP_ERR_INVALID_ARG);
    assert(microlink_destroy_checked(NULL)==ESP_ERR_INVALID_ARG);
    microlink_t *ml=NULL;
    assert(microlink_destroy_checked(&ml)==ESP_OK);
    ml=instance(); ml->tasks_alive=1;
    microlink_t *saved=ml;
    assert(microlink_stop(ml)==ESP_ERR_TIMEOUT);
    assert(cleanup==0 && ml->net_io_task==(void *)1 && ml->disco_sock4==10);
    assert(microlink_destroy_checked(&ml)==ESP_ERR_TIMEOUT);
    assert(ml==saved && freed==0 && cleanup==0);
    ml_task_exiting(ml);
    assert(microlink_stop(ml)==ESP_OK);
    assert(ml->net_io_task==NULL && ml->disco_sock4==-1 && !ml->stop_incomplete);
    assert(microlink_stop(ml)==ESP_OK);
    assert(microlink_destroy_checked(&ml)==ESP_OK && ml==NULL && freed==1);
    assert(microlink_destroy_checked(&ml)==ESP_OK && freed==1);
    ml=instance(); ml->tasks_alive=5; exit_after=300;
    assert(microlink_destroy_checked(&ml)==ESP_OK && ml==NULL); /* deadline edge */
    for(int fail=1;fail<=6;fail++) {
        for(int fast=0;fast<=1;fast++) {
            ml=instance(); fail_at=fail; immediate=fast;
            int ret=create_tasks(ml);
            int successes=fail<=5 ? fail-1 : 5;
            assert(ret==(fail<=5 ? ESP_FAIL : ESP_OK));
            assert(ml->tasks_alive==(fast ? 0 : successes));
            if(ml->tasks_alive) {
                assert(microlink_destroy_checked(&ml)==ESP_ERR_TIMEOUT && ml);
                while(ml->tasks_alive) ml_task_exiting(ml);
            }
            assert(microlink_destroy_checked(&ml)==ESP_OK && ml==NULL && freed==1);
        }
    }
    s_microlink=instance(); s_microlink->tasks_alive=1; saved=s_microlink;
    assert(manager_prior()==ESP_ERR_TIMEOUT && s_microlink==saved && !freed);
    tailscale_disconnect();
    assert(s_microlink==saved && !freed && !held && !tailscale_connected);
    ml_task_exiting(s_microlink);
    tailscale_disconnect();
    assert(!s_microlink && freed==1 && !held);
    s_microlink=instance(); s_microlink->tasks_alive=1; saved=s_microlink;
    assert(manager_start_failed(ESP_FAIL)==ESP_ERR_TIMEOUT && s_microlink==saved);
    ml_task_exiting(s_microlink);
    assert(manager_start_failed(ESP_FAIL)==ESP_FAIL && !s_microlink && freed==1);
    s_microlink=instance();
    assert(manager_prior()==ESP_OK && !s_microlink && freed==1);
    assert(detached>=6);
    return 0;
}
