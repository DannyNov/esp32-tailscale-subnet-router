"""Run offline office regression suites; no live-device test runner is invoked."""
import os,sys,subprocess,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
names=['run_host_tests','run_snmp_tests','test_routes_0130','test_exit_0131','test_upstream_0132','test_wifi_ps_0133','test_factory','test_integration','test_wg_diagnostics','test_wgopt1','test_wgopt2','test_wgopt4','test_wgopt5','test_wgopt6','test_wgopt9','test_wgopt10','test_wgopt12','test_wgopt13','test_snapshot_overlay','test_security_0135','test_ssh_host_keys','test_office_0139']
out=Path(os.environ.get('OFFICE_TEST_RESULTS',str(ROOT/'build/office-tests')));out.mkdir(parents=True,exist_ok=True)
results=[]
for name in names:
    cmd=[sys.executable,str(ROOT/'tools'/(name+'.py'))]
    if name in ['test_routes_0130','test_exit_0131','test_snapshot_overlay','test_security_0135']:
        cmd+=['--cc',os.environ.get('CC','cc')]
    p=subprocess.run(cmd,cwd=ROOT,capture_output=True,text=True,encoding='utf-8',errors='replace')
    (out/(name+'.log')).write_text(p.stdout+p.stderr,encoding='utf-8')
    print(name,'PASS' if p.returncode==0 else 'FAIL',flush=True)
    if p.returncode: print(p.stdout+p.stderr,flush=True)
    results.append({'suite':name,'exit':p.returncode})
for name in ['test_ui','test_snmp_ui']:
    p=subprocess.run(['node',str(ROOT/'tests/host'/(name+'.cjs'))],cwd=ROOT,capture_output=True,text=True,encoding='utf-8',errors='replace')
    (out/(name+'.log')).write_text(p.stdout+p.stderr,encoding='utf-8');results.append({'suite':name,'exit':p.returncode})
    print(name,'PASS' if p.returncode==0 else 'FAIL',flush=True)
(out/'results.json').write_text(json.dumps(results,indent=2)+'\n',encoding='utf-8')
sys.exit(int(any(r['exit'] for r in results)))
