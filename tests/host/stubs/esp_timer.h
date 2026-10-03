#pragma once
#include <stdint.h>
int64_t esp_timer_get_time(void);

#include "esp_err.h"
typedef void *esp_timer_handle_t;
typedef struct { void (*callback)(void *); const char *name; } esp_timer_create_args_t;
static inline esp_err_t esp_timer_create(const esp_timer_create_args_t *a, esp_timer_handle_t *h) { (void)a; *h=(void*)1; return ESP_OK; }
static inline esp_err_t esp_timer_start_periodic(esp_timer_handle_t h, uint64_t us) { (void)h; assert(us==60000000); return ESP_OK; }
