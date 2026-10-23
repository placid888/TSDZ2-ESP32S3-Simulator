import tempfile
import unittest
import test_scenarios

class EnduranceTests(unittest.TestCase):
    def test_three_cycles_each_reset_and_stop(self):
        with tempfile.TemporaryDirectory() as root:
            link,r=test_scenarios.ScenarioTests().make(root);r.values*=3
            r.start('endurance',cycles=3);r.worker.join(2)
            self.assertFalse(r.active);self.assertEqual(r.report['status'],'passed')
            self.assertEqual(r.report['completed_cycles'],3)
            self.assertEqual(len(r.report['steps']),12)
            self.assertEqual(r.report['total_checks'],12)
            self.assertEqual(sum(c[0]=='RUN' for c in link.commands),3)
            self.assertTrue(r.report['stop_confirmed'])
            self.assertTrue(r.report['steps'][8]['name'].startswith('循環 3'))
    def test_failure_in_second_cycle_prevents_third(self):
        with tempfile.TemporaryDirectory() as root:
            link,r=test_scenarios.ScenarioTests().make(root);r.values*=3;r.values[3]={**r.values[3],'rpm':0}
            r.start('endurance',cycles=3);r.worker.join(2)
            self.assertEqual(r.report['status'],'failed')
            self.assertEqual(r.report['completed_cycles'],1)
            self.assertEqual(sum(c[0]=='RUN' for c in link.commands),2)
            self.assertTrue(r.report['stop_confirmed'])
    def test_cancel_after_first_cycle_prevents_restart(self):
        with tempfile.TemporaryDirectory() as root:
            link,r=test_scenarios.ScenarioTests().make(root);r.values*=3
            sequence=r._sequence
            def cancel_after_cycle():
                sequence();r.cancel()
            r._sequence=cancel_after_cycle
            r.start('endurance',cycles=3);r.worker.join(2)
            self.assertEqual(r.report['status'],'cancelled')
            self.assertEqual(r.report['completed_cycles'],1)
            self.assertEqual(sum(c[0]=='RUN' for c in link.commands),1)
            self.assertTrue(r.report['stop_confirmed'])
    def test_invalid_cycles_do_not_touch_device(self):
        with tempfile.TemporaryDirectory() as root:
            link,r=test_scenarios.ScenarioTests().make(root)
            for value in (0,21,True,1.5,'3',None):
                with self.assertRaises(ValueError):r.start('endurance',cycles=value)
            self.assertEqual(link.commands,[])

