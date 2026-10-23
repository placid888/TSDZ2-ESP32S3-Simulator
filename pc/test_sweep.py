import copy
import math
import tempfile
import unittest
from sweep import DEFAULT, plan_sweep, trend_checks
from scenarios import ScenarioRunner
from test_scenarios import FakeLink


class SweepLink(FakeLink):
    def __init__(self):
        super().__init__()
        self.telemetry.update(battery_open_circuit_v=48,grade_percent=0,brake=False)
    def apply(self, values):
        super().apply(values)
        for key, target in [('BATTERY','battery_open_circuit_v'),('PWM','pwm_percent'),('GRADE','grade_percent'),('BRAKE','brake')]:
            if key in values:self.telemetry[target]=values[key]
    def command(self, name):
        if name=='RUN':
            self.commands.append((name,None));self.telemetry['running']=True
        else:super().command(name)


class ComputedRunner(ScenarioRunner):
    def _measure(self, seconds):
        self._check()
        t=self.link.telemetry
        return {'rpm':t['pwm_percent']*t['battery_open_circuit_v']/(1+t['grade_percent']*.025),
                'current_a':t['pwm_percent']*.1,'battery_v':t['battery_open_circuit_v']-1,
                'pwm_percent':t['pwm_percent']}


class SweepTests(unittest.TestCase):
    def test_default_grid_is_unique_and_ordered(self):
        plan, points=plan_sweep()
        self.assertEqual(len(points),18)
        self.assertEqual(len({tuple(p.values()) for p in points}),18)
        self.assertEqual(points[0],{'voltage_v':36,'pwm_percent':20,'grade_percent':0})
        self.assertEqual(points[-1],{'voltage_v':52,'pwm_percent':60,'grade_percent':15})
        plan['voltages'].append(60)
        self.assertEqual(DEFAULT['voltages'],[36,48,52])

    def test_invalid_plans_rejected(self):
        for key, value in [('voltages',[0]),('voltages',[math.nan]),('pwms',[101]),('pwms',[True]),
                           ('grades',[-31]),('grades',[0,0]),('voltages',[]),('pwms','20,40'),('hold_s',1),('hold_s',math.inf)]:
            config=copy.deepcopy(DEFAULT);config[key]=value
            with self.subTest(key=key,value=value), self.assertRaises(ValueError):plan_sweep(config)
        with self.assertRaises(ValueError):plan_sweep({'unknown':1})
        huge={'voltages':[12,24,36,48,52,60],'pwms':[0,20,40,60,80,100],'grades':[0,15],'hold_s':5}
        with self.assertRaises(ValueError):plan_sweep(huge)

    def test_trend_checks_detect_reverse_and_flat_response(self):
        _,points=plan_sweep()
        for p in points:p['observed']={'rpm':p['voltage_v']*p['pwm_percent']/(1+p['grade_percent']*.025)}
        checks=trend_checks(points)
        self.assertEqual(len(checks),21)
        self.assertTrue(all(c['passed'] for c in checks))
        for p in points:p['observed']['rpm']=1000
        self.assertTrue(any(not c['passed'] for c in trend_checks(points)))
        for p in points:p['observed']['rpm']=10000-p['voltage_v']*p['pwm_percent']
        self.assertTrue(any(not c['passed'] for c in trend_checks(points)))

    def test_zero_pwm_can_remain_zero_across_voltage(self):
        points=[{'voltage_v':v,'pwm_percent':0,'grade_percent':0,'observed':{'rpm':0}} for v in [36,48,52]]
        self.assertTrue(all(c['passed'] for c in trend_checks(points)))

    def test_runner_collects_all_points_and_stops(self):
        with tempfile.TemporaryDirectory() as root:
            link=SweepLink();runner=ComputedRunner(link,reports=root)
            runner.start('sweep');runner.worker.join(2)
            self.assertFalse(runner.active)
            self.assertEqual(runner.report['status'],'passed')
            self.assertEqual(len(runner.report['points']),18)
            self.assertEqual(len(runner.report['comparisons']),21)
            self.assertTrue(runner.report['stop_confirmed'])
            self.assertEqual(sum(1 for cmd,_ in link.commands if cmd=='RUN'),18)
            self.assertEqual(runner.snapshot()['report']['total_points'],18)

    def test_bad_request_does_not_touch_device(self):
        with tempfile.TemporaryDirectory() as root:
            link=SweepLink();runner=ComputedRunner(link,reports=root)
            for kind,config in [('other',None),('sweep',{'bad':1})]:
                with self.assertRaises(ValueError):runner.start(kind,config)
            self.assertEqual(link.commands,[])

    def test_wrong_echo_fails_before_comparisons(self):
        with tempfile.TemporaryDirectory() as root:
            link=SweepLink();runner=ComputedRunner(link,reports=root)
            original=runner._measure
            def wrong(seconds):
                result=original(seconds);link.telemetry['grade_percent']=99;return result
            runner._measure=wrong;runner.start('sweep');runner.worker.join(2)
            self.assertEqual(runner.report['status'],'failed')
            self.assertEqual(len(runner.report['points']),1)
            self.assertTrue(runner.report['stop_confirmed'])

if __name__=='__main__':unittest.main()
