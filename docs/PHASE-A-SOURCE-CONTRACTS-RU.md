# A3: предварительная проверка исходников, без link/hardware GO

Официальный ESP-IDF v6.1: `fff9895c82d744c7237be8847347bdd1b07c6643`.
lwIP gitlink: `c6f2f878e7b0f86033214b85547d579be43351e3`.
Mbed TLS gitlink: `a2b32072ea898afc1ed5b6caf6931e36028c91d6`.
Wi-Fi lib gitlink: `7cd4d7b2b4acc38aead43b029ac9409c3eba9c54`.

Exact tag разрешён через официальный Git API; выбранные файлы скачаны по immutable
commit URLs, hashes сопоставлены с фактически установленным PIO package 4.60100.0.
Все 14 проверенных файлов совпали побайтово. Полный manifest и SDK submodule map
сохранены отдельно в `phase-a-evidence/sdk61-source/` и `environment-manifest.json`.
Это выборочная сверка package provenance, не полная Git/ABI аттестация всего SDK.

| Контракт | Что проверено в exact source | Что ещё не доказано |
|---|---|---|
| Wi-Fi TX | private wifi.h объявляет copy TX с `uint16_t len`, return int; by-ref с `size_t len`, return esp_err_t, четвёртый аргумент netstack_buf; совпадает с ручными extern в main/wg10_wifi_tx.c | Closed driver implementation, вызовы wrappers в итоговом SDK6 ELF, ошибочные пути ref/free и hardware ABI |
| Wi-Fi pbuf | wifi_netif.c выбирает by-ref при SPIRAM WiFi/LWIP config; wlanif.c flatten chained pbuf в новый q и освобождает свой q после transmit_wrap; ESP_ERR_NO_MEM отображается в ERR_MEM | Весь callback-registration/release call graph и stress exactly-once accounting |
| tcpip_input | tcpip.c передаёт pbuf в tcpip_inpkt; при memp/trypost error возвращает ERR_MEM, сам входной pbuf не освобождает; wlanif_input освобождает на ошибке | Все application ingress/fallback/custom-chain paths и late callbacks при stop |
| NAPT | ip4_napt.c сохраняет ip_napt_forward(p, iphdr, inp, outp), ip4.c вызывает его и прекращает forwarding при ошибке | Итоговое `--wrap`, LTO/interposition, source-route hook и обе стороны NAPT по map/disassembly/capture |
| ARP extension | В etharp.c присутствуют private arp_table, state/netif/ipaddr и static-entry helpers, используемые etharp_netif.inc в общей translation unit | Build6 с этим кодом, ETHARP flags/config и поведение при DHCP/rebind/overlap |
| netif/pbuf | exact netif.h и pbuf.c сохранены с hashes | Полный lifecycle netif/context/UDP PCB, custom pbuf free и ownership/fault matrix |
| FreeRTOS | tasks.c различает deletion и отложенный idle cleanup; xTasksWaitingTermination остаётся | Handle lease/generation и безопасный last-access epilogue приложения; task counter не заменяет их |
| TLS | exact esp_tls_mbedtls.c и SDK MbedTLS Kconfig сохранены; MbedTLS4 требует PSA init для SSL | PSA port, RNG failure, CA/name/time negatives, coord getter против destroy и DERP reader retirement |
| diagnostics/libc | `tiT` в baseline reporter, новый SDK использует `tcpip`; libc/stdio wrappers требуют проверки | Rename patch с отдельным manifest, Picolibc formatting/reentrancy и link wrappers |

Начальный read-only lookup `components/lwip/port/esp32/netif/wlanif.c` дал 404:
правильный exact SDK путь — `components/esp_netif/lwip/netif/wlanif.c`.
Ошибка сохранена в fetch manifest, успешный новый путь также записан; 404 не
использован как доказательство удаления Wi-Fi adapter.

SDK6 ELF/map отсутствуют из-за crypto compilation blocker. Поэтому ни один
source-only пункт здесь не помечен как полный A3 pass. Никакие linker wrappers,
assertions, WDT, TLS verification, replay checks или функции не выключались.
Lifecycle изменения wgopt14 сюда не включены; известные stop/TLS/readers/queue
риски остаются production NO-GO.
