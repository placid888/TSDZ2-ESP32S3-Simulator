import csv
import io
import json
import tempfile
import unittest
from pathlib import Path
from bms_store import BmsStore


class BmsStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.store=BmsStore(Path(self.tmp.name))
        self.state={'selected_address':'AA:BB:CC:DD:EE:FF','protocol_verified':True,'error':None,'reading':False,
                    'telemetry':{'captured_at':1234567890,'checksum_valid':True,'cell_count':2,
                                 'pack_voltage_v':7,'current_a':-1,'soc_percent':50,
                                 'cells':[{'cell':1,'voltage_v':3.4,'wire_resistance_ohm':.185},
                                          {'cell':2,'voltage_v':3.6,'wire_resistance_ohm':.141}]}}

    def test_saved_snapshot_survives_reopen_with_original_time(self):
        item=self.store.save(self.state,{'source':'test'})
        restored=BmsStore(self.store.root);record=restored.read(item['id'])
        self.assertEqual(record['telemetry'],self.state['telemetry'])
        self.assertEqual(restored.listing()['snapshots'][0]['captured_at'],1234567890)

    def test_tampering_is_rejected_and_history_skips_it(self):
        item=self.store.save(self.state,{})
        path=self.store.path(item['id']);data=json.loads(path.read_text());data['telemetry']['pack_voltage_v']=99
        path.write_text(json.dumps(data))
        with self.assertRaises(ValueError):self.store.read(item['id'])
        self.assertEqual(self.store.listing(),{'snapshots':[],'skipped':1})

    def test_failed_read_is_not_saved_as_new_snapshot(self):
        self.state['error']='timeout'
        with self.assertRaises(ValueError):self.store.save(self.state,{})
        self.assertEqual(self.store.listing()['snapshots'],[])

    def test_csv_is_one_row_per_cell_with_units_and_utc_time(self):
        item=self.store.save(self.state,{})
        rows=list(csv.DictReader(io.StringIO(self.store.csv(item['id']).decode('utf-8-sig'))))
        self.assertEqual(len(rows),2);self.assertEqual(rows[0]['wire_resistance_ohm'],'0.185')
        self.assertEqual(rows[1]['cell_voltage_v'],'3.6');self.assertIn('+00:00',rows[0]['captured_at_utc'])

    def test_invalid_paths_and_nonfinite_data_rejected(self):
        for name in ['../secret','0'*32+'.json','x'*32]:
            with self.assertRaises(ValueError):self.store.read(name)
        self.state['telemetry']['cells'][0]['voltage_v']=float('nan')
        with self.assertRaises(ValueError):self.store.save(self.state,{})

    def test_latest_selects_only_registered_battery(self):
        first=self.store.save(self.state,{})
        self.state['selected_address']='11:22:33:44:55:66';self.state['telemetry']['captured_at']+=100
        self.store.save(self.state,{})
        self.assertEqual(self.store.latest('AA:BB:CC:DD:EE:FF')['id'],first['id'])
        self.assertIsNone(self.store.latest(None));self.assertIsNone(self.store.latest('OTHER'))

    def test_corrupt_newest_snapshot_falls_back_to_valid_same_target(self):
        first=self.store.save(self.state,{})
        self.state['telemetry']['captured_at']+=100;last=self.store.save(self.state,{})
        self.store.path(last['id']).write_text('broken')
        self.assertEqual(self.store.latest(self.state['selected_address'])['id'],first['id'])
