# wgopt4 — точная диагностика провала скорости после 40 секунд

**База:** рабочая `optimization/wgopt2-borrowed-rx-v0135`, коммит `0769828dc36266ceae92e4774b6d512336e1d658`. Переход на mbedTLS из wgopt3 намеренно НЕ включён. Pinned upstream microlink `eb63b97073e529d57bc9c1deaeea25ac304034e5` остаётся нетронутым.

## Почему нужна диагностика, а не следующий спекулятивный фикс
При одинаковых тестах `iperf3 -c 192.168.0.146 -R -t 120 -i 10` офис→дом:
- `wgopt2`: 0–40 с ~7.18 Мбит/с, 40–110 с ~4.87 Мбит/с, 110–120 с 7.14 Мбит/с; средняя 5.83 Мбит/с.
- `wgopt3`: 0–40 с ~7.26 Мбит/с, 40–110 с ~4.66 Мбит/с, 110–120 с 7.03 Мбит/с; средняя 5.72 Мбит/с.

Схожий провал в обеих прошивках исключает объяснение **только** заменой ChaCha20-Poly1305. Но не доказывает конкретную причину: DRAM, переключение direct/DERP, Wi-Fi, TCP/IP, дисковый I/O, CPU starvation или другое. Выбран read-only test build, никаких таймингов/очередей/маршрутов не меняем.

## Что обнаружено в коде
- В `wgopt2` уже есть диагностика `wg_diag_time`, `wg_diag_peer_tx`, `wg_diag_sample_queue`, но её подробный reporter выводит `ESP_LOGI("WG_DIAG")`. При `CONFIG_LOG_DEFAULT_LEVEL_WARN=y` эти строки не попадают в обычный журнал без явного повышения log level. Отсюда отсутствие удобного удалённого снимка.
- При `-R` основной поток на ESP — **TX**: его пакетные данные идут через `wireguardif_peer_output`, затем direct UDP callback либо DERP. Решение выбирается по `peer->ip/port` и `force_derp_output`. Статистика RX очереди сама по себе не объясняет TX провал.
- Код содержит periodic WG tick ~400 мс, DISCO probes ~1 c, direct-stale/data-flowing условия и DERP fallback; по одному iperf нельзя утверждать, какая ветка виновата.

## wgopt4: только наблюдаемость
Генерируемый билдовый компонент наследует все wgopt1 + wgopt2 исправления. Добавлен вызов `wg_diag_wg4_tx(route, result, q->tot_len)` в `wireguardif_peer_output` на `wg_mt == 4` **после** результата отправки. Он записывает атомарные счётчики: `direct_ok/direct_err/direct_bytes`, `derp_ok/derp_err/derp_bytes`. Прямой путь означает передачу в raw UDP, DERP — успешное принятие в очередь; ни то ни другое **не подтверждает доставку удалённому узлу**. Handshake send-both исключён.

Каждые 10 с низкоприоритетный reporter добавляет **ровно две** ограниченные WARN-строки в существующий 16 КБ кольцевой веб-журнал (открывается в интерфейсе **Logs / Журнал**):

- `WG4_TX`: `t_ms` uptime, direct/DERP ok/err/bytes за 10с, `crypto_n`, `crypto_avg_us`, `send_avg_us`, `lock_avg_us`.
- `WG4_RX`: тот же `t_ms`, количество direct и DERP inbound, drop, глубина и **пиковая глубина именно этого 10-секундного окна** `wgq_peak`, среднее время ожидания RX `rx_wait_avg_us`, времена `periodic_avg_us` и `probes_avg_us`, `internal_free`.

В producer и TX нет новых логов, выделений памяти, копирований и задержек. Окна привязаны к **uptime микроконтроллера**, а не к запуску iperf; грань окна может не совпадать с десятисекундными интервалами iperf, допуск ±10 с. Цель: увидеть, меняется ли выход на DERP, множатся ли ошибки, растёт ли время шифрования/отправки или очереди в момент падения скорости.

## Проверки безопасности
- Не модифицировать `external/microlink`: generated-copy overlay с fail-closed anchors.
- Existing tests проверяют неизменённую исходную WireGuard криптографию, replay, ownership, прямой PBUF TX, borrowed RX, маршрутизацию/Tuya, OTA-partitions.
- Дополнительные contract/host-C тесты проверяют отсутствие per-packet printk и корректность накопления/сброса счётчиков по окнам.
- CI: ESP32-S3 firmware.bin, app descriptor version, 4MiB flash, two 1,966,080-byte OTA slots, SHA256 image/partition verification, pinned submodule, no NVS wipe.

## Единственный аппаратный тест
1. Сохранить working **wgopt2** OTA BIN для отката; проверить скачанный wgopt4 SHA256 против `SHA256SUMS.txt`.
2. Загрузить **OTA BIN** `firmware-0.1.35-tuya-wgopt4-esp32-s3-ota.bin` через WebUI. Не выполнять NVS reset/factory/repartition. Убедиться в наличии Tailscale и доступности `192.168.0.146`.
3. На офисном Windows оставить сервер `iperf3 -s -B 192.168.0.146`, его локальный Tailscale выключить. На домашнем Windows `iperf3 -c 192.168.0.146 -R -t 120 -i 10`.
4. Сразу после завершения открыть WebUI ESP32 вкладку **Logs / Журнал**, скопировать строки `WG4_TX` и `WG4_RX` за период теста. Вместе с полным выводом iperf передать их для сопоставления. Встроенный live log ограничен 16KiB: не оставлять устройство надолго, чтобы записи не затёрлись.

Если OTA вызывает сбои, использовать сохранённый `wgopt2` BIN через WebUI без сброса параметров. **Никаких прогнозов ускорения: wgopt4 диагностическая прошивка.**
