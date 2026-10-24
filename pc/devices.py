"""Device inventory and local role bindings. Never opens serial ports or flashes."""
import hashlib
import json
import shutil
import threading
from pathlib import Path

ROLES={'motor':'ESP32-S3 模擬電機','gateway':'ESP32 Gateway','author_board':'原作者 ESP32 板（待確認）'}

def describe_port(port):
    serial=getattr(port,'serial_number',None)
    vid,pid=getattr(port,'vid',None),getattr(port,'pid',None)
    stable=bool(serial and vid is not None and pid is not None)
    raw=f'usb:{vid}:{pid}:{serial}' if stable else f'port:{port.device}:{port.hwid}'
    return {'port':port.device,'description':port.description,'vid':vid,'pid':pid,
            'serial_number':serial,'location':getattr(port,'location',None),'hwid':port.hwid,
            'identity':hashlib.sha256(raw.encode()).hexdigest(),'stable_identity':stable}

class DeviceRegistry:
    def __init__(self,path):
        self.path=Path(path);self.lock=threading.RLock();self.bindings={};self.error=None
        if self.path.exists():
            try:
                data=json.loads(self.path.read_text(encoding='utf-8'))
                if data.get('schema')!=1 or not isinstance(data.get('bindings'),dict):raise ValueError('格式無效')
                for role,binding in data['bindings'].items():
                    if role not in ROLES or not isinstance(binding,dict) or not isinstance(binding.get('identity'),str):
                        raise ValueError('角色資料無效')
                self.bindings=data['bindings']
            except (OSError,ValueError,AttributeError):self.error='角色設定無法讀取，未覆寫原檔'
    def assign(self,role,port,ports):
        if not isinstance(role,str) or role not in ROLES:raise ValueError('未知裝置角色')
        inventory=[describe_port(p) for p in ports]
        matches=[p for p in inventory if p['port']==port]
        if len(matches)!=1:raise ValueError('裝置已離線，請重新掃描')
        device=matches[0]
        if sum(p['identity']==device['identity'] for p in inventory)!=1:
            raise ValueError('裝置識別不唯一，無法保存角色')
        with self.lock:
            if self.error:raise ValueError(self.error)
            if any(k!=role and v['identity']==device['identity'] for k,v in self.bindings.items()):
                raise ValueError('同一裝置已登記為其他角色')
            updated={**self.bindings,role:device}
            self.path.parent.mkdir(parents=True,exist_ok=True)
            temp=self.path.with_suffix('.tmp')
            temp.write_text(json.dumps({'schema':1,'bindings':updated},ensure_ascii=False,indent=2),encoding='utf-8')
            temp.replace(self.path)
            self.bindings=updated
        return device
    def clear(self,role):
        if not isinstance(role,str) or role not in ROLES:raise ValueError('未知裝置角色')
        with self.lock:
            if self.error:raise ValueError(self.error)
            updated={k:v for k,v in self.bindings.items() if k!=role}
            self.path.parent.mkdir(parents=True,exist_ok=True)
            temp=self.path.with_suffix('.tmp')
            temp.write_text(json.dumps({'schema':1,'bindings':updated},ensure_ascii=False,indent=2),encoding='utf-8')
            temp.replace(self.path);self.bindings=updated
    def role_for(self,port,ports):
        devices=[describe_port(p) for p in ports if p.device==port]
        if len(devices)!=1:return None
        with self.lock:
            return next((role for role,b in self.bindings.items() if b['identity']==devices[0]['identity']),None)
    def snapshot(self,ports,connected_port=None):
        inventory=[describe_port(p) for p in ports]
        with self.lock:
            roles=[]
            for role,label in ROLES.items():
                saved=self.bindings.get(role)
                matches=[p for p in inventory if saved and p['identity']==saved['identity']]
                status='unassigned' if not saved else 'offline' if not matches else 'ambiguous' if len(matches)>1 else 'online'
                device=matches[0] if len(matches)==1 else None
                roles.append({'role':role,'label':label,'status':status,'device':device,'saved_port':saved.get('port') if saved else None,
                              'connected':bool(role=='motor' and device and device['port']==connected_port),
                              'identity_note':'USB 序號識別' if saved and saved.get('stable_identity') else '無唯一 USB 序號，換接孔後須重新核對' if saved else '尚未指定'})
        return {'ports':inventory,'roles':roles,'error':self.error,
                'tools':{'adb':bool(shutil.which('adb')),'stm8flash':bool(shutil.which('stm8flash')),
                         'st_link_cli':bool(shutil.which('ST-LINK_CLI'))},
                'pending':[{'role':'stm8','label':'STM8 / ST-Link','status':'尚未接入；除錯器不以串口判定'},
                           {'role':'android','label':'Android 測試手機','status':'尚未接入 ADB 掃描'}]}
