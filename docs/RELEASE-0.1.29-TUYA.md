# 0.1.29-tuya — ESP32-S3 N16R8

Integration branch: `integration/0.1.29-tuya`. Merges upstream `v0.1.29`
into fork main `f15f95734bed5579323ce60cfec53162560820a6` (0.1.28-tuya1).
This is the base Tuya version on upstream 0.1.29; later fork revisions are
`0.1.29-tuya1`, `0.1.29-tuya2`, etc. This historical integration base is superseded
by stable public `v0.1.29-tuya1`; see [release notes](RELEASE-0.1.29-TUYA1.md).
The user hardware smoke-tested that revision after OTA and confirmed Last seen working.

## Changes and preserved behavior

All upstream v0.1.29 changes are included: the WireGuard netif is identified
by name `wg`, CGNAT uplinks remain eligible for LAN bypass, both routing and
route diagnostics skip interfaces that are down or link-down, all URI handler
registrations are checked, and the inline/unauthenticated favicon avoids 404s.
The table has capacity 72 for 60 registrations, including Remembered Clients.

Transient passive discovery with Sticky OFF, persistent Sticky ON, Remembered
Clients/offline visibility, Reserve, conflict protection and Option 145
diagnostics are retained. FORCERENEW packets are not sent. Reserved-client
renewal recovery, live DHCP DNS updates, ARP lookup/static association entries,
SNMPv1/v2c (off by default), its shared temperature sensor and boot timing
remain intact. No unrelated refactor is included.

## Flashing

- `firmware-0.1.29-tuya-esp32-s3-ota.bin`: update through Web UI without
  erasing flash. Existing DHCP/sticky, SNMP and identity settings remain in NVS.
- `firmware-0.1.29-tuya-esp32-s3-factory.bin`: first installation on N16R8,
  flash at `0x0`. Erase a reused board first; this deletes settings/identity.
  Factory contains the bootloader, partition table, OTA metadata and the same
  application as OTA. The NVS region is blank; the existing 4 MB layout remains.
- `factory-manifest.json` records verified block offsets and hashes.
- `SHA256SUMS.txt` records both BIN checksums.

## Storage compatibility

No NVS schema or migration changes are introduced relative to 0.1.28-tuya1.
DHCP/sticky ownership, remembered clients and existing legacy migration remain
unchanged. SNMP retains its separate `snmp_cfg` blob and legacy-key migration.
OTA requires no NVS erasure or new migration.

## Integration audit and validation

Text conflicts and resolutions:
- `CMakeLists.txt`: use exactly `PROJECT_VER=0.1.29-tuya`.
- `main/web_ui.c`: retain Remembered Clients and BOOT_MARK instrumentation;
  use upstream `reg_uri()` for every handler and set capacity 72.
- `README.md`: retain fork functionality/install guidance, document this historical integration and preserve upstream 0.1.29 status and other upstream edits.
- `CHANGELOG.md`: retain the complete fork and upstream entries; add this integration base.

`main/lwip_route_hook.c` and `main/index.html` merge automatically. Their
upstream changes are retained alongside the fork's existing code.

CI runs host DHCP/NVS/passive regressions, production SNMP parser and netif
hook fixtures, UI checks, integration contracts, factory tests, a clean ESP32-S3
build and factory generation/byte verification. The Actions run is the source
of validation results and exact firmware hashes.

Extended hardware checklist (not all cases claimed tested): OTA without erasure; Sticky OFF/ON and
sleeping clients; offline Remembered Clients/Reserve/conflicts; SNMP on/off;
favicon before login and no handler-registration errors; AP/uplink/tailnet/
internet traffic with exit node off and with LAN bypass on; down uplink and,
where available, CGNAT uplink; boot timing and tunnel reconnects.
