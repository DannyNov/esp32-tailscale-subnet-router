# v0.1.32-tuya integration candidate

Hardware acceptance pending. No release or device installation is authorized by this candidate build.

## Provenance
- Stable fork/main: 54bbffcecbfdd694b0b46af7427c3f6575096a76 (v0.1.31-tuya).
- Upstream v0.1.31: b053e0bdf3f7d3b6c274bb28d5c93d7b9ceecd92.
- Upstream v0.1.32: 4030ee4b4b4f08d621be0dcb91be206607163e86, released 2026-10-12.
- microlink: 17a8c9c0b9f6d7871fd1430f800383c87b99caa2 -> 2c796e3b14872b94fb2c54102affaacb1cc4a77b.

The upstream microlink delta is limited to ml_coord.c, ml_derp.c, ml_wg_mgr.c: stop wakes relay wait, null TX queue guarded during OOM teardown, per-packet INFO becomes DEBUG, periodic WARN snapshots become INFO. Keep console WARN during measurements; INFO still synchronously outputs snapshots. OOM/stop contracts are source checks, not runtime fault injection.

## Compatibility and risks
Production Tuya DHCP/passive discovery, ownership, Sticky OFF/ON, remembered clients, reserve, Last seen, NVS migration, SNMP, SSH and peer DNS lifecycle lease remain unchanged. Regression suites cover production host functions and UI contracts. Hardware acceptance remains required. partitions.csv, sdkconfig and platformio.ini retain the stable layout. OTA updates only the application; never erase NVS. Factory image is for a fresh board/recovery and may overwrite settings if flashed across NVS: do not use it as an in-place update.
Manual newline-separated 0.0.0.0/0 now activates exit DNS/NAT, with disabled Tailscale or selected remote exit node still excluding local exit-server mode.

## First prove the office path
1. Record client OS, Tailscale version, office server IP/subnet, ESP32 node identity, advertised/approved office route and other subnet routers.
2. Inspect `tailscale status --json` and `tailscale debug prefs`, client routing (`route print` on Windows, `ip route get OFFICE_IP` on Linux) and approved routes in the admin console. An OS route to Tailscale alone does not identify the chosen subnet router.
3. Run `tailscale ping ESP32_TAILNET_IP` and record direct/DERP. Correlate a controlled office transfer with ESP32 traffic counters/logs. If practical, during an agreed maintenance window temporarily disable only the ESP32 office route and repeat reachability, then restore it. Redundant routers may take over, so also inspect the selected router and counters.
4. If another subnet router carries office traffic, ESP32 update cannot improve that transfer: its WireGuard task is outside the data path. Do not infer office routing merely from the ESP32 being online or a ping to it.

## Hardware acceptance and benchmarks
Before OTA, save configuration/screenshots, MAC/IP reservations, identities and stable OTA BIN/checksum. Establish baseline on v0.1.31-tuya with the same endpoints, WiFi/channel/RSSI, log WARN, no competing transfers. Record direct/DERP, latency, uptime, heap, reconnects, resets and errors.

On an office LAN host reachable through the verified ESP32 subnet route, start `iperf3 -s`. From the remote client:
```
iperf3 -c OFFICE_IP -t 60 -O 5 -P 1 --json > old-direct-upload.json
iperf3 -c OFFICE_IP -t 60 -O 5 -P 1 -R --json > old-direct-download.json
iperf3 -c OFFICE_IP -t 60 -O 5 -P 4 --json > old-direct-upload-p4.json
iperf3 -c OFFICE_IP -t 60 -O 5 -P 4 -R --json > old-direct-download-p4.json
```
Repeat each three times. Repeat after user-approved candidate OTA, using new filenames. Report medians, ranges and retransmits for both directions; keep single-stream results prominent for SMB. The ESP32 need not run iperf3 itself.

For DERP repeat the same matrix in a controlled environment that blocks direct UDP between peers while retaining relay HTTPS, verify `tailscale ping` reports relay and monitor throughout, then restore firewall/network. Do not assume an initial relay ping means the whole transfer stayed relayed. Avoid changing the office firewall remotely without a recovery path. Mark unavailable paths untested.

SMB: use the same server/share and a test directory. Copy a representative large document and a folder of many small documents in both directions, three times per version/path. Use distinct test filenames and record bytes/time, application open/save latency, errors and SHA256 of originals/copies; avoid overwriting production documents. On Windows `robocopy SOURCE DEST /E /COPY:DAT /R:0 /W:0 /NP /LOG:copy.log` can collect timings (exit codes below 8 can mean success); do not use /MIR. Separate warm cache from cold runs. Repeat a 15-minute sustained transfer to expose periodic drops/rekey issues.

After OTA: verify saved settings and Tailscale identity, passive sleeping Tuya discovery without DHCP, Sticky OFF no new automatic persistence, Sticky ON reboot restore, remembered offline devices, reserve conflicts, Last seen/reboot and legacy migration on a dedicated test device. Verify SNMP reads/access policy, SSH auth/host keys, peer DNS lease under concurrent restart, manual default-route DNS/NAT, exit-node exclusion, direct/DERP reconnect, OTA reboot and low heap/stop behavior. Capture reset reason and boot timing.

## Rollback
Use stable v0.1.31-tuya OTA through the existing updater after user authorization, preserving NVS and partition table; verify identity and reservations after reboot. If OTA is unavailable, use serial recovery with backed-up configuration and known offsets; a full-chip erase deletes settings. Never assume automatic rollback is enabled without checking build configuration and device behavior.

## Performance claim boundary
Upstream measured roughly 5-6 Mbit/s on an Exit Node direct-path reference bench. That is not an office LAN/SMB guarantee. Actual improvement requires ESP32 in the office data path and depends on WiFi, relay, RTT, SMB behavior and CPU load. Automated CI cannot measure hardware throughput.
