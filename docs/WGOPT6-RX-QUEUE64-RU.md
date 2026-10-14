# wgopt6 — ограниченное увеличение RX-очереди 32 → 64

## Установленные факты и ограничение гипотезы

База: работоспособная ветка diagnostics/wgopt5-radio-cpu-v0135, commit e494f567967e9ba29e1a5866e30105ee18cb72e5. Immutable pinned microlink: Csontikka/microlink@eb63b97073e529d57bc9c1deaeea25ac304034e5.

В 120-сек тесте TCP office→home (iperf3 -c 192.168.0.146 -R -t 120 -i 10) два последовательных окна показали 44 потерянных direct WG RX-пакета в каждом, wgq_peak=32/32. Нагрузка CPU1=80–82%, а время TX crypto оставалось ~440 мкс. Это доказательство локальной потери пакетов в очереди, но НЕ доказательство того, что все потерянные пакеты были TCP ACK или что их потери — единственная причина колебаний TCP.

UDP -R -u -b 6M -l 1200 -t 120: receiver 6.00 Mbps, потеря 14/74993 (0.019%), 2466 out-of-order. Это не подтверждает отсутствие проблем TCP при более высоких скоростях. Серверная Windows-версия iperf3 не показывает Retr/Cwnd даже с --get-server-output.

## Анализ подтверждённого кода

- ml_net_io_task читает direct UDP, выделяет payload через ml_psram_malloc(n), копирует датаграмму, делает xQueueSend(wg_rx_queue, &pkt, 0). Когда очередь заполнена, пакет отбрасывается и память освобождается.
- ml_wg_mgr_task, единственный consumer, работает на core1 priority7. Два ограниченных WG-drain по 64 пакета/30 мс; между ними WireGuard periodic и DISCO. Из прежних overlays уже действует 2 мс sleep при активных пакетах и 10 мс в простое. Эта схема НЕ меняется.
- ml_rx_packet_t хранит метаданные, pointer payload и метку времени; RX payloads выделяются в PSRAM-first, с fallback в обычную RAM при нехватке PSRAM.
- Больше мест в очереди могут поглотить кратковременный всплеск и сократить drops, но не ускорят криптографию или обработку пакета.

## Одно контролируемое изменение

Только в generated-copy (после wgopt1/2/4/5 overlays): tools/wgopt6_overlay.py заменяет ровно один macro ML_WG_RX_QUEUE_DEPTH 32 на ML_WG_RX_QUEUE_DEPTH 64. Не меняем producer/consumer, порядок FIFO, время обработки, scheduler delay, DERP, replay/policy, NVS/OTA partitions, ключи или версии upstream.

На ESP32-S3 sizeof(ml_rx_packet_t) ≤64 байт (ограничено compile-time host C тестом): дополнительные 32 metadata-элемента требуют не больше **2 048 байт внутренней памяти** (плюс служебные данные FreeRTOS). Дополнительные 32 ciphertext payload могут занять до 48 000 байт плюс allocator overhead, обычно в PSRAM (8 MB на целевой N16R8). Если PSRAM будет исчерпана, ml_psram_malloc может перейти на обычный malloc и усилить расход внутренней RAM. Сохраняем ограничение 64, в отличие от рискованного 128+.

В штатной десятисекундной строке WG4_RX добавляется поле wgq_cap=64. Остальные WG4_TX, WG4_RX, WG5_SYS и вся диагностическая логика остаются прежними.

## CI и безопасность

test_wgopt6.py требует pinned generated source, точного macro, прежнего adaptive sleep 2/10 мс, прежних WG-drain budget, producer drop/free, borrowed RX ownership, DERP path, неизменного heap allocation и собирает под host C настоящий ml_rx_packet_t для bound на память. Полный набор тестов безопасности, криптографии и интеграций из wgopt5 и реальная сборка ESP32-S3 обязательны. Отдельная ветка optimization/wgopt6-rx-queue64-v0135; main/releases не меняем. Аппаратный результат не предсказан и не проверен CI.

## План одного физического A/B-кандидатного прогона

1. Сохранить **рабочую wgopt5 OTA**, скачанный wgopt6 BIN сверить по SHA256SUMS.txt из успешного CI. Прошивать только OTA BIN через WebUI, **без NVS reset, factory или repartition**. Проверить Tailscale/доступ к 192.168.0.146.
2. Офисный Windows: iperf3 -s -B 192.168.0.146. Его собственный Tailscale выключен. Домашний Windows: iperf3 -c 192.168.0.146 -R -t 120 -i 10.
3. Сразу после теста скопировать весь вывод iperf и WG4_RX, WG4_TX, WG5_SYS из WebUI. Веб-журнал 16KiB перезаписывается; лучше копировать во время прогона.
4. Важные метрики: receiver Mbps по окнам, число direct_drop за 10с, wgq_peak/cap, rx_wait_avg_us и RSSI/CPU. В baseline wgopt5 наблюдали подряд 44 и 44 drops на очереди 32. Желательно падение drops без существенного увеличения RX latency. Один хороший прогон ещё НЕ доказывает ускорение; потребуется повторный A/B.

При ухудшении, перегрузке PSRAM/внутренней RAM или потере Tailscale — вернуть wgopt5 OTA без сброса NVS.
