import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from android_device import AndroidMonitor,parse_devices

class AndroidTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.path=Path(self.tmp.name)/'target.json';self.calls=[]
  self.output='List of devices attached\nPHONE1 device product:test model:Test_Phone device:test transport_id:1\nPHONE2 unauthorized\nPHONE3 offline\n'
 def adb_run(self,args,**kwargs):
  self.calls.append((args,kwargs));return SimpleNamespace(returncode=0,stdout='Android Debug Bridge version test\n' if args[-1]=='version' else self.output,stderr='')
 def make(self):return AndroidMonitor(self.path,finder=lambda:'adb.exe',runner=self.adb_run)
 def test_parser_states_and_empty_list(self):
  d=parse_devices(self.output);self.assertEqual([x['state'] for x in d],['device','unauthorized','offline']);self.assertEqual(d[0]['model'],'Test_Phone')
  self.assertEqual(parse_devices('List of devices attached\n\n'),[])
  with self.assertRaises(ValueError):parse_devices('unrecognized output')
 def test_no_tool_does_not_execute(self):
  m=AndroidMonitor(self.path,finder=lambda:None,runner=self.adb_run);s=m.scan();self.assertFalse(s['tool_available']);self.assertTrue(s['error']);self.assertEqual(self.calls,[])
 def test_scan_runs_only_version_and_devices(self):
  m=self.make();self.assertEqual(m.snapshot()['devices'],[]);self.assertEqual(self.calls,[])
  s=m.scan();self.assertEqual(len(s['devices']),3);self.assertIsNone(s['selected_serial'])
  self.assertEqual([x[0] for x in self.calls],[['adb.exe','version'],['adb.exe','devices','-l']])
  self.assertTrue(all('shell' not in kwargs and kwargs['timeout']<=6 for _,kwargs in self.calls))
 def test_only_ready_unique_device_can_be_selected_and_persists(self):
  m=self.make();m.scan()
  for serial in ('PHONE2','PHONE3','missing'):
   with self.assertRaises(ValueError):m.select(serial)
  self.assertFalse(self.path.exists());s=m.select('PHONE1');self.assertEqual(s['selected_status'],'device')
  restored=self.make();self.assertEqual(restored.selected,'PHONE1');self.assertEqual(restored.snapshot()['selected_status'],'not_scanned')
 def test_duplicate_and_stale_scan_rejected(self):
  self.output='List of devices attached\nPHONE1 device\nPHONE1 device\n'
  m=self.make();m.scan()
  with self.assertRaises(ValueError):m.select('PHONE1')
  self.output='List of devices attached\nPHONE1 device\n';m.scan();m.updated-=31
  with self.assertRaises(ValueError):m.select('PHONE1')
 def test_disconnect_does_not_select_another_phone(self):
  m=self.make();m.scan();m.select('PHONE1');self.output='List of devices attached\nOTHER device\n'
  s=m.scan();self.assertEqual(s['selected_status'],'disconnected');self.assertEqual(s['selected_serial'],'PHONE1')
 def test_timeout_and_failed_adb_are_explicit_errors(self):
  m=self.make()
  def timeout(*args,**kwargs):raise subprocess.TimeoutExpired('adb',6)
  m.runner=timeout;s=m.scan();self.assertIn('逾時',s['error']);self.assertEqual(s['devices'],[])
  m.runner=lambda *a,**k:SimpleNamespace(returncode=1,stdout='',stderr='failed')
  self.assertIn('失敗',m.scan()['error'])
 def test_bad_config_is_not_overwritten(self):
  self.path.write_text('broken');m=self.make();m.scan()
  with self.assertRaises(ValueError):m.select('PHONE1')
  self.assertEqual(self.path.read_text(),'broken')

