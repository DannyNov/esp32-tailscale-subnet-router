"""Offline table gate using the unmodified, hash-pinned official IDF v6.1 tool.

Does not connect to a board or validate bootloader/app image compatibility.
"""
import argparse, hashlib, importlib.util, json, pathlib, subprocess, sys

TOOL_SHA='02f6c1c5f012393d47987ee64bc50ba319a2eda48cbcec754d8cfaf780cce529'
EXPECTED=[('nvs',1,2,0x9000,0x10000),('otadata',1,0,0x19000,0x2000),
 ('phy_init',1,1,0x1b000,0x1000),('ota_0',0,0x10,0x20000,0x400000),
 ('ota_1',0,0x11,0x420000,0x400000),('future_data',1,0x40,0x820000,0x7d0000),
 ('coredump',1,3,0xff0000,0x10000)]
p=argparse.ArgumentParser(); p.add_argument('--idf-tool',type=pathlib.Path,required=True)
p.add_argument('--output',type=pathlib.Path,required=True); a=p.parse_args()
assert hashlib.sha256(a.idf_tool.read_bytes()).hexdigest()==TOOL_SHA,'Unexpected SDK tool bytes'
spec=importlib.util.spec_from_file_location('part',a.idf_tool); mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
root=pathlib.Path(__file__).resolve().parents[1]; csv=root/'partitions.flash16.csv'
table=mod.PartitionTable.from_csv(csv.read_text()); table.verify(); table.verify_size_fits(0x1000000)
actual=[(r.name,r.type,r.subtype,r.offset,r.size) for r in table]
assert actual==EXPECTED,actual
for i,r in enumerate(table):
    assert r.offset % (0x10000 if r.type==0 else 0x1000)==0
    assert r.size%0x1000==0
    if i: assert table[i-1].offset+table[i-1].size<=r.offset
assert table[-1].offset+table[-1].size==0x1000000
out=a.output.resolve(); out.mkdir(parents=True,exist_ok=True)
binary=table.to_binary(); (out/'partitions.flash16.bin').write_bytes(binary)
roundtrip=mod.PartitionTable.from_binary(binary); roundtrip.verify()
assert [(r.name,r.type,r.subtype,r.offset,r.size) for r in roundtrip]==EXPECTED
(out/'partitions.flash16.roundtrip.csv').write_text(roundtrip.to_csv())
# Official CLI, with flash-size bound and default MD5 enabled.
subprocess.run([sys.executable,str(a.idf_tool),'--flash-size','16MB',str(csv),str(out/'official-cli.bin')],check=True)
assert (out/'official-cli.bin').read_bytes()==binary
negative=[]
for label,text in [('unaligned-app',csv.read_text().replace('0x420000','0x421000')),
                   ('overlap',csv.read_text().replace('0x820000','0x810000')),
                   ('overflow',csv.read_text().replace('0x7D0000','0x800000'))]:
    try:
        bad=mod.PartitionTable.from_csv(text); bad.verify(); bad.verify_size_fits(0x1000000)
    except (mod.InputError,ValueError): negative.append(label)
    else: raise AssertionError('Invalid table accepted: '+label)
bad=bytearray(binary); bad[14]^=1
try: mod.PartitionTable.from_binary(bytes(bad))
except mod.InputError: negative.append('corrupt-md5')
else: raise AssertionError('Bad MD5 accepted')
baseline=mod.PartitionTable.from_csv((root/'partitions.csv').read_text()); baseline.verify(); baseline.verify_size_fits(0x400000)
assert [(r.name,r.type,r.subtype,r.offset,r.size) for r in baseline][:3]==EXPECTED[:3]
(out/'partitions.baseline.bin').write_bytes(baseline.to_binary())
report=dict(status='TABLE-GO / IMAGE-UNVERIFIED / HARDWARE-NO-GO',sdk='v6.1',sdk_commit='fff9895c82d744c7237be8847347bdd1b07c6643',tool_sha256=TOOL_SHA,
 table_sha256=hashlib.sha256(binary).hexdigest(),binary_bytes=len(binary),partitions=actual,negative_tests=negative,
 data_bytes=0x7d0000,data_mib=0x7d0000/2**20,app_slot_bytes=0x400000,end=0x1000000,
 original_system_partitions_unchanged=True,filesystem_mounted=False,formatted=False,flashed=False)
(out/'validation.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
