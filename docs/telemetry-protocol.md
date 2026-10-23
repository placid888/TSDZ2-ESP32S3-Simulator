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
request identifiers. `STOP` clears PWM, motor state, signal outputs, and DAC
codes; it retains rider settings, battery setting, grade, and requested brake.
