
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdbool.h>
#include <time.h>
#ifdef NDEBUG
#error Assertions required
#endif
typedef void *TaskHandle_t;typedef int esp_err_t;
typedef void *esp_http_client_handle_t;
typedef struct {const char*url;int method,timeout_ms;void*crt_bundle_attach;} esp_http_client_config_t;
#define ESP_OK 0
#define ESP_FAIL -1
#define HTTP_METHOD_GET 0
#define HTTP_METHOD_POST 1
#define MALLOC_CAP_SPIRAM 1
#define MALLOC_CAP_8BIT 2
#define NETTEST_CHUNK 4096
#define NETTEST_BYTES 1048576
#define NETTEST_UP_URL "mock"
#define NETTEST_DOWN_URL "mock"
#define esp_crt_bundle_attach NULL
#define ESP_LOGW(...) ((void)0)
#define vTaskDelete(x) return
typedef enum {NT_IDLE,NT_RUNNING,NT_DONE,NT_CANCELLED,NT_ERROR} nt_state_t;
static nt_state_t s_nt_state;static bool s_nt_cancel;static void*s_nt_task;static char s_nt_err[48];static unsigned s_nt_ms,s_nt_bytes;
static int status,header_fail,alloc_fail,open_fail,partial,allocated,clients,reads;static int64_t now_us;
static size_t fixture_strlcpy(char*d,const char*s,size_t n){size_t l=strlen(s);if(n){size_t c=l<n-1?l:n-1;memcpy(d,s,c);d[c]=0;}return l;}
static void*heap_caps_malloc(size_t n,int c){if(alloc_fail)return NULL;allocated++;return malloc(n);}
static void heap_caps_free(void*p){allocated--;free(p);}
static int ml_tls_time_ready(void){return 1;}
static int64_t esp_timer_get_time(void){now_us+=1000;return now_us;}
static void*esp_http_client_init(void*p){clients++;return (void*)1;}
static int esp_http_client_open(void*p,int n){return open_fail?-1:0;}
static int esp_http_client_fetch_headers(void*p){return header_fail?-1:NETTEST_BYTES;}
static int esp_http_client_get_status_code(void*p){return status;}
static int esp_http_client_read(void*p,char*b,int n){reads++;if(reads>(partial?3:NETTEST_BYTES/NETTEST_CHUNK))return 0;return n;}
static int esp_http_client_write(void*p,char*b,int n){return n;}
static int esp_http_client_get_and_clear_last_tls_error(void*p,int*a,int*b){*a=*b=0;return 0;}
static void esp_http_client_close(void*p){}
static void esp_http_client_cleanup(void*p){clients--;}
static void nettest_task(void *arg)
{
    bool up = ((intptr_t)arg) != 0;
    /* Diagnostic only: observe wall clock before the existing TLS handshake.
     * Never set time, alter certificate verification or log credentials. */
    time_t nt_wall = time(NULL);
    ESP_LOGW("NETTEST_CLOCK", "epoch=%lld uptime_us=%lld tls_clock_ready=%d",
             (long long)nt_wall, (long long)esp_timer_get_time(),
             (int)ml_tls_time_ready());
    char *buf = heap_caps_malloc(NETTEST_CHUNK, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
    if (!buf) {
        fixture_strlcpy(s_nt_err, "no memory", sizeof s_nt_err);
        s_nt_state = NT_ERROR; s_nt_task = NULL; vTaskDelete(NULL); return;
    }

    esp_http_client_config_t cfg = {
        .url               = up ? NETTEST_UP_URL : NETTEST_DOWN_URL,
        .method            = up ? HTTP_METHOD_POST : HTTP_METHOD_GET,
        .timeout_ms        = 5000,
        .crt_bundle_attach = esp_crt_bundle_attach,
    };
    esp_http_client_handle_t cl = esp_http_client_init(&cfg);
    if (!cl) {
        fixture_strlcpy(s_nt_err, "client init failed", sizeof s_nt_err);
        s_nt_state = NT_ERROR;
        heap_caps_free(buf); s_nt_task = NULL; vTaskDelete(NULL); return;
    }

    uint32_t total = 0;
    bool opened = false;
    bool response_ok = true;
    if (up) {
        memset(buf, 'x', NETTEST_CHUNK);
        if (esp_http_client_open(cl, NETTEST_BYTES) == ESP_OK) {
            opened = true;
            int64_t t0 = esp_timer_get_time();
            while (total < NETTEST_BYTES && !s_nt_cancel) {
                int n = (NETTEST_BYTES - total) < (uint32_t)NETTEST_CHUNK
                        ? (int)(NETTEST_BYTES - total) : NETTEST_CHUNK;
                int w = esp_http_client_write(cl, buf, n);
                if (w <= 0) break;
                total += w;
            }
            (void)esp_http_client_fetch_headers(cl);   /* complete the request */
            s_nt_ms = (uint32_t)((esp_timer_get_time() - t0) / 1000);
        }
    } else {
        if (esp_http_client_open(cl, 0) == ESP_OK) {
            opened = true;
            int64_t headers = esp_http_client_fetch_headers(cl);
            int status = esp_http_client_get_status_code(cl);
            response_ok = headers >= 0 && status >= 200 && status < 300;
            int64_t t0 = esp_timer_get_time();
            for (; response_ok;) {
                if (s_nt_cancel) break;
                int r = esp_http_client_read(cl, buf, NETTEST_CHUNK);
                if (r <= 0) break;
                total += r;
            }
            s_nt_ms = (uint32_t)((esp_timer_get_time() - t0) / 1000);
        }
    }

    s_nt_bytes = total;
    if (!opened) {
        int tls_code = 0, tls_flags = 0;
        esp_err_t tls_error = esp_http_client_get_and_clear_last_tls_error(cl, &tls_code, &tls_flags);
        ESP_LOGW("NETTEST_TLS", "esp_err=0x%x tls_code=%d verify_flags=0x%x",
                 (unsigned)tls_error, tls_code, (unsigned)tls_flags);
        if (!s_nt_err[0]) fixture_strlcpy(s_nt_err, "connect failed", sizeof s_nt_err);
        s_nt_state = NT_ERROR;
    } else if (s_nt_cancel) {
        s_nt_state = NT_CANCELLED;
    } else if (!response_ok) {
        fixture_strlcpy(s_nt_err, "HTTP response failed", sizeof s_nt_err);
        s_nt_state = NT_ERROR;
    } else if (total >= NETTEST_BYTES) {
        s_nt_state = NT_DONE;
    } else {
        fixture_strlcpy(s_nt_err, "transfer incomplete", sizeof s_nt_err);
        s_nt_state = NT_ERROR;
    }

    esp_http_client_close(cl);
    esp_http_client_cleanup(cl);
    heap_caps_free(buf);
    s_nt_task = NULL;
    vTaskDelete(NULL);
}

int main(void){
 for(int k=0;k<6;k++){
  status=k==1?503:200;header_fail=k==2;partial=k==3;alloc_fail=k==4;open_fail=k==5;reads=0;s_nt_bytes=s_nt_ms=0;s_nt_cancel=0;s_nt_err[0]=0;s_nt_state=NT_RUNNING;
  nettest_task(NULL);assert(allocated==0&&clients==0);
  if(k==0)assert(s_nt_state==NT_DONE&&s_nt_bytes==NETTEST_BYTES);
  if(k>=3)assert(s_nt_state==NT_ERROR);
  printf("case=%d state=%d bytes=%u ms=%u\n",k,s_nt_state,s_nt_bytes,s_nt_ms);
  /* Desired diagnostic contract: reject HTTP errors and failed headers. */
  if(k==1||k==2){
#ifdef FIXED
   assert(s_nt_state==NT_ERROR);
#else
   assert(s_nt_state==NT_DONE); /* defect reproduced, not accepted contract */
#endif
  }
 }
 puts("PASS exact task fault/cleanup oracles");return 0;
}
