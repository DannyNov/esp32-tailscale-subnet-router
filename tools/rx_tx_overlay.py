"""Bounded adaptive RX scheduling and measurement overlays for wgdiag3.

Applied *after* wgdiag2 to generated build copies only. Fail closed on all
source anchors. No writes to pinned external/microlink, NVS or routing.
"""
from derp_header_overlay import once

def apply(component):
    mgr = component / 'src/ml_wg_mgr.c'
    s = mgr.read_text()
    s = once(s, '        budget_start_ms = ml_get_time_ms();   /* DISCO budget window */',
             '        uint32_t wg_rx_processed_iter = 0;\n        budget_start_ms = ml_get_time_ms();   /* DISCO budget window */')
    original = '            process_wg_packet(ml, &wg_pkt);'
    if s.count(original) != 2:
        raise RuntimeError('Unexpected WG drain count')
    s = s.replace(original, original + '\n            wg_rx_processed_iter++;')
    s = once(s, '        vTaskDelay(pdMS_TO_TICKS(10));',
             '''        /* 2ms active / 10ms idle: always yield to lower-priority tasks.
         * Both 30ms/64-packet WG drains and the DISCO budget stay bounded.
         * Processed packets signal an active stream even if the queue is
         * empty at this exact instant. Never spin while a peer floods us. */
        const bool wg_rx_active = wg_rx_processed_iter > 0 ||
                                  uxQueueMessagesWaiting(ml->wg_rx_queue) > 0;
        wg_diag_wake(wg_rx_active);
        vTaskDelay(pdMS_TO_TICKS(wg_rx_active ? 2 : 10));''')
    s = once(s, 'ESP_LOGI(TAG, "WG endpoint port flip (NAT-rebind) for %s "',
             'ESP_LOGD(TAG, "WG endpoint port flip (NAT-rebind) for %s "')
    mgr.write_text(s)

    backend = component / 'components/wireguard_lwip/src/wireguardif.c'
    s = backend.read_text()
    s = once(s, '\t\t\t\txSemaphoreTake(s_wg_tx_lock, portMAX_DELAY);',
             '''\t\t\t\tint64_t d_lock_us = esp_timer_get_time();
\t\t\t\txSemaphoreTake(s_wg_tx_lock, portMAX_DELAY);
\t\t\t\twg_diag_time(D_TX_LOCK, (uint32_t)(esp_timer_get_time() - d_lock_us));''')
    s = once(s, '\t\t\t\twireguard_encrypt_packet(dst, dst, padded_len, keypair);',
             '''\t\t\t\tint64_t d_crypto_us = esp_timer_get_time();
\t\t\t\twireguard_encrypt_packet(dst, dst, padded_len, keypair);
\t\t\t\twg_diag_time(D_TX_CRYPTO, (uint32_t)(esp_timer_get_time() - d_crypto_us));''')
    s = once(s, '\t\t\t\tresult = wireguardif_peer_output(netif, pbuf, peer);',
             '''\t\t\t\tint64_t d_send_us = esp_timer_get_time();
\t\t\t\tresult = wireguardif_peer_output(netif, pbuf, peer);
\t\t\t\twg_diag_time(D_TX_SEND, (uint32_t)(esp_timer_get_time() - d_send_us));''')
    s = once(s, '\twg_diag_peer_tx(wireguard_peer_index(device, peer), result != ERR_OK);',
             '''\tunsigned d_peer = wireguard_peer_index(device, peer);
\twg_diag_peer_tx(d_peer, result != ERR_OK);
\tif (result == ERR_OK) wg_diag_peer_tx_bytes(d_peer, q ? q->tot_len : 0);''')
    backend.write_text(s)
