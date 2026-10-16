#include "host_stubs.h"
#include "generated_snapshot_functions.c"
#include <cjson/cJSON.h>
#include <assert.h>
#include <stdlib.h>
#include <limits.h>

typedef struct { int errors; } httpd_req_t;
static void httpd_resp_send_500(httpd_req_t *r) { r->errors++; }
static int tailscale_enabled=1;
static char *tailscale_hostname="test-node";
static char *tailscale_advertise_routes="192.0.2.0/24";
static uint32_t tailscale_exit_node_ip=0xc0000201;
/* SUPPORT */
static esp_err_t render_status(cJSON *root, httpd_req_t *req) {
/* STATUS */
    return ESP_OK;
}
static esp_err_t render_runtime(cJSON *root, httpd_req_t *req) {
/* RUNTIME_PEERS */
    return ESP_OK;
}
static unsigned allocation, fail_at=UINT_MAX, live;
static void *checked_malloc(size_t size) {
    if (allocation++==fail_at) return NULL;
    void *p=malloc(size); if(p)live++;
    return p;
}
static void checked_free(void *p) { if(p) { assert(live>0);live--;free(p); } }
static void instance(void) {
    s_microlink=calloc(1,sizeof(*s_microlink)); assert(s_microlink);
    s_microlink->connected=true;
    s_microlink->peer.vpn_ip=0xc0000201;
    s_microlink->peer.online=true; s_microlink->peer.derp_region=5;
    s_microlink->peer.subnet_route_count=1;
    s_microlink->peer.subnet_routes[0]=(microlink_route_t){.network=0xc0000200,.prefix_len=24};
    strcpy(s_microlink->peer.hostname,"peer-test"); strcpy(s_microlink->region,"test-region");
    s_life_generation=1;
}
int main(void) {
    cJSON_Hooks hooks={.malloc_fn=checked_malloc,.free_fn=checked_free};
    cJSON_InitHooks(&hooks);
    esp_err_t (*renderers[])(cJSON *, httpd_req_t *)={render_status,render_runtime};
    unsigned tested=0;
    for(unsigned renderer=0;renderer<2;renderer++) {
        unsigned maximum=0;
        for(unsigned pass=0;pass<2;pass++) {
            unsigned count=pass ? maximum : 1;
            for(unsigned point=0;point<count;point++) {
                instance(); fail_at=UINT_MAX;
                cJSON *root=cJSON_CreateObject(); assert(root);
                allocation=0;fail_at=pass ? point : UINT_MAX;
                httpd_req_t req={0};
                esp_err_t result=renderers[renderer](root,&req);
                if(!pass) maximum=allocation;
                fail_at=UINT_MAX;
                /* Destroy the instance before serializing the owned JSON strings. */
                free(s_microlink);s_microlink=NULL;
                if(pass) { assert(result==ESP_ERR_NO_MEM && req.errors==1);tested++; }
                else {
                    assert(result==ESP_OK && req.errors==0);
                    char *body=cJSON_PrintUnformatted(root);assert(body);
                    assert(strstr(body,"test-node") || strstr(body,"peer-test"));
                    cJSON_free(body);cJSON_Delete(root);
                }
                assert(live==0);
            }
        }
    }
    printf("PASS actual Web UI sections: %u allocation failure points, owned strings, cJSON %s\n",tested,cJSON_Version());
}
