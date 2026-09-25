#pragma once
#include "esp_log.h"
#include "esp_timer.h"
/* WARN survives the default console filter; monotonic time, independent of SNTP. */
#define BOOT_MARK(milestone) ESP_LOGW("boot_timing", "ms=%lld %s", \
    (long long)(esp_timer_get_time() / 1000), (milestone))
