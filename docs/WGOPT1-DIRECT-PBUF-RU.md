# wgopt1 — первая оптимизация реального TX-тракта (0.1.35-tuya-wgopt1)

## База и воспроизводимость
Branch: `optimization/wgopt1-direct-pbuf-v0135`, основание — подтвержденный диагностический `wgdiag4` (commit `f6df4e7efae25a631fba648daec657284c1f7722`). Upstream microlink pin `eb63b97073e529d57bc9c1deaeea25ac304034e5` остается неизменённым. Все патчи строго к build-only copy, проверки исходных SHA256 и якорей fail-closed. Внешние зависимости и версии ESP-IDF не меняются.

## В чём конкретная оптимизация
Измерения `wgdiag4` показывают исходящий WireGuard TX ~445 мкс криптография, ~249 мкс `tx_send`. Имеющийся путь создаёт готовый зашифрованный `PBUF_TRANSPORT` / `PBUF_RAM`, затем:
`pbuf -> PSRAM scratch buffer -> ещё один SPIRAM pbuf_custom -> raw udp_sendto`.
На каждом пакете выполняются минимум две лишние копии данных и несколько alloc/free.

В `wgopt1` добавлен **опциональный синхронный callback borrowed pbuf**. После шифрования готовый одиночный `pbuf` с резервом под UDP/IP заголовки передаётся напрямую в существующий `s_wg_output_pcb/udp_sendto`. Владелец pbuf по-прежнему `wireguardif_output_to_peer`; callback не удерживает/освобождает пакет. Существующий байтовый callback и старый PSRAM-copy путь остаются для `q->len != q->tot_len`, cookie/device-output и других вызовов. Нет экспериментального управления nonce, reorder или лишнего таймера; нельзя считать отсутствие копии гарантией ускорения всего WG.

Сохранено исходное правило **send-both**: WG handshake types 1/2/3 одновременно на прямой UDP endpoint и через DERP; обычный encrypted type 4 через DERP не дублируется. Логика определения peer/key не меняется. Успешная отправка или ошибка возвращается тем же путём. Все старые `wgdiag4` таймеры оставлены, включая `tx_send`, для сравнения. Новое сообщение при инициализации `WGOPT1: direct UDP uses borrowed encrypted PBUF_RAM...` означает регистрацию callback, не подтверждает скорость или реальное прохождение пакетов.

## Ограничения и риски
Путь применим только для прямого magicsock endpoint, только к **одному contiguous pbuf**. Штатное `udp_sendto` синхронно использует pbuf, а исходный владелец освобождает его после возврата (как и прежний custom pbuf). Это сохраняет жизненный цикл в известном lwIP API, но **аппаратный тест обязателен**: возможны отличия WLAN-драйвера, DMA и core affinity. Handshake 64–88 мс не оптимизируется и всплески drop возможны. Производительность ESP32-S3, крипто и forwarding ещё не оптимизированы. CI подтверждает исходные контракты/сборку, не производительность.

Не изменяются идентичность/ключи Tailscale, routes/subnet/exit, Tuya Sticky OFF/ON, Remembered, Last Seen, Reserve, NVS/DHCP, Wi-Fi, WebUI/OTA, SSH/SNMP, flash-partitions, TLS/security config. `main`, tags, опубликованные releases неизменны. **На ESP32 ничего автоматически не прошивается.**

## Smoke-test одного кандидата (вручную)
Перед OTA сохранить рабочий BIN `wgdiag4` и убедиться, что доступен WebUI. Скачать ZIP артефакта CI, проверить SHA256 *именно OTA app BIN* по `SHA256SUMS.txt` внутри ZIP и размер по лимиту OTA. Залить в WebUI только `firmware-0.1.35-tuya-wgopt1-esp32-s3-ota.bin` без factory/erase/NVS reset. Проверить версию в Status, подключение Tailscale, ping от домашнего ПК к офисному `192.168.0.146`, доступность Tuya, WebUI, DHCP и отсутствие повторных reboot. Затем одинаковый с wgdiag4 `iperf3 -c 192.168.0.146 -R -t 30 -i 5` при **выключенном Tailscale на офисном ПК**, офисный iperf3 server `-s -B 192.168.0.146`. Сохранить скорость и полный `WG_DIAG` лог, особенно `tx_send`, `tx_crypto`, `direct drop`, `tx_err`, handshake. Один апаратный замер, без новых сетевых исследований. Если скорость не выросла — не объявлять ускорение; по логам выбрать следующий точечный этап.

## Откат
При сетевом или функциональном регрессе штатный WebUI OTA обратно на сохранённый `wgdiag4`, без очистки NVS. При недоступном WebUI **не пытаться** выполнять factory/repartition/reset без отдельного согласованного плана. 
