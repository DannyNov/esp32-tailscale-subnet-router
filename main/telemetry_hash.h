/* SPDX-License-Identifier: MIT */
#pragma once
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include "sha256_psa.h"

/* Same bytes as wgopt13: MAC || salt, then check_salt || lowercase hex ID.
 * Publish the complete 18-character ID only after both hashes succeed. */
static inline bool telemetry_hash_from_mac(const uint8_t mac[6], char out[19])
{
    static const char salt[] = "esp32-tailscale-router-v1";
    static const char check_salt[] = "esp32-tailscale-v1";
    uint8_t digest[32] = {0};
    char id[19] = {0};
    bool ok = false;
    if (sha256_parts(mac, 6, salt, sizeof(salt) - 1, digest) != PSA_SUCCESS)
        goto cleanup;
    for (int i = 0; i < 8; i++) snprintf(id + i * 2, 3, "%02x", digest[i]);
    if (sha256_parts(check_salt, sizeof(check_salt) - 1, id, 16, digest) != PSA_SUCCESS)
        goto cleanup;
    snprintf(id + 16, 3, "%02x", digest[0]);
    memcpy(out, id, sizeof(id));
    ok = true;
cleanup:
    if (!ok) crypto_wipe(out, 19);
    crypto_wipe(id, sizeof(id));
    crypto_wipe(digest, sizeof(digest));
    return ok;
}
