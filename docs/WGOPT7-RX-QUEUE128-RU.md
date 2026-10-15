# wgopt7 — диагностический кандидат с очередью 128

База: `optimization/wgopt6-rx-queue64-v0135`, SHA
`1a1c9554c99e344dc113b95e5bd9b930aeb89336`.
Аппаратная приёмка и прошивка НЕ выполнялись.

## Изменения

- WG RX FIFO: 64 → 128; прежние overlays wgopt1–6 и pinned microlink сохранены.
- WG burst 64/30ms, адаптивный sleep 2/10ms, crypto, DERP, Tuya,
  Tailscale/NVS/routing не изменены.
- `WG4_RX`: `wgq_cap=128`.
- `WG7_MEM` каждые 10 секунд: реальный размер элемента очереди,
  ёмкость; free/min/largest внутренней RAM и PSRAM.
- `udp_psram_delta`, `udp_fallback_delta`, `udp_alloc_fail_delta`
  считают прямые UDP allocation outcomes. Сюда входят WG и DISCO,
  но не DERP; fallback malloc НЕ гарантирует использование internal.
  Heap allocation порядок и владение пакетами неизменны.

Ожидаемая прибавка к внутренней RAM для очереди:
64 × sizeof(ml_rx_packet_t) ≈ 3584 байта (подтвердить `WG7_MEM`).
Пакеты размещаются отдельно: PSRAM сначала, malloc fallback.
Большая очередь не обязана увеличивать TCP throughput и может увеличить RTT.

## После разрешённой OTA

Сохранить предыдущий проверенный OTA BIN и настройки; прошивать только
application OTA через WebUI, без factory/erase/NVS reset. Проверить доступность
Tailscale, офисной сети, Tuya, WebUI. При аналогичной нагрузке сравнить
`direct_drop`, `wgq_peak`, `internal_min`, `internal_largest`,
`psram_min` и `udp_fallback_delta`. При нестабильности откатиться
на wgopt6 штатным OTA. Интернет дома/офиса уже проверяли 14.10.2026.
Цель — меньше RX drop, не обещание роста Мбит/с.
