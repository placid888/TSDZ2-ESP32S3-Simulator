"""Deterministic PC test sequencing over real ESP32 telemetry, protocol 1."""
import copy
import json
import statistics
import threading
import time
from pathlib import Path


class Cancelled(Exception):
    pass


class ScenarioRunner:
    def __init__(self, link, reports=None, wait_scale=1):
        self.link = link
        self.reports = Path(reports) if reports else Path(__file__).with_name('reports')
        self.wait_scale = wait_scale
        self.cancel_event = threading.Event()
        self.active = False
        self.worker = None
        self.report = None

    def snapshot(self, include_samples=False):
        with self.link.lock:
            report = copy.deepcopy(self.report)
            if report and not include_samples:
                report['sample_count'] = len(report.pop('samples'))
            return {'active': self.active, 'report': report}

    def start(self):
        with self.link.lock:
            if self.active:
                raise ValueError('自動測試已在執行')
            self._fresh()
            t = self.link.telemetry
            if t.get('input') != 'fake' or t.get('gpio') != 'logical-only' or t.get('dac_backend') not in ('mock', 'disabled'):
                raise ValueError('此流程僅適用 fake PWM、邏輯 GPIO 與 mock/disabled DAC')
            self.active = True
            self.cancel_event.clear()
            self.report = {'schema': 1, 'name': '起步 → 爬坡 → 煞車 → 停止',
                           'status': 'running', 'started_at': time.time(), 'finished_at': None,
                           'port': self.link.port_name, 'protocol': t['protocol'],
                           'scope': 'ESP32 model / fake PWM / logical GPIO / DAC mock or disabled',
                           'parameters': {'BATTERY':48,'CADENCE':80,'TORQUE':60,'PWM':40,'GRADE':0,'BRAKE':0},
                           'step': '準備', 'steps': [], 'samples': [], 'stop_confirmed': False,
                           'error': None, 'saved': False, 'save_error': None}
            self.link.event('開始自動測試：起步 / 爬坡 / 煞車 / 停止')
            self.worker = threading.Thread(target=self._run, daemon=True)
            self.worker.start()

    def cancel(self):
        with self.link.lock:
            if self.active:
                self.cancel_event.set()
                self.report['status'] = 'cancelling'
                self.link.event('收到自動測試中止要求')

    def _fresh(self):
        if not self.link.port or not self.link.telemetry or time.monotonic() - self.link.updated > 2.5:
            raise ValueError('裝置未連接或數據過期')

    def _check(self):
        if self.cancel_event.is_set():
            raise Cancelled('使用者中止')
        self._fresh()

    def _stage(self, name, commands):
        with self.link.lock:
            self._check()
            self.report['step'] = name
            self.link.event('自動測試：' + name)
            for command, values in commands:
                self._check()
                if command == 'SET':
                    self.link.apply(values)
                else:
                    self.link.command(command)

    def _measure(self, seconds):
        end = time.monotonic() + seconds * self.wait_scale
        collected = []
        previous = None
        while True:
            with self.link.lock:
                self._check()
                if self.link.updated != previous:
                    previous = self.link.updated
                    sample = {'time':time.time(), 'step':self.report['step'], **self.link.telemetry}
                    self.report['samples'].append(sample)
                    collected.append(sample)
            if time.monotonic() >= end:
                break
            if self.cancel_event.wait(min(.1, max(0, end - time.monotonic()))):
                raise Cancelled('使用者中止')
        # Median of final observations reduces sensitivity to polling phase.
        if len(collected) < 2:
            raise ValueError('測試步驟的有效採樣不足')
        tail = collected[-3:]
        return {key:statistics.median(s[key] for s in tail)
                for key in ('rpm','current_a','battery_v','pwm_percent')}

    def _result(self, name, criteria, passed, observed):
        with self.link.lock:
            self.report['steps'].append({'name':name, 'criteria':criteria,
                                         'passed':bool(passed), 'observed':observed})
        if not passed:
            raise ValueError(name + ' 未達預期')

    def _run(self):
        status, error = 'passed', None
        try:
            self._stage('起步', [('STOP',None), ('SET',self.report['parameters']), ('RUN',None)])
            flat = self._measure(5)
            self._result('起步與壓降', 'RPM > 500、電流 > 0.1 A、電壓 < 47.9 V',
                         flat['rpm']>500 and flat['current_a']>.1 and flat['battery_v']<47.9, flat)
            self._stage('爬坡', [('SET',{'GRADE':15})])
            hill = self._measure(5)
            self._result('爬坡負載', 'RPM < 平路的 90%、電流 > 平路 + 0.3 A',
                         hill['rpm']<flat['rpm']*.9 and hill['current_a']>flat['current_a']+.3, hill)
            self._stage('煞車', [('SET',{'BRAKE':1})])
            brake = self._measure(1.5)
            self._result('煞車', '電流 ≤ 0.01 A、RPM < 爬坡的 20%',
                         brake['current_a']<=.01 and brake['rpm']<hill['rpm']*.2, brake)
            self._stage('停止', [('STOP',None)])
            with self.link.lock:
                stopped = copy.deepcopy(self.link.telemetry)
            self._result('停止與 DAC 歸零', 'running=false、RPM/電流/PWM=0、DAC 8ch=0',
                         not stopped['running'] and stopped['rpm']==0 and stopped['current_a']==0
                         and stopped['pwm_percent']==0 and stopped['dac_codes']==[0]*8, stopped)
        except Cancelled as exc:
            status, error = 'cancelled', str(exc)
        except Exception as exc:
            status, error = 'failed', str(exc)
        finally:
            with self.link.lock:
                if self.cancel_event.is_set() and status == 'passed':
                    status, error = 'cancelled', '使用者中止'
                try:
                    self.link.command('STOP')
                    t = self.link.telemetry
                    self.report['stop_confirmed'] = not t['running'] and t['rpm']==0 and t['pwm_percent']==0 and t['dac_codes']==[0]*8
                    if not self.report['stop_confirmed']:
                        raise ValueError('裝置停止狀態未歸零')
                except Exception as exc:
                    status = 'failed'
                    error = (error + '；' if error else '') + 'STOP 未確認：' + str(exc)
                if self.report['stop_confirmed']:
                    try:
                        self.link.apply({'BRAKE':0})
                    except Exception as exc:
                        status = 'failed'
                        error = (error + '；' if error else '') + '解除煞車設定失敗：' + str(exc)
                self.report.update(status=status, error=error, step='完成', finished_at=time.time())
                try:
                    self.reports.mkdir(parents=True, exist_ok=True)
                    self.report['saved'] = True
                    name = time.strftime('%Y%m%d-%H%M%S') + '-' + str(time.time_ns())[-6:] + '.json'
                    target = self.reports/name
                    temp = target.with_suffix('.tmp')
                    temp.write_text(json.dumps(self.report, ensure_ascii=False, allow_nan=False, indent=2), encoding='utf-8')
                    temp.replace(target)
                except Exception as exc:
                    self.report['saved'] = False
                    self.report['save_error'] = str(exc)
                self.link.event('自動測試 ' + status.upper() + ('：'+error if error else ''))
                self.active = False
