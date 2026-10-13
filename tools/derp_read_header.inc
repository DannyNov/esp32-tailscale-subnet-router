/* Included by ml_derp.c and by the host regression harness.
 * A partial DERP header belongs to this connection until complete or fatal.
 * Idle WANT returns immediately; after the first byte use an absolute deadline.
 */
static int derp_poll_header(microlink_t *ml, uint8_t header[5]) {
    size_t received = 0;
    uint64_t start = 0;
    while (received < 5) {
        if (!ml->derp.connected || ml->derp.sockfd < 0) return -1;
        if (received && ml_get_time_ms() - start >= 5000) return -1;
        int n = mbedtls_ssl_read(&ml->derp.ssl, header + received, 5 - received);
        if (n == MBEDTLS_ERR_SSL_WANT_READ || n == MBEDTLS_ERR_SSL_WANT_WRITE) {
            if (!received) return 0;
            /* At least one tick even with a coarse FreeRTOS tick period. */
            vTaskDelay(1);
            continue;
        }
        /* EOF is fatal, never the poller's idle result. TIMEOUT is fatal too:
         * socket EAGAIN is mapped to WANT_READ by our BIO instead. */
        if (n <= 0) return n == 0 ? -1 : n;
        if ((size_t)n > 5 - received) return -1;
        if (!received) start = ml_get_time_ms();
        received += (size_t)n;
    }
    return 1;
}
