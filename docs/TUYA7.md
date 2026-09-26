# 0.1.27-tuya7 — ESP32-S3 N16R8 test firmware

Branch: `fix/tuya-dhcp-renewal`. No upstream PR or main-branch changes.

## Install

Existing tuya6 device: upload **firmware-0.1.27-tuya7-esp32-s3-ota.bin**
through Web UI OTA. Do not erase flash. Existing settings, Tailscale identity,
manual reservations and sticky bindings retain the same NVS schema/key
(`dhcp_bind_v1`, version 1). Legacy `dhcp_res` migration remains supported.
Transient observations and FORCERENEW diagnostics are RAM-only.

Fresh N16R8 device: use **firmware-0.1.27-tuya7-esp32-s3-factory.bin**
with an ESP32-S3 serial flasher at **0x0** after a full-chip erase.
For esptool 4.x: `esptool.py --chip esp32s3 --port PORT erase_flash`, then
`esptool.py --chip esp32s3 --port PORT write_flash 0x0 firmware-0.1.27-tuya7-esp32-s3-factory.bin`.
Erase removes all existing settings/identity; this is a clean installation,
not the OTA upgrade path. Set Wi-Fi and Tailscale up again after a clean install.

The existing **4 MB firmware layout** is deliberately retained on the 16 MB
flash / 8 MB octal PSRAM hardware. This release does not resize partitions.
Factory inputs/offsets come from PlatformIO's actual serial-upload variables;
`factory-manifest.json` lists every block, hash and generated partition.
CI verifies bootloader, partition table, OTA metadata and application bytes,
checks all offsets against the partition table, and confirms NVS gaps contain
only erased `0xff` bytes. No device flash dump, credentials or user NVS is used.
Both firmware hashes are in `SHA256SUMS.txt`.

## Client discovery and ownership

* Sticky OFF: validated AP Ethernet-source MAC + IPv4-source pairs are kept in
  bounded RAM (16 entries). Connected Clients displays the temporary IP and
  Reserve; AP ARP is restored. Automatic observation never writes NVS.
* Sticky ON: a first valid pair is committed to sticky NVS before ARP when
  persistence succeeds. Duplicate packets never rewrite flash. If persistence
  fails, the pair remains explicitly temporary, with a storage error exposed.
* Validation requires the current AP netif/subnet, a unicast nonzero MAC,
  current association, no denylist entry, and no other persistent, transient,
  live DHCP or ARP owner. Network/broadcast/AP addresses are rejected.
* Transient entries expire when association reconciliation finds the client
  gone, denied or outside the current subnet. A failed station query does not
  discard ownership. Reconciliation runs on disconnect, incoming observations
  and before reservation saves. Reboot clears all transient entries.
* Persistent ownership wins over stale cache/DHCP/ARP candidates. Conflicts
  preserve the owner and are logged; Connected Clients exposes `ip_conflict`.
* OFF does not delete existing persistent entries. Enabling imports valid
  current observations. Explicit Reserve can persist a temporary pair even OFF.

Remembered Clients reads only persistent manual/sticky state. Association is
used solely to label online/offline. Rows are present immediately after reboot,
including sleeping clients; each MAC appears once, manual wins classification.
Auto rows use `unnamed` until given a friendly name. Reserve opens a form with
the actual MAC/IP fixed and an editable name; saving cannot silently change
an existing address. Both Connected and Remembered use the same owner state.

**Forget sticky is deferred.** Removing server state cannot prove that a
sleeping client has released its retained IP. Safe reuse needs a separate
quarantine/release policy. Removing a manual row does not remove its sticky owner.

## FORCERENEW

Option 145 is parsed diagnostically from actual DHCP DISCOVER/REQUEST packets:
`supported` means advertised RFC 6704 algorithm 1; `not advertised` means absent
in a complete options stream; `unknown` covers no live DHCP evidence, malformed
options, unsupported algorithms or unparsed option-overload fields. No state is
invented from passive IPv4 traffic and diagnostics do not survive reboot.
No FORCERENEW packet is sent. Advertisement alone is not proof of a usable
authenticated renewal flow: nonce/authentication negotiation is not implemented.
Sleeping Tuya behavior must be measured on hardware.

## Verification and hardware acceptance

Host tests exercise production binding/storage/parser/ARP/ACK code, OFF/ON,
flash failures, reboot/migration, offline remembered snapshots, manual dedup,
actual-IP Reserve, bounded observations and stale-cache conflicts. Additional
tests cover Option 145, production UI rendering and factory validation. CI
builds the ESP32-S3 image and verifies the actual merged factory bytes.

1. OTA tuya6 → tuya7 without erase; confirm both existing Tuya IPs are unchanged.
2. Immediately after reboot, open Remembered Clients while sensors sleep:
   MAC/IP should already be visible offline. Wake one: online, same IP.
3. With a suitable new temporary client and Sticky OFF, verify IP and Reserve
   appear while sticky count stays unchanged. Its transient entry disappears
   after disconnect/reboot unless explicitly reserved.
4. With a genuinely new Tuya and Sticky ON, send its first IPv4 traffic without
   manual reservation. Expect automatic remembered entry, offline during sleep,
   and retained entry after reboot. Existing manual entries cannot test fresh learning.
5. Reserve an auto row, set only the name, save: one manual row, same MAC/IP.
6. Capture serial output at 115200 from reboot until Web UI becomes reachable.
   Existing tuya6 `boot_timing` instrumentation is retained; correlate absolute
   milestone times with UI availability. This release makes no speculative
   startup restructuring and does not claim the long-start symptom resolved.

Hardware acceptance requires the user's device; host/CI success is not a
substitute for sleeping Tuya, OTA rollback or clean-flash hardware verification.
