"""Capture only the explicitly selected ready ADB target into local history."""
import hashlib
import json
import math
import os
import re
import struct
import subprocess
import threading
import time
import uuid
import zlib
from pathlib import Path

MAX_PNG=16*1024*1024

def png_size(data):
    if not isinstance(data,bytes) or not 45<=len(data)<=MAX_PNG or data[:8]!=b'\x89PNG\r\n\x1a\n':
        raise ValueError('截圖不是有效 PNG 或大小超限')
    offset=8;dimensions=None;has_data=False;ended=False
    while offset<len(data):
        if offset+12>len(data):raise ValueError('PNG 資料不完整')
        size=struct.unpack('>I',data[offset:offset+4])[0];kind=data[offset+4:offset+8];end=offset+12+size
        if end>len(data):raise ValueError('PNG 資料不完整')
        chunk=data[offset+8:offset+8+size]
        if zlib.crc32(kind+chunk)&0xffffffff!=struct.unpack('>I',data[end-4:end])[0]:raise ValueError('PNG 校驗失敗')
        if dimensions is None:
            if kind!=b'IHDR' or size!=13:raise ValueError('PNG 缺少圖片標頭')
            width,height=struct.unpack('>II',chunk[:8])
            if not 0<width<=8192 or not 0<height<=8192 or width*height>40_000_000:raise ValueError('截圖尺寸超限')
            dimensions=(width,height)
        elif kind==b'IHDR':raise ValueError('PNG 標頭重複')
        if kind==b'IDAT':has_data=True
        if kind==b'IEND':
            if size or end!=len(data):raise ValueError('PNG 結尾無效')
            ended=True;break
        offset=end
    if not ended or not has_data:raise ValueError('PNG 資料不完整')
    return dimensions

class CaptureStore:
    def __init__(self,root):self.root=Path(root);self.lock=threading.RLock()
    def _path(self,id,ext):
        if not isinstance(id,str) or not re.fullmatch('[0-9a-f]{32}',id):raise ValueError('截圖識別無效')
        path=self.root/(id+ext)
        if path.is_symlink() or path.resolve().parent!=self.root.resolve():raise ValueError('截圖路徑無效')
        return path
    def read(self,id):
        path=self._path(id,'.json')
        if path.stat().st_size>16384:raise ValueError('截圖紀錄過大')
        info=json.loads(path.read_text(encoding='utf-8'))
        if info.get('id')!=id or not self._path(id,'.png').is_file():raise ValueError('截圖紀錄不完整')
        try:valid_time=type(info.get('created_at')) in (int,float) and math.isfinite(info['created_at'])
        except OverflowError:valid_time=False
        if (not valid_time
            or type(info.get('width')) is not int or type(info.get('height')) is not int
            or not 0<info['width']<=8192 or not 0<info['height']<=8192
            or not isinstance(info.get('sha256'),str) or not re.fullmatch('[0-9a-f]{64}',info['sha256'])):
            raise ValueError('截圖紀錄格式無效')
        return info
    def image(self,id):
        info=self.read(id);path=self._path(id,'.png')
        if path.stat().st_size>MAX_PNG:raise ValueError('截圖過大')
        data=path.read_bytes()
        if hashlib.sha256(data).hexdigest()!=info.get('sha256'):raise ValueError('截圖完整性校驗失敗')
        return data
    def listing(self):
        items=[];skipped=0
        for path in sorted(self.root.glob('*.json'),key=lambda p:p.name):
            try:items.append(self.read(path.stem))
            except (OSError,ValueError,AttributeError):skipped+=1
        return {'captures':sorted(items,key=lambda x:x.get('created_at',0),reverse=True),'skipped':skipped}
    def save(self,data,context):
        width,height=png_size(data);id=uuid.uuid4().hex
        info={**context,'id':id,'created_at':time.time(),'width':width,'height':height,
              'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}
        with self.lock:
            self.root.mkdir(parents=True,exist_ok=True)
            temp=self._path(id,'.png.tmp');temp.write_bytes(data);temp.replace(self._path(id,'.png'))
            temp=self._path(id,'.json.tmp');temp.write_text(json.dumps(info,ensure_ascii=False,indent=2),encoding='utf-8');temp.replace(self._path(id,'.json'))
        return info

def capture_selected(monitor,store,pc_identity):
    with monitor.lock:
        if monitor.config_error or not monitor.selected:raise ValueError('請先指定已授權的測試手機')
        target=monitor.selected;state=monitor.scan()
        matches=[d for d in state['devices'] if d['serial']==target]
        if state['error'] or len(matches)!=1 or matches[0]['state']!='device':raise ValueError('已指定的測試手機未就緒，未執行截圖')
        adb=monitor.finder()
        if not adb:raise ValueError('ADB 工具未找到')
        options={'capture_output':True,'timeout':10}
        if os.name=='nt':options['creationflags']=subprocess.CREATE_NO_WINDOW
        try:result=monitor.runner([adb,'-s',target,'exec-out','screencap','-p'],**options)
        except subprocess.TimeoutExpired:raise ValueError('手機截圖逾時，未保存紀錄') from None
        if result.returncode:raise ValueError('手機未能完成截圖，未保存紀錄')
        return store.save(result.stdout,{'serial':target,'model':matches[0].get('model'),
                                         'adb_version':state['version'],'pc_identity':dict(pc_identity)})
