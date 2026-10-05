# 0.1.30-tuya — stable ESP32-S3 N16R8 release

Based on upstream v0.1.30 (`e41e676a93b80c85fa6321c6707866ff72852312`).

## Changes

- Fix microlink instance leakage on reconnect shortly after connect.
- Preserve uplink access to CGNAT on-link, DNS and DHCP destinations; WG peer host routes take priority.
- Synchronize route supervisor with reconnect teardown and the TCP/IP thread.
- Preserve Tuya sleepy-client DHCP/sticky ownership, passive MAC/IP learning,
  transient/persistent behavior, Remembered Clients, Reserve, Last seen RAM freshness,
  throttled NVS persistence and browser-local rendering, SNMP and SSH host-key security.
- FORCERENEW option 145 remains diagnostic only; no FORCERENEW packets are sent.

## Install

Existing device: `firmware-0.1.30-tuya-esp32-s3-ota.bin` via Web UI OTA **without erase**.
Configuration, identity, sticky ownership and persisted Last seen remain in NVS.
Fresh RAM timestamps may be newer than the last persisted checkpoint.
Clean board only: full erase, then `firmware-0.1.30-tuya-esp32-s3-factory.bin` at **0x0**.
Factory NVS is blank. Partition layout and ownership/Last seen schemas are unchanged.

## Validation and provenance

The user reported the candidate working on hardware and approved publication.
The screenshot confirms remembered/connected names and Last seen display.
Extended reconnect heap stability, teardown races and real CGNAT uplink cases
are not individually claimed hardware-tested.

Production DHCP/passive/NVS/Last seen, SNMP, UI, integration/factory, CGNAT host
harness and 8 SSH host-key tests passed. Sensitive Data Check, C/C++ and Python
CodeQL, firmware build and factory validation passed. Lifecycle/cancellation
host checks are static source contracts, not dynamic concurrency/heap tests.

Published binaries are the exact hardware-accepted candidate files, without rebuild:
source commit `ee9f1846a85247454ad59e2c9f320911322cb1e5`,
[successful build 37359932691](https://github.com/DannyNov/esp32-tailscale-subnet-router/actions/runs/37359932691).
Release finalization only changes documentation; production source/build configuration
matches this firmware source commit. Downloaded hashes, embedded version, factory blocks,
identical OTA application and blank factory NVS independently verified.

SHA256:

```text
ef63ffe6d178f22d206d753e734558b8eae9c04b2ed023e4e685d2c51b06bed2  firmware-0.1.30-tuya-esp32-s3-ota.bin
80ad6ede581035b920cc05f2bdc8951f65ef1eda5b5e0f464947b4d1dc3fabe3  firmware-0.1.30-tuya-esp32-s3-factory.bin
```

See [integration audit and extended device checklist](CANDIDATE-0.1.30-TUYA.md).
