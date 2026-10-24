"""Local immutable BMS snapshot history with integrity-checked JSON/CSV export."""
import hashlib
import json
import math
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from report_bundle import json_bytes, csv_bytes


class BmsStore:
    def __init__(self, root):self.root=Path(root)
    def path(self, id):
        if not isinstance(id,str) or not re.fullmatch('[0-9a-f]{32}',id):raise ValueError('BMS 快照識別無效')
        path=self.root/(id+'.json')
        if path.is_symlink() or path.resolve().parent!=self.root.resolve():raise ValueError('BMS 快照路徑無效')
        return path
    def validate(self, data):
        t=data.get('telemetry')
        if not isinstance(t,dict) or t.get('checksum_valid') is not True:raise ValueError('缺少校驗相符的 BMS 快照')
        if type(t.get('captured_at')) not in (float,int) or not 0<t['captured_at']<4_000_000_000:raise ValueError('採樣時間無效')
        for key in ('pack_voltage_v','current_a','soc_percent'):
            if type(t.get(key)) not in (float,int) or not math.isfinite(t[key]):raise ValueError('電池數值無效')
        cells=t.get('cells')
        if not isinstance(cells,list) or not 1<=len(cells)<=24 or t.get('cell_count')!=len(cells):raise ValueError('電芯資料無效')
        ids=[]
        for cell in cells:
            if not isinstance(cell,dict) or type(cell.get('cell')) is not int or not 1<=cell['cell']<=24:raise ValueError('電芯編號無效')
            ids.append(cell['cell'])
            for key in ('voltage_v','wire_resistance_ohm'):
                if type(cell.get(key)) not in (float,int) or not math.isfinite(cell[key]):raise ValueError('電芯數值無效')
        if len(set(ids))!=len(ids):raise ValueError('電芯編號重複')
        json_bytes(data)  # Reject non-finite numbers anywhere in the record.

    def save(self, state, pc_identity):
        if state.get('error') or not state.get('protocol_verified') or state.get('reading'):raise ValueError('本次 BMS 讀取未成功，不保存舊資料')
        id=uuid.uuid4().hex
        data={'schema':1,'id':id,'address':state['selected_address'],'telemetry':state['telemetry'],'pc_identity':pc_identity,
              'field_notes':{'remaining_ah':'尚未與 App 當下容量交叉核對','nominal_ah':'尚未與 App 當下容量交叉核對',
                             'alarm_raw':'原始告警位元，名稱解碼待核對'},
              'scope':'Historical single BMS snapshot; not a live connection or combined HIL result'}
        self.validate(data)
        record={**data,'sha256':hashlib.sha256(json_bytes(data)).hexdigest()}
        self.root.mkdir(parents=True,exist_ok=True)
        path=self.path(id);temp=path.with_suffix('.tmp');temp.write_bytes(json_bytes(record));temp.replace(path)
        return {'id':id,'captured_at':data['telemetry']['captured_at']}

    def read(self, id):
        path=self.path(id)
        if path.stat().st_size>256000:raise ValueError('BMS 快照過大')
        record=json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(record,dict):raise ValueError('BMS 快照格式無效')
        digest=record.get('sha256');data={k:v for k,v in record.items() if k!='sha256'}
        if data.get('schema')!=1 or data.get('id')!=id or digest!=hashlib.sha256(json_bytes(data)).hexdigest():raise ValueError('BMS 快照校驗不符')
        self.validate(data)
        return record

    def listing(self):
        items=[];skipped=0
        for path in self.root.glob('*.json'):
            try:
                r=self.read(path.stem);t=r['telemetry']
                items.append({'id':r['id'],'captured_at':t['captured_at'],'address':r['address'],
                              'pack_voltage_v':t['pack_voltage_v'],'cell_count':t['cell_count']})
            except (OSError,ValueError,TypeError,KeyError,OverflowError):skipped+=1
        return {'snapshots':sorted(items,key=lambda x:x['captured_at'],reverse=True),'skipped':skipped}

    def csv(self, id):
        r=self.read(id);t=r['telemetry']
        rows=[{'snapshot_id':id,'captured_at_utc':datetime.fromtimestamp(t['captured_at'],timezone.utc).isoformat(),
               'bms_address':r['address'],'pack_voltage_v':t['pack_voltage_v'],'current_a':t['current_a'],
               'soc_percent':t['soc_percent'],'cell':c['cell'],'cell_voltage_v':c['voltage_v'],
               'wire_resistance_ohm':c['wire_resistance_ohm']} for c in t['cells']]
        return csv_bytes(rows)
