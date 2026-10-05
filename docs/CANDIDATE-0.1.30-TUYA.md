# 0.1.30-tuya — integration candidate, hardware pending

Branch: `integration/0.1.30-tuya`. Base fork main:
`4bdcf211121279240a22f35ecddb38d367ba2372`.
Upstream annotated tag v0.1.30: `e41e676a93b80c85fa6321c6707866ff72852312`;
target commit: `16b83a101a7f6c7c2f0a8832e3c735aeaa22e0a7`.
Microlink: `50d4f12498f6f9343b224aa61e565ce6f4b38e5c`.
Stable public release remains `v0.1.29-tuya1`.

## Code audit before build

- Upstream route hook asks WG peer host routes before CGNAT on-link/DNS/DHCP
  exceptions. Other CGNAT destinations retain tunnel routing. Ordinary uplink,
  accepted routes, AP subnet routing and selective NAPT retain upstream logic.
- Supervisor takes the connect/disconnect lifecycle mutex non-blockingly and
  releases it after route publication. Netif lookup, default route and route
  publication use TCP/IP callbacks. Pin completion queues behind the asynchronous
  library callback and holds the lease until completion; generation detects reuse.
- Microlink checks shutdown in region/probe/retry loops, limits select slices to
  250 ms, closes the socket on cancellation, and clears stop_incomplete after all
  tasks exit. Actual reconnect timing and heap reclamation require hardware.
- Route conflict: preserve fork BOOT_MARK and first-online diagnostic, moving
  its microlink read inside the lease. All remaining route/manager differences
  from upstream are existing boot timing instrumentation.
- CMake version conflict: PROJECT_VER is exactly `0.1.30-tuya`.
- README/changelog conflicts: retain fork history/stable installation guidance
  and upstream 0.1.30 notes; clearly identify candidate hardware status.
- Fork DHCP allocator, passive learning, bindings/reservations, remembered API,
  Last seen RAM/checkpoint/NVS/browser logic, SNMP, Option 145 diagnostics and
  SSH host-key tooling are unchanged from base main. No FORCERENEW sender added.
- Partition table, OTA writer and NVS schemas are unchanged. OTA writes the
  inactive application partition without erasing config, identity, dhcp_bind_v1
  or dhcp_seen_v1. Stored Last seen survives; fresh uncheckpointed RAM timestamps
  can lag after reboot under the existing throttle policy.

## Automated validation

Actions runs production DHCP/passive/storage/Last seen host regressions, SNMP,
UI, integration contracts, factory tests, SSH host-key regressions and the new
production CGNAT exception harness; Sensitive Data Check and C++/Python CodeQL
run on this integration branch. The route harness executes extracted production
code with netif/DNS/DHCP stubs. Lifecycle/cancellation checks are source contracts,
not dynamic concurrency, leak or full lwIP-stack simulation. Device functional
tests require an ESP and are pending.

## Images and hardware smoke test

- `firmware-0.1.30-tuya-esp32-s3-ota.bin`: existing board, Web UI OTA without erase.
- `firmware-0.1.30-tuya-esp32-s3-factory.bin`: clean board only; serial flash at
  `0x0` after full erase. Factory NVS is blank, not a configuration backup.
- `factory-manifest.json` and `SHA256SUMS.txt`: offsets, block and image hashes.

Before OTA record configuration, saved manual/sticky rows and persisted Last
seen. After OTA verify version, WiFi/Tailscale identity/config, the same rows and
timestamps, and browser-local date/age. Let a sleeping Tuya wake and send passive
traffic; verify RAM freshness, Sticky OFF transient discovery, Sticky ON ownership,
Reserve/dedup/conflicts, then checkpoint and reboot to verify persistence.

Repeatedly request reconnect immediately after first tunnel connection and flap
WiFi shortly after boot. Record free/minimum internal RAM and PSRAM before/after
each cycle; verify no cumulative instance-sized loss, crash or stale supervisor
access. Check tunnel return, accepted/default routes and exit node toggles.

Verify normal uplink DNS/control/internet, AP client access to advertised subnet
and tailnet, SNMP/UI/favicon/boot timing. With CGNAT uplink (or controlled lab
configuration), check on-link gateway, DNS and DHCP server access plus peer /32
priority when the uplink prefix covers peer IPs; compare route API and real
packet behavior. No local host test proves those device scenarios.

Do not merge main or create a release/tag until user hardware smoke acceptance.
