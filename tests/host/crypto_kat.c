/* SPDX-License-Identifier: MIT. Real PSA success paths, injected failures only. */
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "psa/crypto.h"

static int fail_at, calls, short_digest;
static bool fail_now(void) { return ++calls == fail_at; }
static psa_status_t checked_init(void)
{ return fail_now() ? PSA_ERROR_HARDWARE_FAILURE : psa_crypto_init(); }
static psa_status_t checked_setup(psa_hash_operation_t *op, psa_algorithm_t alg)
{ return fail_now() ? PSA_ERROR_HARDWARE_FAILURE : psa_hash_setup(op, alg); }
static psa_status_t checked_update(psa_hash_operation_t *op, const uint8_t *p, size_t n)
{ return fail_now() ? PSA_ERROR_HARDWARE_FAILURE : psa_hash_update(op, p, n); }
static psa_status_t checked_finish(psa_hash_operation_t *op, uint8_t *p, size_t n, size_t *len)
{
    if (fail_now()) { memset(p, 0xa5, n); return PSA_ERROR_HARDWARE_FAILURE; }
    psa_status_t status = psa_hash_finish(op, p, n, len);
    if (short_digest && status == PSA_SUCCESS) *len = 31;
    return status;
}
static psa_status_t checked_abort(psa_hash_operation_t *op)
{
    psa_status_t status = psa_hash_abort(op);
    return fail_now() ? PSA_ERROR_HARDWARE_FAILURE : status;
}
#define psa_crypto_init checked_init
#define psa_hash_setup checked_setup
#define psa_hash_update checked_update
#define psa_hash_finish checked_finish
#define psa_hash_abort checked_abort
#include "../../components/web_password/web_password.c"
#include "../../main/telemetry_hash.h"
#undef psa_crypto_init
#undef psa_hash_setup
#undef psa_hash_update
#undef psa_hash_finish
#undef psa_hash_abort

static char persisted[256], pending[256];
static int nvs_failure, writes, commits, opens, closes;
static unsigned salt_seed;
esp_err_t nvs_open(const char *ns, int mode, nvs_handle_t *h)
{
    assert(!strcmp(ns, "tsr")); (void)mode;
    if (nvs_failure == 1) return ESP_FAIL;
    *h = 1; opens++; return ESP_OK;
}
esp_err_t nvs_get_str(nvs_handle_t h, const char *key, char *out, size_t *n)
{
    assert(h == 1 && !strcmp(key,"web_password"));
    if (nvs_failure == 2 || (nvs_failure == 3 && out)) return ESP_FAIL;
    if (out) { assert(*n >= strlen(persisted)+1); strcpy(out,persisted); }
    *n = strlen(persisted)+1; return ESP_OK;
}
esp_err_t nvs_set_str(nvs_handle_t h, const char *key, const char *s)
{
    assert(h == 1 && !strcmp(key,"web_password")); writes++;
    if (nvs_failure == 4) return ESP_FAIL;
    strcpy(pending,s); return ESP_OK;
}
esp_err_t nvs_commit(nvs_handle_t h)
{
    assert(h == 1); commits++;
    if (nvs_failure == 5) return ESP_FAIL;
    strcpy(persisted,pending); return ESP_OK;
}
void nvs_close(nvs_handle_t h) { assert(h == 1); closes++; }
void esp_fill_random(void *p, size_t n)
{ for(size_t i=0;i<n;i++) ((uint8_t *)p)[i]=(uint8_t)(salt_seed+i); }

static void reset_faults(void)
{ fail_at=calls=short_digest=nvs_failure=0; }
static void expect_hex(const unsigned char *p, const char *golden)
{
    char hex[65]; bytes_to_hex(p,32,hex); assert(!strcmp(hex,golden));
}
#include "crypto_vectors.h"
int main(void)
{
    assert(psa_crypto_init() == PSA_SUCCESS);
    unsigned char digest[32];
    assert(sha256_parts("",0,NULL,0,digest) == PSA_SUCCESS);
    expect_hex(digest,"e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855");
    assert(sha256_parts("a",1,"bc",2,digest) == PSA_SUCCESS);
    expect_hex(digest,"ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad");
    for(size_t i=0;i<sizeof(password_vectors)/sizeof(password_vectors[0]);i++) {
        const struct password_vector *v=&password_vectors[i];
        reset_faults(); salt_seed=v->seed;
        assert(set_web_password_hashed(v->text) == ESP_OK);
        assert(!strcmp(persisted,v->fixture));
        assert(verify_web_password(v->text));
        assert(!verify_web_password("incorrect synthetic password"));
        /* Re-load independently generated old NVS fixture. */
        strcpy(persisted,v->fixture); assert(verify_web_password(v->text));
    }
    for(size_t i=0;i<sizeof(telemetry_vectors)/sizeof(telemetry_vectors[0]);i++) {
        char id[19]; reset_faults();
        assert(telemetry_hash_from_mac(telemetry_vectors[i].mac,id));
        assert(!strcmp(id,telemetry_vectors[i].id));
    }
    /* Every init/setup/update/finish/abort error, for both telemetry hashes. */
    for(int stage=1;stage<=6;stage++) {
        reset_faults(); strcpy(persisted,password_vectors[0].fixture);
        fail_at=stage; assert(!verify_web_password(password_vectors[0].text));
        reset_faults(); fail_at=stage; int before=writes;
        assert(set_web_password_hashed("replacement") == ESP_FAIL);
        assert(writes == before && !strcmp(persisted,password_vectors[0].fixture));
        reset_faults(); fail_at=stage; memset(digest,0xa5,32);
        assert(sha256_parts("a",1,"b",1,digest) != PSA_SUCCESS);
        for(int j=0;j<32;j++) assert(digest[j] == 0);
    }
    for(int stage=1;stage<=12;stage++) {
        char id[19]; memset(id,0xa5,sizeof(id)); reset_faults(); fail_at=stage;
        assert(!telemetry_hash_from_mac(telemetry_vectors[0].mac,id));
        for(int j=0;j<19;j++) assert(id[j] == 0);
    }
    reset_faults(); short_digest=1;
    assert(!verify_web_password(password_vectors[0].text));
    int before=writes; assert(set_web_password_hashed("replacement") == ESP_FAIL);
    assert(writes == before);
    char bad_id[19]; assert(!telemetry_hash_from_mac(telemetry_vectors[0].mac,bad_id));
    for(int j=0;j<19;j++) assert(bad_id[j] == 0);
    reset_faults(); fail_at=1;
    assert(!verify_web_password(password_vectors[0].text) && calls == 1);
    reset_faults();
    for(int i=0;i<97;i++) {
        if(i == 32) continue;
        strcpy(persisted,password_vectors[0].fixture); persisted[i]='g';
        assert(!verify_web_password(password_vectors[0].text));
    }
    const char *bad[]={"",":","00:11","+0000000000000000000000000000000:00","no colon"};
    for(size_t i=0;i<sizeof(bad)/sizeof(bad[0]);i++) {
        strcpy(persisted,bad[i]); assert(!verify_web_password("anything"));
    }
    for(int i=1;i<=3;i++) {
        reset_faults(); nvs_failure=i;
        assert(!verify_web_password(password_vectors[0].text));
    }
    for(int i=1;i<=5;i++) {
        if(i==2 || i==3) continue;
        reset_faults(); nvs_failure=i; strcpy(persisted,password_vectors[0].fixture);
        assert(set_web_password_hashed("replacement") == ESP_FAIL);
        assert(!strcmp(persisted,password_vectors[0].fixture));
    }
    reset_faults(); assert(!verify_web_password(NULL));
    assert(set_web_password_hashed(NULL) == ESP_ERR_INVALID_ARG);
    strcpy(persisted,empty_password_fixture);
    assert(verify_web_password("")); /* Preserve old verify semantics for such fixtures. */
    strcpy(persisted,password_vectors[0].fixture);
    for(char *p=persisted;*p;p++) if(*p>='a' && *p<='f') *p-=32;
    assert(verify_web_password(password_vectors[0].text));
    assert(set_web_password_hashed("") == ESP_OK && persisted[0] == 0);
    assert(!is_web_password_set() && !verify_web_password(""));
    assert(opens == closes);
    printf("PASS: real TF-PSA SHA256 vectors, %zu password/NVS and %zu telemetry/checksum fixtures; all PSA stage failures, length/hex/NVS/null/empty negatives\n",
           sizeof(password_vectors)/sizeof(password_vectors[0]), sizeof(telemetry_vectors)/sizeof(telemetry_vectors[0]));
    return 0;
}
