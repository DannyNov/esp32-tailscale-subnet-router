# OFFICE upstream v0.1.39 integration

Candidate: `0.1.39-tuya-office-wgopt13`. Prepared 2026-11-18.

## Exact baseline and recovery

- Office branch: `diagnostic/wgopt13-loop-latency-v0135`.
- Before: `ed510efa72da0925cbac3d15ab353175b00c96b2` (0.1.35-tuya-wgopt13).
- The live OFFICE status was read after the operator signed in and confirmed that version and persistent identity. Version confirmation is not a flash readback or cryptographic attestation of the installed image.
- Backup: [`backup/office-wgopt13-20261118`](https://github.com/DannyNov/esp32-tailscale-subnet-router/tree/backup/office-wgopt13-20261118), at the exact baseline commit. A verified local Git bundle also preserves this history.
- Integration: `integration/office-v0.1.39-20261118`.
- Upstream target: [`d166884`](https://github.com/Csontikka/esp32-tailscale-subnet-router/commit/d16688430c938f0eca0cea5e68d50ccb735a81f5), tag v0.1.39, latest upstream main at inspection.
- MicroLink: `eb63b97073e529d57bc9c1deaeea25ac304034e5` -> `6f92800ba25d653fef14a745674a11b9955ac7d1`.

## Incorporated commits and behavior

All eight application commits after v0.1.35 are integrated, with both histories retained:

| Upstream application | Change |
| --- | --- |
| 697cd8c / 801c8d6 | v0.1.36: report actual measured DERP region, move relay on changed region; re-handshake a silent data peer after 15 seconds. |
| 88a4eaf / dc634eb | v0.1.37: bound partial control-frame stalls to 5 seconds; netif lifecycle on TCPIP thread; stop timeout leaves the instance in error. |
| e76b6fb / 42ec108 | v0.1.38: wait for TCPIP lifecycle completion (fixes v0.1.37 roam regression); withdraw router handle before teardown and guard SD snapshots; encrypt in the outgoing SPIRAM pbuf; authenticated diagnostic TX-path control and cost counters. |
| 93223da / d166884 | v0.1.39: send handshakes/cookie/keepalive from TCPIP thread using a private copy when posted; give up dead direct endpoints after 30 seconds of no authenticated direct traffic, independently of relay traffic. |

MicroLink commits: `21929f5`, `ee47277`, `a85e8c4`, `6f92800`. The final version includes the v0.1.38 correction; the intermediate v0.1.37 implementation is not used.

## Conflicts and office patches

Top-level textual conflicts were limited to CMake version and README. The fork documentation and generated-component build are retained, with the candidate version updated.

Pinned-source overlays intentionally fail closed. They were ported to the new source hashes and allocator/output APIs. The old wgopt1 implementation is superseded by upstream's in-place encrypted SPIRAM output, keeping upstream's thread-safe dispatch rather than installing duplicate callbacks. Office wgopt2 borrowed receive, RX128 queue, bounded scheduling, disabled synchronous consumer snapshots, DERP fragmented-header fix, allocation/timing probes, WiFi attribution and wgopt12 bounded FIFO retries remain. Retries still apply only to direct DATA and driver NO_MEM; queue/reference ownership, expiry, overflow and stop cleanup are executed by host tests. The new output callback retains handshake send-both over DERP.

An additional small guard rejects SD-log initialization when its new instance mutex cannot be allocated.

No SPARE experimental SDK6.1, flash16 layout, board identity restrictions or experimental routing stack were imported. The original platform and ESP-IDF dependency selection remain unchanged. Partitions (4 MiB image layout, two 1,966,080-byte OTA slots), sdkconfig defaults, WiFi buffers, NVS persistence, DHCP/Tuya ownership, reservations, Remembered Clients, Last seen and UI inputs remain unchanged. No credentials or device identity are embedded or exported. Existing on-device settings are not read wholesale or changed.

## Validation and limits

`python tools/run_office_regressions.py` runs 24 offline suites: extracted production DHCP/ARP/storage/failure cases, SNMP, CGNAT/routes/exit/DNS, factory validation, two UI suites, integration wiring, reproducible immutable overlays, borrowed buffers, scheduling/queue bounds, driver attribution, FIFO retries/refcounts/expiry/stop, DERP fragmented headers and BIO handling, TLS/replay/Noise/nonce/control checks, SSH host-key mocks, and v0.1.39 dispatch.

The new dispatch test compiles the exact generated helper and executes direct TCPIP send, private async copy, caller releasing/modifying its original buffer, allocation/post failures and detached-PCB cleanup. Source guards cover the 30-second direct-only timer, 5-second control timeout, blocking netif lifecycle and error state after stop timeout. Storage/configuration input files are compared byte-for-byte against the office baseline. These are bounded mocks and source checks, not proof of all concurrent runtime behavior.

The workflow `Build OFFICE v0.1.39 (no deployment)` builds the application and `factory-full.bin`, checks ESP32-S3/image descriptor/version, all segment checksums and appended SHA256, physical flash bounds, generated OTA slots and retained config, and emits commit/source hashes and provenance. The factory target merges the exact generated upload blocks, verifies offsets and blank NVS, and checks that its embedded application is byte-identical to the OTA file. Both images, their hashes and factory manifest are packaged together. The workflow contains no device flash, device upload, reboot, OTA, deployment or credential-bearing device requests.

Hardware runtime, WiFi reconnect/roam, direct/DERP tunnel soak, throughput and persistence across installation remain untested for this candidate. No speed increase or complete production-readiness claim is made. No firmware was installed on OFFICE or SPARE. OTA requires separate authorization; do not install an upstream release binary over this fork merely because the UI offers it.

## GitHub review and artifacts

- [Full upstream change range](https://github.com/Csontikka/esp32-tailscale-subnet-router/compare/v0.1.35...v0.1.39).
- [Office integration comparison](https://github.com/DannyNov/esp32-tailscale-subnet-router/compare/backup/office-wgopt13-20261118...integration/office-v0.1.39-20261118).
- [Build and test runs](https://github.com/DannyNov/esp32-tailscale-subnet-router/actions/workflows/build-wg-diagnostics.yml).

Only a passing, verified integration head is promoted to the office source branch. The old branch name remains for continuity; firmware reports the new version. Main, SPARE source snapshots, stable releases and existing device configuration are not changed by this integration.

## Distributed images

Each fork version includes its own OTA application and `factory-full.bin`, built from the same commit. The full image is for a fresh board / separately authorized recovery at offset 0x0 and contains blank NVS, not the existing OFFICE identity. It must not be used as the Web UI OTA upload. Existing installations retain identity and settings through the application OTA path only. Creating these files does not authorize installing either one.
