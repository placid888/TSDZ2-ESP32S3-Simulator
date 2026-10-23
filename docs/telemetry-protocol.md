# PC telemetry protocol v1

The bench console accepts UTF-8/ASCII commands terminated by LF or CR. Send
`TELEMETRY` to obtain one JSON object on one line. This read-only command captures
the model and DAC codes under the same mutex. Polling at 5 Hz is recommended for
the PC dashboard; there is no unsolicited telemetry stream.

```json
{"type":"telemetry","protocol":1,"running":false,"input":"fake","pwm_percent":0.00,"battery_v":48.000,"battery_open_circuit_v":48.000,"current_a":0.000,"rpm":0.00,"erps":0.00,"cadence_rpm":0.00,"torque_nm":0.00,"grade_percent":0.00,"brake":false,"hall":0,"pas_hz":0.000,"wheel_hz":0.000,"dac_backend":"mock","dac_codes":[0,0,0,0,0,0,0,0],"gpio":"logical-only"}
```

`battery_v` is terminal voltage after simulated internal resistance;
`battery_open_circuit_v` is the value set with `SET BATTERY`. Terminal voltage
feeds the illustrative first-order speed model. At zero battery voltage the
drive produces no current. Rider torque and cadence remain independently set
sensor stimuli; they do not infer unknown controller assistance behavior.

`brake` reports the requested brake state. `hall` is a logical three-bit Hall
state, with zero while stopped; PAS and wheel fields are logical frequencies.
GPIO output remains disabled. These model constants do not establish the final
TSDZ motor, sensor calibration, wiring, or communication protocol.

`dac_backend` is `mock`, `disabled`, or `spi-zero-only`. `dac_codes` lists CH1
through CH8 as integers from 0 to 65535. Mock codes are normalized previews,
not calibrated sensor voltages. CH1 is battery current, CH2 torque, CH3 battery
voltage, CH4 throttle (currently zero), and CH5–8 reserved. SPI mode remains
zero-only pending calibration.

Other commands retain their existing text replies (`OK` or `ERR ...`). `STATUS`
retains its human-readable two-line output. A PC client must tolerate boot logs,
blank lines, command replies, and unknown fields; only parse JSON objects with
`type` equal to `telemetry` and `protocol` equal to 1 as dashboard snapshots.
Only one command should be outstanding at a time because replies have no
request identifiers. `STOP` clears PWM, motor state, signal outputs, active fault, and DAC
codes; it retains rider settings, battery setting, grade, and requested brake.

## Fault injection extension (`fault_api: 1`)

Protocol 1 telemetry adds `fault_api` (integer 1), `fault` (one of the names
below), `effective_cadence_rpm`, `effective_torque_nm`, and `effective_brake`
(boolean). Existing `cadence_rpm`, `torque_nm`, and `brake` always report the
configured values. Effective values report sensor stimuli after fault injection;
while stopped, signal outputs and DAC codes remain zero regardless of those
configured or effective stimulus values. Clients can use `fault_api` to detect
firmware support before offering fault controls.

`SET FAULT <name>` selects exactly one fault and replies `OK`. Names are
case-sensitive; unknown names, missing names, or extra tokens reply `ERR ...`
without changing any state.

| Name | Effect |
| --- | --- |
| `NONE` | All effective inputs use their configured values. |
| `PAS_LOSS` | Effective cadence is zero; PAS frequency and logical PAS signal are zero. |
| `TORQUE_ZERO` | Effective torque is zero; mock DAC CH2 becomes zero. |
| `BRAKE_STUCK` | Effective brake is true; model drive current is zero and brake deceleration applies. |

Faults preserve configured cadence, torque, and brake. Switching to `NONE`
restores the latest configured values; changing a setting during a fault also
preserves the new value for restoration. `STOP` clears the fault to `NONE`.
PAS loss and zero torque do **not** cut the fake PWM drive: controller assistance
logic remains outside this model until its actual behavior is established.
Model signals and mock codes refresh on the next model tick (normally 10 ms).
## 通訊中斷自動停止（link watchdog）

ESP32 在 RUNNING 時若連續 5000 ms 未收到有效完整指令，會在模型工作迴圈自動執行 STOP：PWM、轉速、電流、邏輯訊號及故障清除，DAC 八通道歸零。計時使用 ESP32 單調時鐘，不受模型 dt 上限影響。有效 SET/RUN/STOP/STATUS/TELEMETRY 更新通訊時間；錯誤、過長或不完整指令不更新。

TELEMETRY 增加 `watchdog_ms:5000`、`link_timeout:boolean`、`link_timeout_count:number`。逾時標記保留至下一次明確 RUN；普通查詢、STOP 或重新連線不會清除標記或重新啟動。次數每次開機歸零。RUN 時 PWM 已歸零，必須重新設定後才有驅動。

PC 服務會持續查詢 ESP32，所以只關閉網頁不會觸發停止；應使用 STOP。手動串口操作時也須在 5 秒內送出有效查詢以維持運轉。此機制屬於模型韌體功能，尚未接入實體 STM8/DAC 感測器電路。
## 裝置版本 INFO

`INFO`（不接受其他參數）回傳單行 JSON：type=device_info、protocol=1、project、version、idf_version、build_date、build_time、elf_sha256。版本取自 ESP-IDF 應用程式描述，elf_sha256 是編譯 ELF 的完整 SHA-256。它不是燒錄 binary 檔案的 SHA-256。INFO 是有效通訊，更新 5 秒通訊保護時間，不會自行 RUN。

TELEMETRY 透過 `info_api:1` 宣告支援。PC 連線後僅對支援裝置查詢 INFO；舊韌體仍可連線但無版本資訊。
