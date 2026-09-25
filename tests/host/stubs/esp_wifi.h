#pragma once
#include "esp_err.h"
typedef struct { uint8_t mac[6]; } wifi_sta_info_t;
typedef struct { int num; wifi_sta_info_t sta[16]; } wifi_sta_list_t;
esp_err_t esp_wifi_ap_get_sta_list(wifi_sta_list_t *);
