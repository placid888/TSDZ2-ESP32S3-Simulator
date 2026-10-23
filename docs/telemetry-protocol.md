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
