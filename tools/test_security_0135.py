"""Execute extracted upstream security code with host mocks; no hardware."""
import argparse
import os
from pathlib import Path
import re
import shlex
import subprocess
from prepare_wg_diagnostics import ROOT, prepare

p = argparse.ArgumentParser()
p.add_argument('--cc', default='cc')
a = p.parse_args()
out = ROOT / 'build/security-0135'
prepare(out)
src = out / 'microlink'
wg = (src / 'components/wireguard_lwip/src/wireguard.c').read_text()
wif = (src / 'components/wireguard_lwip/src/wireguardif.c').read_text()
coord = (src / 'src/ml_coord.c').read_text()
derp = (src / 'src/ml_derp.c').read_text()

def function(text, name):
    m = re.search(r'^(?:static )?(?:bool|void|int) ' + name + r'\([^;]*?\)\s*\{', text, re.M)
    assert m, name
    i = m.end(); depth = 1
    while depth:
        depth += (text[i] == '{') - (text[i] == '}'); i += 1
    return text[m.start():i]

# TLS setup/handshake remains byte-identical to the pinned upstream: the
# fragmented-header overlay is confined to BIO/data reads, not verification.
original = (ROOT / 'external/microlink/components/microlink/src/ml_derp.c').read_text()
start = '    bool verify_tls ='
stop = '    /* Store socket fd'
assert derp[derp.index(start):derp.index(stop)] == original[original.index(start):original.index(stop)]
assert 'MBEDTLS_SSL_VERIFY_REQUIRED' in derp and 'esp_crt_bundle_attach' in derp
assert 'mbedtls_ssl_set_hostname(&ml->derp.ssl, tls_name)' in derp
for name in ('ml_coord.c', 'ml_netcheck.c'):
    assert (src / 'src' / name).read_bytes() == (ROOT / 'external/microlink/components/microlink/src' / name).read_bytes()
# wgopt7 adds only queue geometry reporting in generated microlink.c.
# Strip the two exact probes, then require byte-for-byte upstream identity.
generated_init = (src / 'src/microlink.c').read_text(encoding='utf-8')
assert generated_init.startswith('#include "wg_diag.h"\n')
generated_init = generated_init.removeprefix('#include "wg_diag.h"\n')
probe = '    wg_diag_queue_config(ML_WG_RX_QUEUE_DEPTH, sizeof(ml_rx_packet_t));\n'
assert generated_init.count(probe) == 1
generated_init = generated_init.replace(probe, '')
# Exact reviewed checked-destroy overlay output as UTF-8 with universal newlines.
# Do not hash a locale-dependent Windows cp1251 decoding of the same bytes.
# No other C changes are allowed.
import hashlib
assert hashlib.sha256(generated_init.encode('utf-8')).hexdigest() == '6e191802cc92773623624cee576183472e8a4fd1f93ee9286db1a96bfdc241aa'
assert 'body_len < 512 ? 512 : body_len' in coord
assert 'GOAWAY' in coord and 'RST_STREAM' in coord and 'END_STREAM' in coord
assert 'wireguard_expire_keys(peer)' in wif

prefix = '''#include <assert.h>
#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
#include <limits.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#define ESP_LOGI(...) ((void)0)
#define ESP_LOGW(...) ((void)0)
#define ESP_LOGE(...) ((void)0)
#define pdMS_TO_TICKS(x) (x)
#define vTaskDelay(x) ((void)(x))
#define WIREGUARD_AUTHTAG_LEN 16
#define REJECT_AFTER_MESSAGES (UINT64_MAX - 8192)
#define D_REPLAY 13
struct wireguard_keypair { uint64_t replay_counter, sending_counter; uint32_t replay_bitmap; uint8_t receiving_key[32], sending_key[32]; };
static unsigned replays[2], auth_calls;
static bool authenticated = true;
static void wg_diag_add(unsigned path, unsigned metric, unsigned value) { assert(path < 2 && metric == D_REPLAY); replays[path] += value; }
static bool wireguard_aead_decrypt(uint8_t *d, const uint8_t *s, size_t n, void *ad, size_t al, uint64_t c, uint8_t *k) { (void)d;(void)s;(void)n;(void)ad;(void)al;(void)c;(void)k; auth_calls++; return authenticated; }
'''
replay = prefix + function(wg, 'wireguard_check_replay') + '\n' + function(wg, 'wireguard_decrypt_packet_diag') + '''
int main(void) {
 struct wireguard_keypair k={0}; uint8_t data[32]={0};
 assert(wireguard_decrypt_packet_diag(data,data,16,0,&k,0));
 assert(!wireguard_decrypt_packet_diag(data,data,16,0,&k,0)); assert(replays[0]==1);
 uint64_t saved=k.replay_counter; authenticated=false;
 assert(!wireguard_decrypt_packet_diag(data,data,16,100,&k,1)); assert(k.replay_counter==saved && replays[1]==0);
 authenticated=true; unsigned calls=auth_calls;
 assert(!wireguard_decrypt_packet_diag(data,data,15,100,&k,1));
 assert(!wireguard_decrypt_packet_diag(data,data,16,REJECT_AFTER_MESSAGES,&k,1)); assert(auth_calls==calls);
 assert(wireguard_decrypt_packet_diag(data,data,16,UINT64_C(1)<<32,&k,1));
 assert(!wireguard_decrypt_packet_diag(data,data,16,0,&k,1)); assert(replays[1]==1);
 assert(wireguard_decrypt_packet_diag(data,data,16,(UINT64_C(1)<<32)-1,&k,1));
 assert(!wireguard_decrypt_packet_diag(data,data,16,(UINT64_C(1)<<32)-1,&k,1));
 assert(!wireguard_decrypt_packet_diag(data,data,16,(UINT64_C(1)<<32)-32,&k,1));
 return 0;
}
'''
noise_start = coord.index('    /* Parse 3-byte Noise frame header */')
noise_stop = coord.index('    /* Read remaining msg2 payload', noise_start)
allocation = re.search(r'body_buf = ml_psram_malloc\((body_len < 512.*)\);', coord)[1]
noise = '''#include <assert.h>
#include <stdint.h>
#include <stdlib.h>
#define ESP_LOGI(...) ((void)0)
#define ESP_LOGE(...) ((void)0)
static int validate(uint8_t *body_buf) {
''' + coord[noise_start:noise_stop] + '''return msg2_total; }
int main(void) {
 for (unsigned n=0; n<=65535; n++) {
  uint8_t *b=malloc(3); b[0]=2;b[1]=n>>8;b[2]=n;
  int r=validate(b); assert(r==(n==48?51:-1)); if(n==48) free(b);
 }
 for(int body_len=0;body_len<3;body_len++){ size_t size=ALLOCATION; assert(size>=3); uint8_t *b=malloc(size); b[0]=2;b[1]=0;b[2]=48;assert(validate(b)==51);free(b); }
 uint8_t *b=malloc(3);b[0]=4;b[1]=0;b[2]=48;assert(validate(b)==-1);
 return 0;
}
'''
noise = noise.replace('ALLOCATION', allocation)
recv = '''#include <assert.h>
#include <stdint.h>
#include <stddef.h>
#include <errno.h>
#define ESP_LOGW(...) ((void)0)
#define ESP_LOGE(...) ((void)0)
#define pdMS_TO_TICKS(x) (x)
#define vTaskDelay(x) ((void)(x))
typedef int microlink_t;
static int mode,calls;
static int ml_conn_read(microlink_t *ml,uint8_t *b,size_t n) { (void)ml;(void)b;(void)n; calls++; if(mode==0)return 0;if(mode==1){errno=EAGAIN;return -1;}if(mode==2&&calls==1)return 1;if(mode==2){errno=EAGAIN;return -1;}return (int)n; }
''' + function(coord, 'coord_recv') + '''
int main(void) { microlink_t ml=0;uint8_t b[3];errno=EAGAIN;assert(coord_recv(&ml,b,3)==-1);assert(errno==ENOTCONN && calls==1);mode=1;calls=0;assert(coord_recv(&ml,b,3)==-1 && calls==1);mode=2;calls=0;assert(coord_recv(&ml,b,3)==-1 && calls==302);mode=3;assert(coord_recv(&ml,b,3)==0);return 0; }
'''
# Execute the exact send-counter/encryption critical section. Linux CI also
# runs two concurrent senders with pthread mutex mocks; local Windows checks
# the same section serially, with lock assertions on nonce and encryption.
lock_start = wif.index('\t\t\t\tif (!s_wg_tx_lock)')
lock_end = wif.index('xSemaphoreGive(s_wg_tx_lock);', lock_start) + len('xSemaphoreGive(s_wg_tx_lock);')
encrypt = function(wg, 'wireguard_encrypt_packet')
nonce = '''#include <assert.h>
#include <stdint.h>
#include <stddef.h>
#include <string.h>
/* wgdiag3 timings are observational; host nonce test mocks them. */
#define D_TX_LOCK 7
#define D_TX_CRYPTO 8
#define D_TX_COPY 10
static int64_t esp_timer_get_time(void) { return 1234; }
static void wg_diag_time(unsigned t, uint32_t us) { (void)t; (void)us; }
#ifdef CONCURRENT
#include <pthread.h>
typedef pthread_mutex_t StaticSemaphore_t;
static StaticSemaphore_t s_wg_tx_lock_buf=PTHREAD_MUTEX_INITIALIZER;
#else
typedef int StaticSemaphore_t;
static StaticSemaphore_t s_wg_tx_lock_buf;
#endif
static StaticSemaphore_t *s_wg_tx_lock=&s_wg_tx_lock_buf;
static unsigned locked;
static StaticSemaphore_t *xSemaphoreCreateMutexStatic(StaticSemaphore_t *p){return p;}
static void xSemaphoreTake(StaticSemaphore_t *p,int wait){(void)wait;
#ifdef CONCURRENT
 pthread_mutex_lock(p);
#else
 (void)p;
#endif
 assert(!locked);locked=1;}
static void xSemaphoreGive(StaticSemaphore_t *p){assert(locked);locked=0;
#ifdef CONCURRENT
 pthread_mutex_unlock(p);
#else
 (void)p;
#endif
}
#define portMAX_DELAY 0
struct wireguard_keypair {uint64_t sending_counter;uint8_t sending_key[32];};
static struct wireguard_keypair key;
static unsigned seen[20000];
static void wireguard_aead_encrypt(uint8_t *d,const uint8_t *s,size_t n,void *ad,size_t al,uint64_t counter,uint8_t *k){(void)d;(void)s;(void)n;(void)ad;(void)al;(void)k;assert(locked && counter<20000);assert(seen[counter]++==0);}
static void U64TO8_LITTLE(uint8_t *p,uint64_t n){assert(locked);memcpy(p,&n,8);}
static void pbuf_copy_partial(void *q,uint8_t *d,size_t n,int offset){(void)q;(void)d;(void)n;(void)offset;}
''' + encrypt + '''
static void *send_packets(void *ignored) {
 (void)ignored;struct {uint8_t counter[8],enc_packet[16];} h,*hdr=&h;
 struct wireguard_keypair *keypair=&key;uint8_t *dst;size_t padded_len=0,unpadded_len=0;void *q=NULL;
 for(unsigned i=0;i<10000;i++) {
''' + wif[lock_start:lock_end] + '''
 } return NULL;
}
int main(void) {
#ifdef CONCURRENT
 pthread_t a,b;assert(!pthread_create(&a,NULL,send_packets,NULL));assert(!pthread_create(&b,NULL,send_packets,NULL));pthread_join(a,NULL);pthread_join(b,NULL);
#else
 send_packets(NULL);send_packets(NULL);
#endif
 assert(key.sending_counter==20000);for(unsigned i=0;i<20000;i++)assert(seen[i]==1);return 0;
}
'''
def braced(marker):
    start = coord.index(marker, coord.index('H2 END_STREAM on the long-poll'))
    begin = coord.index('{', start); i = begin + 1; depth = 1
    while depth:
        depth += (coord[i] == '{') - (coord[i] == '}'); i += 1
    return coord[start:i]

goaway = braced('if (f_type == 0x07)')
rst = braced('if (f_type == 0x03 && f_stream == 5)')
end_start = coord.rfind('if (f_flags & 0x01)', 0, coord.index('H2 END_STREAM on the long-poll'))
end_end = coord.index('\n                }', end_start) + len('\n                }')
end_stream = coord[end_start:end_end]
data_guard = re.search(r'if \(f_type == 0x00\)', coord[coord.index('if (pos + (int)f_len > frame_len)'):])[0]
h2 = '''#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#define TAG "test"
#define ESP_LOGW(tag, ...) ((void)(tag), (void)snprintf(log_buf,sizeof(log_buf),__VA_ARGS__))
static bool check(unsigned f_type,unsigned f_stream,unsigned f_flags,unsigned f_len) {
 char log_buf[256];uint8_t frame_buf[8]={0};unsigned pos=0;bool proto_err=false;
''' + goaway + ' else ' + rst + '\n' + data_guard + ' { if (f_stream==5) {\n' + end_stream + '''
 }
 } return proto_err;
}
int main(void) {
 for(unsigned len=0;len<=8;len++){assert(check(7,0,0,len));assert(check(3,5,0,len));assert(!check(3,7,0,len));}
 assert(check(0,5,1,0));assert(!check(0,5,0,0));assert(!check(0,7,1,0));return 0;
}
'''
for name, text in [('replay', replay), ('noise', noise), ('coord_recv', recv), ('nonce', nonce), ('h2', h2)]:
    c = out / (name + '.c'); c.write_text(text)
    exe = out / (name + ('.exe' if os.name == 'nt' else ''))
    flags = ['-DCONCURRENT', '-pthread'] if name == 'nonce' and os.name != 'nt' else []
    subprocess.run(shlex.split(a.cc) + ['-std=c11', '-Wall', '-Wextra', '-Werror'] + flags + [str(c), '-o', str(exe)], check=True)
    subprocess.run([str(exe)], check=True)
    print('PASS: extracted ' + name)
print('PASS: TLS verification retained; untouched coordinator/netcheck; all 65536 Noise lengths; authenticated replay and 64-bit jump; EOF/stale errno; 20000 nonce uniqueness')
