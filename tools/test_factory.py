"""Exercise the factory verifier with generated, deliberately unusual offsets."""
import struct
import tempfile
import unittest
from pathlib import Path
from build_factory import validate_plan, verify_merged


class FactoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        def block(name, data):
            p = root / name
            p.write_bytes(data)
            return p
        table = b''.join(struct.pack('<HBBII16sI', 0x50AA, kind, subtype, offset, size, name, 0)
                         for kind, subtype, offset, size, name in [
                             (1, 2, 0x9000, 0x10000, b'nvs'),
                             (1, 0, 0x19000, 0x2000, b'otadata'),
                             (0, 0x10, 0x30000, 0x100000, b'ota_0')])
        self.app = block('firmware.bin', b'APPLICATION')
        self.plan = [(0, block('bootloader.bin', b'BOOT')), (0x8000, block('partitions.bin', table)),
                     (0x19000, block('boot_app0.bin', b'OTA')), (0x30000, self.app)]
        self.output = root / 'factory.bin'

    def test_dynamic_offsets_and_blank_nvs(self):
        images, parts = validate_plan(self.plan, self.app, 4 * 1024**2)
        data = bytearray(b'\xff' * (0x30000 + self.app.stat().st_size))
        for offset, path in images:
            data[offset:offset + path.stat().st_size] = path.read_bytes()
        self.output.write_bytes(data)
        verify_merged(self.output, images, parts)
        data[0x9000] = 1
        self.output.write_bytes(data)
        with self.assertRaises(ValueError):
            verify_merged(self.output, images, parts)

    def test_missing_ota_metadata(self):
        with self.assertRaisesRegex(ValueError, 'OTA metadata'):
            validate_plan([p for p in self.plan if p[0] != 0x19000], self.app, 4 * 1024**2)

    def test_reject_seeded_nvs(self):
        with self.assertRaisesRegex(ValueError, 'NVS'):
            validate_plan(self.plan + [(0x9000, self.plan[0][1])], self.app, 4 * 1024**2)

    def test_app_offset_must_match_table(self):
        with self.assertRaisesRegex(ValueError, 'Application'):
            validate_plan(self.plan[:-1] + [(0x20000, self.app)], self.app, 4 * 1024**2)

    def test_overlap_and_flash_size(self):
        with self.assertRaises(ValueError):
            validate_plan(self.plan + [(1, self.app)], self.app, 4 * 1024**2)
        with self.assertRaises(ValueError):
            validate_plan(self.plan, self.app, 0x100000)


if __name__ == '__main__':
    unittest.main()
