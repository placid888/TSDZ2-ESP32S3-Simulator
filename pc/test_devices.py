import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from devices import DeviceRegistry,describe_port

def port(name='COM5',serial='ONE'):
 return SimpleNamespace(device=name,description='USB board',vid=1234,pid=5678,serial_number=serial,location='1-2',hwid='USB VID:PID=1234:5678')
class DeviceTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.file=Path(self.tmp.name)/'local'/'devices.json';self.registry=DeviceRegistry(self.file)
 def test_stable_identity_follows_com_number_and_persists(self):
  self.registry.assign('motor','COM5',[port()])
  restored=DeviceRegistry(self.file);s=restored.snapshot([port('COM9')],'COM9')
  self.assertEqual(s['roles'][0]['device']['port'],'COM9');self.assertTrue(s['roles'][0]['connected'])
  self.assertEqual(restored.role_for('COM9',[port('COM9')]),'motor')
 def test_unplug_and_duplicate_identity_not_online(self):
  self.registry.assign('motor','COM5',[port()])
  self.assertEqual(self.registry.snapshot([])['roles'][0]['status'],'offline')
  self.assertEqual(self.registry.snapshot([port(),port('COM9')])['roles'][0]['status'],'ambiguous')
  with self.assertRaises(ValueError):self.registry.assign('gateway','COM5',[port(),port('COM9')])
 def test_one_physical_device_cannot_have_two_roles(self):
  self.registry.assign('motor','COM5',[port()])
  with self.assertRaises(ValueError):self.registry.assign('gateway','COM5',[port()])
  self.assertNotIn('gateway',self.registry.bindings)
 def test_no_serial_is_explicitly_unstable(self):
  self.registry.assign('gateway','COM5',[port(serial=None)])
  r=self.registry.snapshot([port(serial=None)])['roles'][1]
  self.assertFalse(r['device']['stable_identity']);self.assertIn('重新核對',r['identity_note'])
  self.assertEqual(self.registry.snapshot([port('COM9',None)])['roles'][1]['status'],'offline')
 def test_invalid_requests_do_not_create_settings(self):
  for role,p in [('unknown','COM5'),([],'COM5'),('motor','COM99')]:
   with self.assertRaises(ValueError):self.registry.assign(role,p,[port()])
  self.assertFalse(self.file.exists())
 def test_corrupt_settings_not_overwritten(self):
  self.file.parent.mkdir();self.file.write_text('broken')
  r=DeviceRegistry(self.file)
  with self.assertRaises(ValueError):r.assign('motor','COM5',[port()])
  self.assertEqual(self.file.read_text(),'broken')
 def test_clear_allows_role_reassignment(self):
  self.registry.assign('motor','COM5',[port()]);self.registry.clear('motor')
  self.registry.assign('gateway','COM5',[port()])
  self.assertEqual(self.registry.role_for('COM5',[port()]),'gateway')
