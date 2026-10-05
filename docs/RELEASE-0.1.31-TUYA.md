# 0.1.31-tuya — stable ESP32-S3 N16R8 release

Based on upstream v0.1.31 (`b053e0bdf3f7d3b6c274bb28d5c93d7b9ceecd92`).

## Changes

- Add optional IPv4 exit-node offering with automatic NAT and isolated peer DNS service (OFF by default). Offering an exit node cannot be combined with using another exit node.
- Queue received tunnel packets in PSRAM to reduce internal-RAM pressure during downloads.
- Fork hardening: protect peer DNS microlink reads with the lifecycle lease during reconnect teardown.
- Preserve Tuya sleepy-client DHCP/sticky ownership, passive MAC/IP learning, transient/persistent behavior, Remembered Clients, Reserve, persisted Last seen and browser-local rendering, SNMP and SSH host-key security.
- FORCERENEW option 145 remains diagnostic only; no packets are sent.

## Installation

Existing ESP: `firmware-0.1.31-tuya-esp32-s3-ota.bin` through Web UI OTA **without erase**.
Configuration, identity, sticky ownership and persisted Last seen remain in NVS.
Fresh RAM activity can be newer than the last persisted checkpoint.
Clean board only: full erase, then `firmware-0.1.31-tuya-esp32-s3-factory.bin` at **0x0**.
Factory NVS is blank. Partition layout and ownership/Last seen schemas are unchanged.

## Validation and provenance

The user confirmed our fork-added functions working on hardware and approved publication.
The new exit-node offering/DNS mode, reconnect concurrency and memory behavior under load
are not claimed hardware-tested in this fork. The mode remains OFF by default.

All host DHCP/passive/NVS/Last seen, SNMP, UI, integration/factory, CGNAT,
exit-mode/routes/DNS parser and 8 SSH security tests passed. Firmware/factory build,
Sensitive Data Check and C++/Python CodeQL passed on the exact firmware source HEAD.
Lifecycle/access/PSRAM source contracts do not substitute for hardware tests.

Published binaries are the exact hardware-accepted candidate files, without rebuild:
source commit `9e54fd9d84741ceaa7214ec39c7e540224be2834`,
[successful build 37371922406](https://github.com/DannyNov/esp32-tailscale-subnet-router/actions/runs/37371922406).
Release finalization changes documentation only. Downloaded hashes, version,
factory blocks, identical OTA application and blank factory NVS independently verified.

SHA256:

```text
e7e4e26e62c3e24b823b4d67b5990f02addde6bd945bd9af5fc2a771e4bb1c3c  firmware-0.1.31-tuya-esp32-s3-ota.bin
af063d7d1f449be08b1d6ba9bf572ea347daadbc9b3a68da9cfcf2f0213547bb  firmware-0.1.31-tuya-esp32-s3-factory.bin
```

See the integration audit and extended hardware checklist in docs/CANDIDATE-0.1.31-TUYA.md.
