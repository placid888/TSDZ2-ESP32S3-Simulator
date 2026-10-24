"""Deterministic PC test sequencing over real ESP32 telemetry, protocol 1."""
import copy
import json
import statistics
import threading
import time
from pathlib import Path
from sweep import plan_sweep, trend_checks
from ride_plan import validate_plan


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

    def start(self, kind='sequence', sweep=None, cycles=5, ride=None):
        if kind not in ('sequence','sweep','faults','endurance','ride'):
            raise ValueError('不支援的測試類型')
        if kind=='endurance' and (type(cycles) is not int or not 1 <= cycles <= 20):
            raise ValueError('循環次數須為 1–20 的整數')
        plan, points = plan_sweep(sweep) if kind == 'sweep' else (None, [])
        if kind=='ride':plan=validate_plan(ride)
        with self.link.lock:
            if self.active:
                raise ValueError('自動測試已在執行')
            self._fresh()
            t = self.link.telemetry
            if t.get('input') != 'fake' or t.get('gpio') != 'logical-only' or t.get('dac_backend') not in ('mock', 'disabled'):
                raise ValueError('此流程僅適用 fake PWM、邏輯 GPIO 與 mock/disabled DAC')
            if kind=='faults' and t.get('fault_api')!=1:
                raise ValueError('裝置韌體尚未支援 fault-v1')
            self.active = True
            self.cancel_event.clear()
            self.report = {'schema': 1, 'name': '起步 → 爬坡 → 煞車 → 停止',
                           'kind':kind, 'plan':plan, 'points':[], 'comparisons':[], 'total_points':len(points),
                           'total_checks':len(plan['steps'])+1 if kind=='ride' else 4*cycles if kind=='endurance' else 8 if kind=='faults' else 4,
                           'status': 'running', 'started_at': time.time(), 'finished_at': None,
                           'port': self.link.port_name, 'protocol': t['protocol'],
                           'provenance':{'firmware':copy.deepcopy(getattr(self.link,'device_info',None)),
                                         'pc':copy.deepcopy(getattr(self.link,'pc_identity',None))},
                           'scope': 'ESP32 model / fake PWM / logical GPIO / DAC mock or disabled',
                           'parameters': {'BATTERY':48,'CADENCE':80,'TORQUE':60,'PWM':40,'GRADE':0,'BRAKE':0},
                           'step': '準備', 'steps': [], 'samples': [], 'stop_confirmed': False,
                           'error': None, 'saved': False, 'save_error': None}
            if kind == 'sweep':
                self.report['name'] = '電壓 / PWM / 坡度掃描'
                self.report['parameters'] = {'CADENCE':80,'TORQUE':60,'BRAKE':0}
            elif kind == 'faults':
                self.report['name'] = '模型故障注入 / 恢復 / 停止'
            if kind=='endurance':
                self.report.update(name=f'連續循環測試 · {cycles} 次', total_cycles=cycles, completed_cycles=0, current_cycle=0)
            if kind=='ride':
                self.report.update(name='自訂騎乘流程',parameters={'BATTERY':plan['battery_v'],'CADENCE':plan['cadence_rpm'],'TORQUE':plan['torque_nm']})
            self.link.event('開始自動測試：'+self.report['name'])
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
            if self.report.get('kind')=='endurance':
                name = f"循環 {self.report['current_cycle']}/{self.report['total_cycles']} · {name}"
            self.report['step'] = name
            self.link.event('自動測試：' + name)
            for command, values in commands:
                self._check()
                if command == 'SET':
                    self.link.apply(values)
                elif command == 'FAULT':
                    self.link.fault(values)
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
            if self.report.get('kind')=='endurance':
                name = f"循環 {self.report['current_cycle']} · {name}"
            self.report['steps'].append({'name':name, 'criteria':criteria,
                                         'passed':bool(passed), 'observed':observed})
        if not passed:
            raise ValueError(name + ' 未達預期')

    def _sweep(self):
        plan, points = plan_sweep(self.report['plan'])
        for index, point in enumerate(points):
            name = f"掃描 {index+1}/{len(points)} · {point['voltage_v']:g} V / PWM {point['pwm_percent']:g}% / 坡度 {point['grade_percent']:g}%"
            settings = {**self.report['parameters'], 'BATTERY':point['voltage_v'],
                        'PWM':point['pwm_percent'], 'GRADE':point['grade_percent']}
            self._stage(name,[('STOP',None), ('SET',settings), ('RUN',None)])
            observed = self._measure(plan['hold_s'])
            with self.link.lock:
                self._check()
                t = self.link.telemetry
                echoed = (abs(t['battery_open_circuit_v']-point['voltage_v'])<.01
                          and abs(t['grade_percent']-point['grade_percent'])<.01
                          and abs(t['pwm_percent']-point['pwm_percent'])<.01
                          and t['running'] and not t['brake'])
                valid = (echoed and 0 <= observed['battery_v'] <= point['voltage_v']+.01
                         and observed['current_a']>=0 and observed['rpm']>=0
                         and (observed['rpm']>0 if point['pwm_percent']>0 else observed['rpm']==0))
                self.report['points'].append({**point, 'observed':observed, 'passed':valid})
            self._result(name,'設定回報相符、電壓/電流/轉速有效；PWM>0 有轉速，PWM=0 為零',valid,observed)
        with self.link.lock:
            checks = trend_checks(self.report['points'])
            self.report['comparisons'] = checks
            if any(not c['passed'] for c in checks):
                raise ValueError('掃描趨勢未達模型預期，請查看比較結果')

    def _sequence(self):
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

    def _fault_sample(self, seconds):
        measured = self._measure(seconds)
        with self.link.lock:
            self._check()
            return {**copy.deepcopy(self.link.telemetry),**measured}

    def _faults(self):
        self._stage('建立正常輸入',[('STOP',None),('SET',self.report['parameters']),('RUN',None)])
        base = self._fault_sample(3)
        self._result('正常基準','fault=NONE、PAS>0、有效扭力60 Nm、電流>0、RPM>500',
                     base['fault']=='NONE' and base['pas_hz']>0 and base['effective_torque_nm']==60
                     and base['current_a']>0 and base['rpm']>500,base)
        self._stage('踏頻訊號中斷',[('FAULT','PAS_LOSS')])
        pas = self._fault_sample(.75)
        self._result('踏頻中斷','有效踏頻/PAS=0、原設定80 RPM不變；fake PWM仍為40%',
                     pas['fault']=='PAS_LOSS' and pas['effective_cadence_rpm']==0 and pas['pas_hz']==0
                     and pas['cadence_rpm']==80 and pas['pwm_percent']==40,pas)
        self._stage('恢復踏頻',[('FAULT','NONE')])
        restored = self._fault_sample(.75)
        self._result('踏頻恢復','fault=NONE、有效踏頻80 RPM、PAS>0',
                     restored['fault']=='NONE' and restored['effective_cadence_rpm']==80 and restored['pas_hz']>0,restored)
        self._stage('扭力訊號歸零',[('FAULT','TORQUE_ZERO')])
        torque = self._fault_sample(.75)
        self._result('扭力歸零','有效扭力=0、CH2=0、原設定60 Nm不變',
                     torque['fault']=='TORQUE_ZERO' and torque['effective_torque_nm']==0
                     and torque['torque_nm']==60 and torque['dac_codes'][1]==0,torque)
        self._stage('恢復扭力',[('FAULT','NONE')])
        restored = self._fault_sample(.75)
        dac_ok = restored['dac_backend']=='disabled' or restored['dac_codes'][1]>0
        self._result('扭力恢復','有效扭力60 Nm；mock CH2>0（disabled不檢查非零碼）',
                     restored['fault']=='NONE' and restored['effective_torque_nm']==60 and dac_ok,restored)
        self._stage('煞車卡住',[('FAULT','BRAKE_STUCK')])
        brake = self._fault_sample(1.5)
        self._result('煞車卡住','有效煞車=true、原設定=false、電流=0、轉速低於正常的20%',
                     brake['fault']=='BRAKE_STUCK' and brake['effective_brake'] and not brake['brake']
                     and brake['current_a']==0 and brake['rpm']<restored['rpm']*.2,brake)
        self._stage('解除煞車故障',[('FAULT','NONE')])
        normal = self._fault_sample(2)
        self._result('煞車恢復','有效煞車=false、電流>0、轉速>500',
                     normal['fault']=='NONE' and not normal['effective_brake']
                     and normal['current_a']>0 and normal['rpm']>500,normal)
        self._stage('停止與清除故障',[('STOP',None)])
        with self.link.lock:
            stop = copy.deepcopy(self.link.telemetry)
        self._result('停止與故障清除','fault=NONE、running=false、轉速/電流/PWM=0、DAC八通道=0',
                     stop['fault']=='NONE' and not stop['running'] and stop['rpm']==0
                     and stop['current_a']==0 and stop['pwm_percent']==0 and stop['dac_codes']==[0]*8,stop)

    def _ride(self):
        plan=self.report['plan'];base=self.report['parameters']
        self._stage('流程準備',[('STOP',None),('SET',{**base,'PWM':0,'GRADE':0,'BRAKE':0})])
        for index,row in enumerate(plan['steps']):
            settings={**base,'PWM':row['pwm_percent'],'GRADE':row['grade_percent'],'BRAKE':int(row['brake'])}
            name=f"步驟 {index+1} · {row['name']}"
            commands=[('SET',settings)]+([('RUN',None)] if index==0 else [])
            self._stage(name,commands)
            observed=self._measure(row['seconds'])
            with self.link.lock:
                self._check();t=self.link.telemetry
                valid=(t['running'] and abs(t['pwm_percent']-row['pwm_percent'])<.01
                       and abs(t['grade_percent']-row['grade_percent'])<.01 and bool(t['brake'])==row['brake']
                       and abs(t['battery_open_circuit_v']-plan['battery_v'])<.01
                       and abs(t['cadence_rpm']-plan['cadence_rpm'])<.01 and abs(t['torque_nm']-plan['torque_nm'])<.01
                       and t.get('fault','NONE')=='NONE' and not t.get('link_timeout',False)
                       and observed['rpm']>=0 and observed['current_a']>=0 and 0<=observed['battery_v']<=plan['battery_v']+.01
                       and (not row['brake'] or observed['current_a']<=.01))
            self._result(name,'設定回報相符、資料有效；煞車時電流歸零（不判斷實車性能）',valid,observed)
        self._stage('流程停止',[('STOP',None)])
        with self.link.lock:t=copy.deepcopy(self.link.telemetry)
        self._result('停止與清理','停止、PWM/轉速/電流/DAC歸零、故障清除',
                     not t['running'] and t['pwm_percent']==0 and t['rpm']==0 and t['current_a']==0
                     and t['dac_codes']==[0]*8 and t.get('fault','NONE')=='NONE',t)

    def _endurance(self):
        for cycle in range(1,self.report['total_cycles']+1):
            with self.link.lock:
                self._check()
                self.report['current_cycle']=cycle
            self._sequence()
            with self.link.lock:
                self.report['completed_cycles']=cycle

    def _run(self):
        status, error = 'passed', None
        try:
            if self.report['kind']=='sweep': self._sweep()
            elif self.report['kind']=='faults': self._faults()
            elif self.report['kind']=='endurance': self._endurance()
            elif self.report['kind']=='ride': self._ride()
            else: self._sequence()
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
                    self.report['stop_confirmed'] = not t['running'] and t['rpm']==0 and t['current_a']==0 and t['pwm_percent']==0 and t['dac_codes']==[0]*8 and t.get('fault','NONE')=='NONE'
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
