import copy
import tempfile
import threading
import time
import unittest
from pathlib import Path
from scenarios import ScenarioRunner, Cancelled


class FakeLink:
    def __init__(self):
        self.lock = threading.RLock()
        self.port, self.port_name = True, 'FAKE'
        self.updated = time.monotonic()
        self.telemetry = {'protocol':1,'input':'fake','gpio':'logical-only','dac_backend':'mock',
                          'running':False,'rpm':0,'current_a':0,'battery_v':48,'pwm_percent':0,'dac_codes':[0]*8}
        self.commands = []
        self.stop_fails = False
    def event(self, message):
        pass
    def apply(self, values):
        self.commands.append(('SET',copy.deepcopy(values)))
    def command(self, name):
        self.commands.append((name,None))
        if name == 'STOP' and self.stop_fails:
            raise OSError('serial lost')
        self.telemetry.update(running=name=='RUN', rpm=0, current_a=0, pwm_percent=0)


class ScriptedRunner(ScenarioRunner):
    def _measure(self, seconds):
        self._check()
        return self.values.pop(0)


class ScenarioTests(unittest.TestCase):
    def make(self, root):
        link = FakeLink()
        runner = ScriptedRunner(link, reports=root)
        runner.values = [{'rpm':1500,'current_a':5,'battery_v':47,'pwm_percent':40},
                         {'rpm':1100,'current_a':8,'battery_v':46.8,'pwm_percent':40},
                         {'rpm':0,'current_a':0,'battery_v':48,'pwm_percent':40}]
        return link, runner

    def test_pass_requires_four_checks_and_confirmed_stop(self):
        with tempfile.TemporaryDirectory() as root:
            link, runner = self.make(root)
            runner.start();runner.worker.join(2)
            self.assertFalse(runner.active)
            self.assertEqual(runner.report['status'],'passed')
            self.assertEqual(len(runner.report['steps']),4)
            self.assertTrue(runner.report['stop_confirmed'])
            self.assertTrue(list(Path(root).glob('*.json')))

    def test_bad_plant_fails_and_still_stops(self):
        with tempfile.TemporaryDirectory() as root:
            link, runner = self.make(root)
            runner.values[0]['rpm'] = 0
            runner.start();runner.worker.join(2)
            self.assertEqual(runner.report['status'],'failed')
            self.assertTrue(runner.report['stop_confirmed'])

    def test_lost_serial_cannot_pass_cleanup(self):
        with tempfile.TemporaryDirectory() as root:
            link, runner = self.make(root)
            link.stop_fails = True
            runner.start();runner.worker.join(2)
            self.assertEqual(runner.report['status'],'failed')
            self.assertFalse(runner.report['stop_confirmed'])

    def test_cancel_cannot_resume_later_stages(self):
        with tempfile.TemporaryDirectory() as root:
            link, runner = self.make(root)
            entered = threading.Event()
            def wait_for_cancel(seconds):
                entered.set();runner.cancel_event.wait(2)
                raise Cancelled('test cancellation')
            runner._measure = wait_for_cancel
            runner.start();self.assertTrue(entered.wait(1))
            with self.assertRaises(ValueError): runner.start()
            runner.cancel();runner.worker.join(2)
            self.assertEqual(runner.report['status'],'cancelled')
            self.assertTrue(runner.report['stop_confirmed'])
            self.assertFalse(any(c==('SET',{'GRADE':15}) for c in link.commands))

    def test_hardware_backend_and_stale_data_refused(self):
        with tempfile.TemporaryDirectory() as root:
            link, runner = self.make(root)
            link.telemetry['dac_backend']='spi-zero-only'
            with self.assertRaises(ValueError): runner.start()
            link.telemetry['dac_backend']='mock';link.updated=0
            with self.assertRaises(ValueError): runner.start()
            self.assertEqual(link.commands,[])

    def test_insufficient_samples_cannot_pass(self):
        with tempfile.TemporaryDirectory() as root:
            link = FakeLink()
            runner = ScenarioRunner(link, reports=root, wait_scale=.001)
            runner.report={'step':'test','samples':[]}
            with self.assertRaisesRegex(ValueError,'採樣不足'): runner._measure(.1)

if __name__ == '__main__':
    unittest.main()
