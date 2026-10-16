# Lifecycle snapshots: manager + telemetry + Web UI (экспериментальный пилот)

**Статус:** HOST-PILOT TESTED; SDK5 BUILD NOT RUN; GLOBAL/DERP/HARDWARE/PRODUCTION **NO-GO**.

Исходная проверенная база: публичная диагностическая ветка `af136603c3db472115fcf3ccd9c82eeef4b19d3c` поверх работающей wgopt13 `ed510efa72da0925cbac3d15ab353175b00c96b2`; закреплённый gitlink `external/microlink` — `eb63b97073e529d57bc9c1deaeea25ac304034e5`. Никакого пуша, изменения настоящей прошивки или прошивки устройства в этом этапе не было.

## Что готово

`apply_patch.py` содержит **конкретную реализацию** и создаёт изменения ровно в четырёх путях:

1. `main/tailscale_snapshot.h` — новый публичный API копий `status`, `diag`, `peer`, RTT и имён регионов (без возврата сырых указателей).
2. `main/tailscale_manager.c` — пять функций снимков, которые защищают **время жизни instance** через существующий `s_life_mux` (неблокирующая попытка). Для peers/RRT/name дополнительно проверяется `s_life_generation`. Начало connect fail-closed при отсутствующем mutex.
3. `main/telemetry.c` — замена единственного сырого `tailscale_get_microlink()` на `tailscale_snapshot_diag()`.
4. `main/web_ui.c` — замена сырых микролинк-указателей при формировании Tailscale runtime/status и списка peers на snapshot API; DERP имена и peers копируются до отпускания mutex. Промежуточный MTU/другой JSON код сохраняется.

**Важно:** генератор проверяет pinned commit, `experiment/` branch, чистый checkout, точный gitlink, git blob SHA исходных 3 файлов и якоря перед записью. Вариант с другим исходником, повреждённым якорем или уже применённым патчем должен STOP. Это не замена full test; необходимо проверить реальную сборку SDK5.

## Запуск в отдельной экспериментальной копии

```bash
# Выполнять только в ЧИСТОМ отдельном checkout, не менять production.
git clone --recurse-submodules https://github.com/DannyNov/esp32-tailscale-subnet-router.git /tmp/esp32-lifecycle-snapshot-test
cd /tmp/esp32-lifecycle-snapshot-test
git checkout af136603c3db472115fcf3ccd9c82eeef4b19d3c
git switch -c experiment/local-lifecycle-snapshot-test

python3 /path/to/this-package/apply_patch.py --repo . --dry-run
python3 /path/to/this-package/apply_patch.py --repo . --manifest generated-manifest.json

# Затем: полный SDK5.5.3/PlatformIO build и существующие 23 host suites.
# Пакет не прошивает ESP32 и не изменяет GitHub сам по себе.
```

Сам пакет проверяется командой `python3 tests/test_generator.py && ./tests/run.sh` (GCC/Clang, оба с ASan+UBSan). Логи этой сессии в `test-run.log`.

## Что тесты *реально* доказывают

`tests/test_generator.py`: изменения якорей, сохранение промежуточного кода, отказ при повторном применении и несоответствующих кусках исходников. Уникальность реальных anchors проверена через GitHub на конкретном pinned commit. При этом patch целиком НЕ был применён к настоящему checkout.

`tests/test_snapshot.c`: скомпилированы **вставляемые функции из `FUNCTIONS` генератора** под pthread-дублёрами FreeRTOS/microlink, 6 конкурирующих читателей + 10 000 замен instance, неуспешный lock, NULL instance, смена generation, копирование DERP region name, peer copies после уничтожения объекта. Это не исполнение `tailscale_manager.c` целиком и не проверка настоящего конкурентного microlink.

## Известные ограничения и safety gates

- Защита только внешнего lifetime против управления manager connect/disconnect через `s_life_mux`. **Внутренние writer tasks microlink не используют этот mutex**: диагностическая snapshot структура не гарантирует консистентные поля при их параллельном обновлении.
- `tailscale_is_connected()` остаётся raw, как и SD writer, DNS, route diagnostics, supervisor special paths и async callbacks. Manager `microlink_destroy()` продолжает возвращать void, его timeout/generation не исправлены, DERP reader/TLS quiescence тоже нет. Более того, другие вызовы `tailscale_get_microlink` в web_ui могли остаться за пределами двух изменённых блоков; нужен полный аудит.
- Неблокирующие снимки при занятости `s_life_mux` возвращают `false` и пустые данные. UI на время connect/disconnect может показать 0 peers/connected=false; это сознательный экспериментальный компромисс. Приложение не должно интерпретировать временную недоступность как подтверждённую потерю связи для автоматики.
- Между получением status и каждого peer происходит отдельный захват mutex; проверка `generation` защищает от **смены instance**, но не от обновления списков/region внутри существующего microlink. Данные UI могут быть неполными при конкуренции, но экземпляр при чтении не освобождается менеджером.
- Нужны полноценные ESP-IDF 5.5.3/PlatformIO сборка, текущие 23 host suites, software regression, затем отдельные тесты на запасной ESP32-S3. До этого в устройства НЕ прошивать.
- GitHub, рабочая ветка wgopt13, gitlink microlink и устройства не модифицированы.
