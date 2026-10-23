"""Bounded sweep planning and model trend checks. No serial I/O here."""
import math
from itertools import product

DEFAULT = {'voltages':[36,48,52], 'pwms':[20,40,60], 'grades':[0,15], 'hold_s':5}


def plan_sweep(config=None):
    config = DEFAULT if config is None else config
    if not isinstance(config, dict) or set(config) != set(DEFAULT):
        raise ValueError('掃描須包含 voltages、pwms、grades、hold_s')
    plan = {}
    for key, low, high in [('voltages',12,60), ('pwms',0,100), ('grades',-30,30)]:
        values = config[key]
        if not isinstance(values,list) or not 1 <= len(values) <= 6:
            raise ValueError(key+' 須有 1–6 個數值')
        if any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or not low <= v <= high for v in values):
            raise ValueError(f'{key} 數值須介於 {low}–{high}')
        if len(set(values)) != len(values):
            raise ValueError(key+' 不可重複')
        plan[key] = sorted(values)
    hold = config['hold_s']
    if isinstance(hold,bool) or not isinstance(hold,(int,float)) or not math.isfinite(hold) or not 2 <= hold <= 15:
        raise ValueError('每點採樣時間須為 2–15 秒')
    plan['hold_s'] = hold
    points = [{'voltage_v':v,'pwm_percent':p,'grade_percent':g}
              for g,v,p in product(plan['grades'],plan['voltages'],plan['pwms'])]
    if len(points)>36:
        raise ValueError('每次最多 36 個掃描點')
    return plan, points


def trend_checks(points):
    checks = []
    for axis, fixed, direction in [('pwm_percent',('voltage_v','grade_percent'),1),
                                    ('voltage_v',('pwm_percent','grade_percent'),1),
                                    ('grade_percent',('voltage_v','pwm_percent'),-1)]:
        groups = {}
        for point in points:
            groups.setdefault(tuple(point[k] for k in fixed),[]).append(point)
        for group, values in sorted(groups.items()):
            values = sorted(values,key=lambda p:p[axis])
            if len(values)<2:
                continue
            rpms = [p['observed']['rpm'] for p in values]
            # Allow small timing/rounding jitter in independently started runs.
            pairs = all(direction*(b-a) >= -max(5,abs(a)*.05) for a,b in zip(rpms,rpms[1:]))
            # Meaningful input spans must also show a net directional response.
            span = values[-1][axis]-values[0][axis]
            threshold = {'pwm_percent':5,'voltage_v':2,'grade_percent':5}[axis]
            zero_pwm = axis != 'pwm_percent' and values[0]['pwm_percent']==0
            gain = True if zero_pwm or span<threshold else direction*(rpms[-1]-rpms[0]) > max(.1,abs(rpms[0])*.01)
            checks.append({'axis':axis, 'fixed':dict(zip(fixed,group)), 'passed':pairs and gain,
                           'inputs':[v[axis] for v in values], 'rpm':rpms,
                           'criteria':'相鄰反向容差 max(5 RPM, 5%)；足夠跨度須有 > max(0.1 RPM, 1%) 的端點方向變化；PWM=0 不要求電壓/坡度轉速變化'})
    return checks
