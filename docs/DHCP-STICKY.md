# DHCP ownership in 0.1.27-tuya5

## Architecture and the tuya1-tuya4 failure

This branch replaces ESP-IDF's DHCP implementation with a project component via
linker wrapping. The old reservation callback only overrode the candidate IP for
its own MAC, after the dynamic-pool scan. It never excluded offline reservations
from that scan; existing RAM leases bypassed the reservation callback altogether.
The linked-list leases disappeared on DHCP stop/reboot. Main also loaded the table
after Wi-Fi start. Static ARP used ip4_route(), and the UI only consulted live
leases/ARP. Neither a reservation nor ARP can change an IP already held by a client.

## Ownership and persistence

- Manual reservations (16) and sticky bindings (128) share one versioned,
  checksummed `tsr/dhcp_bind_v1` NVS record but have separate arrays.
- Existing `tsr/dhcp_res` records migrate when the new key is absent. The legacy key
  is retained; old firmware does not understand new bindings. Downgrading may
  therefore reintroduce address conflicts and is not a safe persistence rollback.
- All manual/sticky mutations run on the TCP/IP task, serialized with allocation.
  Other-task snapshots are copied under a short mutex. No packet lookup reads NVS.
- A new sticky address is committed before ACK is sent. This intentionally protects
  even an ACK lost on the air: power loss cannot leave an acknowledged but forgotten
  address. Retry/renewals of a known binding do not write flash.
- A failed write/commit leaves published RAM unchanged and suppresses ACK. The
  version/checksum/size and duplicate-owner validation reject damaged records;
  allocation and edits fail closed rather than forgetting ownership. Standard NVS
  atomic recovery is used; a corrupt application record is not silently overwritten.
- Auto-reserve is opt-in, default off, to preserve ordinary DHCP for existing APs.
  Enable it before pairing new IoT clients. Existing ACKed leases are imported when
  enabling it. Turning it off stops learning, but never frees previous ownership.
- Capacity is bounded. Neither disconnected clients nor expired leases are evicted
  from persistent storage. Full storage refuses a new sticky ACK and logs the
  reason. It is not intended for an AP with unlimited rotating/randomized MACs.

## Allocation, ARP and reservations

Every candidate, including requested renewals and existing RAM leases, is checked
against both persistent ownership and live leases. Dynamic allocation skips all
other owners, even when they are offline. Only valid AP-subnet host addresses are
accepted; the AP/network/broadcast addresses are rejected. Reservations may lie
outside the dynamic range, but not outside the AP subnet.

Manual Reserve adopts an existing sticky or ACKed address of that MAC. Entering a
new IP does not change that address; the UI explains this and reloads the effective
reservation after save. Duplicate MAC/IP rows, addresses held by another client,
and invalid rows reject the entire save. There is no hidden pending reassignment.
Deleting a manual row does not erase an already learned sticky binding.

At association the TCP/IP callback restores ARP directly on WIFI_AP_DEF's lwIP
netif. A small CMake-built extension shares the SDK etharp translation unit and
calls lwIP's own update primitive with an explicit netif. The SDK installation is
not patched. Removal is scoped to AP; DHCP temporary ARP cleanup restores known
bindings. The ARP table has 64 slots (16 configured AP stations plus headroom).
Connected Clients can show a persistent address without an active DHCP lease.

Tailscale, NAPT, DNS relay and firewall code is unchanged. New NVS commits happen
synchronously on TCP/IP only on first ownership/settings changes, so those rare
operations can briefly delay packet processing. A reboot/reconnect is not a DHCP
request and is never advertised as a way to force a sleeping client to change IP.

## Migration and hardware acceptance

The firmware cannot reconstruct an address that old firmware never recorded and
that a silent client does not transmit. Keep the already verified reservation
`a0:92:08:51:dc:d6 -> 10.71.0.4` during this OTA. No device-specific MAC is hardcoded.
Do not restore the known-wrong `.3` reservation. New devices learned by tuya5 do
not require scanning.

1. OTA flash `firmware-0.1.27-tuya5-esp32-s3-ota.bin`, without erasing NVS. Confirm
   version `0.1.27-tuya5`. Enable **Auto-reserve / Sticky leases** and Save.
2. Wake the current sensor, reboot only ESP, then wake/reassociate the sensor
   without resetting its Wi-Fi settings. Connected Clients must show `.4` even
   when Active DHCP Leases is empty. Test `.4:6668` while it is awake. Logs must
   show ARP install on association with result 0.
3. Pair a second sensor. Its first successful DHCP exchange must allocate a
   different IP automatically. Note that IP in Connected Clients; verify storage
   status is ESP_OK. Reboot ESP, wake the second sensor, check the same IP and TCP
   accessibility without adding a reservation or scanning.
4. Reserve the second sensor but type another address: after Save the table must
   retain its actual sticky IP. Try to assign its IP to a third MAC: Save must fail
   with no partial changes. An offline reserved IP must never appear on another
   DHCP client.
5. Check a normal phone DHCP renewal, outbound Internet/DNS, and Tailscale-to-AP
   access. These require real hardware; host tests and a successful build do not
   establish radio/sleep behavior or live routing performance.

## Automated verification

`python tools/run_host_tests.py` compiles production policy and storage code with
NVS fault injection. It covers mode off/on, first binding, no writes on renew,
reboot without DHCP, manual adoption, conflicts, legacy migration, write/commit
failure, corrupt/truncated records and capacity without eviction. The allocator
suite compiles the exact parser/allocation functions extracted from dhcpserver.c,
with host platform adapters; it tests fresh clients, renewals, pool exclusions,
existing-lease conflicts, addresses outside the pool, invalid subnet addresses,
exhaustion and DHCPDECLINE. The ARP suite tests the actual explicit-netif extension.
Firmware CI runs the host suites before the ESP32-S3 build and publishes the OTA
binary and SHA256SUMS.txt. Tests do not emulate ESP flash hardware or Wi-Fi.
