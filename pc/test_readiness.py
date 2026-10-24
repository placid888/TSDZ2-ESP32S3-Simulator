import unittest
from readiness import preparation


class ReadinessTests(unittest.TestCase):
    def make(self, motor=None, android=None, artifact=None, active=False):
        return preparation(motor or {}, android or {}, {}, artifact or {}, {}, active, now=100)

    def test_empty_state_is_not_ready(self):
        r=self.make();self.assertFalse(r['hil_ready']);self.assertFalse(r['model_start_ready']);self.assertEqual(r['ready_count'],0)

    def test_stale_or_running_model_cannot_start(self):
        motor={'connected':True,'stale':False,'telemetry':{'running':False,'pwm_percent':0}}
        self.assertTrue(self.make(motor)['model_start_ready'])
        self.assertFalse(self.make(motor,active=True)['model_start_ready'])
        motor['stale']=True;self.assertFalse(self.make(motor)['model_start_ready'])
        motor['stale']=False;motor['telemetry']['running']=True
        self.assertFalse(self.make(motor)['model_start_ready'])

    def test_phone_requires_recent_authorized_selected_target(self):
        for age, expected in [(80,True),(69,False),(101,False)]:
            r=self.make(android={'selected_status':'device','scanned_at':age})
            self.assertEqual(next(c['ready'] for c in r['checks'] if c['id']=='android'),expected)

    def test_artifact_must_match_selected_source(self):
        a={'available':True,'artifact_checked':True,'source_matches':False}
        self.assertFalse(next(c['ready'] for c in self.make(artifact=a)['checks'] if c['id']=='stm8_build'))
        a['source_matches']=True
        self.assertTrue(next(c['ready'] for c in self.make(artifact=a)['checks'] if c['id']=='stm8_build'))

    def test_inventory_never_proves_hil(self):
        r=preparation({}, {}, {'usb_candidates':[{'swim_verified':True}]}, {},
                      {'roles':[{'role':'gateway','status':'online'}]}, now=100)
        self.assertFalse(r['hil_ready']);self.assertEqual(r['ready_count'],0)
