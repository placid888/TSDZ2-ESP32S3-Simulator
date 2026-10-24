import hashlib
import io
import json
import unittest
import zipfile
from bench_bundle import bench_bundle


class BenchBundleTests(unittest.TestCase):
    def open(self, **kwargs):
        return zipfile.ZipFile(io.BytesIO(bench_bundle({'generated_at':100,'hil_ready':False}, **kwargs)))

    def test_empty_evidence_still_exports_explicit_missing_items(self):
        with self.open() as archive:
            context=json.loads(archive.read('context.json'))
            self.assertEqual(len(context['missing_or_errors']),3)
            self.assertFalse(context['hil_verified'])
            self.assertNotIn('esp32-report.json',archive.namelist())

    def test_hashes_cover_all_members_except_manifest(self):
        with self.open(model={'status':'passed','started_at':42},build={'revision':'test'},model_id='saved.json') as archive:
            lines=archive.read('SHA256SUMS.txt').decode().splitlines()
            self.assertEqual(len(lines),len(archive.namelist())-1)
            for line in lines:
                digest,name=line.split('  ')
                self.assertEqual(digest,hashlib.sha256(archive.read(name)).hexdigest())
            self.assertEqual(json.loads(archive.read('context.json'))['model_report_started_at'],42)

    def test_failed_and_cancelled_results_are_preserved(self):
        for status in ['failed','cancelled']:
            with self.open(model={'status':status}) as archive:
                self.assertEqual(json.loads(archive.read('esp32-report.json'))['status'],status)
                self.assertFalse(json.loads(archive.read('context.json'))['hil_verified'])

    def test_running_report_rejected(self):
        with self.assertRaises(ValueError):self.open(model={'status':'running'})

    def test_only_fixed_members_are_written(self):
        with self.open(model={'status':'passed','path':'../../secret.txt'}) as archive:
            self.assertEqual(set(archive.namelist()),{'preparation.json','context.json','README.txt','SHA256SUMS.txt','esp32-report.json'})

    def test_bms_evidence_keeps_original_time_and_same_cell_data(self):
        bms={'id':'a'*32,'address':'AA:BB:CC:DD:EE:FF','telemetry':{
             'captured_at':1234567890,'pack_voltage_v':3.5,'current_a':0,'soc_percent':50,
             'cells':[{'cell':1,'voltage_v':3.5,'wire_resistance_ohm':.185}]}}
        with self.open(bms=bms) as archive:
            self.assertEqual(json.loads(archive.read('bms-snapshot.json')),bms)
            context=json.loads(archive.read('context.json'))
            self.assertEqual(context['bms_captured_at'],1234567890);self.assertFalse(context['hil_verified'])
            self.assertIn('0.185',archive.read('bms-cells.csv').decode('utf-8-sig'))
            manifest=archive.read('SHA256SUMS.txt').decode()
            self.assertIn(hashlib.sha256(archive.read('bms-snapshot.json')).hexdigest(),manifest)
