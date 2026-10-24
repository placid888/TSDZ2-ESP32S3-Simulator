import copy
import tempfile
import threading
import unittest
from pathlib import Path
from ride_plan import DEFAULT,validate_plan,read_plan,save_plan
from scenarios import ScenarioRunner,Cancelled
from test_sweep import SweepLink

class RideLink(SweepLink):
 def __init__(self):
  super().__init__();self.telemetry.update(cadence_rpm=80,torque_nm=60)
 def apply(self,values):
  super().apply(values)
  for source,target in [('CADENCE','cadence_rpm'),('TORQUE','torque_nm')]:
   if source in values:self.telemetry[target]=values[source]
class RideRunner(ScenarioRunner):
 def _measure(self,seconds):
  self._check();t=self.link.telemetry
  return {'rpm':.5 if t['brake'] else 1200,'current_a':0 if t['brake'] else 5,'battery_v':48 if t['brake'] else 47,'pwm_percent':t['pwm_percent']}

class RideTests(unittest.TestCase):
 def test_validation_limits_and_no_aliases(self):
  p=validate_plan(DEFAULT);p['steps'][0]['name']='changed';self.assertNotEqual(DEFAULT['steps'][0]['name'],'changed')
  for field,value in [('battery_v',True),('battery_v',float('nan')),('battery_v',10**400),('steps',[]),('steps',[{}])]:
   p=copy.deepcopy(DEFAULT);p[field]=value
   with self.assertRaises(ValueError):validate_plan(p)
  for field,value in [('seconds',1),('seconds',31),('seconds','3'),('pwm_percent',101),('grade_percent',-31),('brake',1),('name','\ninvalid')]:
   p=copy.deepcopy(DEFAULT);p['steps'][0][field]=value
   with self.assertRaises(ValueError):validate_plan(p)
  p=copy.deepcopy(DEFAULT);p['steps']*=4
  for s in p['steps']:s['seconds']=30
  with self.assertRaises(ValueError):validate_plan(p)
 def test_save_roundtrip_and_invalid_save_preserves_file(self):
  with tempfile.TemporaryDirectory() as root:
   path=Path(root)/'plan.json';self.assertFalse(read_plan(path)['saved'])
   save_plan(path,DEFAULT);before=path.read_bytes();self.assertTrue(read_plan(path)['saved'])
   with self.assertRaises(ValueError):save_plan(path,{})
   self.assertEqual(path.read_bytes(),before)
 def test_complete_ride_sets_conditions_and_stops(self):
  with tempfile.TemporaryDirectory() as root:
   link=RideLink();r=RideRunner(link,reports=root);r.start('ride',ride=DEFAULT);r.worker.join(2)
   self.assertFalse(r.active);self.assertEqual(r.report['status'],'passed');self.assertTrue(r.report['stop_confirmed'])
   self.assertEqual(len(r.report['steps']),4);self.assertEqual(r.report['plan'],validate_plan(DEFAULT))
   self.assertEqual(sum(c[0]=='RUN' for c in link.commands),1)
   self.assertEqual([c[1]['GRADE'] for c in link.commands if c[0]=='SET' and 'PWM' in c[1]],[0,0,15,15])
 def test_invalid_plan_never_touches_device(self):
  link=RideLink();r=RideRunner(link)
  with self.assertRaises(ValueError):r.start('ride',ride={})
  self.assertEqual(link.commands,[]);self.assertFalse(r.active)
 def test_wrong_echo_fails_and_cleans_up(self):
  with tempfile.TemporaryDirectory() as root:
   link=RideLink();r=RideRunner(link,reports=root);apply=link.apply
   def ignore_grade(values):apply({k:v for k,v in values.items() if k!='GRADE'})
   link.apply=ignore_grade;r.start('ride',ride=DEFAULT);r.worker.join(2)
   self.assertEqual(r.report['status'],'failed');self.assertTrue(r.report['stop_confirmed'])
   self.assertEqual(len(r.report['steps']),2)
 def test_cancel_never_starts_later_segments(self):
  with tempfile.TemporaryDirectory() as root:
   link=RideLink();r=RideRunner(link,reports=root);entered=threading.Event()
   def wait(seconds):entered.set();r.cancel_event.wait(2);raise Cancelled('cancel')
   r._measure=wait;r.start('ride',ride=DEFAULT);self.assertTrue(entered.wait(1));r.cancel();r.worker.join(2)
   self.assertEqual(r.report['status'],'cancelled');self.assertTrue(r.report['stop_confirmed'])
   self.assertFalse(any(c[0]=='SET' and c[1].get('GRADE')==15 for c in link.commands))
