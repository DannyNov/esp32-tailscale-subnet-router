# wgopt13: пассивная диагностика WG loop

База: wgopt12 `d3b58fc48f406adf86d3122d0684e6b724f65d06`.
Ветка: `diagnostic/wgopt13-loop-latency-v0135`.
Immutable microlink: `eb63b97073e529d57bc9c1deaeea25ac304034e5`.
Версия application: `0.1.35-tuya-wgopt13`.

## Измерения и границы

- Каждый drain отдельно: count/time/empty. Причина — первая ложная проверка
  исходного short-circuit условия: count имеет приоритет над time, time над
  empty. После цикла время и очередь повторно не проверяются. Overshoot одного
  packet processing сохраняется; лимиты не меняются.
- `work`: от начала итерации до начала delay. `cycle`: до возврата delay.
  `active_elapsed` и `idle_elapsed`: elapsed вокруг неизменённого vTaskDelay;
  это wall time с preemption, не exclusive CPU и не гарантия сна.
  При 100 Hz исходный active=0 ticks, idle=1 tick. Новая блокировка не добавлена.
- `control_pre`: начало итерации → перед drain1 (peer updates, DERP/CMM,
  DISCO и диагностика). `control_mid`: после drain1 → перед drain2, включая
  periodic/probes. `peers`: elapsed process_peer_updates. Это длительность
  обслуживания блоков, не возраст команды в coord queue. Среднее/максимум
  относятся к опубликованному окну, не ко всему uptime.
- Queue wait histogram: `<1,<4,<10,<20,<40,<80,>=80 ms`. Использует имеющийся
  enqueue timestamp descriptor и уже прочитанный dequeue timestamp, до
  processing/free. Некорректные timestamps считаются отдельно. Только один
  локальный increment на пакет; нет новых clocks/atomics/logs/allocations на
  packet path. Producers, descriptor layout, backend и ownership неизменны.
- Новое измерение tcpip_input не добавлено: существующее D_RX_LWIP уже
  охватывает input вызов. Это enqueue/input elapsed, **не LAN delivery**.

Live struct принадлежит единственной WG task и находится на её стеке (меньше
320 bytes). Раз в >=10 s после delay фиксируется полный снимок под коротким
portMUX; reporter копирует его под тем же mux, печатает после unlock. Все
11 строк имеют одинаковый end_us. Счётчики uint64, окна неперекрывающиеся;
перезапуск задачи сбрасывает live state. При задержке reporter старый снимок
может быть заменён новым: пропуск виден по временным границам, не суммировать
несмежные окна как непрерывные. Последнее неполное окно при shutdown не
публикуется. Наследуемые WG4/WG12 snapshots асинхронны относительно WG13.
Публикация/сброс не входит в cycle и может попасть в следующий межцикловый gap.
Небольшие накладные расходы clocks и 11 строк/10 s требуют оценки на устройстве.

Не меняются TX retry, security, WDT, IDF, HZ, queues/buffers, task priorities,
wake protocol, routing, NVS и partitions. Нет flash/upload/deploy действий.

## Проверки

`python tools/test_wgopt13.py`: компилирует реальные helpers/reporter и точные
generated drain predicates с deterministic queue/clock mocks. HZ=100/1000,
count/time/empty, precedence, overshoot, границы histogram, zero elapsed,
64-bit sum, invalid timestamps, coherent reporter copy и duplicate suppression.
Контракты сравнивают producers/backend/TX с generated wgopt12 и проверяют
fail-closed anchors. CI выполняет также существующие host regression suites,
собирает только ESP32-S3 application, проверяет chip/version/checksum/appended
SHA256/partition bounds/config/gitlink и пишет provenance + SHA256SUMS.
Host mocks не доказывают target scheduling и реальную стоимость измерений.

## Один аппаратный профиль после проверки нового BIN

Не запускался здесь. После ручной OTA установки именно wgopt13 и проверки
версии: один непрерывный захват /log, 30 s idle → один 120 s receiver iperf
P1 в прежнем направлении/топологии → 30 s idle. Не выполнять дополнительный
P2 или повтор прежнего wgopt12. Сохранить полный лог и iperf JSON с временами.
Сопоставить окна WG13 (drain причины, wait хвост, active/idle elapsed,
control/work/cycle max) с WG4 RX drops/peak, WG12 retries, Wi-Fi NO_MEM,
CPU/RSSI и goodput. Игнорировать переходные неполные окна. Это диагностика
мест задержки, не доказательство ускорения. При WDT/потере связи/росте drops
прекратить профиль и откатиться.

## Rollback

Основной: wgopt12 `d3b58fc48f406adf86d3122d0684e6b724f65d06`,
`firmware-0.1.35-tuya-wgopt12-esp32-s3-ota.bin` из ранее проверенного artifact.
Резервный: wgopt10 `44220ec080e5688c896855d41a90f69cd0fcff26`,
ранее сохранённый wgopt10 application image. Перед установкой сохранить
проверенные BIN/SHA256 и доступный recovery/OTA канал. Здесь их доступность
на устройстве не проверялась. Только application OTA; никаких bootloader,
partition/NVS erase или factory reset. Сначала wgopt12, при необходимости
wgopt10 штатным способом. Никаких изменений main.
