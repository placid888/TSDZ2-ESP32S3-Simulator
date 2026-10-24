"""Bounded ADB inventory only. No shell, app, file, reboot or network commands."""
import json
import os
import shutil
import subprocess
import threading
import time
from pathlib import Path

def find_adb():
    candidates=[]
    for name in ('ANDROID_SDK_ROOT','ANDROID_HOME'):
        if os.environ.get(name):candidates.append(Path(os.environ[name])/'platform-tools'/'adb.exe')
    candidates.append(Path.home()/'AppData'/'Local'/'Android'/'Sdk'/'platform-tools'/'adb.exe')
    on_path=shutil.which('adb')
    if on_path:candidates.append(Path(on_path))
    return next((str(p) for p in candidates if p.is_file()),None)

def valid_serial(serial):
    return isinstance(serial,str) and 0<len(serial)<=200 and not serial.startswith('-') and not any(c.isspace() or ord(c)<32 for c in serial)

def parse_devices(output):
    lines=output.splitlines()
    header=next((i for i,line in enumerate(lines) if line.strip()=='List of devices attached'),None)
    if header is None:raise ValueError('ADB 未回傳有效裝置清單')
    devices=[]
    for line in lines[header+1:]:
        tokens=line.split()
        if not tokens:continue
        if len(tokens)<2:raise ValueError('ADB 裝置資料不完整')
        serial,state=tokens[:2]
        if not valid_serial(serial):raise ValueError('ADB 裝置識別無效')
        if state=='no' and tokens[2:3]==['permissions']:state='no_permissions'
        details={}
        for token in tokens[2:]:
            if ':' in token:
                k,v=token.split(':',1)
                if k in ('model','product','device','transport_id'):details[k]=v
        devices.append({'serial':serial,'state':state,**details})
    return devices

class AndroidMonitor:
    def __init__(self,path,finder=find_adb,runner=subprocess.run):
        self.path=Path(path);self.finder=finder;self.runner=runner;self.lock=threading.RLock()
        self.devices=[];self.scanned_at=None;self.updated=0;self.error=None;self.config_error=None
        self.selected=None;self.version=None
        if self.path.exists():
            try:
                data=json.loads(self.path.read_text(encoding='utf-8'))
                if data.get('schema')!=1 or not valid_serial(data.get('serial')):raise ValueError()
                self.selected=data['serial']
            except (OSError,ValueError,AttributeError):self.config_error='測試手機設定無法讀取，未覆寫原檔'
    def snapshot(self):
        with self.lock:
            matches=[d for d in self.devices if d['serial']==self.selected]
            status='not_selected' if not self.selected else 'not_scanned' if not self.scanned_at else 'ambiguous' if len(matches)>1 else matches[0]['state'] if matches else 'disconnected'
            return {'tool_available':bool(self.finder()),'version':self.version,'devices':[dict(d) for d in self.devices],
                    'selected_serial':self.selected,'selected_status':status,'scanned_at':self.scanned_at,
                    'error':self.error or self.config_error}
    def _run(self,adb,args,timeout):
        options={'capture_output':True,'text':True,'encoding':'utf-8','errors':'replace','timeout':timeout}
        if os.name=='nt':options['creationflags']=subprocess.CREATE_NO_WINDOW
        result=self.runner([adb,*args],**options)
        if result.returncode:raise ValueError('ADB 偵測失敗：'+(result.stderr or result.stdout or '無錯誤說明').strip()[:200])
        return result.stdout
    def scan(self):
        with self.lock:
            self.error=None;self.devices=[];self.updated=0;self.scanned_at=time.time()
            adb=self.finder()
            if not adb:
                self.error='未找到 ADB，請確認 Android SDK platform-tools'
                return self.snapshot()
            try:
                if not self.version:self.version=' · '.join(self._run(adb,['version'],2).strip().splitlines()[:2])
                self.devices=parse_devices(self._run(adb,['devices','-l'],6));self.updated=time.monotonic()
            except subprocess.TimeoutExpired:self.error='ADB 偵測逾時，未執行手機操作'
            except (OSError,ValueError,IndexError) as exc:self.error=str(exc)
            return self.snapshot()
    def select(self,serial):
        with self.lock:
            if self.config_error:raise ValueError(self.config_error)
            if not isinstance(serial,str):raise ValueError('請選擇測試手機')
            if self.error or not self.updated or time.monotonic()-self.updated>30:raise ValueError('請先重新偵測手機')
            matches=[d for d in self.devices if d['serial']==serial]
            if len(matches)!=1 or matches[0]['state']!='device':raise ValueError('只能指定已授權且連線正常的唯一裝置')
            self.path.parent.mkdir(parents=True,exist_ok=True)
            temp=self.path.with_suffix('.tmp');temp.write_text(json.dumps({'schema':1,'serial':serial},ensure_ascii=False),encoding='utf-8');temp.replace(self.path)
            self.selected=serial
            return self.snapshot()
