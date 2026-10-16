# idf61-crypto-compat — экспериментальный SHA этап

16.10.2026. EXPERIMENTAL / BUILD-ONLY. Hardware-GO и production-GO: NO-GO.
База: `3a33e583d70d80f490c6b2f245638ee28ea64f84` опубликованной SDK6 ветки.
Microlink gitlink: `eb63b97073e529d57bc9c1deaeea25ac304034e5`, без изменений.
Flash16 не включён; partitions.csv и upload/flash параметры не менялись.

## Реализовано

`components/web_password/include/sha256_psa.h`: локальный multipart SHA-256,
проверка init/setup/update/finish/длины/abort, выдача digest только после успеха,
очистка временного digest и ошибочного output. Глобальная PSA служба не освобождается.
IDF 6.1 startup hook `components/mbedtls/port/esp_psa_crypto_init.c` выполняет init
на SECONDARY/core0 priority 104. Mbed TLS CMake удерживает hook через linker -u.
TF-PSA `core/psa_crypto.c:psa_crypto_init()` возвращает успех немедленно после
успешной startup initialization. На ошибке init адаптер не вызывает другие PSA API.
Полноценное подтверждение присутствия hook в linked app map ещё невозможно без ELF.

Password: SHA256(raw 16-byte salt || plaintext bytes), lowercase double-digit hex,
NVS namespace/key `tsr/web_password`, формат `32hex:64hex` сохранены. Verify возвращает
false при crypto/NVS/hex ошибке; сравнение всех 32 bytes без раннего выхода по значению.
Set не вызывает NVS write при crypto error; NULL отвергается. Пустой set по прежней
семантике записывает пустую строку (снятие пароля). Пустой plaintext в корректном старом
hashed fixture по-прежнему может пройти verify. Uppercase hex fixtures принимаются.
NVS set/commit ошибки возвращаются; host mock не доказывает физический rollback NVS
при отказе flash/питания. Нет erase, новой схемы, изменений identity или алгоритма.

Telemetry: raw 6-byte MAC || `esp32-tailscale-router-v1` без NUL, первые восемь
digest bytes в lowercase hex. Затем SHA256(`esp32-tailscale-v1` без NUL || 16 ASCII
hex bytes ID), первый checksum byte в двух hex. 18-символьный результат публикуется
только после обоих успехов. Единственный вызов compute_device_hash — telemetry_init;
при отказе MAC/crypto init завершается до load_nvs, counters и создания sender task.

## Исполняемые host проверки

`tools/test_crypto_compat.py --sdk PATH_TO_IDF61 [--cc cc]` компилирует реальные
TF-PSA sources из resolved IDF package с отдельной host-only SHA/HMAC-DRBG config.
Entropy остаётся настоящим системным источником библиотеки; target config не меняется.
PSA success wrappers делегируют реальным операциям, known hashes не подставляются.
NVS и salt generation замоканы только как host boundary; все данные синтетические.

`tools/test_crypto_legacy.py --sdk PATH_TO_IDF553 [--cc cc]` извлекает неизменённые
compute_hash/bytes_to_hex/compute_device_hash из точной публичной базы через git show
и исполняет с настоящей legacy SHA256 SDK5.5.3. Оба теста проверяют одинаковые
независимые Python hashlib fixtures. Empty и abc SHA256 дополнительно зафиксированы
известными golden digests. Пять password fixtures (включая UTF-8, 1024 bytes), три
синтетических MAC и checksum, все PSA stages, init failure без последующих API,
short digest, invalid hex во всех позициях, NVS open/read/set/commit failures,
NULL/empty/uppercase семантика проверяются исполняемыми asserts с -UNDEBUG.
Compilation failure означает test failure; KAT не объявляется выполненным до запуска.
Logs, source/header SHA256, package versions и команды: `build/crypto-compat/`.
Host успех не подтверждает target execution, timing side-channel или TLS interoperability.

Локально: 23/23 прежних host suites PASS; PSA KAT PASS; legacy KAT PASS.
Первый SDK6 build после SHA-port остановился на двух GCC15 stringop-truncation errors
в reset_history.c. Отдельный минимальный commit заменяет эти два strncpy на strlcpy,
не выключая warnings и не меняя размеры/схему полей. Следующий build и два Linux CI
обязательны; итоговые результаты сохраняются отдельно с exact source SHA.

## Карта оставшейся криптографии (не переносить вслепую)

| Исходник pinned microlink | Legacy контракт | IDF6.1/PSA направление и обязательная проверка |
|---|---|---|
| include/microlink_internal.h:27–28,452–453 | entropy/CTR-DRBG includes и per-session поля | Публичные legacy headers удалены. Удаление полей требует согласованного generated header/source overlay с pins/anchors/hashes; upstream gitlink не менять. |
| src/ml_derp.c:891–895,923,1229–1245 | init/seed/conf_rng/free per-session RNG | В Mbed TLS4 ssl_conf_rng удалён; TLS использует PSA. Не заменять RNG фиктивным callback, не освобождать глобальную PSA на session teardown. Нужны failure injection и TLS CA/hostname/time negatives. |
| src/ml_derp.c:897,932 | config_defaults и set_hostname возвращают int, сейчас игнорируются | Сохранять VERIFY_REQUIRED и crt_bundle; добавить проверяемый error unwind, не трогая протокол reader retirement. Контекст не free до завершения reader. |
| src/ml_noise.c:20–21,152–214 | legacy ChaChaPoly, key 32 bytes, nonce 00000000 || BE64(counter), ciphertext || 16-byte tag | PSA import volatile CHACHA20 key/256, CHACHA20_POLY1305, encrypt/decrypt, destroy on всех путях, проверка длины, plaintext не использовать до valid tag. Нужны RFC8439, counter boundary, invalid-tag и protocol fixtures. |
| src/ml_coord.c:35, src/ml_wg_mgr.c:32 | mbedtls/base64.h | API остаётся, не заменять без реального compile blocker. |
| components/wireguard_lwip/src/crypto | Собственные SHA/BLAKE/Curve/ChaCha реализации | Это не mbedtls_sha256 legacy usage; wire format, replay и ключи не менять. |

После этого SHA этапа RNG/Noise адаптация допускается только отдельными reviewable
порциями с собственными криптографическими и TLS proof gates. Незакрытый контракт
владения/ошибок означает STOP, а не отключение проверки или функций ради сборки.

Открытые wgopt14 риски (stop-timeout overlap, TLS reader/free, stale task/log readers,
peer removal queue overflow, sync NVS) сохраняют production NO-GO даже при успешной
компиляции. Lifecycle redesign в эту серию не включён. Устройства не затронуты.

Официальный контракт миграции:
https://docs.espressif.com/projects/esp-idf/en/stable/esp32c61/migration-guides/release-6.x/6.0/security.html
Решающие API и конфигурации сверяются с фактически установленным SDK6.1 package,
а не с изменяемой latest документацией.
