"""Launch the upstream TSDZ app on the explicitly selected authorized test phone."""
import subprocess

PACKAGE = 'spider65.ebike.tsdz2_esp32'
COMPONENT = PACKAGE + '/.MainActivity'


def launch_selected(monitor):
    with monitor.lock:
        if monitor.config_error or not monitor.selected:
            raise ValueError('請先指定已授權的測試手機')
        target = monitor.selected
        state = monitor.scan()
        matches = [d for d in state['devices'] if d['serial'] == target]
        if state['error'] or len(matches) != 1 or matches[0]['state'] != 'device':
            raise ValueError('已指定的測試手機未就緒，未啟動 App')
        adb = monitor.finder()
        if not adb: raise ValueError('未找到 ADB')
        try:
            installed = monitor._run(adb, ['-s', target, 'shell', 'pm', 'path', PACKAGE], 6)
            if not any(line.startswith('package:') for line in installed.splitlines()):
                raise ValueError('測試手機尚未安裝原作者 TSDZ App；未自動安裝')
            output = monitor._run(adb, ['-s', target, 'shell', 'am', 'start', '-W', '-n', COMPONENT], 10)
        except subprocess.TimeoutExpired:
            raise ValueError('App 啟動查詢逾時，手機狀態待確認') from None
        if not any(line.strip() == 'Status: ok' for line in output.splitlines()):
            raise ValueError('Android 未確認 App 啟動成功；請查看手機')
        return {'serial': target, 'package': PACKAGE, 'component': COMPONENT,
                'status': 'started', 'ble_verified': False}
