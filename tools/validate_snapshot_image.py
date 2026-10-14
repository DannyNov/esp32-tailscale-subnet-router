"""Fail closed; only publish an application candidate after successful build."""
from pathlib import Path
import hashlib, json, struct
HERE = Path(__file__).resolve().parents[1]
image=HERE/'.pio/build/esp32-s3/firmware.bin'
data=image.read_bytes()
assert 0 < len(data) <= 1966080, 'OTA partition exceeded'
assert data[0]==0xe9, 'Not an ESP application image'
assert data[3] >> 4 == 2, 'Image flash size must be 4 MiB'
assert b'0.1.35-tuya-wgopt1\0' in data, 'Wrong candidate version'
assert int.from_bytes(data[12:14],'little')==9, 'Not ESP32-S3'
cursor=24; checksum=0xef
for _ in range(data[1]):
    _,length=struct.unpack_from('<II',data,cursor);cursor+=8
    assert cursor+length <= len(data), 'Truncated segment'
    for byte in data[cursor:cursor+length]: checksum ^= byte
    cursor+=length
checksum_pos=cursor|15
assert data[checksum_pos]==checksum, 'Image segment checksum mismatch'
assert data[23]==1, 'Appended image digest missing'
assert hashlib.sha256(data[:checksum_pos+1]).digest()==data[checksum_pos+1:checksum_pos+33], 'Image digest mismatch'
table=(image.parent/'partitions.bin').read_bytes()
slots={}
for pos in range(0,len(table)-31,32):
    magic,kind,subtype,offset,size,label,_=struct.unpack_from('<HBBII16sI',table,pos)
    if magic != 0x50aa: break
    assert offset + size <= 4 * 1024 * 1024, 'Partition exceeds physical 4 MiB flash'
    if kind==0 and subtype in (0x10,0x11): slots[label.split(b'\0')[0].decode()]=size
assert slots=={'ota_0':1966080,'ota_1':1966080}, 'Unexpected generated OTA partition sizes'
config=(HERE/'sdkconfig.esp32-s3').read_text()
for flag in ['CONFIG_ESPTOOLPY_FLASHSIZE_4MB=y','CONFIG_SPIRAM=y','CONFIG_SPIRAM_MODE_OCT=y','CONFIG_SPIRAM_XIP_FROM_PSRAM=y']:
    assert flag in config, flag
assert 'CONFIG_ML_ZERO_COPY_WG=y' not in config
out=HERE/'artifacts'; out.mkdir(exist_ok=True)
target=out/'firmware-0.1.35-tuya-wgopt1-esp32-s3-ota.bin'
target.write_bytes(data)
result={'file':target.name,'bytes':len(data),'partition_bytes':1966080,
        'headroom':1966080-len(data),'sha256':hashlib.sha256(data).hexdigest(),
        'image_checksum_valid':True,'appended_sha256_valid':True,'chip':'ESP32-S3',
        'version':'0.1.35-tuya-wgopt1','flashed':False}
(out/'image.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result))
