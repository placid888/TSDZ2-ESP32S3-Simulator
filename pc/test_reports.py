import json
import tempfile
import unittest
from pathlib import Path
from report_store import ReportStore

class ReportStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.store=ReportStore(self.root)
        self.name='20261023-230053-123456.json'
        self.report={'schema':1,'status':'passed','name':'故障測試','steps':[{'passed':True}], 'points':[], 'stop_confirmed':True}
        (self.root/self.name).write_text(json.dumps(self.report),encoding='utf-8')
    def test_round_trip_and_summary(self):
        self.assertEqual(self.store.read(self.name),self.report)
        summary=self.store.listing();self.assertEqual(summary['skipped'],0)
        self.assertEqual(summary['reports'][0]['checks'],1)
        self.assertTrue(summary['reports'][0]['stop_confirmed'])
    def test_paths_cannot_escape(self):
        for name in ('../secret.json','C:/secret.json','..\\secret.json','20261023-230053-123456.json/../secret','%2e%2e.json'):
            with self.assertRaises(ValueError):self.store.read(name)
    def test_bad_files_skipped_without_losing_good_reports(self):
        for i,body in enumerate(('not json','[]','{"schema":1,"status":"running"}','{"schema":1,"status":"passed","x":NaN}')):
            (self.root/f'20261023-230054-12345{i}.json').write_text(body,encoding='utf-8')
        result=self.store.listing();self.assertEqual(len(result['reports']),1);self.assertEqual(result['skipped'],4)
    def test_oversized_file_rejected(self):
        with (self.root/self.name).open('wb') as f:f.truncate(5_000_001)
        with self.assertRaises(ValueError):self.store.read(self.name)
    def test_overflow_and_invalid_details_rejected(self):
        for body in ('{"schema":1,"status":"passed","x":1e999}', '{"schema":1,"status":"passed","steps":null}'):
            (self.root/self.name).write_text(body,encoding='utf-8')
            with self.assertRaises(ValueError):self.store.read(self.name)
    def test_missing_directory_is_empty(self):
        self.assertEqual(ReportStore(self.root/'missing').listing(),{'reports':[],'skipped':0})
