"""Merge the exact PlatformIO upload image list; never maintain an offset table."""
import hashlib
import json
from pathlib import Path
import struct
import subprocess


def partition_entries(path):
    data = Path(path).read_bytes()
    result = []
    for pos in range(0, len(data) - 31, 32):
        magic, kind, subtype, offset, size, label, flags = struct.unpack_from('<HBBII16sI', data, pos)
        if magic != 0x50AA:
            break  # MD5 trailer or padding
        result.append(dict(type=kind, subtype=subtype, offset=offset, size=size,
                           name=label.split(b'\0', 1)[0].decode('ascii')))
    if not result:
        raise ValueError('No entries in generated partition table')
    return result


def validate_plan(images, app, flash_bytes):
    images = sorted((int(str(offset), 0), Path(path).resolve()) for offset, path in images)
    if len(images) < 3 or len({offset for offset, _ in images}) != len(images):
        raise ValueError('Incomplete/duplicate PlatformIO upload plan')
    previous_end = 0
    for offset, path in images:
        end = offset + path.stat().st_size
        if offset < previous_end or end > flash_bytes:
            raise ValueError('Overlapping/out-of-flash upload blocks')
        previous_end = end
    table = [p for _, p in images if p.name in ('partitions.bin', 'partition-table.bin')]
    if len(table) != 1 or not any('bootloader' in p.name for _, p in images):
        raise ValueError('Missing generated bootloader/partition table')
    parts = partition_entries(table[0])
    if any(p['offset'] + p['size'] > flash_bytes for p in parts):
        raise ValueError('Partition table exceeds configured flash')
    app = Path(app).resolve()
    app_offsets = [offset for offset, path in images if path == app]
    if len(app_offsets) != 1 or not any(p['type'] == 0 and p['offset'] == app_offsets[0]
                                      and app.stat().st_size <= p['size'] for p in parts):
        raise ValueError('Application upload offset does not match generated partitions')
    for p in parts:
        overlapping = [(offset, path) for offset, path in images
                       if offset < p['offset'] + p['size'] and offset + path.stat().st_size > p['offset']]
        if p['type'] == 1 and p['subtype'] in (2, 4) and overlapping:
            raise ValueError('Factory plan must not contain NVS or NVS keys')
        if p['type'] == 1 and p['subtype'] == 0 and not any(offset == p['offset'] for offset, _ in overlapping):
            raise ValueError('OTA metadata missing from upload configuration')
    return images, parts


def verify_merged(output, images, parts):
    data = Path(output).read_bytes()
    cursor = 0
    for offset, path in images:
        original = path.read_bytes()
        if data[cursor:offset] != b'\xff' * (offset - cursor):
            raise ValueError('Factory padding contains data')
        if data[offset:offset + len(original)] != original:
            raise ValueError(f'Merged block differs from build input: {path.name}')
        cursor = offset + len(original)
    if len(data) != cursor:
        raise ValueError('Unexpected factory image length')
    for p in parts:
        if p['type'] == 1 and p['subtype'] in (2, 4):
            area = data[p['offset']:p['offset'] + p['size']]
            if any(b != 255 for b in area):
                raise ValueError('Factory contains nonblank NVS')


def build_factory(images, app, flash_size, chip, esptool, python, output, manifest):
    flash_bytes = int(flash_size.removesuffix('MB')) * 1024 * 1024
    images, parts = validate_plan(images, app, flash_bytes)
    if chip != 'esp32s3':
        raise ValueError('This release targets ESP32-S3')
    cmd = [str(python), str(esptool), '--chip', chip, 'merge_bin', '-o', str(output),
           '--flash_mode', 'keep', '--flash_freq', 'keep', '--flash_size', 'keep']
    for offset, path in images:
        cmd.extend([hex(offset), str(path)])
    subprocess.run(cmd, check=True)
    verify_merged(output, images, parts)
    metadata = dict(chip=chip, flash_size=flash_size, factory_flash_offset='0x0',
                    source='PlatformIO FLASH_EXTRA_IMAGES + ESP32_APP_OFFSET',
                    partitions=parts, images=[dict(offset=hex(offset), file=path.name,
                    size=path.stat().st_size, sha256=hashlib.sha256(path.read_bytes()).hexdigest())
                    for offset, path in images])
    Path(manifest).write_text(json.dumps(metadata, indent=2) + '\n', encoding='utf-8')
    print('PASS: factory image offsets, input blocks, OTA metadata and blank NVS verified')
