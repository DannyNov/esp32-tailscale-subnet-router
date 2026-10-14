# OTA-кандидат WG memory/RX

База: v0.1.35-tuya, 3bd26480a4fb82aeb14cf2483bae9d3f2b9c2beb;
microlink eb63b97073e529d57bc9c1deaeea25ac304034e5. Версия кандидата:
0.1.35-tuya-wgdiag2. Только OTA application BIN, без factory.

Изменён только build-only overlay и диагностика. Исходный submodule чистый.
Очередь 32, budgets 30ms/64, sleep 10ms сохранены. Защита проверяет pin,
чистоту, SHA256 нормализованного текста исходников и точные anchors.
Разметка 4MiB, OTA slot 1966080 bytes, octal PSRAM 8MiB сохранены.
Tuya Sticky OFF/ON, Remembered, Last Seen, Reserve/NVS, DHCP, WebUI,
SNMP, SSH, identity/routes/OTA не изменены; аппаратная приёмка ожидается.

Раз в 10s WG_DIAG показывает tx_stage=internal_wrapper/psram_payload/custom_pbuf/
udp_sendto и raw_err (-1 означает ERR_MEM). tx_err по-прежнему считает только
ошибки udp_sendto. rx_wait — от timestamp перед enqueue до dequeue (включает
затраты enqueue); drain_gap включает простои без трафика, loop_gap — sleep и
работу цикла. us_max_boot — максимум с загрузки, slow30_delta — >30ms за окно.
direct_drop_runs_delta: последовательные отказы, разрыв при успешном enqueue
либо >10ms между отказами; run_max_boot включает незавершённую серию.
Это операционное определение серии, а не доказательство сетевого burst.
Существующие S-слоты источников и wgi-слоты RX непрозрачны, без ключей в логах.
TX также агрегируется по wgi и direction=tx в существующей точке вывода;
это индекс peer с возможным повторным использованием после его удаления.
Сопоставление направления не читает таблицу microlink из чужой задачи.
Перепакетный WG_OUT_FAIL заменён агрегатами без endpoint и ключей.

SMB download обычно преимущественно TX от ESP, RX чаще ACK. Нельзя считать
переполнение RX единственной причиной ограничения скорости без новых измерений.

Smoke-test после самостоятельной установки пользователем: сохранить известный
рабочий OTA BIN и SHA256 v0.1.35-tuya; проверить SHA256 кандидата по artifact.
Записать текущую версию, настройки и состояние Tuya/резервирования. Установить
только application BIN штатной OTA процедурой. Проверить загрузку, PSRAM,
WebUI, SSH, SNMP, DHCP, Sticky OFF/ON, Remembered/Last Seen, Reserve и прежние
identity/routes. 30s idle, затем 60–120s скачивания одного большого файла
из \\192.168.0.146\d на домашний ПК прежним путём через офис и ESP.
Tailscale офиса оставить выключенным. Сохранить скорость и полные окна WG_DIAG
до/во время/после. При отказах сравнить tx_stage и raw_err, rx_wait, loop_gap,
periodic/probes и серии drops. Повторить тем же файлом/условиями.

Откат: пользователь загружает сохранённый рабочий application BIN через штатный
OTA; NVS не очищать, factory не использовать. При недоступной OTA остановить
тест и отдельно согласовать восстановление. Автоматическая прошивка и reboot
не выполнялись. CI artifact содержит SHA256, размер, provenance и проверку
структуры ESP32-S3 image; это готовность к аппаратному тесту, не его результат.
