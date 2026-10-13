# Результат проверок snapoff1

14 октября 2026, МСК. Локальная ESP32-S3 сборка успешна: PlatformIO 6.2.0, espressif32 6.13.0, ESP-IDF 5.5.3, Xtensa 14.2.0. Журнал `build-snapoff.log`, SUCCESS, 285,82 с. Предыдущая попытка была заблокирована Windows sandbox при запуске компилятора; успешный запуск выполнен после разрешения автоматической проверки. Это локальная сборка, не remote CI.

| Параметр | Значение |
|---|---|
| Firmware | 0.1.33-tuya-wgdiag1-snapoff1 (с derphdr1) |
| BIN / OTA приложение | 1 579 584 байта |
| OTA slot ota_0 и ota_1 | 1 966 080 байт каждый |
| Запас | 386 496 байт |
| SHA256 | d64ef7c7abdd5597f2ebc044420423c20a65edf6b520e9e561d9bbc0327593b5 |
| Статическая RAM | 84 340 байт |
| Chip / checksum / appended SHA256 | ESP32-S3 / valid / valid |

BIN меньше сохраненного derphdr1 на 1920 байт; статическая RAM больше на 32 байта. Это не измерение свободной heap/stack на устройстве. Встроенная версия, размеры реальных generated partitions, checksum сегментов, image digest, 4MB flash и octal PSRAM/XIP проверены. CONFIG_ML_ZERO_COPY_WG выключен. Прежние warnings DHCP const qualifier и upstream unused variables остаются.

PASS: воспроизводимость/idempotence overlay, fail-closed anchors, immutable pin, 25 allocation sites, ограничение набора измененных generated файлов; snapshot call отсутствует в consumer, оба WG drains/budgets/yield сохранены. Точный extracted periodic C block прошел 10000 окон без snapshot и peer/netif pointers. DERP: 17 header + 11 BIO + 9 poll C-тестов PASS. DHCP/ARP/allocator/diagnostics и SNMP host suites PASS; route/exit C и source contracts PASS; upstream pin/logging/shutdown, Wi-Fi PS, factory, integration и два UI suites PASS. Первые route/exit запуски не нашли cc, повтор с --cc прошел. SSH host-key regression запущен с зависимостями в отдельном build/test-deps. Существующий pthread telemetry тест локально SKIP (Windows runner без cc); предусмотрен как обязательный в Linux CI.

Побайтовое сравнение generated data-plane с ранее собранным derphdr1 подтвердило: изменен только вызов snapshot в ml_wg_mgr.c. ml_derp.c, ml_net_io.c, wireguardif.c совпадают. main/ и components/ приложения (кроме generated HTML), sdkconfig.defaults, platformio.ini и partitions.csv совпадают с диагностической базой. Исходные diagnostic worktree и pinned microlink чистые. Машинные результаты сохранены локально в artifacts/image.json и artifacts/overlay-comparison.json.

## Измененные файлы кандидата

- tools/prepare_wg_diagnostics.py — отключение snapshot, сохранение derphdr1, provenance policy.
- tools/derp_header_overlay.py и tools/derp_read_header.inc — прежний derphdr1 в существующей генерации overlay.
- tools/test_wg_diagnostics.py — отсутствие вызова snapshot и сохранение consumer contracts.
- tools/test_snapshot_overlay.py — исполняемый periodic block и DERP C-регрессии.
- tests/host/derp/test_header.c, test_bio.c, test_poll.c — прежние DERP fixtures.
- tools/validate_snapshot_image.py — проверка реального BIN, checksum, partitions, config.
- tools/diagnostic_provenance.py — имя и версия кандидата.
- CMakeLists.txt и tools/test_integration.py — версия кандидата и соответствующий source contract.
- .github/workflows/build-wg-diagnostics.yml — изолированная ветка, тесты и проверка BIN, artifact без deployment.
- docs/WG-SNAPSHOT-AUDIT-RU.md и этот отчет — аудит, риски и предложенный аппаратный тест.

Runtime эффект нового изменения относительно derphdr1 — удаление одного вызова snapshot. Upstream submodule/pin не изменены. Отдельная ветка создается только после подтвержденных локальных тестов и сборки. Сведения о commit и попытке remote CI фиксируются отдельно при завершении задачи.

Аппаратное подтверждение устранения SMB деградации отсутствует. Согласование и выполнение smoke test — следующий отдельный шаг; устройство в этой задаче не изменено.
