import json
import tempfile
import unittest
from pathlib import Path
from stm8_artifacts import Stm8Artifacts
from stm8_build import inspect_hex, UPSTREAM, REVISION


class ArtifactTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name); self.store = Stm8Artifacts(self.root)
        self.image = self.root / 'firmware.hex'
        self.image.write_text(':02800000123438\n:00000001FF\n', encoding='ascii')
        self.data = {'status':'passed','repository':UPSTREAM,'revision':REVISION,
                     'compiler_version':'SDCC test','compiler_sha256':'a'*64,
                     'warning_lines':['example warning'], 'image':inspect_hex(self.image),
                     'programmed':False,'hardware_verified':False,'firmware_version_macro':17}
        self.save()

    def save(self):
        (self.root / 'build-report.json').write_text(json.dumps(self.data), encoding='utf-8')

    def test_valid_report_and_source_match(self):
        result = self.store.snapshot(UPSTREAM)
        self.assertTrue(result['available']); self.assertTrue(result['artifact_checked'])
        self.assertTrue(result['source_matches']); self.assertFalse(result['programmed'])
        self.assertEqual(result['warnings'], ['example warning'])

    def test_different_selected_source_is_explicit(self):
        result = self.store.snapshot('https://github.com/example/other')
        self.assertTrue(result['available']); self.assertFalse(result['source_matches'])

    def test_missing_or_tampered_firmware_never_reports_success(self):
        self.image.write_text(':02800000123439\n:00000001FF\n')
        self.assertFalse(self.store.snapshot(UPSTREAM)['available'])
        self.image.unlink(); self.assertFalse(self.store.snapshot(UPSTREAM)['available'])

    def test_mismatched_manifest_and_unsupported_revision_rejected(self):
        self.data['image']['sha256'] = 'b'*64; self.save()
        self.assertFalse(self.store.snapshot(UPSTREAM)['available'])
        self.data['image'] = inspect_hex(self.image); self.data['revision'] = 'bad'; self.save()
        self.assertFalse(self.store.snapshot(UPSTREAM)['available'])

    def test_failed_or_corrupt_report_rejected(self):
        self.data['status'] = 'failed'; self.save()
        self.assertFalse(self.store.snapshot(UPSTREAM)['available'])
        (self.root / 'build-report.json').write_text('{')
        self.assertFalse(self.store.snapshot(UPSTREAM)['available'])
