import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from stm8_build import inspect_hex, build


def record(address, kind, data=b''):
    raw = bytes([len(data), address >> 8, address & 255, kind]) + data
    return ':' + (raw + bytes([-sum(raw) & 255])).hex().upper()


class Stm8BuildTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name); self.image = self.root / 'test.hex'

    def parse(self, lines):
        self.image.write_text('\n'.join(lines), encoding='ascii')
        return inspect_hex(self.image)

    def test_extended_address_and_checksum(self):
        result = self.parse([record(0, 4, b'\0\1'), record(0x8000, 0, b'\x12\x34'), record(0, 1)])
        self.assertEqual((result['minimum_address'], result['maximum_address'], result['data_bytes']), (0x18000, 0x18001, 2))
        self.assertEqual(len(result['sha256']), 64)

    def test_corrupt_checksum_and_missing_eof_rejected(self):
        for lines in [[record(0x8000, 0, b'1')[:-2] + '00', record(0, 1)], [record(0x8000, 0, b'1')]]:
            with self.subTest(lines=lines), self.assertRaises(ValueError): self.parse(lines)

    def test_overlap_trailing_records_and_malformed_eof_rejected(self):
        data = record(0x8000, 0, b'1')
        for lines in [[data, data, record(0, 1)], [data, record(0, 1), data], [data, record(0, 1, b'1')]]:
            with self.subTest(lines=lines), self.assertRaises(ValueError): self.parse(lines)

    def test_wrong_revision_refuses_before_creating_output_or_running_compiler(self):
        compiler = self.root / 'sdcc.exe'; compiler.touch(); output = self.root / 'output'
        with patch('stm8_build.subprocess.check_output', return_value='wrong\n'), patch('stm8_build.subprocess.run') as run:
            with self.assertRaisesRegex(ValueError, 'pinned'): build(self.root, compiler, output)
            run.assert_not_called(); self.assertFalse(output.exists())

    def test_dirty_checkout_refuses(self):
        from stm8_build import REVISION
        compiler = self.root / 'sdcc.exe'; compiler.touch()
        with patch('stm8_build.subprocess.check_output', side_effect=[REVISION, ' M src/main.c']), patch('stm8_build.subprocess.run') as run:
            with self.assertRaisesRegex(ValueError, 'clean'): build(self.root, compiler, self.root / 'output')
            run.assert_not_called()
