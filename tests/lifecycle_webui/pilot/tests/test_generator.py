#!/usr/bin/env python3
import importlib.util
from pathlib import Path
spec=importlib.util.spec_from_file_location('patch',Path(__file__).resolve().parent.parent/'apply_patch.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

def check(f,original,expected,excluded):
    updated=m.transform(f,original)
    assert expected in updated, f
    assert excluded not in updated, f
    try:
        m.transform(f,updated)
    except ValueError:pass
    else:raise AssertionError(f + ' was not fail-closed on repeated transform')
    return updated

manager='''#include "tailscale_config.h"
struct microlink_s *tailscale_get_microlink(void)
{
    return s_microlink;
}
static esp_err_t tailscale_connect_locked(void)
{
'''
check('main/tailscale_manager.c',manager,'bool tailscale_snapshot_status(', 'invalid-impossible')
tele='''#include "tailscale_config.h"
    microlink_diag_t mdiag = {0};
    {
        struct microlink_s *mlh = tailscale_get_microlink();
        if (mlh) microlink_get_diag(mlh, &mdiag);
    }
'''
check('main/telemetry.c',tele,'(void)tailscale_snapshot_diag(&mdiag);','struct microlink_s *mlh =')
web='''#include "tailscale_config.h"
''' + m.STATUS_OLD + '\n    legacy_status_content();\n    cJSON_AddItemToObject(root, "tailscale", ts);\n' + '''    /* Runtime state. tailscale_is_connected() refreshes tunnel_ip from
     * test */
    legacy_runtime_content();
    cJSON_AddItemToObject(root, "runtime", runtime);
    /* MTU block preserved */
    cJSON *peers = cJSON_CreateArray();
    legacy_peers_content();
    cJSON_AddItemToObject(root, "peers", peers);
'''
w=check('main/web_ui.c',web,'tailscale_snapshot_peer(runtime_snapshot.generation','legacy_peers_content();')
assert '    /* MTU block preserved */' in w
assert 'legacy_status_content()' not in w
assert 'legacy_runtime_content()' not in w
assert w.count('tailscale_snapshot_status(&') == 2
for target in m.PINS:
    try:m.transform(target,'bad')
    except ValueError:pass
    else:raise AssertionError('bad source transform did not fail: '+target)
print('PASS: anchored transforms, modified content, preservation and fail-closed behavior')
