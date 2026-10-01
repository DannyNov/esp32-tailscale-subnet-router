# 0.1.27-tuya7 — Tuya sleeping-client support

ESP32-S3 N16R8 firmware with improved address discovery and persistence for low-power AP clients that reconnect without DHCP.

## Changes

- Learn validated MAC/IPv4 pairs from AP client traffic, including silent reconnects.
- Sticky OFF: temporary RAM discovery, Connected Clients IP display and Reserve, without automatic NVS writes.
- Sticky ON: persistent address ownership, no flash rewrite for duplicate packets, recovery after reboot.
- Remembered Clients displays saved manual/sticky devices even while offline. Manual entries take precedence and duplicate MACs are combined.
- Reserve preserves the current MAC/IP and allows a friendly name. Conflicting ownership is rejected.
- Option 145 capability diagnostics are based on live DHCP packets. No FORCERENEW packets are sent.
- Added a verified factory image alongside the OTA firmware.

## Downloads and installation

- Existing device: `firmware-0.1.27-tuya7-esp32-s3-ota.bin`, uploaded through Web UI OTA **without erasing NVS**.
- Clean ESP32-S3 N16R8 installation: `firmware-0.1.27-tuya7-esp32-s3-factory.bin`, serial flash at **0x0** after full-chip erase. Erasing removes existing settings and identity.
- `SHA256SUMS.txt`, `factory-manifest.json` and `README.md` provide checksums, factory block metadata and detailed installation instructions.

The existing 4 MB partition layout on N16R8 is unchanged. NVS schema remains version 1 (`dhcp_bind_v1`); legacy migration is retained.

## Validation and limitations

Host/regression tests, UI tests, ESP32-S3 compilation, factory generation and byte-level factory verification passed in [Actions run 36223192734](https://github.com/DannyNov/esp32-tailscale-subnet-router/actions/runs/36223192734).
The downloaded factory application's bytes match the OTA image; the NVS region contains erased bytes.
On 1 October 2026, the operator reported that version 7 appeared to work on the existing device. This is a field smoke check, not confirmation of every acceptance case or a clean factory flash.

The intermittent long-start symptom remains under investigation; boot timing logs are retained. Safe Forget sticky is deferred because sleeping clients may retain their IP after server-side removal.

Source commit: `fe9d502576e37271b9f890161b056c5f7353bfcb`.

```text
9cec558001593be03601b86a37ed75993703f75535cc158719ca610453efb670  firmware-0.1.27-tuya7-esp32-s3-ota.bin
f1ca636eac15618c2e740f962962fd5b40a4c0794f1fdde7d0beb80832105f44  firmware-0.1.27-tuya7-esp32-s3-factory.bin
```
