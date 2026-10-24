"""Summarize observed preparation; never grant hardware-operation permission."""
import time


def preparation(motor, android, stm8, artifact, devices, active=False, now=None):
    now = time.time() if now is None else now
    checks = []
    def add(key, label, ready, detail):
        checks.append({'id':key,'label':label,'ready':bool(ready),'detail':detail})
    telemetry = motor.get('telemetry') or {}
    fresh = bool(motor.get('connected') and not motor.get('stale') and not motor.get('error'))
    stopped = fresh and telemetry.get('running') is False and telemetry.get('pwm_percent') == 0
    add('motor', 'ESP32 模型通訊', fresh, '已連線且回報有效' if fresh else '請連接模擬器並確認回報')
    add('stopped', '測試前停止狀態', stopped and not active, '已停止且沒有自動流程' if stopped and not active else '需確認停止、PWM 歸零並結束自動流程')
    built = artifact.get('available') and artifact.get('artifact_checked') and artifact.get('source_matches')
    add('stm8_build', 'STM8 離線韌體', built, '已保存且檔案校驗相符' if built else artifact.get('error') or '需核對產物與登記來源')
    scan_time = android.get('scanned_at')
    recent = isinstance(scan_time, (int, float)) and 0 <= now - scan_time <= 30
    phone = android.get('selected_status') == 'device' and not android.get('error') and recent
    add('android', 'Android 測試手機', phone, '最近 30 秒內確認指定手機已授權' if phone else '請接入、授權、指定手機，再重新偵測；快照超過 30 秒需重查')
    gateway = next((x for x in devices.get('roles', []) if x.get('role') == 'gateway'), {})
    add('gateway', 'Gateway 身分與通訊', False, '已登記且 USB 在場；通訊與 BLE 尚未驗證' if gateway.get('status') == 'online' and not devices.get('error') else '需確認 Gateway 板型、登記裝置並驗證通訊')
    add('stm8_target', 'STM8 實體目標', False, 'USB 候選裝置不等於 SWIM、晶片與接線已驗證')
    add('dac', 'DAC8568 實體訊號', False, '目前 mock；待到貨後核對供電、接線與校正')
    add('ble', '手機真 BLE 流程', False, 'App 啟動與截圖不等於 BLE 回歸通過')
    return {'schema':1,'generated_at':now,'scope':'preparation_snapshot',
            'model_start_ready':bool(fresh and stopped and not active), 'hil_ready':False,
            'checks':checks, 'ready_count':sum(c['ready'] for c in checks),
            'note':'僅供準備檢視，不會連線、啟動 App、編譯、燒錄或執行測試。各項快照非同時量測；開始操作仍重新確認裝置。',
            'observed':{'motor_port':motor.get('port'),'motor_age_s':motor.get('age_s'),
                        'android_scanned_at':scan_time,'stm8_scanned_at':stm8.get('scanned_at'),
                        'stm8_repository':stm8.get('repository_url'),'stm8_revision':artifact.get('revision')}}
