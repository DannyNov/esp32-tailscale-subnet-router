#!/usr/bin/env python3
"""Deterministic, fail-closed pilot patch for manager/telemetry/web UI lifetime snapshots.
Only run against a separate scratch checkout at af136603c3db...; never on production.
"""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path

BASE = 'af136603c3db472115fcf3ccd9c82eeef4b19d3c'
PINS = {
    'main/tailscale_manager.c': 'a130ad60b0926a1984ecec6eac3369c2ea8eb2af',
    'main/telemetry.c': '75be60e261e72f1edf59aaa268a57ecdd4b40629',
    'main/web_ui.c': '9c851958329900fb91e5fe6bb7e8ceeecdea66e6',
}
HEADER = '''/* SPDX-License-Identifier: MIT
 * EXPERIMENTAL: task-context snapshots, protecting instance lifetime
 * against manager connect/disconnect. Does not solve microlink's internal
 * mutable-state races, stop/destroy lifetime defects, or DERP TLS teardown.
 */
#pragma once
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include "microlink.h"

typedef struct {
    microlink_diag_t diag;
    bool connected;
    uint32_t vpn_ip; /* host order */
    uint32_t generation;
    int peer_count;
    int peers_online;
} tailscale_status_snapshot_t;

typedef struct {
    microlink_peer_info_t peer;
    char derp_region_name[64];
} tailscale_peer_snapshot_t;

/* All calls are non-blocking, for task context (not an ISR/tcpip raw hook).
 * Contention, missing instance, or reinitialization -> false/zero output.
 * No pointer into the instance is returned. */
bool tailscale_snapshot_status(tailscale_status_snapshot_t *out);
bool tailscale_snapshot_diag(microlink_diag_t *out);
bool tailscale_snapshot_peer(uint32_t generation, int index, tailscale_peer_snapshot_t *out);
int tailscale_snapshot_derp_rtts(uint32_t generation, microlink_derp_rtt_t *out, int capacity);
bool tailscale_snapshot_region_name(uint32_t generation, uint16_t region, char *out, size_t capacity);
'''
FUNCTIONS = '''/* Lifetime-safe read adapter: s_life_mux serializes all manager-owned
 * instance replacements. Never retain ml after releasing the mutex. This
 * does not synchronize simultaneous writes by INTERNAL microlink tasks. */
static bool snapshot_try_lock(void)
{
    return s_life_mux && xSemaphoreTake(s_life_mux, 0) == pdTRUE;
}

bool tailscale_snapshot_status(tailscale_status_snapshot_t *out)
{
    if (!out) return false;
    memset(out, 0, sizeof(*out));
    if (!snapshot_try_lock()) return false;
    microlink_t *ml = s_microlink;
    bool ok = false;
    if (ml && microlink_get_diag(ml, &out->diag) == ESP_OK) {
        out->generation = s_life_generation;
        out->connected = microlink_is_connected(ml);
        out->vpn_ip = microlink_get_vpn_ip(ml);
        int n = microlink_get_peer_count(ml);
        if (n < 0) n = 0;
        if (n > 64) n = 64;  /* config max_peers <= 64 */
        out->peer_count = n;
        if (out->connected) {
            for (int i = 0; i < n; i++) {
                microlink_peer_info_t info;
                if (microlink_get_peer_info(ml, i, &info) == ESP_OK && info.online)
                    out->peers_online++;
            }
        }
        ok = true;
    }
    xSemaphoreGive(s_life_mux);
    if (!ok) memset(out, 0, sizeof(*out));
    return ok;
}

bool tailscale_snapshot_diag(microlink_diag_t *out)
{
    if (!out) return false;
    memset(out, 0, sizeof(*out));
    /* A standalone diag avoids a full peer traversal for telemetry. */
    if (!snapshot_try_lock()) return false;
    bool ok = s_microlink && microlink_get_diag(s_microlink, out) == ESP_OK;
    xSemaphoreGive(s_life_mux);
    if (!ok) memset(out, 0, sizeof(*out));
    return ok;
}

bool tailscale_snapshot_peer(uint32_t generation, int index, tailscale_peer_snapshot_t *out)
{
    if (!out) return false;
    memset(out, 0, sizeof(*out));
    if (!snapshot_try_lock()) return false;
    bool ok = false;
    microlink_t *ml = s_microlink;
    if (ml && generation == s_life_generation && index >= 0 && index < 64 &&
        microlink_get_peer_info(ml, index, &out->peer) == ESP_OK) {
        if (out->peer.derp_region) {
            const char *name = microlink_get_derp_region_name(ml, out->peer.derp_region);
            if (name) snprintf(out->derp_region_name, sizeof(out->derp_region_name), "%s", name);
        }
        ok = true;
    }
    xSemaphoreGive(s_life_mux);
    if (!ok) memset(out, 0, sizeof(*out));
    return ok;
}

int tailscale_snapshot_derp_rtts(uint32_t generation, microlink_derp_rtt_t *out, int capacity)
{
    if (!out || capacity <= 0) return 0;
    if (!snapshot_try_lock()) return 0;
    int count = (s_microlink && generation == s_life_generation)
        ? microlink_get_derp_rtts(s_microlink, out, capacity) : 0;
    xSemaphoreGive(s_life_mux);
    return count > 0 && count <= capacity ? count : 0;
}

bool tailscale_snapshot_region_name(uint32_t generation, uint16_t region, char *out, size_t capacity)
{
    if (!out || capacity == 0) return false;
    out[0] = '\\0';
    if (!snapshot_try_lock()) return false;
    bool ok = false;
    if (s_microlink && generation == s_life_generation) {
        const char *name = microlink_get_derp_region_name(s_microlink, region);
        if (name) {
            snprintf(out, capacity, "%s", name);
            ok = true;
        }
    }
    xSemaphoreGive(s_life_mux);
    return ok;
}
'''

STATUS_OLD = '''    /* Tailscale (microlink) — runtime state from tailscale_config.h.
     * tailscale_is_connected() polls microlink + refreshes the cached
     * tunnel_ip; we use its return value over the stale bool global. */'''
STATUS_START = '''    /* Tailscale (microlink) — task-context lifetime-safe snapshot. */
    tailscale_status_snapshot_t ts_snapshot;
    bool ts_has_snapshot = tailscale_snapshot_status(&ts_snapshot);
    bool ts_connected = ts_has_snapshot && ts_snapshot.connected;
    cJSON *ts = cJSON_CreateObject();
    cJSON_AddBoolToObject  (ts, "enabled",   tailscale_enabled != 0);
    cJSON_AddBoolToObject  (ts, "connected", ts_connected);
    if (tailscale_hostname)         cJSON_AddStringToObject(ts, "hostname",         tailscale_hostname);
    if (tailscale_advertise_routes) cJSON_AddStringToObject(ts, "advertise_routes", tailscale_advertise_routes);
    if (ts_has_snapshot && ts_snapshot.vpn_ip) {
        char buf[16];
        ip4_hbo_to_str(ts_snapshot.vpn_ip, buf, sizeof buf);
        cJSON_AddStringToObject(ts, "tunnel_ip", buf);
    }
    if (tailscale_exit_node_ip) {
        char buf[16];
        ip4_hbo_to_str(tailscale_exit_node_ip, buf, sizeof buf);
        cJSON_AddStringToObject(ts, "exit_node_ip", buf);
    }
    cJSON_AddNumberToObject(ts, "peers_online", ts_has_snapshot ? ts_snapshot.peers_online : 0);
    cJSON_AddNumberToObject(ts, "peers_total",  ts_has_snapshot ? ts_snapshot.peer_count : 0);
    if (ts_has_snapshot) {
        const microlink_diag_t *diag = &ts_snapshot.diag;
        cJSON_AddNumberToObject(ts, "register_user_id", diag->register_user_id);
        if (diag->register_user_name[0]) cJSON_AddStringToObject(ts, "register_user_name", diag->register_user_name);
        cJSON_AddBoolToObject(ts, "identity_persistent", diag->identity_persistent);
        cJSON_AddStringToObject(ts, "identity_pubkey_prefix", diag->identity_pubkey_prefix);
    }
    cJSON_AddItemToObject(root, "tailscale", ts);'''

RUNTIME_START = '''    /* Runtime: standalone copy, never a borrowed microlink pointer. */
    tailscale_status_snapshot_t runtime_snapshot;
    bool runtime_has_snapshot = tailscale_snapshot_status(&runtime_snapshot);
    bool ts_runtime_connected = runtime_has_snapshot && runtime_snapshot.connected;
    cJSON *runtime = cJSON_CreateObject();
    cJSON_AddBoolToObject(runtime, "connected", ts_runtime_connected);
    if (runtime_has_snapshot && runtime_snapshot.vpn_ip) {
        char buf[16];
        ip4_hbo_to_str(runtime_snapshot.vpn_ip, buf, sizeof buf);
        cJSON_AddStringToObject(runtime, "tunnel_ip", buf);
    }
    if (runtime_has_snapshot) {
        const microlink_diag_t *diag = &runtime_snapshot.diag;
        cJSON_AddNumberToObject(runtime, "register_user_id", diag->register_user_id);
        if (diag->register_user_name[0]) cJSON_AddStringToObject(runtime, "register_user_name", diag->register_user_name);
        cJSON_AddBoolToObject(runtime, "identity_persistent", diag->identity_persistent);
        cJSON_AddStringToObject(runtime, "identity_pubkey_prefix", diag->identity_pubkey_prefix);
        cJSON_AddNumberToObject(runtime, "derp_home_region", diag->derp_home_region);
        cJSON_AddNumberToObject(runtime, "derp_region_default", diag->derp_region_default);
        char home_name[64];
        if (tailscale_snapshot_region_name(runtime_snapshot.generation, diag->derp_home_region,
                                           home_name, sizeof(home_name)))
            cJSON_AddStringToObject(runtime, "derp_home_region_name", home_name);
        microlink_derp_rtt_t rtts[32];
        int nr = tailscale_snapshot_derp_rtts(runtime_snapshot.generation, rtts, 32);
        cJSON *derp_rtts = cJSON_CreateArray();
        for (int i = 0; i < nr; i++) {
            cJSON *e = cJSON_CreateObject();
            char name[64];
            bool known = tailscale_snapshot_region_name(runtime_snapshot.generation,
                                                         rtts[i].region_id, name, sizeof(name));
            cJSON_AddNumberToObject(e, "region_id", rtts[i].region_id);
            cJSON_AddStringToObject(e, "name", known ? name : "?");
            cJSON_AddNumberToObject(e, "rtt_ms", rtts[i].rtt_ms);
            cJSON_AddItemToArray(derp_rtts, e);
        }
        cJSON_AddItemToObject(runtime, "derp_rtts", derp_rtts);
    }
    cJSON_AddItemToObject(root, "runtime", runtime);'''

PEERS_NEW = '''    /* Peer snapshots are copies; generation check avoids mixing old/new instances. */
    cJSON *peers = cJSON_CreateArray();
    if (runtime_has_snapshot) {
        for (int i = 0; i < runtime_snapshot.peer_count; i++) {
            tailscale_peer_snapshot_t snap;
            if (!tailscale_snapshot_peer(runtime_snapshot.generation, i, &snap)) continue;
            microlink_peer_info_t *pi = &snap.peer;
            cJSON *p = cJSON_CreateObject();
            cJSON_AddStringToObject(p, "hostname", pi->hostname);
            cJSON_AddBoolToObject(p, "online", ts_runtime_connected && pi->online);
            cJSON_AddBoolToObject(p, "direct_path", ts_runtime_connected && pi->direct_path);
            cJSON_AddBoolToObject(p, "is_exit_node", pi->is_exit_node);
            cJSON_AddNumberToObject(p, "derp_region", pi->derp_region);
            if (pi->derp_region && snap.derp_region_name[0])
                cJSON_AddStringToObject(p, "derp_region_name", snap.derp_region_name);
            char buf[16];
            ip4_hbo_to_str(pi->vpn_ip, buf, sizeof buf);
            cJSON_AddStringToObject(p, "vpn_ip", buf);
            cJSON *routes = cJSON_CreateArray();
            for (int r = 0; r < pi->subnet_route_count && r < MICROLINK_MAX_PEER_ROUTES; r++) {
                cJSON *rt = cJSON_CreateObject();
                ip4_hbo_to_str(pi->subnet_routes[r].network, buf, sizeof buf);
                cJSON_AddStringToObject(rt, "network", buf);
                cJSON_AddNumberToObject(rt, "prefix_len", pi->subnet_routes[r].prefix_len);
                cJSON_AddItemToArray(routes, rt);
            }
            cJSON_AddItemToObject(p, "subnet_routes", routes);
            cJSON_AddItemToArray(peers, p);
        }
    }
    cJSON_AddItemToObject(root, "peers", peers);'''


def swap_once(text, a, b, label):
    n = text.count(a)
    if n != 1:
        raise ValueError(f'STOP: {label}: expected exactly one anchor, found {n}')
    return text.replace(a, b, 1)


def between_once(text, start, end, content, label):
    if text.count(start) != 1 or text.count(end) != 1:
        raise ValueError(f'STOP: {label}: wrong marker multiplicity ({text.count(start)}, {text.count(end)})')
    a = text.index(start)
    b = text.index(end) + len(end)
    if b <= a:
        raise ValueError(f'STOP: {label}: out of order')
    return text[:a] + content + text[b:]


def transform(name, src):
    if '#include "tailscale_snapshot.h"\n' in src:
        raise ValueError("STOP: patch appears already applied")
    if name == 'main/tailscale_manager.c':
        src = swap_once(src, '#include "tailscale_config.h"\n', '#include "tailscale_config.h"\n#include "tailscale_snapshot.h"\n',name)
        anchor = 'struct microlink_s *tailscale_get_microlink(void)\n{\n    return s_microlink;\n}\n'
        src = swap_once(src, anchor, anchor + '\n' + FUNCTIONS, name)
        # If no mutex is available, do not initiate an unprotected connect.
        src = swap_once(src, 'static esp_err_t tailscale_connect_locked(void)\n{\n',
            'static esp_err_t tailscale_connect_locked(void)\n{\n    if (!s_life_mux) return ESP_ERR_INVALID_STATE;\n',name)
    elif name == 'main/telemetry.c':
        src = swap_once(src, '#include "tailscale_config.h"\n', '#include "tailscale_config.h"\n#include "tailscale_snapshot.h"\n',name)
        old = '''    microlink_diag_t mdiag = {0};
    {
        struct microlink_s *mlh = tailscale_get_microlink();
        if (mlh) microlink_get_diag(mlh, &mdiag);
    }
'''
        src = swap_once(src, old, '    microlink_diag_t mdiag = {0};\n    (void)tailscale_snapshot_diag(&mdiag);\n',name)
    elif name == 'main/web_ui.c':
        src = swap_once(src,'#include "tailscale_config.h"\n','#include "tailscale_config.h"\n#include "tailscale_snapshot.h"\n',name)
        src = between_once(src, STATUS_OLD, '    cJSON_AddItemToObject(root, "tailscale", ts);', STATUS_START, 'status')
        src = between_once(src,'    /* Runtime state. tailscale_is_connected() refreshes tunnel_ip from',
                           '    cJSON_AddItemToObject(root, "runtime", runtime);',RUNTIME_START,'runtime')
        src = between_once(src, '    cJSON *peers = cJSON_CreateArray();',
                           '    cJSON_AddItemToObject(root, "peers", peers);',PEERS_NEW,'peers')
    else:
        raise ValueError(name)
    return src


def git_blob(data):
    return hashlib.sha1(b'blob ' + str(len(data)).encode()+b'\0'+data).hexdigest()

def sha(data): return hashlib.sha256(data).hexdigest()

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--repo', type=Path, required=True)
    p.add_argument('--dry-run',action='store_true')
    p.add_argument('--manifest',type=Path)
    a=p.parse_args()
    repo = a.repo.resolve()
    # Fail closed if this is not an untouched experimental checkout from the
    # *exact* CI baseline. Input blob checks below add a second barrier.
    def git(*args):
        result = subprocess.run(['git','-C',str(repo),*args], capture_output=True, text=True)
        if result.returncode != 0:
            raise ValueError('STOP: git check failed: ' + ' '.join(args))
        return result.stdout.strip()
    if git('rev-parse','HEAD') != BASE:
        raise ValueError('STOP: checkout HEAD != pinned baseline')
    branch=git('branch','--show-current')
    if not branch.startswith('experiment/'):
        raise ValueError('STOP: checkout must be on a separate experiment/* branch')
    if git('status','--porcelain'):
        raise ValueError('STOP: working tree not clean')
    submodule=git('ls-tree','HEAD','external/microlink').split()
    if len(submodule) < 3 or submodule[1] != 'commit' or submodule[2] != 'eb63b97073e529d57bc9c1deaeea25ac304034e5':
        raise ValueError('STOP: pinned microlink gitlink mismatched')
    outputs={}
    inputs={}
    for path,pin in PINS.items():
        source=(repo/path).read_bytes()
        actual=git_blob(source)
        if actual != pin: raise ValueError(f'STOP: {path}: upstream blob SHA mismatch: {actual} != {pin}')
        if b'\r\n' in source: raise ValueError('STOP: CRLF original')
        outputs[path]=transform(path,source.decode('utf-8')).encode('utf-8')
        inputs[path]={'git_blob_sha1':actual,'sha256':sha(source)}
    h='main/tailscale_snapshot.h'
    if (repo/h).exists(): raise ValueError('STOP: header exists already')
    outputs[h]=HEADER.encode('utf-8')
    manifest={'baseline':BASE,'third_party_submodule_unchanged':True,
              'scope':'manager/telemetry/web UI diagnostic snapshots only',
              'inputs':inputs,'outputs':{p:sha(content) for p,content in outputs.items()}}
    if not a.dry_run:
        for path,data in outputs.items(): (repo/path).write_bytes(data)
    if a.manifest: a.manifest.write_text(json.dumps(manifest,indent=2,ensure_ascii=False))
    print(json.dumps(manifest,indent=2,ensure_ascii=False))

if __name__=='__main__': main()
