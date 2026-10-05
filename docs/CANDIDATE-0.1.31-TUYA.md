# 0.1.31-tuya — ESP32-S3 N16R8 integration candidate

Hardware smoke test pending. Stable release remains v0.1.30-tuya.
Base main: f35a8854efd9118d1a2dce3ced1f8ffd20d9f827.
Upstream v0.1.31: b053e0bdf3f7d3b6c274bb28d5c93d7b9ceecd92.
Microlink: 17a8c9c0b9f6d7871fd1430f800383c87b99caa2.

## Audit

Merge preserves upstream history. Conflicts: PROJECT_VER becomes 0.1.31-tuya;
README retains fork history, stable installation and upstream 0.1.31 status.
All DHCP/passive/bindings/reservations/Last seen/SNMP/SSH host-key production
files are unchanged from main. UI/API changes add only exit-node controls and
isolated DNS startup; existing remembered/Last seen rendering is preserved.
Upstream adds exit-node default routes alongside AP subnet routes, automatic
WG-to-uplink NAT, port 41180 peer DNS and 31 socket capacity. Mode is OFF by
default and incompatible with using another exit node. IPv4 data plane only.
Microlink queues received packets in PSRAM and advertises the peer API service.
Fork fix: peer DNS authorization now holds the lifecycle lease while reading
microlink, preventing teardown during these reads. It releases before forwarding.
DNS only accepts the router's tailnet destination and a known peer source;
server starts only in exit mode. GET base64url and POST DNS payloads are bounded.
Admin UI remains on its separate server. DNS UDP falls back to TCP on truncation.

## Tests and images

CI runs existing DHCP/passive/NVS/Last seen/SNMP/UI/factory/integration/SSH
regressions, production CGNAT harness and new exit-mode/route dedup/DNS parser
host regressions, Sensitive Data Check, C++/Python CodeQL and firmware build.
Lifecycle/access/PSRAM checks are source contracts; hardware concurrency and
heap stability are not proven by host tests.

- firmware-0.1.31-tuya-esp32-s3-ota.bin: Web UI OTA without erase.
- firmware-0.1.31-tuya-esp32-s3-factory.bin: clean board only, erase then flash 0x0.
- SHA256SUMS.txt and factory-manifest.json: final and block hashes/offsets.

Partition layout and OTA path are unchanged. OTA retains configuration,
identity, dhcp_bind_v1 and persisted dhcp_seen_v1; fresh RAM timestamps may be
newer than the last checkpoint. The new ts_adv_exit setting defaults to OFF.
Factory NVS is blank and is not a settings backup.

## Hardware smoke checklist

OTA without erase: version, settings/identity, remembered/sticky rows and saved
Last seen; sleeping Tuya passive learning, Sticky OFF/ON, Reserve/dedup and reboot.
With offer mode OFF check normal AP subnet/tailnet, DNS, SNMP/UI and remote exit
node usage. Under download load compare internal RAM/PSRAM and verify no crashes.
With offer mode ON approve in Tailscale admin console and select on an official
client: verify egress IP, DNS/site loads, UI responsiveness during parallel DNS,
and rejection of uplink/AP DNS callers. Verify the port is closed after OFF plus
restart, incompatible exit selection is refused, and repeated reconnect during
DNS use cannot crash. Recheck CGNAT exceptions, peer /32 priority and AP routes.
Do not merge main or publish release/tag until user hardware acceptance.
