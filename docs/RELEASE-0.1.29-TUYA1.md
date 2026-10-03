# 0.1.29-tuya1 — Stable Last seen release for ESP32-S3 N16R8

Branch: `integration/0.1.29-tuya1`, based on integration base
`0836da5d0f243dcca5acd9101e5479588b54272c` (`0.1.29-tuya`).
Stable public release: `v0.1.29-tuya1`, based on upstream `v0.1.29`.
Hardware smoke-tested by the user after OTA without erase: Remembered Clients works, Last seen shows offline age (6 min ago) and online now for an active Tuya, and previous behavior is preserved. This confirms the reported smoke scenarios, not every acceptance case.

## Last seen semantics

Remembered Clients / Sticky Leases adds Last seen between Status and Type.
`GET /api/dhcp/remembered` returns `last_seen` as Unix **seconds**, numeric,
with `0` meaning unknown. Status retains its existing station-list logic.
A manual+sticky MAC still has a single row. Reserve, Name and IP behavior
are unchanged.

A permitted Wi-Fi association updates RAM immediately, even without DHCP.
A valid AP passive IPv4 observation updates RAM after provenance, current
association, subnet and ownership/conflict checks. Passive input retains its
existing bounded once-per-second handoff. DHCP is not an additional timestamp
source in this revision. ARP, lease caches, station-list refresh, persistent
ownership and API reads never update activity.

The system wall clock must be at least 2024-01-01 (the same plausibility
approach as existing firmware time consumers; boot starts at 1970 and SNTP
sets wall time). Events before valid time leave saved timestamps untouched;
they are not retroactively dated after sync. A later real event updates normally.
Backward clock corrections never reduce the newest known timestamp.

The browser displays unknown without a timestamp; with a timestamp it displays
online now, just now, N min ago, N h ago or N d ago. The title contains the exact
browser-local date and time (`Date.toLocaleString()`), independent of ESP TZ.
The existing horizontally scrollable table wrapper is preserved for mobile.

## Storage, throttle and compatibility

`dhcp_bind_v1` is unchanged, including its 2380-byte ABI, checksum, ownership
and legacy `dhcp_res` migration. No erase is required for OTA. This revision
adds an optional, separate versioned/checksummed `dhcp_seen_v1` blob, with up to
144 unique MACs (128 sticky plus 16 manual), 64-bit Unix seconds and checkpoint
wall times. Old installations with no blob load Last seen as unknown and
create it lazily on a checkpoint after real activity. Invalid optional blobs
are reported and ignored without disabling DHCP or altering ownership.

RAM holds up to 160 MACs (144 remembered plus 16 transient); only non-owners'
transient history can be evicted. Persisted history is for remembered/manual
owners. Sticky OFF and disconnect do not remove their Last seen history.
Association before explicit Reserve is retained in bounded RAM and can be
checkpointed once it becomes an owner. No destructive Forget function is added.

A timer checks every 60 seconds and hands work to TCP/IP. Events never write
this blob. Dirty MACs are included no more often than once per 20 minutes;
other MACs' checkpoints leave non-due entries at their previous saved value.
Failed writes are also throttled. Saved checkpoint wall time preserves the
write boundary across reboot; unset/backwards time cannot accelerate writes.
No forced write occurs on disconnect. After abrupt power loss the last saved
checkpoint is shown: first activity may take up to a minute to persist, and
later activity may lag by roughly 20 minutes plus timer scheduling. The RAM
value shown while running remains fresh. NVS I/O errors are visible through
the existing storage_status field and do not affect bindings or ACK decisions.

## Firmware and validation

`PROJECT_VER` is exactly `0.1.29-tuya1`.
- `firmware-0.1.29-tuya1-esp32-s3-ota.bin`: Web UI OTA, without erase.
- `firmware-0.1.29-tuya1-esp32-s3-factory.bin`: first installation at 0x0.
- `factory-manifest.json` and `SHA256SUMS.txt`: verified offsets/block hashes
  and final BIN hashes. Factory NVS is blank, application matches OTA.

CI runs production host DHCP/passive/NVS/Last seen tests, SNMP parser/hooks,
UI syntax/rendering and local-date checks, integration contracts and factory
regressions, then ESP32-S3 compilation and factory byte validation. Preserves
route-hook hardening, favicon, checked 60 URI registrations/capacity 72,
Sticky OFF discovery, Sticky ON ownership, Remembered Clients, Reserve,
conflict protection, Option 145, SNMP, boot_timing and factory/OTA builder.

Extended hardware checklist (not a claim that every case was tested): OTA without erase; check saved rows start unknown, observe a
sleeping manual client association and passive traffic, check relative/exact
local time, wait for checkpoint and reboot before NTP, verify the saved date
survives and pre-sync traffic cannot erase it. Repeat with Sticky OFF and ON,
Reserve and manual+sticky dedup; verify SNMP, UI/favicon, routing and boot timing
as described in the base integration's extended checklist.
