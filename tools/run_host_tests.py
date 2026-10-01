#!/usr/bin/env python3
"""Host regression tests of production address policy, storage and DHCP parser.
The allocator test extracts complete functions verbatim (never a Python model).
Pass --cc 'zig cc' if GCC/Clang is not installed.
"""
import argparse, os, pathlib, shlex, subprocess
root=pathlib.Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--cc',default=os.environ.get('CC','cc'));a=p.parse_args()
build=root/'tests/host/build';build.mkdir(exist_ok=True)
source=(root/'components/dhcpserver/dhcpserver.c').read_text(encoding='utf-8-sig')
def function(name):
    import re
    match=re.search(r'^(?:static )?(?:s16_t|u8_t|bool|void) '+name+r'\([^;]*?\)\s*\{',source,re.M)
    assert match,name
    start=match.start();i=match.end();depth=1
    while depth:
        if source[i]=='{':depth+=1
        if source[i]=='}':depth-=1
        i+=1
    return source[start:i]
(build/'allocator_under_test.inc').write_text('\n'.join(function(n) for n in ['parse_options','dhcps_address_valid','dhcps_address_in_use','parse_msg']),encoding='utf-8')
(build/'ack_under_test.inc').write_text(function('send_ack'),encoding='utf-8')
for name in ['bindings','allocator','arp','ack','diagnostics']:
    exe=build/(name+('.exe' if os.name=='nt' else ''))
    command=shlex.split(a.cc)+['-std=c11','-Wall','-Wextra','-Werror','-Wno-unused-but-set-variable','-Wno-misleading-indentation','-Itests/host/stubs','-Imain','-Icomponents/dhcpserver/include','-Itests/host/build',f'tests/host/test_{name}.c','main/dhcp_bindings.c','-o',str(exe)]
    subprocess.run(command,cwd=root,check=True)
    subprocess.run([str(exe)],cwd=root,check=True)
