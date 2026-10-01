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
assert capacity >= len(re.findall(r'httpd_register_uri_handler\(server,', web))
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
