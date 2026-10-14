"""Additional bounded diagnostics; transport and scheduling stay identical."""
from pathlib import Path
from derp_header_overlay import once

def apply(component):
    header = component / 'include/microlink_internal.h'
    header.write_text(once(header.read_text(), '} ml_rx_packet_t;', '    int64_t diag_enqueued_us;\n} ml_rx_packet_t;'))
    for rel in ('src/ml_net_io.c', 'src/ml_derp.c'):
        f = component / rel
        s = f.read_text()
        s = once(s, '    BaseType_t accepted = xQueueSend(' if 'derp' in rel else '        BaseType_t accepted = xQueueSend(',
                 ('    ' if 'derp' in rel else '        ') + 'pkt.diag_enqueued_us = esp_timer_get_time();\n' + ('    ' if 'derp' in rel else '        ') + 'BaseType_t accepted = xQueueSend(')
        if 'net_io' in rel:
            s = once(s, '        wg_diag_add(D_DIRECT, D_RX, 1);', '        wg_diag_burst(accepted == pdTRUE, pkt.diag_enqueued_us);\n        wg_diag_add(D_DIRECT, D_RX, 1);')
        f.write_text(s)
    f = component / 'src/ml_wg_mgr.c'
    s = f.read_text()
    s = once(s, '    if (!wrap) return ERR_MEM;', '    if (!wrap) { wg_diag_tx(0, ERR_MEM); return ERR_MEM; }')
    s = once(s, '    if (!wrap->data_spiram) {', '    if (!wrap->data_spiram) {\n        wg_diag_tx(1, ERR_MEM);')
    s = once(s, '    if (!p) {\n        heap_caps_free(wrap->data_spiram);', '    if (!p) {\n        wg_diag_tx(2, ERR_MEM);\n        heap_caps_free(wrap->data_spiram);')
    s = once(s, '    wg_diag_add(D_DIRECT, D_TX, 1);', '    wg_diag_tx(3, err);\n    wg_diag_add(D_DIRECT, D_TX, 1);')
    anchor = '            int64_t d_start = esp_timer_get_time();'
    assert s.count(anchor) == 2
    s = s.replace(anchor, anchor + '\n            wg_diag_time(D_WAIT, (uint32_t)(d_start - wg_pkt.diag_enqueued_us));\n            wg_diag_drain(d_start);')
    s = once(s, '        int64_t d_loop_start = esp_timer_get_time();', '        int64_t d_loop_start = esp_timer_get_time();\n        wg_diag_loop_gap(d_loop_start);')
    f.write_text(s)
    f = component / 'components/wireguard_lwip/src/wireguardif.c'
    s = f.read_text()
    begin = s.index('\tif (result != ERR_OK) {', s.index('\ndone:'))
    end = s.index('\t} else if (wg_ctrl) {', begin)
    # Replace the failure log, retain the original control-success branch.
    s = s[:begin] + '\twg_diag_peer_tx(wireguard_peer_index(device, peer), result != ERR_OK);\n\tif (result != ERR_OK) {\n\t\t/* Failure totals reported asynchronously, without endpoint/key logs. */\n' + s[end:]
    f.write_text(s)
