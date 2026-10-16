"""Build-only diagnostic runner. Never accesses devices or publishes firmware."""
import json,os,pathlib,subprocess,sys,shutil
root=pathlib.Path(__file__).resolve().parents[1]; out=root/'phase-a-ci'; out.mkdir(exist_ok=True)
scripts=['run_host_tests','run_snmp_tests','test_routes_0130','test_exit_0131','test_upstream_0132','test_wifi_ps_0133','test_factory','test_integration','test_wg_diagnostics','test_wgopt1','test_wgopt2','test_wgopt4','test_wgopt5','test_wgopt6','test_wgopt9','test_wgopt10','test_wgopt12','test_wgopt13','test_snapshot_overlay','test_security_0135','test_ssh_host_keys']
commands=[[sys.executable,'tools/'+s+'.py'] for s in scripts]+[['node','tests/host/test_ui.cjs'],['node','tests/host/test_snmp_ui.cjs']]
results=[]
for i,cmd in enumerate(commands):
    p=subprocess.run(cmd,cwd=root,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    (out/f'host-{i:02}.log').write_bytes(p.stdout)
    results.append({'command':cmd,'exit':p.returncode}); print(cmd[-1],p.returncode,flush=True)
(out/'host-results.json').write_text(json.dumps(results,indent=2))
# Resolve the exact target package before compiling the independent host KAT.
with (out/'package-install.log').open('wb') as log:
    install=subprocess.run([sys.executable,'-m','platformio','pkg','install','-e','esp32-s3'],cwd=root,stdout=log,stderr=subprocess.STDOUT)
if install.returncode:
    sys.exit(install.returncode)
sdk=pathlib.Path(os.environ.get('PLATFORMIO_CORE_DIR',str(pathlib.Path.home()/'.platformio')))/'packages/framework-espidf'
with (out/'crypto-kat.log').open('wb') as log:
    kat=subprocess.run([sys.executable,'tools/test_crypto_compat.py','--sdk',str(sdk)],cwd=root,stdout=log,stderr=subprocess.STDOUT)
if kat.returncode == 0:
    legacy_storage=root/'build/legacy-packages'
    with (out/'legacy-package-install.log').open('wb') as log:
        legacy_install=subprocess.run([sys.executable,'-m','platformio','pkg','install','--global','--storage-dir',str(legacy_storage),'--tool','platformio/framework-espidf@3.50503.0'],cwd=root,stdout=log,stderr=subprocess.STDOUT)
    if legacy_install.returncode:
        sys.exit(legacy_install.returncode)
    with (out/'legacy-kat.log').open('wb') as log:
        kat=subprocess.run([sys.executable,'tools/test_crypto_legacy.py','--sdk',str(legacy_storage/'framework-espidf')],cwd=root,stdout=log,stderr=subprocess.STDOUT)
for f in (root/'build/crypto-compat').glob('*'):
    if f.suffix in ('.json','.log','.h'):
        shutil.copyfile(f,out/('crypto-'+f.name))
if kat.returncode:
    (out/'build-result.json').write_text(json.dumps({'skipped':'crypto KAT failed','flashed':False,'production_go':False}))
    sys.exit(kat.returncode)
# Target diagnostics only after SHA KAT success.
with (out/'build.log').open('wb') as log:
    p=subprocess.run([sys.executable,'-m','platformio','run','-e','esp32-s3'],cwd=root,stdout=log,stderr=subprocess.STDOUT)
(out/'build-result.json').write_text(json.dumps({'exit':p.returncode,'flashed':False,'production_go':False}))
sys.exit(1 if p.returncode or any(r['exit'] for r in results) else 0)
