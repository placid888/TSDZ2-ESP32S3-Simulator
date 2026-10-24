import copy
import csv
import hashlib
import io
import json
import unittest
import zipfile
from report_bundle import make_bundle

class BundleTests(unittest.TestCase):
    def make_report(self):
        return {'schema':1,'name':'故障測試','status':'passed','stop_confirmed':True,
                'samples':[{'rpm':1200,'current_a':-1.5,'dac_codes':[1,2,0],'step':'起步'}],
                'steps':[{'name':'起步','passed':True,'observed':{'rpm':1200}}], 'points':[],
                'provenance':{'firmware':{'version':'abc'},'pc':{'source_sha256':'xyz'}}}
    def test_round_trip_and_fixed_safe_members(self):
        r=self.make_report();before=copy.deepcopy(r)
        with zipfile.ZipFile(io.BytesIO(make_bundle(r))) as z:
            self.assertIsNone(z.testzip())
            self.assertEqual(set(z.namelist()),{'report.json','samples.csv','steps.csv','points.csv','provenance.json','README.txt','SHA256SUMS.txt'})
            self.assertEqual(json.loads(z.read('report.json')),r)
            self.assertEqual(json.loads(z.read('provenance.json')),r['provenance'])
            rows=list(csv.DictReader(io.StringIO(z.read('samples.csv').decode('utf-8-sig'))))
            self.assertEqual(rows[0]['current_a'],'-1.5')
            self.assertEqual(json.loads(rows[0]['dac_codes']),[1,2,0])
        self.assertEqual(r,before)
    def test_manifest_verifies_every_payload(self):
        with zipfile.ZipFile(io.BytesIO(make_bundle(self.make_report()))) as z:
            lines=z.read('SHA256SUMS.txt').decode().splitlines()
            self.assertEqual(len(lines),len(z.namelist())-1)
            for line in lines:
                expected,name=line.split('  ',1)
                self.assertEqual(hashlib.sha256(z.read(name)).hexdigest(),expected)
    def test_formula_text_escaped_but_json_unchanged(self):
        r=self.make_report();r['samples']=[{'step':s} for s in ('=1+1','  +SUM(1)','-formula','@formula','normal')]
        with zipfile.ZipFile(io.BytesIO(make_bundle(r))) as z:
            rows=list(csv.DictReader(io.StringIO(z.read('samples.csv').decode('utf-8-sig'))))
            self.assertTrue(all(x['step'].startswith("'") for x in rows[:4]))
            self.assertEqual(rows[-1]['step'],'normal')
            self.assertEqual(json.loads(z.read('report.json')),r)
    def test_cancelled_old_report_with_no_samples_or_versions(self):
        with zipfile.ZipFile(io.BytesIO(make_bundle({'status':'cancelled','name':'舊報告'}))) as z:
            self.assertEqual(json.loads(z.read('provenance.json')),{'firmware':None,'pc':None})
            self.assertIn('cancelled',z.read('README.txt').decode('utf-8-sig'))
    def test_invalid_samples_rejected(self):
        for samples in (None,{},['bad']):
            with self.assertRaises(ValueError):make_bundle({'samples':samples})
