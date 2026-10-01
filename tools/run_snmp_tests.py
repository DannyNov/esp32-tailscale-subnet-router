#!/usr/bin/env python3
"""Execute upstream BER/PDU and netif hook code verbatim with host fixtures."""
import argparse
import os
from pathlib import Path
import re
import shlex
import subprocess

root = Path(__file__).resolve().parents[1]
source = (root / 'components/snmp_agent/snmp_agent.c').read_text()
p = argparse.ArgumentParser()
p.add_argument('--cc', default=os.environ.get('CC', 'cc'))
args = p.parse_args()
build = root / 'tests/host/build'
build.mkdir(exist_ok=True)

def function(name):
    match = re.search(r'^static [^\n]+\b' + name + r'\([^;]*?\)\s*\{', source, re.M)
    assert match, name
    end = match.end()
    depth = 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[match.start():end]

defines = '\n'.join(re.findall(r'^#define (?:PKT_BUF|MAX_OID|VBL_BUF|PDU_BODY_BUF|VB_BUF|COMM_TLV_BUF)\s+\d+.*$', source, re.M))
buffers = source[source.index('typedef struct {\n    uint8_t rx['):source.index('} snmp_buffers_t;') + len('} snmp_buffers_t;')]
types = source[source.index('typedef struct { uint32_t arc['):source.index('/* --- system group --- */')]
codec = source[source.index('static int ber_put_len('):source.index('/* OID table (lexicographic order)')]
# The trailing section divider is an open comment at this slice boundary.
codec = codec[:codec.rfind('/* ------------------------------------------------------------------ */')]
fixture = (root / 'tests/host/test_snmp.inc').read_text()
generated = '\n'.join([
    '#define _POSIX_C_SOURCE 200809L\n#include <stdint.h>\n#include <stdbool.h>\n#include <string.h>\n#include <assert.h>\n#include <stdio.h>',
    defines, buffers, types, codec,
    'static char test_value[256] = "router";\nstatic val_t value(void) { return (val_t){.s=test_value}; }\n'
    'static const mib_row_t s_mib[] = {\n'
    ' {{{1,3,6,1,2,1,1,1,0},9}, VT_STRING, value},\n'
    ' {{{1,3,6,1,2,1,1,5,0},9}, VT_STRING, value}\n};\n#define MIB_LEN 2',
    '\n'.join(function(n) for n in ['oid_cmp', 'mib_get', 'mib_getnext', 'encode_val', 'process_pdu']),
    fixture
])
path = build / 'snmp_under_test.c'
path.write_text(generated)
exe = build / ('snmp.exe' if os.name == 'nt' else 'snmp')
subprocess.run(shlex.split(args.cc) + ['-std=c11', '-Wall', '-Wextra', '-Werror', str(path), '-o', str(exe)], cwd=root, check=True)
subprocess.run([str(exe)], cwd=root, check=True)

hook_types = source[source.index('typedef struct {\n    volatile uint32_t rx_octets'):source.index('static atomic_bool s_hooks_enabled')]
hooks = source[source.index('#define DEFINE_IF_HOOKS'):source.index('/* Re-scan for interfaces worth counting.')]
hook_prefix = '''
#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
#include <assert.h>
#include <stdio.h>
typedef int err_t;
struct netif;
struct pbuf { unsigned tot_len; };
typedef struct { uint32_t addr; } ip4_addr_t;
typedef err_t (*netif_input_fn)(struct pbuf *, struct netif *);
typedef err_t (*netif_linkoutput_fn)(struct netif *, struct pbuf *);
typedef err_t (*netif_output_fn)(struct netif *, struct pbuf *, const ip4_addr_t *);
struct netif { char name[2]; unsigned num; struct netif *next;
 netif_input_fn input; netif_linkoutput_fn linkoutput; netif_output_fn output; };
static struct netif *netif_list;
#define ESP_LOGI(...) ((void)0)
'''
path = build / 'snmp_hooks_under_test.c'
path.write_text(hook_prefix + hook_types + hooks + function('find_ts_netif') +
                (root / 'tests/host/test_snmp_hooks.inc').read_text())
exe = build / ('snmp_hooks.exe' if os.name == 'nt' else 'snmp_hooks')
subprocess.run(shlex.split(args.cc) + ['-std=c11', '-Wall', '-Wextra', '-Werror', str(path), '-o', str(exe)], cwd=root, check=True)
subprocess.run([str(exe)], cwd=root, check=True)
