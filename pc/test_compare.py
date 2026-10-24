import copy
import unittest
from report_compare import compare_reports

def report():
 return {'schema':1,'protocol':1,'kind':'sequence','scope':'model','parameters':{'PWM':40},'plan':None,
         'status':'passed','stop_confirmed':True,'steps':[{'name':'起步','criteria':'RPM>500','passed':True,
         'observed':{'rpm':1000,'current_a':5,'battery_v':47}}]}

class CompareTests(unittest.TestCase):
 def test_delta_direction_and_inputs_unchanged(self):
  a=report();b=copy.deepcopy(a);b['steps'][0]['observed'].update(rpm=1100,current_a=4,battery_v=47.2)
  original=copy.deepcopy((a,b));r=compare_reports(a,b)
  self.assertEqual(r['rows'][0]['metrics']['rpm']['delta'],100)
  self.assertEqual(r['rows'][0]['metrics']['current_a']['delta'],-1)
  self.assertEqual((a,b),original);self.assertNotIn('passed',r)
 def test_incompatible_conditions_refused(self):
  for key,value in [('kind','faults'),('parameters',{'PWM':60}),('plan',{'hold_s':10}),('scope','hardware'),('total_cycles',2)]:
   a=report();b=copy.deepcopy(a);b[key]=value
   with self.subTest(key=key),self.assertRaises(ValueError):compare_reports(a,b)
 def test_incomplete_or_failed_refused(self):
  for key,value in [('status','cancelled'),('status','failed'),('stop_confirmed',False),('steps',[])]:
   a=report();a[key]=value
   with self.assertRaises(ValueError):compare_reports(a,report())
 def test_changed_criteria_or_step_refused(self):
  for key,value in [('name','不同步驟'),('criteria','不同門檻'),('passed',False)]:
   a=report();a['steps'][0][key]=value
   with self.assertRaises(ValueError):compare_reports(a,report())
 def test_invalid_measurements_refused(self):
  for value in (True,None,'1000',float('nan'),float('inf'),10**400):
   a=report();a['steps'][0]['observed']['rpm']=value
   with self.assertRaises(ValueError):compare_reports(a,report())
 def test_zero_and_missing_provenance_supported(self):
  a=report();a['steps'][0]['observed']['rpm']=0
  r=compare_reports(a,a)
  self.assertEqual(r['rows'][0]['metrics']['rpm']['delta'],0)
  self.assertIsNone(r['baseline']['provenance'])
