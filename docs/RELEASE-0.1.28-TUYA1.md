# 0.1.28-tuya1 — ESP32-S3 N16R8

Integration branch: `integration/0.1.28-tuya1`. Merges upstream `v0.1.28`
into tuya7 `fe9d502576e37271b9f890161b056c5f7353bfcb`.

All tuya7 DHCP ownership, transient passive discovery with Sticky OFF,
persistent Sticky ON, remembered clients, Reserve, conflict protection,
Option 145 diagnostics and boot timing are retained. FORCERENEW is not sent.
Upstream SNMPv1/v2c, its UI/API, netif lifecycle fixes, shared temperature
sensor and radio validation are retained; SNMP is off by default.

## Flashing

- `firmware-0.1.28-tuya1-esp32-s3-ota.bin`: update a configured device through
  its web UI. Do not erase flash; DHCP/sticky settings remain in NVS.
- `firmware-0.1.28-tuya1-esp32-s3-factory.bin`: first installation, flash at
  `0x0`. Erase flash first on a reused board. Factory contains the generated
  bootloader, partition table, OTA metadata and the same application as OTA.
  The NVS region is blank. It uses the PlatformIO upload plan and 4 MB layout.
- `factory-manifest.json` records input offsets and hashes.
- `SHA256SUMS.txt` records the hashes of both firmware files.

Upstream's `factory-full.bin` release convention is documented upstream;
this Actions package retains tuya7's validated factory filename and builder.
There is no upstream factory build/workflow change in the v0.1.28 Git diff.

## Storage compatibility

DHCP/sticky NVS schema and its existing migration are unchanged. Upstream
adds the separate `snmp_cfg` blob and retains migration from legacy SNMP
keys. No migration or erasure of tuya7 DHCP data is introduced.

## Integration audit

Text conflicts: `CMakeLists.txt` (set `0.1.28-tuya1`) and `CHANGELOG.md`
(retain both fork fixes and the complete upstream release entry).
`main/CMakeLists.txt`, `main/index.html`, `main/web_ui.c`, `main/main.c` and
`sdkconfig.defaults` merged automatically and were reviewed. `telemetry.c`
retains upstream's updated comment. The HTTP handler capacity accommodates
both SNMP endpoints and Remembered Clients. ACL/passive hooks install before
SNMP; the Web UI uses SNMP's sole temperature sensor owner.

CI runs host DHCP/NVS/passive regressions, production SNMP parser and netif
hook host fixtures, UI checks, integration contracts, factory validation,
and a clean ESP32-S3 build followed by factory merge and byte verification.
Hardware SNMP walks, tunnel reconnects, temperature readings and sleeping
Tuya behavior still require a device check after OTA.
