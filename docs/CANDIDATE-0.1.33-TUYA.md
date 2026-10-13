# 0.1.33-tuya ESP32-S3 N16R8 candidate

Hardware acceptance pending. No stable release, merge, device configuration change or installation is authorized. Obtain separate user authorization before OTA or changing Power Save on the physical device.

## Provenance

- Fork main inspected: `54bbffcecbfdd694b0b46af7427c3f6575096a76` (stable 0.1.31-tuya).
- Starting candidate and draft PR #1 head: `bd0a9c0dd2e0109544a6aa2a441e92e2670df62a`, `integration/v0.1.32-tuya`. The user reports this version installed on the office ESP32; installed binary/source equality has not been independently verified.
- Upstream v0.1.32: `4030ee4b4b4f08d621be0dcb91be206607163e86`.
- Upstream feature: `84030ab578a205754ed43bc8c9d39aca83923aba`; v0.1.33: `ace09b31e322c2dc5e8823862b66802494360860`.
- microlink remains `2c796e3b14872b94fb2c54102affaacb1cc4a77b`.
- Integration branch: `integration/v0.1.33-tuya`. Merge retains upstream history. Version and README conflicts resolved retaining the fork and stable release references.
- Artifact provenance.json records exact candidate source SHA, parents, pinned tool/dependency versions and workflow run. SHA256SUMS.txt identifies the actual images. Do not substitute a later branch head for the recorded build SHA.

## Change and compatibility

System adds WiFi Power Save / modem sleep. Missing `wifi_ps` NVS key means ON, preserving previous IDF behaviour. Boolean OFF saves `wifi_ps=0` and applies `WIFI_PS_NONE` immediately; ON saves 1 and applies `WIFI_PS_MIN_MODEM`. Boot reads the same key after WiFi start. No reboot is requested by this setting. API rejects non-boolean values by ignoring them as upstream does; a missing field preserves the setting.

This is a latency option at increased current consumption when OFF. Neither a throughput increase nor the cause of office latency is proven. Upstream reference latency figures were removed from the UI; none are presented as our measurements. Upstream implementation does not check return codes of live WiFi/NVS changes, so UI success alone is insufficient: verify live behaviour and persistence after reboot on hardware.

Passive MAC/IP discovery, Sticky ON/OFF, Remembered Clients, Reserve, Last seen, NVS schemas/migrations, SNMP, SSH host-key checks, peer DNS lifecycle lease, OTA and partition configuration are preserved. Automated tests include byte comparisons of protected files against the exact prior candidate plus existing host/API/UI suites. Source contracts do not prove runtime radio behaviour or concurrency safety.

## OTA and rollback — only after separate authorization

1. Save settings/screenshots, reservations/remembered clients and identity. Obtain the exact working 0.1.32-tuya OTA binary and checksum from PR #1's build. Preserve it locally for rollback; a version label alone does not identify a binary.
2. Verify candidate OTA BIN SHA256 against SHA256SUMS.txt and inspect provenance. Use only `firmware-0.1.33-tuya-esp32-s3-ota.bin` in the existing Web UI updater. Do not erase flash/NVS or alter partitions.
3. After OTA reboot verify version/build, node identity, office route, settings, Sticky state, remembered clients, reservations and Last seen. Power Save should be ON if this NVS key was absent.
4. Roll back through the same updater using the saved 0.1.32-tuya OTA BIN, without erase. Recheck identity and saved state. Old firmware ignores the new wifi_ps key and uses its former default; returning to 0.1.33 reads the saved key again. Do not assume automatic rollback is enabled.
5. Factory BIN is for a clean board or separately authorized serial recovery. It contains bootloader/partitions/application and blank NVS gaps; flashing it over the existing device can destroy settings. It is not an OTA image or configuration backup. Follow factory-manifest.json offsets; never use a full-chip erase for an in-place update.

## Controlled Power Save comparison

User's historical observations on installed 0.1.32-tuya: direct Tailscale was observed once at 18 ms; ordinary ICMP to ESP32 was 30/30, min/mean/max 63/135/231 ms; office PC 30/30, 67/114/269 ms, idle. SMB instantaneous display fluctuated around 1.5–8 MB/s. These observations are not a controlled ON/OFF comparison. No causal conclusion follows. The Windows singbox TUN exclusion previously enabled direct office UDP; keep that known configuration identical throughout.

Use the same Windows client, ESP32, uplink AP/channel/RSSI, power supply, server, route and file set. Set console WARN identically; keep competing transfers absent. Record client/Tailscale/iperf versions, uptime, heap/PSRAM, RSSI/channel, temperature if available, reconnects, reset reasons and traffic counters. Verify ESP32 counters correspond to office transfers, excluding an alternate subnet router.

After authorized OTA, use A1=ON, B1=OFF, A2=ON, B2=OFF; run each three times. Save in separate directories, wait 60 seconds after Save, and confirm displayed setting. Verify direct path before and after every run (and during long transfers); invalidate a run with DERP/path change, reconnect or competing traffic.

On Windows define `$EspIp` as the ESP32 tailnet address and `$OfficeIp` as the office LAN PC address from the user context. For every state/run:

```powershell
tailscale ping --c 10 $EspIp
tailscale ping --c 10 $OfficeIp
ping $EspIp -n 100 | Tee-Object ping-esp-idle.txt
ping $OfficeIp -n 100 | Tee-Object ping-pc-idle.txt
```

Tailscale ping tests the tunnel path; ordinary ping tests different processing paths. Record loss and min/mean/max (median/p95 when raw samples are parsed). Do not compare one direct discovery ping with an ICMP average as identical probes.

If iperf3 is available on the office PC, start `iperf3 -s` there after authorization for that host; ESP32 does not need an iperf server. From Windows, three repetitions each, with distinct output names:

```powershell
iperf3 -c $OfficeIp -t 60 -O 5 -P 1 --json > upload-p1.json
iperf3 -c $OfficeIp -t 60 -O 5 -P 1 -R --json > download-p1.json
iperf3 -c $OfficeIp -t 60 -O 5 -P 4 --json > upload-p4.json
iperf3 -c $OfficeIp -t 60 -O 5 -P 4 -R --json > download-p4.json
```

Run ordinary ping to both endpoints in separate windows during each transfer. Report sustained receiver throughput, retransmits and latency under load by direction and stream count. Compare medians/ranges; keep single-stream results prominent for SMB. Mark unavailable iperf tests untested.

SMB: same share, large test file and folder of small test files, both directions, three runs per state, dedicated test directories without overwriting production data. Record total bytes/time, failures, file SHA256, and cache state (warm and cold separately). Use `robocopy SOURCE DEST /E /COPY:DAT /R:0 /W:0 /NP /LOG:copy.log`; no /MIR. Exit codes below 8 can indicate success. Instantaneous Explorer speed is not sustained throughput. Finish with 15 minutes of transfer per state and watch path, heap, reconnect/reset logs. If results vary without reproducibility, report inconclusive.

## Hardware acceptance matrix

All rows pending until recorded on a real ESP32-S3. Record result, build SHA, logs and deviations.

| Scenario | Acceptance |
|---|---|
| OTA 0.1.32 → 0.1.33 without erase | Same identity, settings, office route, sticky/remembered/reserve/Last seen; layout unchanged |
| Missing wifi_ps key | ON after boot and System load |
| ON → OFF → ON | Live operation without restart; correct API/UI state, no disconnect/reset; persistence after authorized reboot |
| Invalid/omitted wifi_power_save | No change; existing System fields still save |
| Passive sleeping Tuya | Learns valid MAC/IP without new DHCP; ownership conflicts rejected |
| Sticky OFF/ON | OFF temporary discoveries; ON persistence and restore |
| Remembered/Reserve/Last seen | Offline rows, friendly names, dedup/conflict policy and timestamps preserved |
| NVS legacy migration | Test on dedicated board/backup only; no destructive production migration test |
| SNMP and SSH | Existing access/auth/host-key rejection policies preserved |
| Peer DNS/exit routing | Lifecycle lease during concurrent reconnect, known-peer access and exit-mode exclusion preserved |
| Direct routing and sustained load | Both office endpoints, both directions, heap/PSRAM and reconnect/reset logs, 15-minute runs |
| Rollback OTA to exact 0.1.32 | Saved identity/settings retained; old PS behaviour returns |

Hardware acceptance is required before merge or stable publication. This candidate makes no claim that office latency or SMB throughput has improved.
