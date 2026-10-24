"""A preparation snapshot and independently collected local test evidence."""
import hashlib
import io
import zipfile
from report_bundle import json_bytes


def bench_bundle(preparation, model=None, build=None, issues=None, model_id=None):
    entries = {'preparation.json': json_bytes(preparation)}
    missing = list(issues or [])
    if model is not None:
        if model.get('status') not in ('passed', 'failed', 'cancelled'):
            raise ValueError('只能匯出已完成的 ESP32 報告')
        entries['esp32-report.json'] = json_bytes(model)
    else:
        missing.append('沒有可納入的已完成 ESP32 測試報告')
    if build is not None:
        entries['stm8-build-report.json'] = json_bytes(build)
    else:
        missing.append('沒有可納入的有效 STM8 離線編譯報告')
    entries['context.json'] = json_bytes({
        'schema':1, 'generated_at':preparation['generated_at'], 'scope':'independent_local_evidence',
        'hil_verified':False, 'model_report_id':model_id,
        'model_report_status':model.get('status') if model else None,
        'model_report_started_at':model.get('started_at') if model else None,
        'missing_or_errors':missing,
        'note':'準備快照、歷史 ESP32 測試與 STM8 編譯不是同一次跨裝置測試；不得據此認定 HIL 通過。'})
    entries['README.txt'] = (
        'TSDZ 整合測試資料包\n\n'
        'preparation.json：匯出時的準備狀態，各設備快照不一定同時取得。\n'
        'esp32-report.json：最近一份可讀取的已保存模型測試，若存在才納入；包含原測試時間與結果。\n'
        'stm8-build-report.json：韌體檔重新校驗相符的離線編譯報告，若存在才納入。\n'
        'context.json：缺少項目、ESP32 報告識別及範圍限制。失敗與中止報告仍保留原結果。\n'
        '各份證據分開取得，不代表完整 HIL、BLE、接線或實車性能已驗證。\n'
        '匯出不啟動測試、不改裝置；ZIP 不包含韌體、手機畫面、聊天附件或編譯器。\n'
        'SHA256SUMS.txt：每個檔案的完整性雜湊，不包含自身；不代表來源數位簽章。\n'
    ).encode('utf-8-sig')
    entries['SHA256SUMS.txt'] = ''.join(hashlib.sha256(value).hexdigest()+'  '+key+'\n'
                                        for key,value in entries.items()).encode('ascii')
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for key, value in entries.items(): archive.writestr(key, value)
    return output.getvalue()
