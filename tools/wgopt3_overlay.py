"""wgopt3: alternative authenticated ChaCha20-Poly1305 backend for WG data only.

Build-copy overlay after wgopt2. Handshake and XChaCha use untouched refc.
For data: mbedTLS ChaChaPoly encrypts/validates per packet. A nonce is the
WireGuard 96-bit encoding 0x00000000 || LE64(counter). On ANY TX error:
no packet output and NO sending-counter advancement. Replay is still checked
only AFTER AEAD authentication, inside original wireguard.c. CMake requires
mbedtls and fails closed without the configured ChaChaPoly implementation.
"""
from derp_header_overlay import once


HEADER = """#pragma once
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

/* Packet data only; 16 bytes of tag space MUST exist after len on encrypt.
 * Both operations are synchronous. Validated auth-decrypt is fail-closed. */
bool wgopt3_encrypt_data(uint8_t *data, size_t len, uint64_t counter,
                         const uint8_t key[32]);
bool wgopt3_decrypt_data(uint8_t *dst, const uint8_t *src, size_t len_with_tag,
                         uint64_t counter, const uint8_t key[32]);
"""

SOURCE = """/* WireGuard data-packet AEAD using ESP-IDF's tested mbedTLS implementation.
 * Original reference ChaCha20-Poly1305 is retained for handshakes and as an
 * upstream reference for host known-answer tests. */
#include "wgopt3_crypto.h"
#include "mbedtls/chachapoly.h"
#include <string.h>

#if !defined(MBEDTLS_CHACHAPOLY_C)
#error "wgopt3 requires MBEDTLS_CHACHAPOLY_C in the ESP-IDF mbedTLS configuration"
#endif

static void wgopt3_nonce(uint8_t iv[12], uint64_t counter) {
    memset(iv, 0, 4);
    for (unsigned n = 0; n < 8; ++n) {
        iv[4 + n] = (uint8_t)(counter >> (8 * n));
    }
}

bool wgopt3_encrypt_data(uint8_t *data, size_t len, uint64_t counter,
                         const uint8_t key[32]) {
    if (!data || !key || len > (size_t)(UINT32_MAX - 16)) return false;
    uint8_t iv[12];
    wgopt3_nonce(iv, counter);
    mbedtls_chachapoly_context c;
    mbedtls_chachapoly_init(&c);
    int rc = mbedtls_chachapoly_setkey(&c, key);
    if (rc == 0) {
        /* Overlapping input == output is supported by MbedTLS.
         * WireGuard already allocated 16 tag bytes after len. */
        rc = mbedtls_chachapoly_encrypt_and_tag(&c, len, iv, NULL, 0,
                                                data, data, data + len);
    }
    mbedtls_chachapoly_free(&c);
    return rc == 0;
}

bool wgopt3_decrypt_data(uint8_t *dst, const uint8_t *src, size_t len_with_tag,
                         uint64_t counter, const uint8_t key[32]) {
    if (!src || !key || len_with_tag < 16 || (len_with_tag > 16 && !dst))
        return false;
    size_t ctlen = len_with_tag - 16;
    uint8_t iv[12];
    wgopt3_nonce(iv, counter);
    mbedtls_chachapoly_context c;
    mbedtls_chachapoly_init(&c);
    int rc = mbedtls_chachapoly_setkey(&c, key);
    if (rc == 0) {
        /* auth_decrypt performs constant-time tag validation and returns
         * failure on mismatches. Never consume or route unauthenticated data. */
        rc = mbedtls_chachapoly_auth_decrypt(&c, ctlen, iv, NULL, 0,
                                            src + ctlen, src, dst);
    }
    mbedtls_chachapoly_free(&c);
    return rc == 0;
}
"""


def apply(component):
    backend = component / "components/wireguard_lwip"
    (backend / "src/wgopt3_crypto.h").write_text(HEADER)
    (backend / "src/wgopt3_crypto.c").write_text(SOURCE)

    cm = backend / "CMakeLists.txt"
    s = cm.read_text()
    s = once(s, '        "src/wg_diag.c"', '        "src/wg_diag.c"\n        "src/wgopt3_crypto.c"')
    s = once(s, "        esp_timer\n)", "        esp_timer\n        mbedtls\n)")
    cm.write_text(s)

    wgif = backend / "src/wireguardif.c"
    s = wgif.read_text()
    s = once(s, '#include "wg_diag.h"', '#include "wg_diag.h"\n#include "wgopt3_crypto.h"')
    # The output stage is already timed by rx_tx_overlay. Preserve the
    # measurement and original tx mutex; fail-closed if AEAD fails.
    anchor = '\t\t\t\twireguard_encrypt_packet(dst, dst, padded_len, keypair);'
    s = once(s, anchor,
        """                /* wgopt3: exact WG transport AEAD, unchanged monotonic
                 * counter. Do not advance counter or send on cipher error. */
                bool wgopt3_ok = wgopt3_encrypt_data(dst, padded_len,
                                    keypair->sending_counter, keypair->sending_key);
                if (wgopt3_ok) keypair->sending_counter++;""")
    s = once(s, '\t\t\t\txSemaphoreGive(s_wg_tx_lock);',
        """                xSemaphoreGive(s_wg_tx_lock);
                if (!wgopt3_ok) {
                    pbuf_free(pbuf);
                    return ERR_VAL;
                }""")
    wgif.write_text(s)

    wg = backend / "src/wireguard.c"
    s = wg.read_text()
    s = once(s, '#include "wg_diag.h"', '#include "wg_diag.h"\n#include "wgopt3_crypto.h"')
    s = once(s,
        'if (!wireguard_aead_decrypt(dst, src, src_len, NULL, 0, counter, keypair->receiving_key)) return false;',
        'if (!wgopt3_decrypt_data(dst, src, src_len, counter, keypair->receiving_key)) return false;')
    wg.write_text(s)
