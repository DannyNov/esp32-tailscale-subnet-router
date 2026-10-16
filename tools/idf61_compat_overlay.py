"""Generated-only SDK6.1 compatibility; upstream and baseline manifest untouched."""
import argparse,hashlib,json,pathlib

INPUT_SHA='96832240983b3949c248a7a1a43b8e72e8e3f1811e8c6c016545494a03931c70'
SDK_VERSION_SHA='09228291a5c5ee860c432c782a79bb2abd24e6989254d5d5614de7a8d822b747'
def digest(text): return hashlib.sha256(text.encode('utf-8')).hexdigest()
def apply(component,sdk):
    version=(sdk/'tools/cmake/version.cmake').read_text(encoding='utf-8')
    if digest(version)!=SDK_VERSION_SHA: raise RuntimeError('Unrecognized SDK version source; expected exact 6.1.0')
    target=component/'CMakeLists.txt'; before=target.read_text(encoding='utf-8')
    if digest(before)!=INPUT_SHA: raise RuntimeError('Generated CMake input hash mismatch')
    anchor='    json\n'
    if before.count(anchor)!=1: raise RuntimeError('cJSON anchor mismatch')
    after=before.replace(anchor,'    espressif__cjson\n')
    target.write_text(after,encoding='utf-8',newline='\n')
    manifest=dict(stage='A2-cjson-only',sdk='v6.1',microlink='eb63b97073e529d57bc9c1deaeea25ac304034e5',
        hash_policy='UTF-8 text with LF for input/output comparisons; raw output hashes also recorded',
        inputs={'CMakeLists.txt':digest(before),'sdk/tools/cmake/version.cmake':digest(version)},
        outputs={'CMakeLists.txt':digest(after)},
        generated_sha256={str(f.relative_to(component)).replace('\\','/'):hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted(component.rglob('*')) if f.is_file()})
    (component.parent/'idf61-compat-provenance.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--component',type=pathlib.Path,required=True);p.add_argument('--sdk-root',type=pathlib.Path,required=True);a=p.parse_args();apply(a.component,a.sdk_root)
