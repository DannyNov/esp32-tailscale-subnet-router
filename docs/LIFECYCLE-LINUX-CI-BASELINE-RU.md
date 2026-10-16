# microlink-lifecycle-linux-ci-baseline — инфраструктурный STOP

Дата: 2026-10-16. Linux compile/link/execute не подтверждён. Lifecycle-патча нет.

База: `ed510efa72da0925cbac3d15ab353175b00c96b2`.
Ветка: `experiment/microlink-lifecycle-linux-ci-20261016`.
Gitlink external/microlink: `eb63b97073e529d57bc9c1deaeea25ac304034e5`.
Предыдущий audit commit: `ef6575b1a1e853a87bb1f51d60a670b60eb21c78`,
его parent совпадает с базой. Оба прежних проверенных checkout чистые.
Все 136 input hashes последнего audit-manifest совпали; production tree в
новом worktree не изменён. Существующая wgopt13 ветка не переключалась.

## Что действительно выполнено

- Проверка доступности: git доступен; GCC, Clang, gh, Docker отсутствуют в PATH.
  `wsl --list --quiet`: exit 1, Windows Subsystem for Linux не установлен.
- Zig executable из `../derp-header-fix/test-runtime/ziglang/zig.exe`:
  `version` → `0.16.0`, exit 0.
- Единственный новый compiler smoke:
  `zig.exe cc -std=c11 -Wall -Wextra -Werror -UNDEBUG tests/lifecycle_ci/smoke.c -o smoke.exe`
  (в фактическом запуске пути были от родительского workspace).
  Exit 1: `unable to rename temporary ...smoke-....obj.tmp ...smoke.obj: Permission denied`.
  Link и execute не состоялись. Повторных компиляций Zig не делалось.
- Обычный текстовый rename в отдельном evidence-каталоге прошёл.
  Smoke source не read-only. После ошибки процессы zig/clang/gcc/cc1 не найдены;
  это не исключает кратковременные locks. Temp указывает на виртуальный
  sandbox AC/Temp. Защищённые каталоги не менялись. Причина rename неизвестна:
  ни policy block, ни ошибка конкретного компонента не доказаны.
- Первоначальный local clone завершился ошибкой MSYS NtCreateDirectoryObject
  `0xC0000022`; вместо clone обычный `git worktree add` успешно создал изоляцию.
  ACL, настройки защиты и cache не менялись; escalation не запрашивалась.
- Python syntax check и `run.py --prepare-only` прошли, exit 0.
  Это проверка подготовки, а НЕ компиляция/выполнение C.

## Подготовленный baseline

`tests/lifecycle_ci/run.py` проверяет pin и чистоту submodule и извлекает
неизменённый фрагмент reconnect из `components/microlink/src/ml_derp.c`.
Это реальный source fragment с deterministic FreeRTOS/TLS boundary doubles,
НЕ полный объект ml_derp.c, НЕ реальный TLS runtime и НЕ доказательство target UAF.
Ожидаемый контракт: teardown после 20 × 10 ms при rx_parked=false.
При подтверждении expected violation тест возвращает 0; любое несовпадение
ожидания или compiler/runtime failure завершает workflow ошибкой.
Отдельный control.c — положительная небольшая модель, не production fix.
Smoke, negative и control имеют отдельные compile/run stdout/stderr и exit codes.

SHA256 pinned ml_derp.c:
`35a89a5d771b3b222beabde50f44fa375e3f1abe8cf46b0b88d8881353e1d2e2`.
SHA256 нормализованного извлечённого фрагмента:
`21934d923b9a4d8ce569d932ae815e143b7afae4be0795b21f9f6dcfd0f56a84`.

## Публикационный блокер

Локальный candidate scan всей reachable основной истории базы: 452 commits,
2823 objects, 1248 blobs. Найдено 505 записей-кандидатов по категориям
credentials, private addresses и другим чувствительным данным; значения в
отчёт не выводились. Это не 505 подтверждённых секретов. Полная классификация
и история submodule не выполнены. Публикационный gate НЕ пройден.
Push, GitHub Actions, releases, uploads, SDK builds и прошивка не выполнялись.
Ссылка на CI отсутствует. GitHub access/runner availability не проверены запуском.
Workflow имеет contents: read, без secrets, deploy, firmware и artifact uploads.

Evidence находится локально рядом с checkout:
`../microlink-lifecycle-linux-ci-evidence/scan-and-provenance.json`.
Сканер: `../lifecycle-ci-local-audit.py`. Эти файлы не публикуются.

## Воспроизведение в разрешённом Linux checkout

После полного security review истории и новых публикуемых файлов:

```sh
git submodule update --init --recursive
command -v gcc clang python3
gcc --version
clang --version
python3 --version
python3 tests/lifecycle_ci/run.py --cc gcc
python3 tests/lifecycle_ci/run.py --cc clang
python3 tests/lifecycle_ci/run.py --cc gcc --sanitize
python3 tests/lifecycle_ci/run.py --cc clang --sanitize
```

Результаты ожидаются в build/lifecycle-ci, но сейчас их исполняемого подтверждения
нет. Workflow подготовлен для ubuntu-24.04 с двумя compiler jobs. GCC/Clang
versions, sanitizer compatibility и успешные exit codes пока неизвестны.
Существующие 23 host suites в этом этапе НЕ запускались; прежние результаты
SDK6 CI не переносятся на этот checkout.

| Gate | Статус |
|---|---|
| CI environment | NO-GO / compile+execute не подтверждён |
| negative baseline | NOT DEMONSTRATED; только подготовка source fragment |
| global lifecycle safety | NO-GO |
| DERP lifecycle | NO-GO |
| SDK5 production firmware | UNCHANGED; не собиралась |
| SDK6 | NO-GO; вне этапа |
| hardware | NO-GO |
| production | NO-GO |

Следующий конкретный шаг: завершить классификацию кандидатов в истории и
security review submodule до push только экспериментальной ветки либо запустить
эти команды в доступном разрешённом изолированном Linux runner без публикации.
К lifecycle refactor этот этап не переходил.
