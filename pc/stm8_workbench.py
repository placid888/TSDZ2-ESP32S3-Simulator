"""Read-only Windows USB/tool readiness; no probe access or programming."""
import json
import os
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path
from urllib.parse import urlparse

USB_QUERY=r"$ErrorActionPreference='Stop'; [Console]::OutputEncoding=[System.Text.UTF8Encoding]::new($false); Get-CimInstance Win32_PnPEntity | Where-Object { $_.Present -ne $false -and $_.PNPDeviceID -like 'USB\*' -and ($_.Name -match 'ST[- _]?LINK|STM8|SWIM' -or $_.PNPDeviceID -match 'VID_0483') } | Select-Object Name,Status,PNPClass,PNPDeviceID,ConfigManagerErrorCode | ConvertTo-Json -Compress"

def find_tools():
    paths={}
    roots=[Path(os.environ.get('ProgramFiles','C:/Program Files')),Path(os.environ.get('ProgramFiles(x86)','C:/Program Files (x86)'))]
    for key,exe,relative in [('sdcc','sdcc','SDCC/bin/sdcc.exe'),('stvp','STVP_CmdLine','STMicroelectronics/st_toolset/stvp/STVP_CmdLine.exe'),('stm8flash','stm8flash',None)]:
        candidates=([Path(shutil.which(exe))] if shutil.which(exe) else [])+[p/relative for p in roots if relative]
        paths[key]=next((str(p) for p in candidates if p.is_file()),None)
    return paths

def repository_url(value):
    if not isinstance(value,str) or len(value)>300:raise ValueError('請提供 GitHub repository 網址')
    parsed=urlparse(value.strip())
    if parsed.scheme!='https' or parsed.netloc!='github.com' or parsed.query or parsed.fragment:
        raise ValueError('來源須為 https://github.com/擁有者/專案，不含帳密、查詢或片段')
    path=parsed.path.rstrip('/')
    if path.endswith('.git'):path=path[:-4]
    if not re.fullmatch(r'/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',path) or any(p in ('.','..') for p in path.split('/')[1:]):
        raise ValueError('請提供 repository 根網址')
    return 'https://github.com'+path

def usb_devices(output):
    raw=json.loads(output) if output.strip() else []
    rows=[raw] if isinstance(raw,dict) else raw
    if not isinstance(rows,list):raise ValueError('USB 裝置資料格式無效')
    result=[]
    for row in rows:
        if not isinstance(row,dict) or not isinstance(row.get('PNPDeviceID'),str):raise ValueError('USB 裝置資料不完整')
        name=str(row.get('Name') or '未命名 USB 裝置')
        result.append({'name':name,'instance_id':row['PNPDeviceID'],'class':row.get('PNPClass'),
                       'driver_status':row.get('Status'),'driver_error_code':row.get('ConfigManagerErrorCode'),
                       'stlink_name_match':bool(re.search(r'ST[- _]?LINK',name,re.I)),
                       'swim_verified':False})
    return result

class Stm8Workbench:
    def __init__(self,path,runner=subprocess.run,tools=find_tools,shell=None,platform=os.name):
        self.path=Path(path);self.runner=runner;self.tools=tools;self.platform=platform
        self.shell=shell or shutil.which('pwsh') or str(Path(os.environ.get('SystemRoot','C:/Windows'))/'System32'/'WindowsPowerShell'/'v1.0'/'powershell.exe')
        self.lock=threading.RLock();self.usb=[];self.scanned_at=None;self.error=None;self.config_error=None;self.source=None
        if self.path.exists():
            try:
                data=json.loads(self.path.read_text(encoding='utf-8'))
                if data.get('schema')!=1:raise ValueError()
                self.source=repository_url(data.get('repository_url'))
            except (OSError,ValueError,AttributeError):self.config_error='STM8 來源設定無法讀取，未覆寫原檔'
    def snapshot(self):
        with self.lock:
            tools=self.tools()
            return {'scanned_at':self.scanned_at,'usb_candidates':[dict(x) for x in self.usb],
                    'tools':{k:{'found':bool(v),'path':v,'version_verified':False} for k,v in tools.items()},
                    'repository_url':self.source,'source_verified':False,'programming_enabled':False,
                    'error':self.error or self.config_error,
                    'missing':([ 'STM8 韌體來源尚未登記' ] if not self.source else [])+
                              (['未找到 SDCC 編譯器；仍需依專案確認工具鏈'] if not tools.get('sdcc') else [])+
                              (['未找到 STVP / stm8flash 燒錄工具'] if not (tools.get('stvp') or tools.get('stm8flash')) else [])+
                              ['STM8 晶片、接線與 SWIM 連線尚未驗證']}
    def scan(self):
        with self.lock:
            self.usb=[];self.scanned_at=time.time();self.error=None
            if self.platform!='nt':self.error='目前 USB 除錯器偵測僅支援 Windows';return self.snapshot()
            if not Path(self.shell).is_file():self.error='未找到 Windows 裝置查詢工具';return self.snapshot()
            try:
                r=self.runner([self.shell,'-NoLogo','-NoProfile','-NonInteractive','-Command',USB_QUERY],
                    capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=8,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                if r.returncode:raise ValueError('Windows USB 裝置查詢失敗')
                self.usb=usb_devices(r.stdout)
            except subprocess.TimeoutExpired:self.error='Windows USB 裝置查詢逾時'
            except (OSError,ValueError) as exc:self.error=str(exc)
            return self.snapshot()
    def save_source(self,value):
        url=repository_url(value)
        with self.lock:
            if self.config_error:raise ValueError(self.config_error)
            self.path.parent.mkdir(parents=True,exist_ok=True)
            temp=self.path.with_suffix('.tmp');temp.write_text(json.dumps({'schema':1,'repository_url':url},ensure_ascii=False),encoding='utf-8');temp.replace(self.path)
            self.source=url
            return self.snapshot()
