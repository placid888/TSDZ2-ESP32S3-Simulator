# TSDZ Virtual Bench — Phase 1

## Repository inspection

Starting commit: `e98c186`, only remote branch `main`, initially clean checkout.
The existing firmware uses ESP-IDF C, NimBLE remote overrides and a UART1
29-byte simulator packet. It is not a controller PWM capture implementation.
README and CI mention v5.1, while the development container floats to latest.
There was no PlatformIO configuration or test suite. Keep ESP-IDF rather than
introducing a second build system. No additional skill installation is needed.

The default build retains legacy BLE/UART mode. The new bench mode bypasses
legacy startup entirely: no legacy UART traffic is sent to a real STM8.
The old packet format is retained, not asserted to be a verified TSDZ protocol.

## Build and run

Use an activated ESP-IDF shell. Both modes target ESP32-S3.

```sh
# Legacy mode (fresh configuration)
idf.py -B build-legacy -D SDKCONFIG=build-legacy/sdkconfig build

# Bench mode (fresh configuration, mock DAC)
idf.py -B build-bench -D SDKCONFIG=build-bench/sdkconfig -D SDKCONFIG_DEFAULTS="sdkconfig.defaults;sdkconfig.bench" build
idf.py -B build-bench -D SDKCONFIG=build-bench/sdkconfig flash monitor
```

Alternatively enable Virtual Bench in `idf.py menuconfig`. Select mock,
disabled, or SPI DAC backend there. Use separate build/config directories so
switching modes does not silently reuse the other configuration.
For a CH343/CP210x USB-UART bridge, replace `sdkconfig.bench` with
`sdkconfig.bench-uart` in the fresh-build command above. That preset uses the
default UART0 console at 115200 baud; the USB Serial/JTAG preset needs the
board's native USB connection for CLI input.
The USB Serial/JTAG console carries newline-terminated, uppercase commands.
CR, LF and CRLF are accepted. Maximum line length is 127 bytes; oversized lines
are discarded through the next newline. Invalid commands do not mutate state.

```text
SET BATTERY 48
SET CADENCE 80
SET TORQUE 60
SET GRADE 5
SET BRAKE 0
SET PWM 40
RUN
STATUS
STOP
```

| SET key | Unit | Allowed range |
|---|---|---|
| BATTERY | open-circuit V | 0–60 |
| CADENCE | crank RPM | 0–200 |
| TORQUE | rider Nm | 0–200 |
| GRADE | percent | -30–30 |
| BRAKE | boolean | 0 or 1 |
| PWM | fake controller duty percent | 0–100 |

Starts stopped. RUN starts integration. STOP immediately clears motor speed,
current, PWM, logical signals and DAC codes; scenario settings remain available.
BRAKE cuts motor current on the next model step and decelerates the model.
This is a software simulator, not an emergency-stop circuit.

## Components and model limits

`VirtualMotor`, `VirtualBattery`, `VirtualRider`, `SignalGenerator` and
`ControllerInput` are portable structs in `bench_model.h`. Model and CLI state
share a mutex. The task integrates from measured elapsed time, capped at 100 ms
after a scheduling gap. Motor dynamics are an illustrative first-order plant;
grade changes load, fake PWM and battery voltage change target RPM, and current
causes battery voltage sag. No regeneration or measured motor calibration.
Rider cadence drives PAS; torque is an independent sensor stimulus, not a second
motor power source. Wheel speed assumes a configurable example gear ratio.

SignalGenerator calculates Hall sequence 001/101/100/110/010/011, PAS, wheel and
brake states/frequencies. **Phase 1 uses logical signals only, not timed GPIO
waveforms.** A task snapshot cannot reproduce every high-frequency Hall edge.
Timer/RMT hardware edge generation and real PWM capture are later stages, after
confirmed wiring and timing requirements. `ControllerInput.fake` is currently
always true. No STM8 final pin mapping or unknown protocol is invented.

## Board and DAC8568

All GPIO assignments are centralized in `main/board_config.h`. Existing legacy
TX17/RX18/LED48 assignments are retained; new DAC/Hall/PAS/Wheel/Brake/PWM pins
are -1 (unassigned). No new GPIO is driven by bench mode.

| Bench channel | DAC output | Purpose |
|---|---|---|
| CH1 | A / address 0 | battery current |
| CH2 | B / address 1 | torque |
| CH3 | C / address 2 | battery voltage |
| CH4 | D / address 3 | throttle (zero) |
| CH5–8 | E–H / addresses 4–7 | reserved (zero) |

Driver supports all eight channels, unsigned 16-bit codes, software reset,
internal reference enable, per-channel write/update and broadcast zero.
32-bit MSB-first SPI frames use command bits 27:24, channel 23:20 and code 19:4.
SPI mode 1 at 1 MHz samples DIN on falling edges. The LDAC mask overrides
physical LDAC for all channels. For 16-pin parts hold CLR high; LDAC can be high.
See [TI DAC8568 datasheet, sections 8.3 and 8.5](https://www.ti.com/lit/ds/symlink/dac8568.pdf).

Mock mode records codes and the last frame without accessing SPI. Its display
scales are illustrative: 40 A, 200 Nm and 60 V correspond to code 65535.
These are **not STM8 electrical transfer functions**. Disabled mode performs no
transport or code updates. SPI mode rejects unassigned/duplicate pins; it is
implemented but kept at zero by the bench application until calibrated sensor
transfer functions are supplied. Do not wire its output to controller ADCs
using the mock scales. Internal 2.5 V reference gives nominal 5 V full scale;
actual module supply, logic thresholds, ADC limits and conditioning must be
confirmed before connecting hardware. No analog output hardware is validated.

## Verification and next stages

Host tests exercise acceleration, grade load, voltage sag, PAS frequency,
braking/STOP, malformed/nonfinite/range CLI inputs without partial changes,
all DAC channels, frame byte order, mock/disabled behavior, invalid pins and
transport failure propagation. Run on Linux/macOS with a C compiler:

```sh
cmake -S tests -B build-host
cmake --build build-host
ctest --test-dir build-host --output-on-failure
```

Windows with Visual Studio: configure with its generator, build with
`--config Release`, and pass `-C Release` to ctest.

Next: confirm exact ESP32-S3/module/STM8 interfaces, add calibrated sensor
transfers and timer-based signal edges, scope-test DAC and digital outputs,
then implement real PWM capture. Only after that connect STM8 and run a closed
loop HIL scenario. BLE gateway and Android/ADB integration remain later stages.
