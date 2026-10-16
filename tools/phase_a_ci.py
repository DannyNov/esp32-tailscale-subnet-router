"""Build-only diagnostic runner. Never accesses devices or publishes firmware."""
import json,os,pathlib,subprocess,sys
root=pathlib.Path(__file__).resolve().parents[1]; out=root/'phase-a-ci'; out.mkdir(exist_ok=True)
scripts=['run_host_tests','run_snmp_tests','test_routes_0130','test_exit_0131','test_upstream_0132','test_wifi_ps_0133','test_factory','test_integration','test_wg_diagnostics','test_wgopt1','test_wgopt2','test_wgopt4','test_wgopt5','test_wgopt6','test_wgopt9','test_wgopt10','test_wgopt12','test_wgopt13','test_snapshot_overlay','test_security_0135','test_ssh_host_keys']
commands=[[sys.executable,'tools/'+s+'.py'] for s in scripts]+[['node','tests/host/test_ui.cjs'],['node','tests/host/test_snmp_ui.cjs']]
results=[]
for i,cmd in enumerate(commands):
    p=subprocess.run(cmd,cwd=root,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    (out/f'host-{i:02}.log').write_bytes(p.stdout)
    results.append({'command':cmd,'exit':p.returncode}); print(cmd[-1],p.returncode,flush=True)
(out/'host-results.json').write_text(json.dumps(results,indent=2))
# A failing host gate must remain visible, but configure errors are independently useful.
with (out/'build.log').open('wb') as log:
    p=subprocess.run([sys.executable,'-m','platformio','run','-e','esp32-s3'],cwd=root,stdout=log,stderr=subprocess.STDOUT)
(out/'build-result.json').write_text(json.dumps({'exit':p.returncode,'flashed':False,'production_go':False}))
sys.exit(1 if p.returncode or any(r['exit'] for r in results) else 0)
