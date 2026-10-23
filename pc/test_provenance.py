import tempfile
import unittest
from pathlib import Path
from provenance import source_identity
from server import BenchLink
from test_server import FakeSerial
import json
import test_scenarios

class ProvenanceTests(unittest.TestCase):
    def test_fingerprint_stable_and_detects_source_changes(self):
        with tempfile.TemporaryDirectory() as root:
            path=Path(root);(path/'web').mkdir();(path/'server.py').write_text('one')
            first=source_identity(root);self.assertEqual(first,source_identity(root))
            (path/'test_example.py').write_text('ignored');self.assertEqual(first,source_identity(root))
            (path/'server.py').write_text('two');self.assertNotEqual(first,source_identity(root))
    def test_info_validation(self):
        link=BenchLink()
        info={'type':'device_info','protocol':1,'version':'v1','elf_sha256':'a'*64}
        link.port=FakeSerial([(json.dumps(info)+'\n').encode()])
        self.assertEqual(link._line('INFO',info=True),info)
        for bad in ({**info,'elf_sha256':'bad'},{**info,'type':'telemetry'}):
            link.port=FakeSerial([(json.dumps(bad)+'\n').encode()])
            with self.assertRaises(ValueError):link._line('INFO',info=True)
    def test_report_captures_identity_without_aliasing(self):
        with tempfile.TemporaryDirectory() as root:
            link,r=test_scenarios.ScenarioTests().make(root)
            link.device_info={'version':'v1'};link.pc_identity={'source_sha256':'abc'}
            r.start();r.worker.join(2)
            link.device_info['version']='changed'
            self.assertEqual(r.report['provenance']['firmware']['version'],'v1')
            self.assertEqual(r.report['provenance']['pc']['source_sha256'],'abc')
