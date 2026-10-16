/* Host-only SHA KAT configuration; target SDK configuration is unchanged.
 * SPDX-License-Identifier: MIT */
#define MBEDTLS_PSA_CRYPTO_C
#define PSA_WANT_ALG_SHA_256 1
#define MBEDTLS_HMAC_DRBG_C
#define MBEDTLS_PSA_BUILTIN_GET_ENTROPY
#define MBEDTLS_PLATFORM_C
#define MBEDTLS_MD_C
#define PSA_WANT_ALG_HMAC 1
