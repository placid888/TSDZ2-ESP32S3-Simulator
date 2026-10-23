#pragma once
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>

typedef struct { float rpm, current_a, erps; } VirtualMotor;
typedef struct { float open_circuit_v, terminal_v, current_a, resistance_ohm; } VirtualBattery;
typedef struct { float cadence_rpm, torque_nm; } VirtualRider;
typedef struct { float pwm_percent; bool fake; } ControllerInput;
typedef enum { BENCH_FAULT_NONE, BENCH_FAULT_PAS_LOSS, BENCH_FAULT_TORQUE_ZERO,
               BENCH_FAULT_BRAKE_STUCK } BenchFault;
typedef struct {
    double hall_phase, pas_phase, wheel_phase;
    uint8_t hall; bool pas, wheel, brake;
    float hall_hz, pas_hz, wheel_hz;
} SignalGenerator;
typedef struct {
    VirtualMotor motor;
    VirtualBattery battery;
    VirtualRider rider;
    ControllerInput controller;
    SignalGenerator signals;
    float grade_percent;
    bool brake, running;
    BenchFault fault;
    int64_t last_contact_us;
    bool link_timeout;
    uint32_t link_timeout_count;
} VirtualBench;

#define BENCH_LINK_TIMEOUT_MS 5000
void bench_init(VirtualBench *b);
void bench_keepalive(VirtualBench *b, int64_t now_us);
/* Monotonic elapsed time, independent of model integration/scheduler clamp. */
bool bench_check_link(VirtualBench *b, int64_t now_us);
void bench_step(VirtualBench *b, float dt);
float bench_effective_cadence(const VirtualBench *b);
float bench_effective_torque(const VirtualBench *b);
bool bench_effective_brake(const VirtualBench *b);
/* Complete line, strict grammar and finite bounded values; no partial mutation. */
bool bench_command(VirtualBench *b, const char *line, char *reply, size_t size);
/* Atomic snapshot supplied by caller. Returns false and an empty string if the
   buffer cannot hold the complete JSON record (never emits truncated JSON). */
bool bench_telemetry(const VirtualBench *b, const char *dac_backend,
                     const uint16_t dac_codes[8], char *reply, size_t size);
