#pragma once
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>

typedef struct { float rpm, current_a, erps; } VirtualMotor;
typedef struct { float open_circuit_v, terminal_v, current_a, resistance_ohm; } VirtualBattery;
typedef struct { float cadence_rpm, torque_nm; } VirtualRider;
typedef struct { float pwm_percent; bool fake; } ControllerInput;
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
} VirtualBench;

void bench_init(VirtualBench *b);
void bench_step(VirtualBench *b, float dt);
/* Complete line, strict grammar and finite bounded values; no partial mutation. */
bool bench_command(VirtualBench *b, const char *line, char *reply, size_t size);
