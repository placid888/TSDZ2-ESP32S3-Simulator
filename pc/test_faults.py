import json
import tempfile
import unittest
from server import BenchLink
from scenarios import ScenarioRunner
from test_server import FakeSerial
from test_sweep import SweepLink


class FaultLink(SweepLink):
    def __init__(self):
        super().__init__()
        self.telemetry.update(fault_api=1,fault='NONE',cadence_rpm=80,torque_nm=60,pas_hz=16,
                              effective_cadence_rpm=80,effective_torque_nm=60,effective_brake=False)
    def fault(self, value):
        self.commands.append(('FAULT',value))
        self.telemetry.update(fault=value,effective_cadence_rpm=0 if value=='PAS_LOSS' else 80,
                              effective_torque_nm=0 if value=='TORQUE_ZERO' else 60,
                              effective_brake=value=='BRAKE_STUCK',pas_hz=0 if value=='PAS_LOSS' else 16)
    def command(self,name):
        super().command(name)
        if name=='STOP':
            self.telemetry.update(fault='NONE',effective_cadence_rpm=80,effective_torque_nm=60,
                                  effective_brake=False,pas_hz=0,dac_codes=[0]*8)
    def apply(self, values):
        super().apply(values)


class FaultRunner(ScenarioRunner):
    def _measure(self, seconds):
        self._check()
        t=self.link.telemetry
        t['pas_hz']=0 if t['fault']=='PAS_LOSS' else 16
        t['dac_codes'][1]=0 if t['fault']=='TORQUE_ZERO' else 19661
        return {'rpm':.01 if t['effective_brake'] else 1500,'current_a':0 if t['effective_brake'] else 5,
                'battery_v':48 if t['effective_brake'] else 47.25,'pwm_percent':t['pwm_percent']}


class FaultTests(unittest.TestCase):
    def test_manual_fault_requires_firmware_capability_and_valid_name(self):
        link=BenchLink();link.port=FakeSerial([])
        for name in ('NONE','PAS_LOSS'):
            with self.assertRaises(ValueError):link.fault(name)
        link.telemetry={'fault_api':1}
        with self.assertRaises(ValueError):link.fault('NONE\nRUN')
        self.assertEqual(link.port.commands,[])

    def test_manual_fault_sends_exact_command_and_refreshes(self):
        link=BenchLink();link.telemetry={'fault_api':1}
        t={'type':'telemetry','protocol':1,'fault_api':1,'fault':'PAS_LOSS',
           'rpm':0,'battery_v':48,'current_a':0,'cadence_rpm':80,'torque_nm':60,'pwm_percent':0}
        link.port=FakeSerial([b'OK\n',json.dumps(t).encode()+b'\n'])
        link.fault('PAS_LOSS')
        self.assertEqual(link.port.commands,['SET FAULT PAS_LOSS','TELEMETRY'])
        self.assertEqual(link.telemetry['fault'],'PAS_LOSS')

    def test_fault_suite_restores_inputs_and_stops(self):
        with tempfile.TemporaryDirectory() as root:
            link=FaultLink();runner=FaultRunner(link,reports=root)
            runner.start('faults');runner.worker.join(2)
            self.assertFalse(runner.active)
            self.assertEqual(runner.report['status'],'passed')
            self.assertEqual(len(runner.report['steps']),8)
            self.assertTrue(runner.report['stop_confirmed'])
            self.assertEqual([v for c,v in link.commands if c=='FAULT'],
                             ['PAS_LOSS','NONE','TORQUE_ZERO','NONE','BRAKE_STUCK','NONE'])
            self.assertEqual(link.telemetry['fault'],'NONE')

    def test_old_firmware_cannot_start_fault_suite(self):
        with tempfile.TemporaryDirectory() as root:
            link=FaultLink();del link.telemetry['fault_api'];runner=FaultRunner(link,reports=root)
            with self.assertRaises(ValueError):runner.start('faults')
            self.assertEqual(link.commands,[])

    def test_ignored_injection_fails_and_cleans_up(self):
        with tempfile.TemporaryDirectory() as root:
            link=FaultLink();runner=FaultRunner(link,reports=root)
            link.fault=lambda name:None
            runner.start('faults');runner.worker.join(2)
            self.assertEqual(runner.report['status'],'failed')
            self.assertTrue(runner.report['stop_confirmed'])
            self.assertEqual(len(runner.report['steps']),2)

if __name__=='__main__':unittest.main()
