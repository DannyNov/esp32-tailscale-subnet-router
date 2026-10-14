# wgdiag4 — раздельное профилирование TX/RX и уменьшение пауз handshake

Основа: 0.1.35-tuya-wgdiag3 (9a1dc18094819b6bdc8ba37be627372430f1d50f); исходный релиз v0.1.35-tuya; immutable microlink eb63b97073e529d57bc9c1deaeea25ac304034e. Всё меняется только в генерируемой при сборке копии. Никакого OTA на реальное устройство не выполнено.

## Причина эксперимента
Реальное копирование SMB с офисного PC (192.168.0.146) через ESP32 subnet router — около 680–710 КБ/с, на wgdiag3 немного более волатильно. В журнале WG-RX было 366 drops большими сериями (до 128 подряд) во время handshake, но скорость ограничена и в интервалах без потерь. WG-TX error 0. Без подтверждения нельзя считать RX queue единственным ограничением.

## Изменения относительно wgdiag3
- Дорогостоящие для UART синхронные WARN при **успешных** WireGuard handshake (9 мест), INFO send-both handshake и WARN каждого 32-го RX queue overflow переведены на DEBUG. WARN ошибок MAC/key/handshake оставлены. Все drop counters и периодическая диагностика по-прежнему работают. Цель — снизить мешающий обработке RX синхронный вывод. Алгоритм X25519, отправка ответов, WireGuard session, DISCO и маршрутизация не меняются.
- Новый набор счетчиков по 10-секундным окнам: timer=tx_pbuf (выделение PBUF), tx_copy, tx_crypto (существующий), tx_send (существующий); rx_pbuf, rx_copy (копирование UDP в pbuf), rx_dec_pbuf, rx_decrypt, rx_lwip (только синхронный netif->input), rx_handshake (type 1–3), rx_data (type 4/other). Таймеры записываются в микросекундах: n_delta, us_sum_delta, us_max_boot, slow30_delta. Это **wall time**, не прямое измерение CPU. Тайминги вложены и не должны складываться вслепую.
- Планировщик остается как в wgdiag3: активная пауза 2 мс, idle 10 мс, WG drain два раза по максимум 64 пакета/30 мс. Размер очереди 32; не добавлены задачи или небезопасная многопоточная криптография.
- Никаких изменений Tuya Sticky OFF/ON, Remembered/Last Seen/Reserve/NVS, Wi-Fi AP/STA, WebUI, SNMP, SSH, DHCP, маршрутам Tailscale/subnet/exit, ключам, 4MiB flash, 8MiB octal PSRAM или OTA-разметке.

## Аппаратный smoke-test и откат
1. Убедиться, что есть рабочие OTA BIN wgdiag2 и wgdiag3, и доступ по WebUI. Скачать ZIP CI, проверить SHA256 firmware-0.1.35-tuya-wgdiag4-esp32-s3-ota.bin по SHA256SUMS.txt.
2. Только штатный WebUI OTA без удаления NVS и без factory/erase; проверить версию, Tailscale, Tuya, WebUI, DHCP.
3. Записать 30–40 с WG_DIAG без нагрузки. Затем тот же файл GX020296 скачать из \\192.168.0.146\d на домашний ПК, офисный Tailscale остается выключенным, 90–120 секунд, записать скорость и все строки WG_DIAG. Подождать еще 20 с.
4. Сравнить с предыдущими логами wgdiag2/3: скорость и волатильность SMB, прирост/снижение RX drops и run_max_boot, rx_handshake, rx_data, rx_pbuf, rx_copy, rx_dec_pbuf, rx_decrypt, rx_lwip, tx_pbuf, tx_copy, tx_crypto, tx_send. Отдельно проверить 10-секундные окна без drops. Не считать 0 drop гарантией роста скорости.
5. Если функциональность регрессировала — штатный WebUI OTA на сохраненную wgdiag2/3, NVS не стирать. При недоступном WebUI остановиться и согласовать recovery, не использовать factory.bin на работающем устройстве.

CI обязан PASS по регрессиям, image checksum, SHA256, OTA partition size 1966080 байт, Source pin и проверке версии. Ни main, ни release/tag не изменяются.
