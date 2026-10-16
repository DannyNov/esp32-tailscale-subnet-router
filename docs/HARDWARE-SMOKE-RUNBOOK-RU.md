# Public template: replace symbolic lab addresses locally; do not commit real topology.

# Аппаратный стенд: план, НЕ исполнен

Дата: 16.10.2026, UTC (document date only). Только резервная ESP32-S3 N16R8.
Сейчас нет разрешения на flash, USB операции или изменение рабочих устройств.
Production NO-GO сохраняется независимо от компиляции.

## 0. Входной gate и журнал

Перед аппаратными испытаниями проверить отчёт Phase A. При BUILD-NO-GO разрешён только будущий
read-only identify/backup после отдельной команды; экспериментальную app не шить.
Для каждого этапа фиксировать время, board serial/MAC, app/boot/table SHA256,
sdkconfig, image metadata, маршрут и PASS/FAIL/NOT-RUN. Секреты, NVS, ключи и полные
логи авторизации хранить локально, вне Git/CI/общедоступных artifacts.
Отдельное явное согласие должно назвать резервную плату, вариант (4MB или 16MB),
hash комплекта, допустимые записи и проверенный recovery. Это не согласие на рабочую ESP.

## 1. Топология и независимость

Тестовый ПК — upstream gateway UPSTREAM_SUBNET. lab OpenWrt gateway находится за upstream gateway;
ESP STA подключается к WiFi lab gateway. Адрес/subnet LAN lab gateway выяснить, не предполагать
UPSTREAM_SUBNET. ESP SoftAP — отдельный SSID и TEST_AP_SUBNET (gateway TEST_AP_GATEWAY).
Рабочие PRODUCTION_SUBNET, ESP и основной роутер не менять.

Проверить, что TEST_AP_SUBNET не используется LAN/VPN/route table ни одного клиента.
Новые hostname, Tailnet node identity и test auth key; не клонировать рабочую NVS.
На первом старте advertisements пустые, exit-node off, route acceptance off.
После проверки ACL отдельное разрешение администратора только на TEST_AP_SUBNET;
никаких PRODUCTION_SUBNET, UPSTREAM_SUBNET, LAN lab gateway, 0.0.0.0/0 или ::/0.
Проверить реальные advertised/approved routes в control plane после reconnect/reboot.
Не использовать ключ, автоматически одобряющий широкие маршруты.

На ПК сохранить `ipconfig /all`, `route print`, `Get-NetIPConfiguration`,
`tailscale status`, `tailscale netcheck`, выбранный interface/next-hop.
На lab gateway только read-only inventory: `ubus call network.interface dump`,
`ip addr`, `ip rule show`, `ip route show table all`, статус policy routing/proxy/VPN,
при необходимости scoped counters/packet capture. Не останавливать и не перенастраивать сервисы.
Учитывать double NAT: ПК из upstream gateway не обязательно имеет прямой доступ к ESP STA.
Для локального UI использовать отдельный клиент в ESP SoftAP/lab gateway либо test Tailnet IP;
не открывать port forwarding на основном роутере ради теста.

Для каждого измерения записать direct endpoint или DERP region, transport,
выход через policy routing/proxy и используемый uplink. Наличие UDP не доказывает direct.
Удалённый тестовый endpoint — отдельное позднее измерение, не смешивать с локальной базой.

## 2. Read-only identify, backup и recovery

Физически отключить рабочую ESP от тестового ПК/USB hub. Сверить фото/маркировку
резервной N16R8, USB VID/PID/COM и MAC. Не выбирать «первый найденный COM».
Проверить кабель data, питание, BOOT/RESET и возможность manual download mode.
Не запускать автоматический upload/erase из IDE.

Команды ниже — примеры для установленного esptool 4.x; сначала проверить `--help`
точной версии. Для esptool 5 имена подкоманд могут отличаться. Не исполнялись здесь:

```text
python -m esptool --chip esp32s3 --port COM_TEST chip_id
python -m esptool --chip esp32s3 --port COM_TEST flash_id
python -m espefuse --chip esp32s3 --port COM_TEST summary
python -m esptool --chip esp32s3 --port COM_TEST read_flash 0x0 0x1000000 spare-full-16m.bin
python -m esptool --chip esp32s3 --port COM_TEST read_flash 0x8000 0x1000 spare-table-sector.bin
```

Не писать eFuse. Определить secure boot/flash encryption, UART download restrictions,
anti-rollback/security version, chip revision и фактический flash ID/16MiB.
При защите чтения/непонятном режиме остановиться: сырой ciphertext backup может
не обеспечивать переносимость/восстановление. Никакого force/disable-security обхода.
PSRAM 8MiB и octal режим сверить по boot log/self-test, это не вывод из flash ID.

Сделать два независимых чтения backup и сверить SHA256. Если есть различия из-за
живых NVS writes — обеспечить quiescent download mode и повторить до совпадения.
Распарсить реальную partition table с MD5, сохранить bootloader region и обе apps,
otadata/OTA state и NVS/identity по фактическим offset/size. 0x9000/0x10000 — только
ожидание базы, не команда чтения до проверки таблицы. Сохранить flash header mode,
frequency/size, app chip/revision/secure_version/checksum/appended digest.
Full backup содержит ключи; зашифровать локально, ограничить доступ, не прикладывать в GitHub.

Recovery gate: manual BOOT работает, точная команда/план возврата и offsets
проверены offline, известны совместимые bootloader/table/app и backup NVS этой
резервной платы. Не восстанавливать рабочую identity на вторую онлайн ESP.
При отсутствии serial recovery — STOP до любых записей.

## 3. Явное согласие на конкретную запись

Показать пользователю hashes, exact flasher_args, что будет overwritten/erased,
и способ восстановления. Получить отдельную команду на flash резервной платы.
Не включать write/erase команду в автоматически запускаемые скрипты этого комплекта.
Не менять flash voltage, eFuse, security settings или calibration/NVS schema.

Сначала SDK6 в прежней 4MB разметке. Проверка новой app со старым bootloader/table
на резервной плате — отдельный тест: bootloader реально старый, header/size совместимы,
конкретный OTA slot известен; ничего не писать на рабочую ESP.
Только затем отдельное согласие на 16MB USB FULL flash согласованного комплекта.
App-only OTA не заменяет table/bootloader. Full erase не подразумевается словом FULL:
если нужен erase, отдельно согласовать потерю spare NVS; merged gaps FF могут её стереть.
Инициализацию otadata для новой ota_1 позиции проверить, не переносить старый выбор слота вслепую.

## 4. Boot и базовая сеть

1. Serial log от reset до app-ready; chip, reset reason, bootloader/app versions,
   реальная flash size/mode/frequency, octal PSRAM 8MiB, tests, CPU 240MHz/HZ100.
   Проверить rollback enabled, asserts/WDT enabled и настройки core locking.
2. Сверить startup NVS без format/erase/migration. При NVS error остановиться;
   identity переживает два reboot только на резервной плате.
3. До нагрузки: INTERNAL/8BIT, DMA, SPIRAM free/min/largest block, task stacks,
   WDT/IDLE progress, telemetry. Для IDF6 tcpip task должен быть видим, а не «0%» из-за tiT.
4. STA lab gateway association/DHCP/DNS/NTP. SoftAP TEST_AP_GATEWAY/PREFIX, тестовый client
   TEST_CLIENT_IP: lease/renew/reconnect/conflict handling. Проверить AP+STA channel,
   route/netif binding, DNS relay и связь с UI/SNMP/console.
5. NAPT только на стенде: client→STA uplink, TCP/UDP/ICMP, return traffic,
   checksum/TTL, MTU/PMTU/DF, chained/custom pbuf paths и counters ownership.
   SYN/large transfer/fragment cases; no duplicate free/leak/assert. Отсутствие crash
   не заменяет source/map contract audit.

## 5. Tailnet, TLS, DERP, маршруты и HA

1. Авторизация отдельной node; ACL и advertisements проверить до одобрения
   TEST_AP_SUBNET. Нет exit node, конфликтующих или внезапно восстановленных маршрутов.
2. Coord TLS и WG direct: handshake, key persistence, ping и короткая передача
   в обе стороны; endpoint/path подтверждён peers/counters/capture.
3. DERP отдельным сценарием. Если необходим UDP block — только scoped rule на
   отдельном test client с заранее записанным remove plan, не роутере/рабочем peer.
   Подтвердить region/relay counters; проверить reconnect, fragmented TLS records,
   EOF/DNS error/WANT_READ/WRITE, правильную CA/hostname/time validation.
4. Negative TLS на контролируемом test endpoint/DERP map: bad CA/name/expired,
   future validity/clock unset. Production control plane не подменять. Отказ
   ожидается безопасный; не включать InsecureForTests или отключать проверку.
5. Stalled read >200ms, WiFi flap, delayed coord shutdown и stop timeout,
   быстрый stop/start, repeated partial init, stale SD snapshots, full peer queue
   removal/revocation — известные lifecycle блокеры. Выполнять лишь после принятия
   отдельного fault plan; текущая сборка сама по себе их не исправляет.
   Любой unsafe free/overlap/stale TaskHandle/removal loss — STOP, production NO-GO.
6. HA/Tuya — отдельный тестовый endpoint/устройство в TEST_AP_SUBNET. Проверить
   route reachability/ACL, локальное управление, discovery/broadcast assumptions,
   reconnect и длительные HA sessions. WG routing не гарантирует L2 broadcast discovery.
   Не переносить рабочие Tuya и не менять рабочую HA configuration ради smoke.

## 6. OTA slots, rollback и serial возврат

Проверить ota_0→ota_1→ota_0 на согласованном тестовом комплекте, active/running
partition и OTA states по serial/API; version/hash каждого slot фиксировать.
Pending-verify reset и interrupted OTA тестировать только на запасной плате
после проверки recovery; interrupted bootloader/table write в smoke не делать.
`app_main` подтверждает image рано: поздний DERP/NAPT failure не гарантирует
автоматический rollback. Отдельно доказать ручной возврат и сохранность spare NVS.
Для 16MB слот 4MiB не делает старый 4MB bootloader автоматически совместимым.
Возврат к прежней разметке — согласованный serial full restore, включая table,
OTA metadata и совместимый bootloader; NVS этой платы восстановить только по плану.

## 7. Производительность и soak — после smoke

Сначала одинаковый local path и endpoint: baseline wgopt13 и candidate,
P1 receiver 120s, затем reverse; не сравнивать локальный direct с VPS/DERP.
Сохранить iperf version/args, RSSI/channel/PS, endpoint, loss/retransmits,
WiFi errors/NO_MEM, RX drops, loop/control-plane latency, queues/retry stats,
internal/DMA/PSRAM min/largest, stack high-water, WDT/reset counters.
Ориентир ≥95% от сопоставимой базы 5.13Mbps = 4.8735Mbps, drops=0 и NO_MEM=0;
это предложенный gate, не результат. Затем DERP и отдельно удалённый тестовый endpoint.
Soak ≥24h с тестовыми HA/Tuya, controlled reconnect/peer churn; сравнить память
после quiescence, keys/NVS persistence, маршруты и все resets. Не объявлять pass
по одной успешной загрузке/iperf.

## 8. Итоговые разрешения

BUILD-GO: clean builds/tests/KAT/source-map-image gates закрыты.
HARDWARE-GO: пройдены spare smoke/recovery/slots/rollback/negative tests,
принят бюджет памяти; отдельное разрешение на каждый следующий flash.
PRODUCTION-GO: отдельное решение после lifecycle/fault/security/soak proofs.
Unresolved timeout/overlap, TLS retirement, DERP reader ack, stale handles/readers,
peer-removal queue overflow и sync NVS delays сохраняют production NO-GO.
