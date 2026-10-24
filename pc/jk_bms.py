"""BLE discovery, explicit JK BMS registration and bounded query-only snapshots."""
import asyncio
import importlib.util
import json
import re
import threading
import time
import copy
from pathlib import Path
from jk_reader import read_snapshot


def valid_address(value):
    return isinstance(value, str) and bool(re.fullmatch(r'(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}', value))


async def discover():
    from bleak import BleakScanner
    found = await asyncio.wait_for(BleakScanner.discover(timeout=5, return_adv=True), timeout=9)
    return [{'address':device.address, 'name':advert.local_name or device.name or '未命名 BLE 裝置',
             'rssi':advert.rssi} for device, advert in found.values()]


class JkMonitor:
    def __init__(self, path, scanner=discover):
        self.path=Path(path); self.scanner=scanner; self.lock=threading.RLock(); self.scan_lock=threading.Lock()
        self.devices=[]; self.selected=None; self.scanned_at=None; self.updated=0; self.error=None; self.config_error=None
        self.telemetry=None;self.telemetry_address=None;self.reading=False
        if self.path.exists():
            try:
                data=json.loads(self.path.read_text(encoding='utf-8'))
                address=data.get('address')
                if data.get('schema')!=1 or (address is not None and not valid_address(address)):raise ValueError()
                self.selected=address.upper() if address else None
            except (OSError,ValueError,AttributeError):self.config_error='BMS 登記檔無法讀取，未覆寫原檔'

    def snapshot(self):
        with self.lock:
            recent=bool(self.updated and time.monotonic()-self.updated<=60)
            return {'tool_available':importlib.util.find_spec('bleak') is not None,
                    'devices':[dict(d) for d in self.devices], 'selected_address':self.selected,
                    'scanned_at':self.scanned_at, 'scan_recent':recent, 'error':self.error or self.config_error,
                    'protocol_verified':bool(self.telemetry and self.telemetry_address==self.selected),
                    'connected':False,'reading':self.reading,'telemetry':copy.deepcopy(self.telemetry),
                    'scope':'Explicit single snapshot; only 0x97/0x96 queries; disconnect after read'}

    def read(self, reader=read_snapshot):
        if not self.scan_lock.acquire(blocking=False):raise ValueError('BMS 操作正在進行')
        try:
            with self.lock:
                if self.config_error or not self.selected:raise ValueError('請先登記明確的 BMS 藍牙位址')
                address=self.selected;self.reading=True;self.error=None
            try:
                async def bounded():return await asyncio.wait_for(reader(address),35)
                data=asyncio.run(bounded())
                with self.lock:self.telemetry=data;self.telemetry_address=address
            except Exception as exc:
                with self.lock:self.error='BMS 讀取失敗；先前快照不代表目前狀態：'+(str(exc) or type(exc).__name__)[:240]
            finally:
                with self.lock:self.reading=False
            return self.snapshot()
        finally:self.scan_lock.release()

    def scan(self):
        if not self.scan_lock.acquire(blocking=False):raise ValueError('BMS 藍牙掃描正在進行')
        try:
            with self.lock:self.devices=[];self.updated=0;self.scanned_at=time.time();self.error=None
            try:
                rows=asyncio.run(self.scanner())
                devices=[]
                for row in rows:
                    if not valid_address(row.get('address')):raise ValueError('BLE 裝置位址格式無效（目前支援 Windows MAC 位址）')
                    name=str(row.get('name') or '未命名 BLE 裝置')[:120]
                    rssi=row.get('rssi')
                    devices.append({'address':row['address'].upper(),'name':name,
                                    'rssi':rssi if type(rssi) is int else None,
                                    'jk_name_hint':bool(re.match(r'^(JK|JIKONG)',name,re.I))})
                with self.lock:
                    self.devices=sorted(devices,key=lambda d:(not d['jk_name_hint'],d['name'],d['address']))
                    self.updated=time.monotonic()
            except (ImportError,OSError,RuntimeError,ValueError,TimeoutError) as exc:
                with self.lock:self.error='藍牙掃描失敗，請確認 PC 藍牙已開啟及支援 BLE：'+str(exc)[:220]
            except Exception as exc:
                # Backend-specific Bleak/WinRT errors must never appear as an empty successful scan.
                with self.lock:self.error='藍牙介面無法掃描：'+str(exc)[:220]
            return self.snapshot()
        finally:self.scan_lock.release()

    def select(self, address):
        with self.lock:
            if self.reading:raise ValueError('BMS 讀取期間不可切換目標')
            if self.config_error:raise ValueError(self.config_error)
            if not valid_address(address):raise ValueError('請明確選擇掃描到的 BMS 裝置')
            if self.error or not self.updated or time.monotonic()-self.updated>60:raise ValueError('請先重新掃描 BMS 藍牙')
            address=address.upper()
            if sum(d['address']==address for d in self.devices)!=1:raise ValueError('裝置未出現或位址不唯一')
            self.path.parent.mkdir(parents=True,exist_ok=True)
            temp=self.path.with_suffix('.tmp');temp.write_text(json.dumps({'schema':1,'address':address}),encoding='utf-8');temp.replace(self.path)
            if self.selected!=address:self.telemetry=None;self.telemetry_address=None
            self.selected=address
            return self.snapshot()
