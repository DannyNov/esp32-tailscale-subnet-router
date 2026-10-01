# 0.1.27-tuya6: passive AP learning and boot timing

## Passive learning

The tuya5 ownership record, DHCP exclusions, explicit-AP ARP helper and Connected
Clients fallback are reused. No new NVS schema or migration is needed. Manual
lookups take priority; a valid stored manual/sticky pair always has the same IP.

`ap_input_hook`, installed only on `WIFI_AP_DEF`, observes allowed Ethernet IPv4
frames before MSS/PMTU processing. The source is Ethernet source MAC plus IPv4
source address. The parser handles chained pbufs, IPv4 options and alignment,
checks lengths/version/header checksum and rejects zero/multicast MACs. It does
not learn from a destination, ARP payload, STA interface or DHCP option.

The hook copies only the header into a fixed 16-slot handoff. A pending MAC is
coalesced; completed attempts are rate-limited to one per second per MAC. Queue
failure/full pool drops an observation without blocking packet forwarding; a
later packet retries. No pbuf is retained, no heap allocation or NVS access occurs
in the input hook. This matters because netif input can run on the Wi-Fi task.

The TCP/IP callback rechecks AP identity, the current Wi-Fi association list,
denylist, current DHCP/AP subnet, network/broadcast/AP addresses, manual/sticky
ownership, live DHCP offers/leases and an existing AP ARP owner. It never replaces
a known address with a different observed address. Allocation, edits and learning
are serialized on TCP/IP. New learning requires Auto-reserve ON and commits the
existing atomic NVS blob before publishing the RAM binding and installing static
ARP on the AP netif. A failed commit leaves the binding unpublished. Existing
pairs can restore ARP with no flash writes, including when Auto-reserve is OFF.
OFF never creates a new persistent observation.

The first commit logs `ap_passive: learned ... (NVS committed, AP ARP result=0)`.
An ARP failure does not lose ownership; later traffic/association retries ARP.
Connected Clients already falls back to persistent bindings and offers Reserve
when an IP exists and no manual reservation exists, even with no active lease.

This is passive first-claim learning, not cryptographic client identity. It uses
the associated source MAC as requested; it cannot discover a device that sends
no IPv4 traffic at all, or identify an offline unknown owner never recorded by
DHCP, NVS or ARP. Learned addresses are never evicted automatically.

## Read-only boot trace: findings

No definite cause of the reported long UI outage was established from tuya5.
Service ordering and rollback confirmation are deliberately preserved.

1. `app_main`: netif/event loop, NVS initialization/recovery, log capture, reset
   history NVS update, DNS task creation, core-dump inspection/erase and NVS updates.
2. Tailscale settings are loaded without connecting. MTU, telemetry and route
   supervisor tasks are started; ACL loads; SD is mounted synchronously (including
   driver/filesystem I/O even when recording is disabled); remote console starts
   its own task if enabled. All occur before Wi-Fi starts.
3. Bindings load/validation and legacy conversion are synchronous reads, without
   a commit on load. Conversion is persisted with the next actual mutation.
4. Wi-Fi driver/AP IP/DHCP/STA setup, `esp_wifi_start`, default route/NAPT, input
   hooks, cached Wi-Fi table, timezone, portmap/denylist, OTA init, then web UI.
   There is no STA got-IP wait in this path. Network setup calls can marshal work
   onto TCP/IP and therefore deserve timing, not assumptions about zero latency.
5. STA got-IP starts a separate Tailscale connect task. Its SNTP wait is at most
   60 x 500 ms, followed by microlink init/start/control-plane work. Web startup
   does not join this task or its lifecycle mutex. `microlink_start` success is
   distinct from an online node.
6. DNS listener has a 3-second settle delay, independent of app_main, then bind
   retries starting at 2 seconds with backoff. DNS workers have their own I/O and
   retry waits. HTTP at an IP address does not require the relay to be ready.
7. Route supervisor runs independently at 2-second intervals. OTA poller has a
   20-second grace period in its own task. Neither blocks web initialization.
8. `web_ui_init` reads the session timeout from NVS, calls `httpd_start` on port 80,
   then registers handlers. No Internet, DNS, SNTP or password derivation wait is
   present there. Password checks happen on requests. A visible AP and an online
   Tailscale node do not prove the HTTP listener or route to it is already usable.

`boot_timing: ms=...` uses monotonic `esp_timer_get_time`, not wall time/SNTP.
WARN level makes markers visible under the default log filter. Begin/end markers
cover the synchronous phases, binding load/legacy conversion and NVS commits,
AP_START, STA got IP, DHCP ready, DNS bound, HTTP start/handlers, Tailscale start
and first online observation (2-second supervisor sampling). The first GET `/`
is marked separately. The earliest markers precede log-ring installation, so
UART is the complete source. Later markers are also available in the web log.

## Hardware acceptance

1. Download Actions artifact `esp32-s3-0.1.27-tuya6-ota` for this branch/commit.
   Verify SHA256SUMS.txt and upload `firmware-0.1.27-tuya6-esp32-s3-ota.bin` through
   the existing OTA UI without erasing NVS. Confirm version tuya6. Preserve the
   first sensor's working `10.71.0.4` mapping.
2. Enable Auto-reserve. For second sensor `a0:92:08:96:67:69`, test with no manual
   reservation and wake it so it sends IPv4/cloud traffic. Its IP and Reserve
   button must appear on the next Connected Clients refresh, even with no DHCP
   lease. Check the `ap_passive: learned` line and TCP 6668 while it is awake.
   Do not assume its IP is `.5`: use its actual observed source.
3. If that sensor was already saved in tuya5, deleting its manual row may still
   leave a sticky binding. In that case this device tests preservation/recovery,
   not fresh learning. Do not erase NVS or the first sensor's mapping to simulate
   a fresh device; use a never-recorded client for that part. No destructive
   per-client forget API is introduced in this release.
4. Reboot ESP, wake/reassociate both sensors, verify the same addresses without
   manual reservations, first sensor `.4:6668` through Tailscale, and second
   sensor's TCP access. Confirm normal DHCP, Internet/DNS, firewall and OTA UI.
5. Capture one full serial log at 115200 8N1 from before reboot until UI opens.
   Record when the AP becomes visible, node appears online and
   `http://10.71.0.1/` opens, and whether the browser is directly on ESP's AP or
   accessing it through Tailscale. Keep refreshing during the delay. Send that
   log including `boot_timing`, Wi-Fi, DHCP and error lines. If serial is
   unavailable, export the web log immediately after recovery, but it may omit
   earliest events. A gap before `Web UI listening` implicates startup; a long
   gap afterward before `first HTTP GET /` points to reachability/request arrival.

## Regression coverage

`tools/run_host_tests.py` compiles production code with host platform adapters.
The passive integration tests exercise the actual header parser, pbuf chain copy,
bounded asynchronous callback, association/provenance checks, owner policy, NVS
module and ARP call order. Cases include fresh learn, duplicate/no rewrite,
invalid MAC/header/subnet/network/broadcast/AP IP, disconnected/denied/wrong
interface, manual/sticky/live DHCP/live ARP conflicts, unchanged known bindings,
OFF and settings changes while queued, queue exhaustion/failure, write/commit
failure and reboot recovery. Existing allocator, ACK and explicit-netif ARP
regressions still run. CI executes the suites before building ESP32-S3.
