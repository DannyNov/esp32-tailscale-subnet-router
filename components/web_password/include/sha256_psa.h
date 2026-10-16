/* SPDX-License-Identifier: MIT */
#pragma once
#include <string.h>
#include "psa/crypto.h"

static inline void crypto_wipe(void *buffer, size_t length)
{
    volatile unsigned char *p = buffer;
    while (length--) *p++ = 0;
}

/* IDF 6.1 initializes PSA at startup (SECONDARY/core0 priority 104).
 * Repeated init after success is guaranteed to succeed by the PSA contract.
 * Never free the global PSA service from a caller's local cleanup. */
static inline psa_status_t sha256_parts(const void *a, size_t a_len,
                                      const void *b, size_t b_len,
                                      unsigned char output[32])
{
    psa_hash_operation_t operation = PSA_HASH_OPERATION_INIT;
    unsigned char digest[32] = {0};
    size_t length = 0;
    psa_status_t status = psa_crypto_init();
    if (status != PSA_SUCCESS) {
        crypto_wipe(output, 32);
        return status; /* No other PSA calls after failed initialization. */
    }
    if (status == PSA_SUCCESS)
        status = psa_hash_setup(&operation, PSA_ALG_SHA_256);
    if (status == PSA_SUCCESS)
        status = psa_hash_update(&operation, a, a_len);
    if (status == PSA_SUCCESS && b_len)
        status = psa_hash_update(&operation, b, b_len);
    if (status == PSA_SUCCESS)
        status = psa_hash_finish(&operation, digest, sizeof(digest), &length);
    if (status == PSA_SUCCESS && length != sizeof(digest))
        status = PSA_ERROR_CORRUPTION_DETECTED;
    psa_status_t cleanup = psa_hash_abort(&operation);
    if (status == PSA_SUCCESS) status = cleanup;
    if (status == PSA_SUCCESS) memcpy(output, digest, sizeof(digest));
    else crypto_wipe(output, 32);
    crypto_wipe(digest, sizeof(digest));
    return status;
}
