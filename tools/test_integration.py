#!/usr/bin/env python3
"""Check integration contracts that a successful link cannot verify."""
from pathlib import Path
import re

root = Path(__file__).resolve().parents[1]
main = (root / 'main/main.c').read_text()
web = (root / 'main/web_ui.c').read_text()
hooks = (root / 'main/netif_hooks.c').read_text()
assert main.index('    netif_hooks_init();') < main.index('    snmp_agent_init();') < main.index('    web_ui_init();')
capacity = int(re.search(r'conf.max_uri_handlers\s*=\s*(\d+)', web)[1])
registered = re.findall(r'reg_uri\(server, &(\w+)\);', web)
assert capacity == 72
assert len(registered) == len(set(registered)) == 60
assert capacity > len(registered)
assert {'uri_dhcp_remembered', 'uri_favicon'} <= set(registered)
assert 'httpd_register_uri_handler(server,' not in web
assert 'esp_err_t err = httpd_register_uri_handler(srv, u);' in web
assert 'if (err != ESP_OK)' in web[web.index('static void reg_uri('):]
favicon = web[web.index('static esp_err_t favicon_handler('):web.index('static void reg_uri(')]
assert 'require_auth' not in favicon
assert 'image/svg+xml' in favicon
assert 'rel="icon"' in (root / 'main/index.html').read_text(encoding='utf-8')
route = (root / 'main/lwip_route_hook.c').read_text()
assert "n->name[0] == 'w' && n->name[1] == 'g'" in route
hook, explain = route.split('void route_explain(', 1)
for implementation in (hook, explain):
    assert 'if (!netif_is_up(n) || !netif_is_link_up(n)) continue;' in implementation
    assert 'if (netif_is_wg(n)) continue;' in implementation
assert 'ap_passive_observe(p, netif);' in hooks
assert 'ap_passive_init();' in hooks
assert 'temperature_sensor_install(' not in re.sub(r'/\*.*?\*/', '', web, flags=re.S)
assert 'if (!snmp_agent_chip_temp_c(&tc)) return -999.0f;' in web
assert 'CONFIG_LWIP_MAX_SOCKETS=26' in (root / 'sdkconfig.defaults').read_text()
assert 'snmp_agent' in (root / 'main/CMakeLists.txt').read_text()
assert '.uri = "/api/snmp", .method = HTTP_GET' in web
assert '.uri = "/api/snmp", .method = HTTP_POST' in web
assert '.uri = "/api/dhcp/remembered"' in web
print('PASS: ACL/passive -> SNMP -> Web UI order, URI capacity, single temperature owner, sockets and both subsystems registered')

assert 'dhcp_last_seen_activity(event->mac);' in main
association = main.split('event_id == WIFI_EVENT_AP_STACONNECTED', 1)[1].split('event_id == WIFI_EVENT_AP_STADISCONNECTED', 1)[0]
assert association.index('mac_deny_is_blocked(event->mac)') < association.index('dhcp_last_seen_activity(event->mac);')
remembered = web.split('static esp_err_t dhcp_remembered_handler(', 1)[1].split('static const httpd_uri_t uri_dhcp_remembered', 1)[0]
assert 'cJSON_AddNumberToObject(entry, "last_seen", (double)r->last_seen);' in remembered
assert 'dhcp_last_seen_activity(' not in remembered
assert 'set(PROJECT_VER "0.1.30-tuya")' in (root / 'CMakeLists.txt').read_text()
print('PASS: real association wiring, deny filtering, read-only remembered API with Unix seconds, candidate version')
