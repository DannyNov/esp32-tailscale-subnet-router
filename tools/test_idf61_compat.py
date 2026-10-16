"""Exercise generated overlay, hash drift, unique anchor and reapplication gates."""
import argparse,json,pathlib,tempfile
from prepare_wg_diagnostics import prepare
from idf61_compat_overlay import apply
p=argparse.ArgumentParser();p.add_argument('--sdk-root',type=pathlib.Path,required=True);a=p.parse_args()
with tempfile.TemporaryDirectory(prefix='idf61-compat-') as tmp:
    out=pathlib.Path(tmp); prepare(out); component=out/'microlink'
    before={str(f.relative_to(component)):f.read_bytes() for f in component.rglob('*') if f.is_file()}
    apply(component,a.sdk_root)
    after={str(f.relative_to(component)):f.read_bytes() for f in component.rglob('*') if f.is_file()}
    changed=[k for k in before if before[k]!=after[k]]
    assert changed==['CMakeLists.txt'],changed
    manifest=json.loads((out/'idf61-compat-provenance.json').read_text())
    assert len(manifest['generated_sha256'])==67
    assert b'espressif__cjson' in (component/'CMakeLists.txt').read_bytes()
    try: apply(component,a.sdk_root)
    except RuntimeError: pass
    else: raise AssertionError('Repeated overlay accepted')
    for marker in ('# drift\n','    json\n'):
        f=component/'CMakeLists.txt'; f.write_bytes(before['CMakeLists.txt']+marker.encode())
        try: apply(component,a.sdk_root)
        except RuntimeError: pass
        else: raise AssertionError('Mutated input accepted')
    (component/'CMakeLists.txt').write_bytes(before['CMakeLists.txt'])
    bad=out/'bad-sdk/tools/cmake';bad.mkdir(parents=True);(bad/'version.cmake').write_text('set(IDF_VERSION_MAJOR 5)\n')
    try: apply(component,out/'bad-sdk')
    except RuntimeError: pass
    else: raise AssertionError('Unknown SDK accepted')
print('PASS: cJSON-only generated diff, 67-file manifest, reapply/drift/duplicate-anchor/wrong-SDK rejection')
