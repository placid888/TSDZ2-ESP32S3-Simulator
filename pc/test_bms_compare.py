import copy
import csv
import io
import unittest
from bms_compare import compare_snapshots, comparison_csv

class ComparisonTests(unittest.TestCase):
    def setUp(self):
        self.a={'id':'a','address':'same','telemetry':{'captured_at':100,'protocol':'JK02_24S','device_info':{'software':'10.07'},'pack_voltage_v':7,'current_a':0,'soc_percent':50,'cells':[{'cell':2,'voltage_v':3.6},{'cell':1,'voltage_v':3.4}]}}
        self.b=copy.deepcopy(self.a);self.b['id']='b';self.b['telemetry']['captured_at']=160
    def test_signed_delta_sorted_cells_and_original_times(self):
        self.b['telemetry']['cells'][1]['voltage_v']=3.39
        r=compare_snapshots(self.a,self.b)
        self.assertEqual(r['cells'][0]['cell'],1);self.assertEqual(r['cells'][0]['delta'],-.01)
        self.assertEqual(r['elapsed_seconds'],60);self.assertFalse(r['hil_verified'])
    def test_incompatible_snapshots_rejected(self):
        for key,value in [('address','other'),('id','a')]:
            b=copy.deepcopy(self.b);b[key]=value
            with self.assertRaises(ValueError):compare_snapshots(self.a,b)
        for key,value in [('protocol','other'),('device_info',{}),('cells',[{'cell':3,'voltage_v':3.5}])]:
            b=copy.deepcopy(self.b);b['telemetry'][key]=value
            with self.assertRaises(ValueError):compare_snapshots(self.a,b)
    def test_reverse_time_is_explicit_and_missing_temperatures_not_invented(self):
        r=compare_snapshots(self.b,self.a)
        self.assertEqual(r['elapsed_seconds'],-60);self.assertEqual(len(r['metrics']),3)

    def test_csv_preserves_provenance_units_negative_values_and_utf8(self):
        self.b['telemetry']['pack_voltage_v']=6.99
        data=comparison_csv(compare_snapshots(self.a,self.b))
        self.assertTrue(data.startswith(b'\xef\xbb\xbf'))
        rows=list(csv.DictReader(io.StringIO(data.decode('utf-8-sig'))))
        self.assertEqual(len(rows),5)
        self.assertEqual(rows[0]['label'],'總電壓')
        self.assertEqual(float(rows[0]['delta_target_minus_baseline']),-.01)
        self.assertIn('+00:00',rows[0]['baseline_captured_at_utc'])
        self.assertEqual(rows[-1]['cell'],'2')
        self.assertEqual(rows[-1]['baseline_id'],'a')
