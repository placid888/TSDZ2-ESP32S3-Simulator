import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from stm8_workbench import Stm8Workbench,repository_url,usb_devices,USB_QUERY

class Stm8Tests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
  self.shell=self.root/'powershell.exe';self.shell.touch();self.calls=[];self.output='';self.code=0
 def query(self,args,**kwargs):
  self.calls.append((args,kwargs));return SimpleNamespace(returncode=self.code,stdout=self.output,stderr='')
 def make(self):return Stm8Workbench(self.root/'project.json',runner=self.query,tools=lambda:{'sdcc':None,'stvp':None,'stm8flash':None},shell=str(self.shell),platform='nt')
 def test_snapshot_never_queries_hardware_and_reports_missing(self):
  state=self.make().snapshot();self.assertEqual(self.calls,[]);self.assertFalse(state['programming_enabled']);self.assertEqual(len(state['missing']),4)
 def test_scan_is_only_fixed_windows_inventory(self):
  m=self.make();state=m.scan();self.assertEqual(state['usb_candidates'],[]);self.assertIsNone(state['error'])
  args,options=self.calls[0];self.assertEqual(args[-1],USB_QUERY);self.assertIn('Get-CimInstance',args[-1]);self.assertNotIn('shell',options);self.assertEqual(options['timeout'],8)
 def test_probe_name_does_not_prove_swim(self):
  rows=usb_devices(json.dumps([{'Name':'ST-LINK/V2','PNPDeviceID':'USB\\VID_0483&PID_TEST\\ONE','Status':'OK','ConfigManagerErrorCode':0},{'Name':'STM32 Bootloader','PNPDeviceID':'USB\\VID_0483\\TWO'}]))
  self.assertTrue(rows[0]['stlink_name_match']);self.assertFalse(rows[0]['swim_verified']);self.assertFalse(rows[1]['stlink_name_match'])
 def test_invalid_output_and_timeout_are_not_empty_success(self):
  m=self.make();self.output='broken';self.assertIsNotNone(m.scan()['error'])
  def timeout(*a,**k):raise subprocess.TimeoutExpired('powershell',8)
  m.runner=timeout;self.assertIn('逾時',m.scan()['error'])
 def test_source_registration_is_local_only_and_persistent(self):
  m=self.make();state=m.save_source('https://github.com/example/stm8-firmware.git/')
  self.assertEqual(state['repository_url'],'https://github.com/example/stm8-firmware');self.assertEqual(self.calls,[])
  self.assertFalse(state['source_verified']);self.assertFalse(state['programming_enabled']);self.assertEqual(self.make().source,state['repository_url'])
 def test_invalid_source_and_corrupt_settings_not_overwritten(self):
  m=self.make()
  for value in ('file:///secret','https://user:pass@github.com/o/r','https://evil.example/o/r','https://github.com/o/r?token=secret','https://github.com/o/r/tree/main',None):
   with self.assertRaises(ValueError):m.save_source(value)
  self.assertFalse(m.path.exists());m.path.write_text('broken');m=self.make()
  with self.assertRaises(ValueError):m.save_source('https://github.com/example/project')
  self.assertEqual(m.path.read_text(),'broken')
 def test_unsupported_os_explains_limit(self):
  m=self.make();m.platform='posix';self.assertIn('Windows',m.scan()['error']);self.assertEqual(self.calls,[])
