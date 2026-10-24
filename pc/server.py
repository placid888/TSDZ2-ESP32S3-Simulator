"""Local USB serial bridge. No cloud service, simulated PC data, or auto-RUN."""
import argparse
import csv
import io
import json
import math
import threading
import time
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

import serial
from serial.tools import list_ports
from scenarios import ScenarioRunner
from report_store import ReportStore
from report_compare import compare_reports
from report_bundle import make_bundle
from devices import DeviceRegistry
from android_device import AndroidMonitor
from android_capture import CaptureStore, capture_selected
from ride_plan import read_plan, save_plan
from stm8_workbench import Stm8Workbench
from stm8_artifacts import Stm8Artifacts
from android_app import launch_selected
from readiness import preparation
from provenance import source_identity
PC_IDENTITY = source_identity()

RANGES = {"BATTERY": (0, 60), "CADENCE": (0, 200), "TORQUE": (0, 200),
          "GRADE": (-30, 30), "PWM": (0, 100), "BRAKE": (0, 1)}
FIELDS = ["time", "running", "rpm", "current_a", "battery_v", "cadence_rpm",
          "torque_nm", "grade_percent", "pwm_percent", "brake", "fault",
          "effective_cadence_rpm", "effective_torque_nm", "effective_brake"]
FAULTS = ('NONE','PAS_LOSS','TORQUE_ZERO','BRAKE_STUCK')


def validate_settings(settings):
    if not isinstance(settings, dict) or not settings:
        raise ValueError("請提供設定值")
    result = []
    for name, value in settings.items():
        if name not in RANGES or isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("未知參數或數值格式錯誤")
        lo, hi = RANGES[name]
        if not math.isfinite(value) or not lo <= value <= hi or (name == "BRAKE" and value not in (0, 1)):
            raise ValueError(f"{name} 必須介於 {lo} 與 {hi}")
        result.append(f"SET {name} {value:g}")
    return result


class BenchLink:
    def __init__(self):
        self.lock = threading.RLock()
        self.port = None
        self.port_name = None
        self.telemetry = None
        self.device_info = None
        self.pc_identity = PC_IDENTITY
        self.updated = 0
        self.samples = deque(maxlen=1200)
        self.events = deque(maxlen=60)
        self.error = None
        self.failures = 0

    def event(self, message):
        self.events.append({"time": time.time(), "message": message})

    def _line(self, command, telemetry=False, info=False):
        if not self.port:
            raise ValueError("尚未連接 ESP32")
        self.port.write((command + "\n").encode("ascii"))
        self.port.flush()
        deadline = time.monotonic() + 1.5
        while time.monotonic() < deadline:
            raw = self.port.read_until(b"\n", 2048)
            if not raw:
                continue
            line = raw.decode("utf-8", errors="replace").strip()
            if line.startswith("ERR"):
                raise ValueError("ESP32: " + line)
            if info and line.startswith('{'):
                value=json.loads(line)
                if (not isinstance(value,dict) or value.get('type')!='device_info' or value.get('protocol')!=1
                    or not isinstance(value.get('version'),str) or not isinstance(value.get('elf_sha256'),str)
                    or len(value['elf_sha256'])!=64 or any(c not in '0123456789abcdef' for c in value['elf_sha256'])):
                    raise ValueError('ESP32 回報無效版本資訊')
                return value
            if telemetry and line.startswith("{"):
                value = json.loads(line)
                if value.get("type") != "telemetry" or value.get("protocol") != 1:
                    raise ValueError("不相容的 ESP32 telemetry 版本")
                required = ("rpm", "battery_v", "current_a", "cadence_rpm", "torque_nm", "pwm_percent")
                if any(not isinstance(value.get(k), (int, float)) or not math.isfinite(value[k]) for k in required):
                    raise ValueError("ESP32 回報無效數據")
                return value
            if not telemetry and not info and line == "OK":
                return
        raise TimeoutError("ESP32 回應逾時；請確認已燒入支援 TELEMETRY 的串口版韌體")

    def _refresh(self):
        data = self._line("TELEMETRY", telemetry=True)
        previous_count=(self.telemetry or {}).get('link_timeout_count',0)
        if data.get('link_timeout') and data.get('link_timeout_count',0)>previous_count:
            self.event('ESP32 已因通訊逾時自動停止；需手動套用並 RUN')
        self.telemetry = data
        self.updated = time.monotonic()
        self.samples.append({"time": time.time(), **data})
        self.error = None
        self.failures = 0

    def connect(self, name):
        if name not in [p.device for p in list_ports.comports()]:
            raise ValueError("找不到這個串口，請重新整理")
        with self.lock:
            if self.port:
                raise ValueError("請先中斷目前連線")
            port = serial.Serial()
            port.port, port.baudrate = name, 115200
            port.timeout, port.write_timeout = 0.15, 1
            port.dtr = port.rts = False
            port.open()
            self.port, self.port_name = port, name
            self.telemetry = None
            self.device_info = None
            self.samples.clear()
            try:
                time.sleep(0.3)
                self._refresh()
                if self.telemetry.get("info_api")==1:
                    self.device_info=self._line("INFO",info=True)
                self.event(f"已連接 {name} · 115200 baud · protocol 1")
            except Exception:
                port.close()
                self.port, self.port_name = None, None
                raise

    def disconnect(self):
        with self.lock:
            if self.port:
                try:
                    self._line("STOP")
                    self.event("ESP32 已確認 STOP，已中斷連線")
                except Exception as exc:
                    self.event(f"中斷連線；STOP 未確認：{exc}")
                self.port.close()
                self.port = None
                self.port_name = None

    def apply(self, settings):
        commands = validate_settings(settings)  # validate the whole request first
        with self.lock:
            try:
                for command in commands:
                    self._line(command)
                self._refresh()
                self.event("已套用 " + " / ".join(commands))
            except Exception:
                if self.port:
                    try:
                        self._line("STOP")
                    except Exception:
                        pass
                raise

    def command(self, command):
        if command not in ("RUN", "STOP"):
            raise ValueError("不支援的命令")
        with self.lock:
            if command == "RUN" and (not self.telemetry or time.monotonic() - self.updated > 2.5):
                raise ValueError("數據已過期，請重新連接後再 RUN")
            self._line(command)
            self.event("ESP32 已確認 " + command)
            self._refresh()

    def fault(self, name):
        if name not in FAULTS:
            raise ValueError('不支援的模型故障')
        with self.lock:
            if not self.telemetry or self.telemetry.get('fault_api') != 1:
                raise ValueError('裝置韌體尚未支援 fault-v1')
            self._line('SET FAULT '+name)
            self._refresh()
            self.event('模型故障 '+name)

    def snapshot(self):
        with self.lock:
            age = time.monotonic() - self.updated if self.updated else None
            return {"connected": bool(self.port), "port": self.port_name,
                    "age_s": age, "stale": age is None or age > 2.5,
                    "device_info":self.device_info,"pc_identity":self.pc_identity,
                    "telemetry": self.telemetry, "samples": list(self.samples)[-240:],
                    "events": list(self.events), "error": self.error}

    def poll(self):
        while True:
            time.sleep(0.25)
            with self.lock:
                if self.port:
                    try:
                        self._refresh()
                    except Exception as exc:
                        self.error = str(exc)
                        self.failures += 1
                        if self.failures >= 3:
                            self.event("連線中斷：" + self.error + "；無法確認裝置停止狀態")
                            self.port.close()
                            self.port, self.port_name = None, None


LINK = BenchLink()
RUNNER = ScenarioRunner(LINK)
REPORTS = ReportStore(RUNNER.reports)
STATIC = Path(__file__).with_name("web")
STM8 = Stm8Workbench(Path(__file__).with_name("local")/"stm8_project.json")
STM8_BUILD = Stm8Artifacts(Path(__file__).with_name('local')/'stm8-build')
CAPTURES = CaptureStore(Path(__file__).with_name("local")/"android_captures")
ANDROID = AndroidMonitor(Path(__file__).with_name("local")/"android_target.json")
RIDE_PLAN = Path(__file__).with_name("local")/"ride_plan.json"
DEVICES = DeviceRegistry(Path(__file__).with_name("local")/"devices.json")


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def respond(self, data, status=200, kind="application/json; charset=utf-8", filename=None):
        if isinstance(data, (dict, list)):
            data = json.dumps(data, allow_nan=False, ensure_ascii=False).encode("utf-8")
        elif isinstance(data, str):
            data = data.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(data)))
        if filename:self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(data)

    def allowed(self):
        host = self.headers.get("Host", "")
        return host in (f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}")

    def do_GET(self):
        if not self.allowed():
            return self.respond({"error": "Invalid host"}, 403)
        path = urlparse(self.path).path
        if path in ('/api/readiness', '/api/readiness/report'):
            motor = LINK.snapshot()
            stm8 = STM8.snapshot()
            result = preparation(motor, ANDROID.snapshot(), stm8,
                STM8_BUILD.snapshot(stm8['repository_url']),
                DEVICES.snapshot(list_ports.comports(), motor['port']), RUNNER.snapshot()['active'])
            return self.respond(result, filename='bench-preparation.json' if path.endswith('/report') else None)
        if path == '/api/stm8/state':
            return self.respond(STM8.snapshot())
        if path == '/api/stm8/build':
            return self.respond(STM8_BUILD.snapshot(STM8.snapshot()['repository_url']))
        if path == '/api/stm8/build/report':
            try:
                return self.respond(STM8_BUILD.report(), filename='stm8-offline-build.json')
            except (OSError, ValueError, TypeError, AttributeError, KeyError):
                return self.respond({'error': '尚無可驗證的 STM8 離線編譯報告'}, 404)
        if path == '/api/stm8/scan':
            return self.respond(STM8.scan())
        if path == '/api/android/captures':
            return self.respond(CAPTURES.listing())
        if path.startswith('/api/android/captures/'):
            name=path[len('/api/android/captures/'):]
            try:
                if name.endswith('.png'):return self.respond(CAPTURES.image(name[:-4]),kind='image/png')
                if name.endswith('.json'):return self.respond(CAPTURES.read(name[:-5]))
            except (OSError,ValueError,AttributeError):pass
            return self.respond({'error':'截圖不存在或格式無效'},404)
        if path == '/api/android/state':
            return self.respond(ANDROID.snapshot())
        if path == '/api/android/scan':
            return self.respond(ANDROID.scan())
        if path == '/api/ride-plan':
            try:return self.respond(read_plan(RIDE_PLAN))
            except (OSError,ValueError,TypeError):return self.respond({'error':'保存的流程無法讀取，原檔未修改'},400)
        if path == '/api/devices':
            return self.respond(DEVICES.snapshot(list_ports.comports(),LINK.port_name))
        if path.startswith('/api/bundle/'):
            try:
                name=path[len('/api/bundle/'):]
                report=REPORTS.read(name)
                return self.respond(make_bundle(report),kind='application/zip',filename=name[:-5]+'.zip')
            except (OSError,ValueError,TypeError,OverflowError):
                return self.respond({'error':'報告不存在或格式無效，無法建立測試包'},404)
        if path == '/api/compare':
            try:
                query=parse_qs(urlparse(self.path).query)
                if set(query)!= {'baseline','candidate'} or any(len(v)!=1 for v in query.values()):
                    raise ValueError('請選擇基準與比較報告')
                a,b=query['baseline'][0],query['candidate'][0]
                if a==b:raise ValueError('請選擇兩份不同報告')
                result=compare_reports(REPORTS.read(a),REPORTS.read(b))
                return self.respond({**result,'baseline_id':a,'candidate_id':b})
            except OSError:
                return self.respond({'error':'找不到報告'},404)
            except (ValueError,TypeError,KeyError,AttributeError) as exc:
                return self.respond({'error':str(exc)},400)
        if path == '/api/reports':
            return self.respond(REPORTS.listing())
        if path.startswith('/api/reports/'):
            try:
                return self.respond(REPORTS.read(path[len('/api/reports/'):]))
            except (OSError, ValueError, TypeError):
                return self.respond({'error':'報告不存在或格式無效'},404)
        if path == "/api/state":
            return self.respond({**LINK.snapshot(), 'test': RUNNER.snapshot()})
        if path == "/api/test/report":
            report = RUNNER.snapshot(include_samples=True)['report']
            if not report:
                return self.respond({'error':'尚無自動測試報告'}, 404)
            return self.respond(report)
        if path == '/api/test/points.csv':
            report = RUNNER.snapshot()['report']
            if not report or report.get('kind')!='sweep':
                return self.respond({'error':'尚無掃描結果'},404)
            content = io.StringIO(newline='')
            writer = csv.DictWriter(content,fieldnames=['voltage_v','pwm_percent','grade_percent','rpm','current_a','battery_v','passed'])
            writer.writeheader()
            writer.writerows({**{k:p[k] for k in ('voltage_v','pwm_percent','grade_percent','passed')},
                              **{k:p['observed'][k] for k in ('rpm','current_a','battery_v')}} for p in report['points'])
            return self.respond(content.getvalue(),kind='text/csv; charset=utf-8')
        if path == "/api/ports":
            return self.respond([{"device": p.device, "description": p.description} for p in list_ports.comports()])
        if path == "/api/export.csv":
            with LINK.lock:
                rows = list(LINK.samples)
            content = io.StringIO(newline="")
            writer = csv.DictWriter(content, fieldnames=FIELDS, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
            return self.respond(content.getvalue(), kind="text/csv; charset=utf-8")
        files = {"/": "index.html", "/app.js": "app.js", "/ride.js": "ride.js", "/android.js": "android.js", "/stm8.js": "stm8.js", "/style.css": "style.css"}
        if path not in files:
            return self.respond({"error": "Not found"}, 404)
        kind = {"/": "text/html", "/app.js": "text/javascript", "/ride.js": "text/javascript", "/android.js": "text/javascript", "/stm8.js": "text/javascript", "/style.css": "text/css"}[path]
        return self.respond((STATIC / files[path]).read_bytes(), kind=kind + "; charset=utf-8")

    def do_POST(self):
        origin = self.headers.get("Origin")
        if not self.allowed() or (origin and origin != "http://" + self.headers.get("Host", "")):
            return self.respond({"error": "Invalid origin"}, 403)
        try:
            length = int(self.headers.get("Content-Length", 0))
            if not 0 < length <= 16384 or not self.headers.get("Content-Type", "").startswith("application/json"):
                raise ValueError("Invalid request")
            data = json.loads(self.rfile.read(length))
            if not isinstance(data, dict):
                raise ValueError("JSON request must be an object")
            path = urlparse(self.path).path
            if path == '/api/stm8/source':
                with LINK.lock:
                    if RUNNER.active:raise ValueError('請先結束正在執行的測試')
                return self.respond({'ok':True,'stm8':STM8.save_source(data.get('repository_url'))})
            if path == '/api/android/capture':
                with LINK.lock:
                    if RUNNER.active:raise ValueError('請先結束正在執行的自動測試')
                return self.respond({'ok':True,'capture':capture_selected(ANDROID,CAPTURES,PC_IDENTITY)})
            if path == '/api/android/launch':
                with LINK.lock:
                    if RUNNER.active:raise ValueError('請先結束正在執行的自動測試')
                return self.respond({'ok':True,'app':launch_selected(ANDROID)})
            if path == '/api/android/select':
                with LINK.lock:
                    if RUNNER.active:raise ValueError('請先結束正在執行的測試')
                return self.respond({'ok':True,'android':ANDROID.select(data.get('serial'))})
            with LINK.lock:
                if RUNNER.active and path not in ('/api/test/cancel','/api/command'):
                    raise ValueError('自動測試進行中，請先中止並等待停止確認')
                if path == '/api/ride-plan':
                    save_plan(RIDE_PLAN,data.get('plan'))
                    LINK.event('已保存騎乘流程；未操作裝置')
                elif path == '/api/devices/assign':
                    DEVICES.assign(data.get('role'),data.get('port'),list_ports.comports())
                    LINK.event('已保存裝置角色；未操作串口')
                elif path == '/api/devices/clear':
                    DEVICES.clear(data.get('role'))
                    LINK.event('已解除裝置角色；未操作串口')
                elif path == "/api/connect":
                    role=DEVICES.role_for(data.get('port'),list_ports.comports())
                    if role and role!='motor':raise ValueError('此裝置登記為其他角色，請核對後再連接模擬器')
                    LINK.connect(data.get("port"))
                elif path == "/api/disconnect":
                    LINK.disconnect()
                elif path == "/api/settings":
                    LINK.apply(data.get("settings"))
                elif path == "/api/command":
                    if RUNNER.active:
                        if data.get('command') != 'STOP':
                            raise ValueError('自動測試進行中，僅接受 STOP')
                        RUNNER.cancel()
                    LINK.command(data.get("command"))
                elif path == '/api/fault':
                    LINK.fault(data.get('fault'))
                elif path == '/api/test/start':
                    RUNNER.start(data.get('kind','sequence'),data.get('sweep'),data.get('cycles',5),data.get('ride'))
                elif path == '/api/test/cancel':
                    RUNNER.cancel()
                    LINK.command('STOP')
                else:
                    return self.respond({"error": "Not found"}, 404)
                result = {"ok": True, "state": {**LINK.snapshot(), 'test': RUNNER.snapshot()}}
            self.respond(result)
        except (ValueError, TimeoutError, serial.SerialException, OSError) as exc:
            self.respond({"error": str(exc)}, 400)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    threading.Thread(target=LINK.poll, daemon=True).start()
    print(f"TSDZ Virtual Bench http://127.0.0.1:{args.port}", flush=True)
    try:
        server.serve_forever()
    finally:
        LINK.disconnect()
        server.server_close()


if __name__ == "__main__":
    main()
