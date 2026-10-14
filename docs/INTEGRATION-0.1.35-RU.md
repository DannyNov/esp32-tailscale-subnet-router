# Интеграция upstream v0.1.35 с Tuya и диагностикой

14 октября 2026, МСК. Кандидат `0.1.35-tuya-wgdiag1-snapoff1`, ветка
`integration/0.1.35-tuya`. Аппаратная приёмка не выполнена. Никаких OTA/upload,
перезапусков, изменений настроек/NVS, merge main или публикации release.

## Проверенные исходники

Read-only проверка GitHub refs до создания рабочей копии:

- main: `54bbffcecbfdd694b0b46af7427c3f6575096a76`.
- Tuya integration/v0.1.33-tuya: `3c42a3096cf93c6ef36015998ac6ed5e4029b2a5`.
- WG_DIAG diagnostic/wg-rx-0.1.33-tuya: `5ad09418064050395c8c647de5f3c08ba590d24f`.
- snapoff1: `821150edef100ad019433b0b60f3e356800551db`.
- upstream v0.1.33: `ace09b31e322c2dc5e8823862b66802494360860`.
- upstream v0.1.35: `a9fbf2d53c21d111ab4371f4634fe1000adc81af`.
- microlink: `2c796e3b14872b94fb2c54102affaacb1cc4a77b` →
  `eb63b97073e529d57bc9c1deaeea25ac304034e5`, семь коммитов.

Локальный main был чистым. Создана новая рабочая копия от snapoff1, выполнен
merge v0.1.35 с двумя родителями. Конфликты CMakeLists/README разрешены
с сохранением build overlay и документации форка. Microlink остаётся immutable
submodule: инструментирование выполняется только в generated build copy.

## Что пришло из upstream

Пять коммитов приложения: обновление microlink, default netcheck_override=1,
DERP RTT массив/лимит 32, changelog/README и версия. NVS ts_nc_ovr остаётся
приоритетнее default: сохранённая настройка не переписывается.

Семь microlink-коммитов: DERP CA bundle/hostname verification (CertName и
upstream InsecureForTests сохранены без новых bypass), WG authenticated replay
с 64-bit arithmetic, key expiry/handshake state и X25519, быстрый STUN netcheck
с hysteresis, только DISCO-confirmed endpoint, mutex send counter/encryption,
Noise msg2 bounds, немедленный reconnect на EOF/GOAWAY/RST_STREAM/END_STREAM.

## Собственные изменения сохранены

Tuya AP/DHCP sticky/remembered/Last seen/reservations/ownership, passive ARP,
NAT/subnet/exit routes, WebUI, SNMP, SSH host-key security, OTA, NVS identity,
профиль и сохранённые маршруты. main/ и components/ относительно Tuya базы
изменились только upstream строками netcheck и RTT. partitions.csv и
sdkconfig.defaults совпадают с базой. platformio.ini отличается только ранее
введённым pin espressif32@6.13.0; flash upload/config остаётся 4MB.

derphdr1 сохранён: upstream ml_derp.c меняет TLS setup, но не исправляет
частичный 5-byte TLS frame header. Overlay читает его до полного заголовка,
различает idle WANT и EOF, имеет deadline, использует unsigned длину и
не превращает handshake timeout в бесконечный retry. TLS setup и hostname
check generated C побайтно соответствуют новому pin.

WG_DIAG сохранён. Старый replay-якорь исчез: upstream проверяет replay внутри
wireguard_decrypt_packet до обновления peer и для keepalive. Generated C/H
переименовывают только эту функцию в wireguard_decrypt_packet_diag и добавляют
явный параметр RX path; после upstream replay check учитывают отказ. Не добавлен
глобальный текущий path или доступ к peer pointers из reporter. Replay rejection
также входит в decrypt_error (upstream boolean теперь включает replay), поэтому
эти метрики не следует складывать как независимые потери. Counter-at-limit и
неверная AEAD остаются decrypt_error; D_REPLAY считает authenticated window reject.

WG_SNAP оставлен отключённым. Аппаратный A/B snapoff1 не улучшил SMB; это
опровергает обещание прироста от одного отключения, но не устраняет блокирующий
UART вывод из consumer. Возвращать его для обновления безопасности нет причины.
WG_DIAG, stack sample, оба RX drains, burst=64, budget=30ms и yield 10ms сохранены.
Это диагностический кандидат, отдельная production Tuya версия не объявляется.

## Изменённые файлы относительно snapoff1

- external/microlink — новый upstream pin.
- main/tailscale_manager.c, main/web_ui.c — только upstream изменения.
- CHANGELOG.md, README.md, CMakeLists.txt — upstream и версия/ссылка кандидата.
- tools/prepare_wg_diagnostics.py — pin и authenticated replay instrumentation.
- tools/test_wg_diagnostics.py — allowlist дополнительных generated C/H.
- tools/test_security_0135.py — исполняемые extracted WG/Noise/EOF/H2 regressions.
- tools/test_upstream_0132.py, tools/test_integration.py — pin/версия contracts.
- tools/validate_snapshot_image.py, tools/diagnostic_provenance.py — версия,
  hash/provenance и физический flash bound.
- .github/workflows/build-wg-diagnostics.yml — новая ветка, security tests,
  artifact; contents:read, без deployment/release.
- docs/INTEGRATION-0.1.35-RU.md — этот отчёт.

## Локальные проверки и образ

PASS: DHCP bindings/allocator/ACK/ARP/diagnostics, SNMP BER/hooks, routes/exit,
upstream/PS/factory/integration contracts, оба WebUI suites, SSH 8/8,
overlay reproducibility/idempotence/fail-closed anchors и 25 allocation sites,
snapshot 10000 окон, DERP 17 header + 11 BIO + 9 poll cases.

PASS extracted security C: 65536 Noise payload lengths, короткие body allocation,
authenticated replay/keepalive/64-bit jump/window/limit, EOF со stale EAGAIN,
partial recv timeout, GOAWAY/RST_STREAM short frames и END_STREAM, 20000
уникальных nonces с lock assertions. Windows nonce test последовательно вызывает
два sender; Linux CI выполняет их одновременно через pthread. Существующий
pthread telemetry suite локально SKIP (нет cc/pthread runner); обязателен в CI.
Это host mocks и source contracts, не аппаратные TLS/SMB/concurrency measurements.

Локальная сборка SUCCESS, 238.28 s: PlatformIO 6.2.0, espressif32 6.13.0,
ESP-IDF 5.5.3, Xtensa 14.2.0+20251107, esptool 4.11.0. Первую попытку остановили
из-за длинных Windows путей; успешная использует уже установленный toolchain
в коротком временном каталоге. Настройки Windows не менялись. Прежние DHCP
const qualifier и upstream unused-variable warnings остаются.

Локальный OTA BIN 1 585 440 байт; ota_0 и ota_1 по 1 966 080 байт; запас
380 640 байт. SHA256:
`6fea571e2f723afd060dcb9ff33e6b0fd143124066c88dc10201b8d2d8542bd9`.
Статическая RAM 84 404 байта; это не свободная heap на оборудовании.
Проверены chip ID, встроенная версия, image checksum/appended SHA256,
реальные generated partitions, их границы в 4 MiB flash, octal PSRAM/XIP,
CONFIG_ML_ZERO_COPY_WG выключен. Board N16R8/bootstrap esp32s3box не означает
16 MiB фактического flash: оба flash config и image header указывают 4 MiB.
CI имеет собственный hash и provenance для точного commit, см. итоговый отчёт
в artifacts после окончания CI; побитовая идентичность локального/CI BIN не заявляется.

## Ограничения, rollback и аппаратный план

По контексту/данным пользователя установлен `0.1.33-tuya-wgdiag1-snapoff1`;
live проверка устройства намеренно не выполнялась. A/B не улучшил примерно
700 КБ/с, RX drops продолжались (+116 и +46 за окна 10s). Офисный тест
2026-10-14: upload 251.60/download 215.59 Mbps, ping 5ms. Это исключает тариф
как объяснение наблюдавшихся 5–6 Mbps, но не доказывает конкретную причину
RX потерь. Upstream changelog приводит 4.6 Mbps (5.1 с четырьмя соединениями)
на ином exit-node тесте; это другой путь/нагрузка, не прогноз нашего SMB.
Nonce fix обязателен для security, прирост SMB от него не обещается.

Риски: новое TLS verification требует доверенный CA/name и корректное время;
DERP с самоподписанным сертификатом теперь штатно отвергается. Изменены replay,
key lifetime и endpoint discovery; реальный rekey/DERP fallback требует smoke.
Rollback исходников — предыдущая диагностическая ветка/commit. При отдельном
согласовании OTA сохранить текущий BIN/конфигурацию и использовать штатный
OTA путь без NVS erase/repartition/factory image. Старая прошивка содержит
старые security defects, длительный rollback нежелателен. В этой задаче
аппаратный rollback не нужен: устройство не менялось.

Предлагаемый отдельный ручной A/B/A: сначала согласовать OTA приложения и smoke;
сохранить текущий профиль, убедиться в фактическом inactive slot, одинаковые
клиент/SMB файл/маршрут/direct UDP/условия Wi-Fi. Повторить 2–3 минуты и rekey
soak >4 минут; сохранить все WG_DIAG 10s окна, rx/drop доли, queues/HWM,
decrypt/replay/forward, process/loop slow30, TX errors, heap/stack, control
reconnect, Windows TCP retransmissions и устойчивую скорость без стартового
пика. Отдельно проверить DERP fallback, TLS reject на стенде, Tuya sleepy
reassociation/remembered/Last seen/reserve, WebUI/SNMP/SSH и persistence после
согласованного reboot. Критерии: нет nonce/regression/crash, сохранены сервисы,
drops и скорость сравниваются повторно; улучшение нельзя объявлять по одному пику.
