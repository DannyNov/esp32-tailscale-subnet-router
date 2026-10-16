"""WiFi PS integration contracts; no latency/runtime claims."""
from pathlib import Path
import subprocess

root = Path(__file__).resolve().parents[1]
main = (root / 'main/main.c').read_text()
web = (root / 'main/web_ui.c').read_text()
html = (root / 'main/index.html').read_text(encoding='utf-8')
boot = main.split('/* Preserve the IDF modem-sleep default', 1)[1].split('/* Optional TX-power', 1)[0]
assert main.index('ESP_ERROR_CHECK(esp_wifi_start()') < main.index('/* Preserve the IDF modem-sleep default')
for token in ['uint8_t ps = 1;', 'nvs_param_get_u8("wifi_ps", &ps);', 'if (ps == 0)', 'esp_wifi_set_ps(WIFI_PS_NONE)']:
    assert token in boot
get = web.split('static esp_err_t system_handler(', 1)[1].split('static esp_err_t system_save_handler(', 1)[0]
assert 'uint8_t ps = 1;' in get
assert 'cJSON_AddBoolToObject(root, "wifi_power_save", ps != 0);' in get
save = web.split('/* WiFi power save -- persist + apply live', 1)[1].split('/* Telemetry block', 1)[0]
for token in ['cJSON_IsBool(ps_j)', 'nvs_save_u8("wifi_ps", on ? 1 : 0)', 'esp_wifi_set_ps(on ? WIFI_PS_MIN_MODEM : WIFI_PS_NONE)']:
    assert token in save
assert 'esp_restart' not in save
for token in ['id="sys-wifi-ps"', '(d.wifi_power_save !== false)', "id === 'sys-wifi-ps' ? 'change' : 'input'", 'wifi_power_save: wifi_ps', 'Throughput improvement is not guaranteed']:
    assert token in html
# Byte equality with the exact prior candidate for protected production files.
protected = ['partitions.csv', 'sdkconfig.defaults', 'platformio.ini',
             'main/ap_passive.c', 'main/dhcp_bindings.c', 'main/dhcp_reservations.c',
             'main/dhcp_last_seen.inc', 'main/nvs_params.c', 'main/peer_dns.c',
             'main/ota.c', 'tools/test_lib/common.py']
protected += subprocess.check_output(['git', 'ls-files', 'components/dhcpserver', 'components/snmp_agent'], cwd=root, text=True).splitlines()
for path in protected:
    if not (root / path).exists():
        raise AssertionError(f'Protected path missing: {path}')
    old = subprocess.check_output(['git', 'show', f'bd0a9c0dd2e0109544a6aa2a441e92e2670df62a:{path}'], cwd=root)
    current = (root / path).read_bytes().replace(b'\r\n', b'\n')
    if path == 'main/peer_dns.c':
        # Exact approved lifecycle delta; all other DNS bytes remain protected.
        include = b'#include "tailscale_config.h"\n#include "tailscale_snapshot.h"'
        new = (b'    tailscale_status_snapshot_t status;\n'
               b'    /* Contention must reject the resolver rather than bypass loop checks. */\n'
               b'    if (!tailscale_snapshot_status(&status)) return true;\n'
               b'    return status.vpn_ip == ntohl(resolver_nbo);')
        prior = (b'    microlink_t *ml = tailscale_get_microlink();\n'
                 b'    return ml && microlink_get_vpn_ip(ml) == ntohl(resolver_nbo);')
        assert current.count(include) == 1 and current.count(new) == 1
        current = current.replace(include, b'#include "tailscale_config.h"').replace(new, prior)
    if path == 'platformio.ini':
        # Diagnostic build pins the exact platform used by the original CI.
        # All hardware/network/build flags remain byte-identical.
        assert current.count(b'platform = espressif32@6.13.0') == 1
        current = current.replace(b'platform = espressif32@6.13.0',
                                  b'platform = espressif32@^6.4.0')
    assert current == old.replace(b'\r\n', b'\n'), path
print('PASS: PS boot/API/UI source contracts and unchanged protected production files; runtime pending hardware')
