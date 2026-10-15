# wgopt10 — источник Wi-Fi TX ERR_MEM

База: wgopt9 `6a3e19e1b094940ddef50ac06ffe16019b104695`. Цель:
различить возвращённый драйвером `ESP_ERR_NO_MEM` и ошибку до обращения
к `esp_wifi_internal_tx_by_ref/esp_wifi_internal_tx`.

## Что исследовано

В ESP-IDF v5.5 `components/esp_netif/lwip/netif/wlanif.c`
`low_level_output()` в случае нескольких pbuf выделяет
`pbuf_alloc(PBUF_RAW_TX,...,PBUF_RAM)` и при ошибке возвращает
`ERR_MEM` без вызова драйвера. После вызова `esp_netif_transmit_wrap`
`ESP_ERR_NO_MEM` также преобразуется в `ERR_MEM`.
`components/esp_wifi/src/wifi_netif.c` при
`CONFIG_SPIRAM_TRY_ALLOCATE_WIFI_LWIP` использует
`esp_wifi_internal_tx_by_ref()`; иначе `esp_wifi_internal_tx()`.

## Изменения

В `main/wg10_wifi_tx.c` две GNU ld `--wrap` обёртки на внешние вызовы
`esp_wifi_internal_tx[_by_ref]` записывают фактический raw `esp_err_t`
после возврата исходной функции. Аргументы и результат передаются без
изменений, буферы не удерживаются, retries/sleeps отсутствуют.
`sta_linkoutput_hook` наблюдает pbuf chain shape перед вызовом оригинала.
Счётчики привязаны к FreeRTOS-task активной прямой WG UDP отправки wgopt9,
не к фоновой Wi-Fi активности. Нет per-packet логов.

Строка `WG10_WIFI_TX` каждые ~10 секунд:
* `sta_errmem_driver_nomem`: STA ERR_MEM и перехваченный Wi-Fi TX вернул `ESP_ERR_NO_MEM` (0x101).
* `sta_errmem_driver_other`: STA ERR_MEM и Wi-Fi TX вернул другую nonzero ошибку.
* `sta_errmem_driver_ok`: STA ERR_MEM, Wi-Fi TX вернул success (неожиданный результат).
* `sta_errmem_no_driver_chain`: STA ERR_MEM, pbuf chain был, перехваченного вызова Wi-Fi TX не было;
  возможен pbuf_alloc до Wi-Fi, но не доказан.
* `sta_errmem_no_driver_single`: аналогично для одиночного pbuf/неувиденной формы.
* `ref_calls`, `copy_calls`: перехваченные вызовы внутри scoped WG UDP передачи;
  нужны для проверки фактического пути и работоспособности обёртки.
* `raw_other_errors`: другие raw nonzero Wi-Fi ошибки во время scoped direct send.

`WG9_TXPATH`, `WG4_TXERR`, `WG4_RX`, `WG7_MEM` сохранены. Новые
счётчики атомарны; соседние репорты могут отставать на граничном пакете.
Отсутствие перехвата при `ref_calls=copy_calls=0` **нельзя** трактовать
как подтверждённый отказ раннего pbuf. Это может быть проблема с linker
wrap (функция внутри одного объекта / другой API).

Неизменны RX-очередь 128, оба Wi-Fi TX buffer caps 32, PSRAM/N16R8,
WireGuard/Tailscale/DERP, маршруты, packet ownership, scheduling, NVS.
Только OTA application BIN (не factory); сохранить прошлую wgopt9.
После CI SUCCESS и аппаратной проверки Tailscale/office route запустить
сопоставимый 120-секундный iperf3 и сохранить журнал. Версия диагностическая,
пропускная способность не гарантируется.
