"""Verify that the published factory embeds the published OTA and blank NVS."""
import hashlib,json,os
from pathlib import Path
root=Path(os.environ.get('OFFICE_ARTIFACT_DIR','artifacts'))
manifest=json.loads((root/'factory-manifest.json').read_text())
factory=(root/'factory-full.bin').read_bytes()
ota=(root/'firmware-0.1.39-tuya-office-wgopt13-esp32-s3-ota.bin').read_bytes()
assert manifest['chip']=='esp32s3' and manifest['flash_size']=='4MB'
assert manifest['factory_flash_offset']=='0x0' and len(factory)<=4*1024*1024
cursor=0;app_count=0
for block in manifest['images']:
    start=int(block['offset'],0);end=start+block['size']
    assert start>=cursor and end<=len(factory)
    assert factory[cursor:start]==b'\xff'*(start-cursor)
    data=factory[start:end]
    assert hashlib.sha256(data).hexdigest()==block['sha256'],block['file']
    if block['file']=='firmware.bin':
        assert data==ota;app_count+=1
    cursor=end
assert cursor==len(factory) and app_count==1
for part in manifest['partitions']:
    assert part['offset']+part['size']<=4*1024*1024
    if part['type']==1 and part['subtype'] in (2,4):
        assert all(b==255 for b in factory[part['offset']:part['offset']+part['size']])
proof={'factory_bytes':len(factory),'factory_sha256':hashlib.sha256(factory).hexdigest(),
       'ota_sha256':hashlib.sha256(ota).hexdigest(),'ota_matches_embedded_app':True,
       'blank_nvs':True,'flash_offset':'0x0','flashed':False}
(root/'factory-verification.json').write_text(json.dumps(proof,indent=2)+'\n')
print(json.dumps(proof,indent=2))
