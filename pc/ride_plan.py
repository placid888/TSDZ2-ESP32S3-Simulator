"""Bounded ride plans; validation and persistence never operate a device."""
import json
import math
from pathlib import Path

DEFAULT={'battery_v':48,'cadence_rpm':80,'torque_nm':60,'steps':[
 {'name':'平路起步','seconds':3,'pwm_percent':40,'grade_percent':0,'brake':False},
 {'name':'爬坡','seconds':3,'pwm_percent':40,'grade_percent':15,'brake':False},
 {'name':'煞車','seconds':2,'pwm_percent':40,'grade_percent':15,'brake':True}]}

def number(value,low,high,label):
    try:valid=type(value) in (int,float) and math.isfinite(value) and low<=value<=high
    except OverflowError:valid=False
    if not valid:
        raise ValueError(f'{label} 須介於 {low}–{high}')
    return value

def validate_plan(config):
    if not isinstance(config,dict) or set(config)!={'battery_v','cadence_rpm','torque_nm','steps'}:
        raise ValueError('流程格式無效')
    result={'battery_v':number(config['battery_v'],12,60,'電池電壓'),
            'cadence_rpm':number(config['cadence_rpm'],0,200,'踏頻'),
            'torque_nm':number(config['torque_nm'],0,200,'扭力'),'steps':[]}
    if not isinstance(config['steps'],list) or not 1<=len(config['steps'])<=12:
        raise ValueError('流程須有 1–12 個步驟')
    for row in config['steps']:
        if not isinstance(row,dict) or set(row)!={'name','seconds','pwm_percent','grade_percent','brake'}:
            raise ValueError('步驟格式無效')
        name=row['name']
        if not isinstance(name,str) or not 1<=len(name.strip())<=40 or any(ord(c)<32 for c in name):
            raise ValueError('步驟名稱須為 1–40 字且不能含控制字元')
        if type(row['brake']) is not bool:raise ValueError('煞車須為布林值')
        result['steps'].append({'name':name.strip(),'seconds':number(row['seconds'],2,30,'步驟秒數'),
            'pwm_percent':number(row['pwm_percent'],0,100,'PWM'),
            'grade_percent':number(row['grade_percent'],-30,30,'坡度'),'brake':row['brake']})
    if sum(row['seconds'] for row in result['steps'])>180:raise ValueError('流程持續時間最多 180 秒')
    return result

def read_plan(path):
    path=Path(path)
    if not path.exists():return {'plan':validate_plan(DEFAULT),'saved':False}
    return {'plan':validate_plan(json.loads(path.read_text(encoding='utf-8'))),'saved':True}

def save_plan(path,config):
    plan=validate_plan(config);path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix('.tmp');temp.write_text(json.dumps(plan,ensure_ascii=False,indent=2),encoding='utf-8');temp.replace(path)
    return plan
