"""wgopt3: source contracts and compiled, independent/reference AEAD vectors.

Requires libmbedtls-dev (CI installs it). Compiles *generated copy* of the
exact ESP-IDF mbedTLS WG-data wrapper and upstream refc implementation.
Reference known-answer ciphertext/tag was independently generated with the
Python cryptography library (ChaCha20Poly1305), WireGuard 0||LE64 nonce.
"""
from pathlib import Path
from tempfile import TemporaryDirectory
from prepare_wg_diagnostics import prepare
import subprocess
import shutil

with TemporaryDirectory(prefix="wgopt3-") as tmp:
    out = Path(tmp)
    prepare(out)
    b = out / "microlink/components/wireguard_lwip"
    wgif = (b / "src/wireguardif.c").read_text()
    wireguard = (b / "src/wireguard.c").read_text()
    cmake = (b / "CMakeLists.txt").read_text()
    fast = (b / "src/wgopt3_crypto.c").read_text()
    assert "mbedtls_chachapoly_encrypt_and_tag" in fast
    assert "mbedtls_chachapoly_auth_decrypt" in fast
    assert "MBEDTLS_CHACHAPOLY_C" in fast
    assert '"src/wgopt3_crypto.c"' in cmake and "        mbedtls" in cmake
    assert "wireguard_encrypt_packet(dst, dst, padded_len, keypair);" not in wgif
    assert "bool wgopt3_ok = wgopt3_encrypt_data" in wgif
    assert "if (wgopt3_ok) keypair->sending_counter++;" in wgif
    assert "if (!wgopt3_ok)" in wgif and "return ERR_VAL;" in wgif
    assert "if (!wgopt3_decrypt_data(dst, src, src_len, counter, keypair->receiving_key)) return false;" in wireguard
    assert "wireguard_check_replay(keypair, counter)" in wireguard
    assert "if (!accepted) wg_diag_add(diag_path, D_REPLAY, 1);" in wireguard
    assert "bool wgopt3_ok" in wgif and "xSemaphoreGive(s_wg_tx_lock);" in wgif
    assert wireguard.count("wgopt3_decrypt_data(") == 1
    assert "wireguard_aead_encrypt(dst, src, src_len, NULL, 0, keypair->sending_counter" in wireguard

    c = r"""
#include <stdint.h>
#include <stdio.h>
#include <stdbool.h>
#include <stdlib.h>
#include <string.h>
#include "wgopt3_crypto.h"
#include "crypto/refc/chacha20poly1305.h"
static unsigned checks;
static void verify(const unsigned n, const uint64_t ctr) {
    uint8_t key[32], original[1500], a[1516], b[1516], dec[1516];
    for(unsigned i=0;i<32;i++) key[i] = (uint8_t)(i*17+3);
    for(unsigned i=0;i<n;i++) original[i] = (uint8_t)(i*113u+7u);
    memcpy(a,original,n); memcpy(b,original,n);
    chacha20poly1305_encrypt(b,b,n,NULL,0,ctr,key);
    if(!wgopt3_encrypt_data(a,n,ctr,key) ||
       memcmp(a,b,n+16) != 0) abort();
    if(!wgopt3_decrypt_data(dec,a,n+16,ctr,key) ||
       memcmp(dec,original,n) != 0) abort();
    /* Rejected corrupt tags must not decrypt successfully. */
    a[n+15] ^= 0x40;
    if(wgopt3_decrypt_data(dec,a,n+16,ctr,key)) abort();
    a[n+15] ^= 0x40;
    if(!wgopt3_decrypt_data(a,a,n+16,ctr,key) ||
       memcmp(a,original,n)!=0) abort();
    checks++;
}
static void independent_vector(void) {
    uint8_t key[32], data[128] = "WGOPT3-wireguard-data-interop";
    const uint8_t expected[45] = {
      0xa7,0x0e,0xe2,0xb4,0xff,0x0a,0xc7,0x6f,0x0d,0xd9,0x4f,
      0xab,0x06,0x19,0x13,0xdc,0xcd,0x62,0x93,0xb0,0xe9,0x69,
      0x2c,0xf0,0x23,0x50,0xd5,0x32,0x99,0xec,0xf4,0x49,0x45,
      0xd1,0x12,0x84,0xe0,0x63,0x48,0x59,0x46,0x08,0xc9,0xfb,0x2b
    };
    for(unsigned i=0;i<32;i++) key[i] = (uint8_t)i;
    const size_t n = strlen((char *)data);
    if(n!=29 || !wgopt3_encrypt_data(data,n,0x0102030405060708ULL,key) ||
       memcmp(data,expected,sizeof(expected))!=0) abort();
    checks++;
}
int main(void) {
    const unsigned lengths[] = {0,1,2,15,16,17,31,32,63,64,65,127,128,129,255,256,1279,1408,1420};
    const uint64_t ctrs[] = {0,1,0x0102030405060708ULL,0xffffffffULL,0xFFFFFFFFFFFFFFFFULL};
    independent_vector();
    for(unsigned j=0;j<sizeof(ctrs)/sizeof(ctrs[0]);j++)
      for(unsigned i=0;i<sizeof(lengths)/sizeof(lengths[0]);i++)
        verify(lengths[i],ctrs[j]);
    if(wgopt3_decrypt_data(NULL,NULL,0,0,NULL)) abort();
    printf("PASS: %u wgopt3 AEAD vectors (independent KAT, reference parity, malformed tags, in-place, zero-length, 1420-byte)\n",checks);
    return 0;
}
"""
    cfile = out / "wgopt3_host.c"
    binary = out / "wgopt3_host"
    cfile.write_text(c)
    cmd = [
        shutil.which("cc") or "cc","-std=c11","-O2",
        "-I"+str(b / "src"),"-I"+str(b / "src/crypto/refc"),
        str(cfile),
        str(b / "src/wgopt3_crypto.c"),
        str(b / "src/crypto/refc/chacha20poly1305.c"),
        str(b / "src/crypto/refc/chacha20.c"),
        str(b / "src/crypto/refc/poly1305-donna.c"),
        str(b / "src/crypto.c"),
        "-lmbedcrypto","-o",str(binary),
    ]
    subprocess.run(cmd,check=True)
    subprocess.run([str(binary)],check=True)

print("PASS: wgopt3 build-copy cryptographic contract and host vectors")
