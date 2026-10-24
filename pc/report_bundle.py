"""Portable read-only export of one saved bench report."""
import csv
import hashlib
import io
import json
import zipfile

def json_bytes(value):
    return json.dumps(value,ensure_ascii=False,allow_nan=False,indent=2).encode('utf-8')

def cell(value):
    if value is None:return ''
    if isinstance(value,(dict,list)):return json.dumps(value,ensure_ascii=False,allow_nan=False)
    if isinstance(value,str) and value.lstrip().startswith(('=','+','-','@')):return "'"+value
    return value

def csv_bytes(rows):
    if not isinstance(rows,list) or any(not isinstance(row,dict) for row in rows):
        raise ValueError('報告採樣格式無效')
    columns=sorted({key for row in rows for key in row})
    stream=io.StringIO(newline='')
    writer=csv.DictWriter(stream,fieldnames=columns)
    writer.writeheader()
    for row in rows:writer.writerow({key:cell(value) for key,value in row.items()})
    return stream.getvalue().encode('utf-8-sig')

def make_bundle(report):
    entries={'report.json':json_bytes(report),
             'provenance.json':json_bytes(report.get('provenance') or {'firmware':None,'pc':None}),
             'samples.csv':csv_bytes(report.get('samples',[])),
             'steps.csv':csv_bytes(report.get('steps',[])),
             'points.csv':csv_bytes(report.get('points',[]))}
    summary=(f"TSDZ Virtual Bench 測試包\n\n測試：{report.get('name','未記錄')}\n"
             f"結果：{report.get('status','未記錄')}\n停止確認：{report.get('stop_confirmed',False)}\n"
             f"檢查項目：{len(report.get('steps',[]))}\n採樣數：{len(report.get('samples',[]))}\n"
             f"掃描測點：{len(report.get('points',[]))}\n錯誤：{report.get('error') or '無'}\n\n"
             "report.json：完整已保存報告；未重新執行測試。\n"
             "samples.csv：本次測試的採樣，不是 PC 的即時資料。\n"
             "steps.csv / points.csv：檢查結果與掃描測點；巢狀欄位以 JSON 文字保存。\n"
             "provenance.json：已記錄的版本；null 代表當時未記錄，不推測。\n"
             "CSV 使用 UTF-8 BOM；可能被試算表當成公式的文字加單引號，數值保持數值。\n"
             "SHA256SUMS.txt：各檔案的完整性指紋；不包含自身。\n"
             "本測試包不包含韌體 binary、帳號憑證、其他報告或聊天附件。\n")
    entries['README.txt']=summary.encode('utf-8-sig')
    entries['SHA256SUMS.txt']=''.join(hashlib.sha256(data).hexdigest()+'  '+name+'\n' for name,data in entries.items()).encode('ascii')
    output=io.BytesIO()
    with zipfile.ZipFile(output,'w',compression=zipfile.ZIP_DEFLATED) as archive:
        for name,data in entries.items():archive.writestr(name,data)
    return output.getvalue()
