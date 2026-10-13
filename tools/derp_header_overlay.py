"""Preserve tested derphdr1 build overlay; no upstream writes."""
from pathlib import Path

def once(s, old, new):
    if s.count(old) != 1: raise RuntimeError("DERP anchor mismatch: " + old[:90])
    return s.replace(old, new, 1)

def apply(original):
    s = once(original, 'return MBEDTLS_ERR_SSL_TIMEOUT;',
             '''/* Retry transport waits only in the established data phase.
             * Keep handshake timeout terminal: its WANT loop has no deadline. */
            return timeout == 20 ? MBEDTLS_ERR_SSL_WANT_READ : MBEDTLS_ERR_SSL_TIMEOUT;''')
    s = once(s, 'Returns bytes read, or MBEDTLS_ERR_SSL_TIMEOUT, MBEDTLS_ERR_SSL_WANT_READ.',
             'Returns bytes read, WANT_READ for transport wait, or a fatal network error.')
    start = s.index('    /* Read 5-byte frame header.', s.index('static int poll_derp_read'))
    end = s.index('    uint8_t frame_type', start)
    s = s[:start] + '''    uint8_t header[5];
    int n = derp_poll_header(ml, header);
    if (n <= 0) return n;

''' + s[end:]
    s = once(s, 'static int poll_derp_read(microlink_t *ml) {',
             (Path(__file__).with_name('derp_read_header.inc')).read_text() + '\nstatic int poll_derp_read(microlink_t *ml) {')
    s = once(s, '(header[1] << 24) | (header[2] << 16) | (header[3] << 8)',
             '((uint32_t)header[1] << 24) | ((uint32_t)header[2] << 16) | ((uint32_t)header[3] << 8)')
    # EOF in the payload must also request reconnect, not masquerade as idle.
    s = once(s, '            free(buf);\n            return n;', '            free(buf);\n            return n == 0 ? -1 : n;')
    s = once(s, '    while (total_read < len) {', '''    while (total_read < len) {
        if (!ml->derp.connected || ml->derp.sockfd < 0) {
            free(buf);
            return -1;
        }''')
    # Actual TLS TIMEOUT is terminal; only transport WANT is retryable.
    begin = s.index('static int derp_tls_read_all(')
    end = s.index('\n/**', begin)
    read_all = s[begin:end].replace(' ||\n                ret == MBEDTLS_ERR_SSL_TIMEOUT', '')
    s = s[:begin] + read_all + s[end:]
    s = s.replace(' ||\n            n == MBEDTLS_ERR_SSL_TIMEOUT', '')
    s = s.replace('vTaskDelay(pdMS_TO_TICKS(5));', 'vTaskDelay(pdMS_TO_TICKS(5) ? pdMS_TO_TICKS(5) : 1);')
    s = s.replace('Uses mbedtls recv_timeout (100ms)', 'Uses mbedtls recv_timeout (20ms)')
    s = s.replace('0 = timeout (no data)', '0 = idle WANT (no header byte consumed)')
    return s
