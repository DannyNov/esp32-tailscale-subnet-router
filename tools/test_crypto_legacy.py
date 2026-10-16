"""Execute unmodified baseline hash functions with real SDK5.5.3 SHA256.
SPDX-License-Identifier: MIT
"""
import argparse, hashlib, json, os, pathlib, re, shlex, subprocess, sys
root=pathlib.Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser()
p.add_argument('--sdk',required=True,type=pathlib.Path)
p.add_argument('--cc',default=os.environ.get('CC','cc'))
a=p.parse_args()
sdk=a.sdk.resolve(); lib=sdk/'components/mbedtls/mbedtls'
out=root/'build/crypto-compat'; out.mkdir(parents=True,exist_ok=True)
assert (out/'crypto_vectors.h').exists(), 'Run test_crypto_compat.py first'
base='3a33e583d70d80f490c6b2f245638ee28ea64f84'
def original(path):
    return subprocess.check_output(['git','show',base+':'+path],cwd=root).decode()
def function(text,name):
    match=re.search(r'^static (?:void|int) '+name+r'\([^;]+?\)\s*\{',text,re.M)
    assert match,name
    pos=match.end(); depth=1
    while depth:
        depth+=(text[pos]=='{')-(text[pos]=='}');pos+=1
    return text[match.start():pos]
pw=original('components/web_password/web_password.c')
tlm=original('main/telemetry.c')
prefix='''#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "mbedtls/sha256.h"
#include "crypto_vectors.h"
#define TELEMETRY_DH_HEX_LEN 16
#define TELEMETRY_DH_FULL_LEN 18
static struct { char device_hash[19]; } s_state;
static unsigned char fixture_mac[6];
static void esp_efuse_mac_get_default(unsigned char *out) { memcpy(out,fixture_mac,6); }
'''
source=prefix+function(pw,'bytes_to_hex')+'\n'+function(pw,'compute_hash')+'\n'+function(tlm,'compute_device_hash')+'''
int main(void) {
    for (unsigned i=0;i<sizeof(password_vectors)/sizeof(password_vectors[0]);i++) {
        unsigned char salt[16],digest[32]; char fixture[98];
        for(unsigned j=0;j<16;j++) salt[j]=(unsigned char)(password_vectors[i].seed+j);
        compute_hash(salt,16,password_vectors[i].text,digest);
        bytes_to_hex(salt,16,fixture); fixture[32]=':';
        bytes_to_hex(digest,32,fixture+33);
        assert(!strcmp(fixture,password_vectors[i].fixture));
    }
    for (unsigned i=0;i<sizeof(telemetry_vectors)/sizeof(telemetry_vectors[0]);i++) {
        memcpy(fixture_mac,telemetry_vectors[i].mac,6); compute_device_hash();
        assert(!strcmp(s_state.device_hash,telemetry_vectors[i].id));
    }
    puts("PASS: unmodified baseline password and telemetry functions + real SDK5 SHA256 match every golden fixture");
}
'''
(out/'legacy-kat.c').write_text(source)
sources=[out/'legacy-kat.c',lib/'library/sha256.c',lib/'library/platform_util.c',lib/'library/platform.c']
exe=out/('legacy-kat.exe' if os.name=='nt' else 'legacy-kat')
command=[s.strip('"') for s in shlex.split(a.cc,posix=os.name!='nt')]+[
    '-O0','-g','-UNDEBUG','-std=c11','-DMBEDTLS_CONFIG_FILE="legacy_crypto_config.h"',
    '-I'+str(root/'tests/host'),'-I'+str(out),'-I'+str(lib/'include'),'-I'+str(lib/'library')]
command += [str(s) for s in sources]+['-o',str(exe)]
manifest={'baseline':base,'command':command,'source_sha256':{
    str(s.relative_to(sdk)) if s.is_relative_to(sdk) else s.name:hashlib.sha256(s.read_bytes()).hexdigest() for s in sources}}
result=subprocess.run(command,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
(out/'legacy-compile.log').write_bytes(result.stdout);manifest['compile_exit']=result.returncode
if result.returncode==0:
    result=subprocess.run([str(exe)],stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    (out/'legacy-kat.log').write_bytes(result.stdout);manifest['kat_exit']=result.returncode
(out/'legacy-manifest.json').write_text(json.dumps(manifest,indent=2))
print(result.stdout.decode(errors='replace'),end='')
sys.exit(result.returncode)
