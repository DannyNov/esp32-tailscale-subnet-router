# Независимый эксперимент Flash 16 MiB

Статус: EXPERIMENTAL / BUILD-ONLY / NOT FOR PRODUCTION. Прошивка не разрешена этим документом.
База: wgopt13 `ed510efa72da0925cbac3d15ab353175b00c96b2`, исходный SDK5.5.3.
Эта ветка не содержит SDK6 compatibility port; её можно перенести отдельным commit
на проверенный SDK6 port только после закрытия 4MB compile gate.

## Разметка

| Раздел | Начало | Размер | Конец (исключительно) |
|---|---:|---:|---:|
| nvs | 0x9000 | 0x10000 | 0x19000 |
| otadata | 0x19000 | 0x2000 | 0x1B000 |
| phy_init | 0x1B000 | 0x1000 | 0x1C000 |
| ota_0 | 0x20000 | 0x400000 | 0x420000 |
| ota_1 | 0x420000 | 0x400000 | 0x820000 |
| future_data | 0x820000 | 0x7D0000 | 0xFF0000 |
| coredump | 0xFF0000 | 0x10000 | 0x1000000 |

Системная область до 0x20000 сохраняет существующие служебные разделы и зазоры.
Все физические 16 MiB учтены адресным планом; 0x1C000..0x20000 остаётся
существующим alignment reserve, а не скрытым новым файловым разделом.
OTA по 4 MiB; DATA 8 192 000 bytes = 7.8125 MiB; coredump 64 KiB в конце.
Нет factory app или отдельного recovery app. Bootloader и partition table
по-прежнему занимают существующую системную область; их реальный размер и offset
обязательно сверять по flasher_args и образам конкретной сборки.

`future_data`, type `data`, custom subtype `0x40`: явно резервируем raw DATA.
Не использовать `storage/fat/spiffs/littlefs` до выбора формата. Код приложения
сейчас этот раздел не ищет, не монтирует и не форматирует. Отсутствие FS не означает,
что flash заполнена FF: при переносе layout могут сохраняться старые данные.

Возможный следующий storage проект: bounded кольцевой журнал с CRC/version,
atomic commit marker и восстановлением после power loss; либо отдельно выбранная
LittleFS/FAT+wear-leveling. Нужны бюджет записей, минимальный свободный запас,
ротация по размеру/возрасту, backpressure и защита NVS от частого логирования.
Смена subtype/формата и on-disk schema — отдельная миграция с backup; никакого
автоматического format-on-mount-failure или переноса identity в этом этапе.

## Offline gate

Запуск `tools/validate_flash16.py --idf-tool <official gen_esp32part.py> --output <dir>`.
Ожидается unmodified tool из ESP-IDF v6.1 commit
`fff9895c82d744c7237be8847347bdd1b07c6643`, SHA256
`02f6c1c5f012393d47987ee64bc50ba319a2eda48cbcec754d8cfaf780cce529`.
Gate проверяет exact rows, system partitions, app 64KiB alignment, data 4KiB,
отсутствие overlap/overflow, MD5 и binary→CSV roundtrip; negative cases обязаны падать.
Результат таблицы не удостоверяет app, bootloader, chip/security или установленную плату.

## Отдельный build variant и fallback

`pio run -c platformio.flash16.ini -e esp32-s3-flash16` — только сборка.
Отдельные build directory и sdkconfig (`sdkconfig.esp32-s3-flash16`).
Variant добавляет flash16 defaults после baseline и явно выбирает DIO/80MHz/16MB.
Обязательно проверить, что resolved sdkconfig, bootloader и image headers
действительно соответствуют этому выбору: одна строка в ini этого не доказывает.
Размер каждого app ≤ 4MiB; предлагаемый reserve ≥128KiB остаётся отдельным gate.
Secure boot padding/signatures и chip revision constraints проверяются по реальным images.

Без `-c platformio.flash16.ini` остаются прежние platformio.ini, partitions.csv,
4MB defaults и baseline layout. Ничего из них этот patch не заменяет.
Обычный app-only OTA не переносит таблицу/bootloader/flash setting. Обратно к 4MB
после full-flash16 также нужен serial recovery с согласованным старым комплектом,
а не загрузка старой app в произвольный новый slot.

USB FULL flash означает отдельную будущую операцию обновления согласованного
bootloader + table + OTA metadata + app, после backup/recovery и явного согласия.
Не запускать factory merge/erase вслепую: заполненные FF gaps могут стереть NVS.
Новая таблица меняет положение ota_1/coredump; старые otadata могут выбирать
несуществующую app. План начального OTA state должен быть проверен заранее.
Не включать bootloader/table в production OTA bundle.
