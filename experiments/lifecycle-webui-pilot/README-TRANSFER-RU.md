# Lifecycle Web UI pilot — пакет для Work

Это **экспериментальная передача архива**, а не применённый патч и не рабочая прошивка.

## Источник
- Точная база: `af136603c3db472115fcf3ccd9c82eeef4b19d3c`.
- Gitlink microlink: `eb63b97073e529d57bc9c1deaeea25ac304034e5`.
- Архив: `experiments/lifecycle-webui-pilot/lifecycle-webui-pilot.zip`.
- SHA256 ZIP: `8476d7fcd9c2f41e32707bf9a6a1e33c28064efa01b9786c5b177c9a1e84940f`.
- Git blob SHA-1 ZIP: `0b337d9669eacc5949ce9ac8336b6fc26d211866`.
- Содержимое: 8 файлов (README-RU.md, apply_patch.py, test-run.log, tests/*, checksums.json).

## Как получить Work
Пакет хранится **как бинарный ZIP в Git**, а не как ссылка на ChatGPT Library. Открой ссылку на ZIP в GitHub и нажми Download raw file, либо выполни в *отдельном* checkout:

```bash
git fetch origin experiment/lifecycle-webui-pilot-transfer-20261016
git switch --detach FETCH_HEAD
sha256sum experiments/lifecycle-webui-pilot/lifecycle-webui-pilot.zip
unzip -l experiments/lifecycle-webui-pilot/lifecycle-webui-pilot.zip
```

На Windows предпочтительнее `Copy-Item` бинарного файла после checkout, а не PowerShell-редирект `git show > zip`, который может повредить байты.

ПРОВЕРКИ перед применением: сначала распаковать, проверить SHA256 архива и внутренние checksums.json. Затем прочитать README-RU.md, dry-run fail-closed генератора в **другом чистом экспериментальном checkout** точной базы, только затем применять. Package не прошивает ESP32 и не изменяет production code самостоятельно. Полный SDK5 build, CI и аппаратные тесты для этого пакета ещё не выполнены; все lifecycle/DERP/hardware/production gates NO-GO.

Не cherry-pick этот transfer-коммит в рабочую integration-ветку: он содержит только перенос пакета и может нарушить проверку чистоты дерева генератором.
