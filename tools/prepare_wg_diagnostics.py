"""Build-only instrumentation of the immutable, pinned microlink component.

No file inside external/ is written. Anchor mismatches abort configuration.
Allocation site map is generated with original upstream file/line numbers.
"""
from pathlib import Path
import argparse
import hashlib
import json
import re
import shutil
import subprocess
from derp_header_overlay import apply as apply_derp_header
from pressure_overlay import apply as apply_pressure
from rx_tx_overlay import apply as apply_rx_tx
from wg4_overlay import apply as apply_wg4

ROOT = Path(__file__).resolve().parents[1]
PIN = 'eb63b97073e529d57bc9c1deaeea25ac304034e5'

def replace(text, old, new, count=1):
    actual = text.count(old)
    if actual != count:
        raise RuntimeError(f'Anchor mismatch ({actual} != {count}): {old[:100]}')
    return text.replace(old, new)

def prepare(out):
    upstream = ROOT / 'external/microlink'
    sha = subprocess.check_output(['git', '-C', str(upstream), 'rev-parse', 'HEAD'], text=True).strip()
    if sha != PIN:
        raise RuntimeError(f'microlink HEAD {sha} != {PIN}')
    if subprocess.check_output(['git', '-C', str(upstream), 'status', '--porcelain', '--untracked-files=no'], text=True).strip():
        raise RuntimeError('Pinned microlink worktree must be clean')
    component = out / 'microlink'
    expected = json.loads((ROOT / 'diagnostics/source-hashes.json').read_text())
    for rel, digest in expected.items():
        actual = hashlib.sha256((upstream / 'components/microlink' / rel).read_text(encoding='utf-8').encode('utf-8')).hexdigest()
        if actual != digest:
            raise RuntimeError('Pinned source hash mismatch: ' + rel)
    shutil.copytree(upstream / 'components/microlink', component, dirs_exist_ok=True)
    backend = component / 'components/wireguard_lwip'
    for name in ('wg_diag.c', 'wg_diag.h'):
        shutil.copyfile(ROOT / 'diagnostics' / name, backend / 'src' / name)
    cm = backend / 'CMakeLists.txt'
    cm.write_text(replace(cm.read_text(), '        "src/wireguardif.c"',
                         '        "src/wireguardif.c"\n        "src/wg_diag.c"'))
    sites = []
    files = ('src/ml_net_io.c', 'src/ml_derp.c', 'src/ml_wg_mgr.c',
             'components/wireguard_lwip/src/wireguardif.c')
    hashes = {}
    for rel in files:
        f = component / rel
        original = f.read_text()
        hashes[rel] = hashlib.sha256(f.read_bytes()).hexdigest()
        # Only assignment RHS function calls, balanced parentheses, never comments.
        pattern = r'=\s*(?:\([A-Za-z_][\w\s]*\*\)\s*)?((?:ml_psram_malloc|malloc|heap_caps_malloc|mem_malloc|WG_OUT_ALLOC|pbuf_alloc|pbuf_alloced_custom)\s*\()'
        spans = []
        for m in re.finditer(pattern, original):
            start = m.start(1); i = m.end(1); depth = 1
            while depth:
                depth += (original[i] == '(') - (original[i] == ')'); i += 1
            site = len(sites)
            sites.append({'site': site, 'file': rel, 'line': original[:start].count('\n') + 1,
                          'expression': original[start:i]})
            spans.append((start, i, site))
        text = original
        for start, end, site in reversed(spans):
            text = text[:start] + f'D_ALLOC({site}, {text[start:end]})' + text[end:]
        text = '#include "wg_diag.h"\n' + text
        if rel == 'src/ml_net_io.c':
            text = replace(text, '    case PKT_WIREGUARD:\n        if (xQueueSend(ml->wg_rx_queue, &pkt, 0) != pdTRUE) {', '''    case PKT_WIREGUARD: {
        wg_diag_type(D_DIRECT, data, len);
        BaseType_t accepted = xQueueSend(ml->wg_rx_queue, &pkt, 0);
        wg_diag_add(D_DIRECT, D_RX, 1);
        wg_diag_add(D_DIRECT, D_BYTES, len);
        wg_diag_add(D_DIRECT, accepted == pdTRUE ? D_ENQUEUE : D_DROP, 1);
        wg_diag_sample_queue(0, ml->wg_rx_queue);
        wg_diag_source(D_DIRECT, NULL, src_ip, src_port, len, accepted == pdTRUE);
        if (accepted != pdTRUE) {''')
            text = replace(text, '        break;\n    default:', '        break;\n    }\n    default:')
        elif rel == 'src/ml_derp.c':
            text = replace(text, '    if (xQueueSend(target, &pkt, 0) != pdTRUE) {', '''    BaseType_t accepted = xQueueSend(target, &pkt, 0);
    if (target == ml->wg_rx_queue) {
        wg_diag_type(D_DERP, data, len);
        wg_diag_add(D_DERP, D_RX, 1);
        wg_diag_add(D_DERP, D_BYTES, len);
        wg_diag_add(D_DERP, accepted == pdTRUE ? D_ENQUEUE : D_DROP, 1);
        wg_diag_source(D_DERP, src_pubkey, 0, 0, len, accepted == pdTRUE);
    }
    wg_diag_sample_queue(target == ml->wg_rx_queue ? 0 : 1, target);
    if (accepted != pdTRUE) {''')
            text = replace(text, '            free(dropped.data);  /* Drop oldest */',
                           '            wg_diag_add(D_DERP, D_TX_EVICT, 1);\n            free(dropped.data);  /* Drop oldest */')
            text = replace(text, '    free(pkt_data);\n    return ESP_ERR_TIMEOUT;',
                           '    wg_diag_add(D_DERP, D_TX_DROP, 1);\n    free(pkt_data);\n    return ESP_ERR_TIMEOUT;')
            text = replace(text, '        return ESP_OK;\n    }\n\n    /* Queue full - backpressure:',
                           '        wg_diag_add(D_DERP, D_TX_ENQUEUE, 1);\n        wg_diag_sample_queue(2, ml->derp_tx_queue);\n        return ESP_OK;\n    }\n\n    /* Queue full - backpressure:')
            text = replace(text, '        if (xQueueSend(ml->derp_tx_queue, &item, 0) == pdTRUE) {\n            return ESP_OK;',
                           '        if (xQueueSend(ml->derp_tx_queue, &item, 0) == pdTRUE) {\n            wg_diag_add(D_DERP, D_TX_ENQUEUE, 1);\n            wg_diag_sample_queue(2, ml->derp_tx_queue);\n            return ESP_OK;')
            text = replace(text, '                    ret = derp_send_packet(ml, item.dest_pubkey, item.data, item.len);', '''                    ret = derp_send_packet(ml, item.dest_pubkey, item.data, item.len);
                    wg_diag_add(D_DERP, D_TX, 1);
                    if (ret < 0) wg_diag_add(D_DERP, D_TX_ERROR, 1);''')
            text = replace(text, '            int ret = poll_derp_read(ml);', '''            int ret = poll_derp_read(ml);
            if (ret < 0) wg_diag_add(D_DERP, D_READ_ERROR, 1);''')
        elif rel == 'src/ml_wg_mgr.c':
            text = replace(text, '    err_t err = udp_sendto(s_wg_output_pcb, p, &dst, dest_port);', '''    err_t err = udp_sendto(s_wg_output_pcb, p, &dst, dest_port);
    wg_diag_add(D_DIRECT, D_TX, 1);
    if (err != ERR_OK) wg_diag_add(D_DIRECT, D_TX_ERROR, 1);''')
            text = replace(text, '            process_wg_packet(ml, &wg_pkt);', '''            int64_t d_start = esp_timer_get_time();
            wg_diag_add(wg_pkt.via_derp ? D_DERP : D_DIRECT, D_DEQUEUE, 1);
            process_wg_packet(ml, &wg_pkt);
            wg_diag_time(D_PROCESS, (uint32_t)(esp_timer_get_time() - d_start));''', 2)
            text = replace(text, '    while (!(xEventGroupGetBits(ml->events) & ML_EVT_SHUTDOWN_REQUEST)) {', '''    wg_diag_start();
    while (!(xEventGroupGetBits(ml->events) & ML_EVT_SHUTDOWN_REQUEST)) {
        int64_t d_loop_start = esp_timer_get_time();''')
            text = replace(text, '            wireguardif_periodic((struct netif *)ml->wg_netif);', '''            int64_t d_periodic_start = esp_timer_get_time();
            wireguardif_periodic((struct netif *)ml->wg_netif);
            wg_diag_time(D_PERIODIC, (uint32_t)(esp_timer_get_time() - d_periodic_start));''')
            text = replace(text, '            disco_periodic_probes(ml);', '''            int64_t d_probe_start = esp_timer_get_time();
            disco_periodic_probes(ml);
            wg_diag_time(D_PROBES, (uint32_t)(esp_timer_get_time() - d_probe_start));''')
            text = replace(text, '        vTaskDelay(pdMS_TO_TICKS(10));', '''        wg_diag_sample_queue(0, ml->wg_rx_queue);
        wg_diag_sample_queue(1, ml->disco_rx_queue);
        wg_diag_sample_queue(2, ml->derp_tx_queue);
        wg_diag_time(D_LOOP, (uint32_t)(esp_timer_get_time() - d_loop_start));
        vTaskDelay(pdMS_TO_TICKS(10));''')
            text = replace(text, '            dump_wg_state_snapshot(ml);',
                           '            wg_diag_stack_sample();\n            /* WG_SNAP disabled in diagnostic overlay: synchronous UART stalls RX. */')
        else:
            # Results below occur after WG peer lookup/decrypt, unlike the
            # pre-authenticated DERP source labels and UDP endpoints.
            text = replace(text, '\t\t\t\tbool decrypt_ok = wireguard_decrypt_packet(pbuf->payload, src, src_len, nonce, keypair);', '''\t\t\t\tbool decrypt_ok = wireguard_decrypt_packet_diag(pbuf->payload, src, src_len, nonce, keypair, wg_diag_rx_path());
                wg_diag_peer(wireguard_peer_index(device, peer), decrypt_ok);
                wg_diag_add(wg_diag_rx_path(), decrypt_ok ? D_DECRYPT_OK : D_DECRYPT_ERROR, 1);''')
            text = replace(text, 'if (device->netif->input(pbuf, device->netif) == ERR_OK) {', '''err_t d_forward = device->netif->input(pbuf, device->netif);
                                    wg_diag_add(wg_diag_rx_path(), d_forward == ERR_OK ? D_FORWARD_OK : D_FORWARD_ERROR, 1);
                                    if (d_forward == ERR_OK) {''')
            text = replace(text, 'WG_DEBUG("[WG_RX_IP] DROPPED: dest_ok=false\\n");',
                           'wg_diag_add(wg_diag_rx_path(), D_POLICY_DROP, 1);\n\t\t\t\t\t\t\t\t\tWG_DEBUG("[WG_RX_IP] DROPPED: dest_ok=false\\n");')
        text = text.replace('wg_diag_rx_path()', '(ip_addr_isany(addr) ? D_DERP : D_DIRECT)')
        if rel == 'src/ml_derp.c':
            text = apply_derp_header(text)
        f.write_text(text)
    # Upstream now authenticates and checks replay inside decrypt, including
    # keepalives. Carry the RX path explicitly: no shared/thread-local state.
    for name in ('wireguard.c', 'wireguard.h'):
        f = backend / 'src' / name
        hashes['components/wireguard_lwip/src/' + name] = hashlib.sha256(f.read_bytes()).hexdigest()
        text = f.read_text()
        text = replace(text, 'wireguard_decrypt_packet(uint8_t *dst, const uint8_t *src, size_t src_len, uint64_t counter, struct wireguard_keypair *keypair)',
                       'wireguard_decrypt_packet_diag(uint8_t *dst, const uint8_t *src, size_t src_len, uint64_t counter, struct wireguard_keypair *keypair, unsigned diag_path)')
        if name == 'wireguard.c':
            text = '#include "wg_diag.h"\n' + text
            text = replace(text, 'return wireguard_check_replay(keypair, counter);',
                           'bool accepted = wireguard_check_replay(keypair, counter);\n    if (!accepted) wg_diag_add(diag_path, D_REPLAY, 1);\n    return accepted;')
        f.write_text(text)
    apply_pressure(component)
    apply_rx_tx(component)
    apply_wg4(component)
    if len(sites) > 64:
        raise RuntimeError('Allocation site table exceeded')
    (out / 'allocation-sites.json').write_text(json.dumps(sites, indent=2) + '\n')
    (out / 'overlay-provenance.json').write_text(json.dumps({'microlink': PIN, 'source_sha256': hashes, 'snapshot_policy': 'disabled-in-wg-consumer', 'derp_header_overlay': 'derphdr1'}, indent=2) + '\n')

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    prepare(parser.parse_args().output.resolve())
