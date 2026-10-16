"""wgopt5 host test of actual generated ESP-IDF diagnostics implementation.

Compiles wg5_diag.c against deterministic Wi-Fi / FreeRTOS mocks. Verifies
startup baseline, delta CPU fractions per core, RSSI/power-save transitions,
and task-cap refusal (never infer idle=0 on missing/oversized snapshots).
"""
from pathlib import Path
from tempfile import TemporaryDirectory
import shutil
import subprocess
from prepare_wg_diagnostics import prepare, ROOT

(ROOT / "build").mkdir(exist_ok=True)
with TemporaryDirectory(prefix="wgopt5-", dir=ROOT / "build") as t:
    tmp = Path(t)
    prepare(tmp)
    src = tmp / "microlink/components/wireguard_lwip/src"
    diag = (src / "wg5_diag.c").read_text()
    parent = (src / "wg_diag.c").read_text()
    cmake = (tmp / "microlink/components/wireguard_lwip/CMakeLists.txt").read_text()
    assert cmake.count('"src/wg5_diag.c"') == 1
    assert "        esp_wifi\n" in cmake
    assert parent.count("wg5_report();") == 1
    assert "esp_wifi_sta_get_ap_info(&ap)" in diag and "esp_wifi_get_ps(&wifi_ps)" in diag
    assert "uxTaskGetSystemState(taskbuf, WG5_MAX_TASKS, &total)" in diag
    assert "WG5_SYS" in diag
    assert "WG5_MAX_TASKS 64" in diag
    assert "esp_wifi_internal_" not in diag and "reg_txcb" not in diag
    assert "WIFI_PS_NONE" not in diag  # diagnostic only; never alter PS state
    assert "esp_wifi_set_" not in diag
    assert "vTaskDelay" not in diag and "xTaskCreate" not in diag

    stub = tmp / "stub"
    (stub / "freertos").mkdir(parents=True)
    (stub / "esp_wifi.h").write_text("""#pragma once
#include <stdint.h>
#define ESP_OK 0
typedef int wifi_ps_type_t;
typedef struct { int8_t rssi; uint8_t primary; uint8_t phy_11n; } wifi_ap_record_t;
int esp_wifi_sta_get_ap_info(wifi_ap_record_t *ap);
int esp_wifi_get_ps(wifi_ps_type_t *ps);
""")
    (stub / "esp_log.h").write_text("""#pragma once
void test_log(const char *tag, const char *fmt, ...);
#define ESP_LOGW(tag, fmt, ...) test_log(tag,fmt,##__VA_ARGS__)
""")
    (stub / "esp_heap_caps.h").write_text("""#pragma once
#include <stddef.h>
#define MALLOC_CAP_SPIRAM 1
#define MALLOC_CAP_8BIT 2
void *heap_caps_malloc(size_t len, unsigned caps);
""")
    (stub / "esp_timer.h").write_text("""#pragma once
#include <stdint.h>
int64_t esp_timer_get_time(void);
""")
    (stub / "freertos/FreeRTOS.h").write_text("""#pragma once
typedef unsigned UBaseType_t;
""")
    (stub / "freertos/task.h").write_text("""#pragma once
#include <stdint.h>
#include "freertos/FreeRTOS.h"
typedef struct { const char *pcTaskName; uint32_t ulRunTimeCounter; } TaskStatus_t;
UBaseType_t uxTaskGetNumberOfTasks(void);
UBaseType_t uxTaskGetSystemState(TaskStatus_t *taskArray, UBaseType_t arraySize,
                                 uint32_t *totalRunTime);
""")
    test = tmp / "host.c"
    test.write_text(r"""
#include <assert.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include "esp_wifi.h"
#include "freertos/task.h"
void wg5_report(void);
static char lastlog[1024];
static unsigned allocations, samples, number_tasks=6;
static int sample_rssi=-49, sample_ps=1;
static const char *nms[]={"IDLE0","IDLE1","wifi","tiT","ml_wg_mgr","ml_net_io"};
static const uint32_t delta[]={200,700,100,50,400,50};
void test_log(const char *tag, const char *fmt, ...) {
    assert(strcmp(tag,"WG5_SYS")==0);
    va_list ap;va_start(ap,fmt);
    vsnprintf(lastlog,sizeof(lastlog),fmt,ap);
    va_end(ap);
}
void *heap_caps_malloc(size_t n, unsigned caps) {
    assert(caps==3);allocations++;return malloc(n);
}
int esp_wifi_sta_get_ap_info(wifi_ap_record_t *ap) {
    ap->rssi=sample_rssi;ap->primary=6;ap->phy_11n=1;return ESP_OK;
}
int esp_wifi_get_ps(wifi_ps_type_t *ps) {*ps=sample_ps;return ESP_OK;}
int64_t esp_timer_get_time(void) { return 10000000LL + (int64_t)samples * 10000000LL; }
UBaseType_t uxTaskGetNumberOfTasks(void) { return number_tasks; }
UBaseType_t uxTaskGetSystemState(TaskStatus_t *arr,UBaseType_t limit,uint32_t *total) {
    assert(limit>=6);*total=100000+samples*1000;
    for(unsigned i=0;i<6;i++) {
        arr[i].pcTaskName=nms[i];
        arr[i].ulRunTimeCounter=100+(uint32_t)samples*delta[i];
    }
    samples++;return 6;
}
int main(void) {
    wg5_report();
    assert(strstr(lastlog,"sta=1 rssi=-49 ch=6 phy11n=1 ps=1"));
    assert(strstr(lastlog,"cpu0_busy=-1 cpu1_busy=-1"));
    assert(strstr(lastlog,"prof=1"));
    sample_rssi=-73;sample_ps=0;
    wg5_report();
    assert(strstr(lastlog,"sta=1 rssi=-73 ch=6 phy11n=1 ps=0"));
    assert(strstr(lastlog,"cpu0_busy=80 cpu1_busy=30"));
    assert(strstr(lastlog,"wifi_task=10 tcpip_task=5 wg_task=40 netio_task=5"));
    assert(allocations==1 && samples==2);
    number_tasks=65;
    wg5_report();
    assert(strstr(lastlog,"tasks=65 prof=0"));
    assert(strstr(lastlog,"cpu0_busy=-1 cpu1_busy=-1"));
    assert(allocations==1 && samples==2);
    puts("PASS: wgopt5 real C reporter, passive radio, CPU core/task deltas, missing-sample guard, bounded persistent PSRAM");
    return 0;
}
""")
    cc = shutil.which("cc")
    if not cc:
        raise RuntimeError("wgopt5 requires host C compiler")
    cmd = [cc, "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror", "-UNDEBUG",
           "-I"+str(stub), str(test), str(src / "wg5_diag.c"), "-o", str(tmp / "test")]
    subprocess.run(cmd, check=True)
    subprocess.run([str(tmp / "test")], check=True)
