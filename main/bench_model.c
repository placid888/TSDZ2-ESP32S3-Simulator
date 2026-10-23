#include "bench_model.h"
#include "board_config.h"
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static float clamp(float x, float lo, float hi) { return fminf(hi, fmaxf(lo, x)); }
static const char *fault_name(BenchFault fault) {
    switch (fault) {
        case BENCH_FAULT_PAS_LOSS: return "PAS_LOSS";
        case BENCH_FAULT_TORQUE_ZERO: return "TORQUE_ZERO";
        case BENCH_FAULT_BRAKE_STUCK: return "BRAKE_STUCK";
        default: return "NONE";
    }
}
float bench_effective_cadence(const VirtualBench *b) {
    return b->fault == BENCH_FAULT_PAS_LOSS ? 0 : b->rider.cadence_rpm;
}
float bench_effective_torque(const VirtualBench *b) {
    return b->fault == BENCH_FAULT_TORQUE_ZERO ? 0 : b->rider.torque_nm;
}
bool bench_effective_brake(const VirtualBench *b) {
    return b->brake || b->fault == BENCH_FAULT_BRAKE_STUCK;
}
void bench_init(VirtualBench *b) {
    memset(b, 0, sizeof(*b));
    b->battery = (VirtualBattery){48, 48, 0, 0.15f};
    b->controller.fake = true;
}
void bench_step(VirtualBench *b, float dt) {
    if (!isfinite(dt) || dt <= 0 || dt > 0.1f) return;
    if (!b->running) return;
    bool brake = bench_effective_brake(b);
    float duty = brake || b->battery.open_circuit_v <= 0 ? 0 : b->controller.pwm_percent / 100.0f;
    /* Simple first-order plant. Grade increases load; no regeneration model. */
    float load = clamp(1 + b->grade_percent * 0.025f, 0.25f, 2);
    float target = duty * 4000 * (b->battery.terminal_v / 48) / load;
    b->motor.rpm += (target - b->motor.rpm) * (1 - expf(-dt / (brake ? 0.15f : 1.5f)));
    b->motor.current_a = duty * (2 + 18 * load * clamp(1 - b->motor.rpm / 4000, 0, 1));
    b->motor.erps = b->motor.rpm / 60 * BENCH_POLE_PAIRS;
    b->battery.current_a = b->motor.current_a;
    b->battery.terminal_v = fmaxf(0, b->battery.open_circuit_v - b->battery.current_a * b->battery.resistance_ohm);
    SignalGenerator *s = &b->signals;
    s->hall_hz = b->motor.erps;
    s->pas_hz = bench_effective_cadence(b) / 60 * BENCH_PAS_PULSES;
    s->wheel_hz = b->motor.rpm / 60 / BENCH_GEAR_RATIO;
    s->hall_phase = fmod(s->hall_phase + s->hall_hz * dt, 1);
    s->pas_phase = fmod(s->pas_phase + s->pas_hz * dt, 1);
    s->wheel_phase = fmod(s->wheel_phase + s->wheel_hz * dt, 1);
    const uint8_t sequence[] = {1, 5, 4, 6, 2, 3};
    s->hall = sequence[(unsigned)(s->hall_phase * 6) % 6];
    s->pas = s->pas_hz > 0 && s->pas_phase < 0.5;
    s->wheel = s->wheel_hz > 0 && s->wheel_phase < 0.5;
    s->brake = brake;
}
bool bench_telemetry(const VirtualBench *b, const char *dac_backend,
                     const uint16_t dac_codes[8], char *reply, size_t size) {
    /* Backend is a closed enum at the wire boundary, never arbitrary JSON text. */
    if (!strcmp(dac_backend, "mock") || !strcmp(dac_backend, "disabled") ||
        !strcmp(dac_backend, "spi-zero-only")) {
        int n = snprintf(reply, size,
            "{\"type\":\"telemetry\",\"protocol\":1,\"running\":%s,\"input\":\"fake\","
            "\"pwm_percent\":%.2f,\"battery_v\":%.3f,\"battery_open_circuit_v\":%.3f,"
            "\"current_a\":%.3f,\"rpm\":%.2f,\"erps\":%.2f,\"cadence_rpm\":%.2f,"
            "\"torque_nm\":%.2f,\"grade_percent\":%.2f,\"brake\":%s,\"hall\":%u,"
            "\"pas_hz\":%.3f,\"wheel_hz\":%.3f,\"dac_backend\":\"%s\","
            "\"dac_codes\":[%u,%u,%u,%u,%u,%u,%u,%u],\"gpio\":\"logical-only\","
            "\"fault_api\":1,\"fault\":\"%s\",\"effective_cadence_rpm\":%.2f,"
            "\"effective_torque_nm\":%.2f,\"effective_brake\":%s}",
            b->running ? "true" : "false", b->controller.pwm_percent,
            b->battery.terminal_v, b->battery.open_circuit_v, b->motor.current_a,
            b->motor.rpm, b->motor.erps, b->rider.cadence_rpm, b->rider.torque_nm,
            b->grade_percent, b->brake ? "true" : "false", b->signals.hall,
            b->signals.pas_hz, b->signals.wheel_hz, dac_backend,
            dac_codes[0], dac_codes[1], dac_codes[2], dac_codes[3],
            dac_codes[4], dac_codes[5], dac_codes[6], dac_codes[7],
            fault_name(b->fault), bench_effective_cadence(b), bench_effective_torque(b),
            bench_effective_brake(b) ? "true" : "false");
        if (n >= 0 && (size_t)n < size) return true;
    }
    if (size) reply[0] = 0;
    return false;
}
bool bench_command(VirtualBench *b, const char *line, char *reply, size_t size) {
    char verb[16], key[16], value[40], extra[2];
    int n = sscanf(line, "%15s %15s %39s %1s", verb, key, value, extra);
    if (n == 1 && !strcmp(verb, "STATUS")) {
        snprintf(reply, size, "OK running=%d input=fake pwm=%.1f battery_v=%.3f current_a=%.3f rpm=%.2f erps=%.2f cadence_rpm=%.1f torque_nm=%.1f grade_pct=%.1f brake=%d hall=%u pas_hz=%.2f wheel_hz=%.2f",
            b->running, b->controller.pwm_percent, b->battery.terminal_v, b->motor.current_a,
            b->motor.rpm, b->motor.erps, b->rider.cadence_rpm, b->rider.torque_nm,
            b->grade_percent, b->brake, b->signals.hall, b->signals.pas_hz, b->signals.wheel_hz);
        return true;
    }
    if (n == 1 && !strcmp(verb, "RUN")) { b->running = true; }
    else if (n == 1 && !strcmp(verb, "STOP")) {
        b->running = false;
        b->fault = BENCH_FAULT_NONE;
        b->controller.pwm_percent = 0;
        b->motor = (VirtualMotor){0};
        b->battery.current_a = 0;
        b->battery.terminal_v = b->battery.open_circuit_v;
        b->signals = (SignalGenerator){0};
    } else if (n == 3 && !strcmp(verb, "SET")) {
        if (!strcmp(key, "FAULT")) {
            BenchFault fault;
            if (!strcmp(value, "NONE")) fault = BENCH_FAULT_NONE;
            else if (!strcmp(value, "PAS_LOSS")) fault = BENCH_FAULT_PAS_LOSS;
            else if (!strcmp(value, "TORQUE_ZERO")) fault = BENCH_FAULT_TORQUE_ZERO;
            else if (!strcmp(value, "BRAKE_STUCK")) fault = BENCH_FAULT_BRAKE_STUCK;
            else goto error;
            b->fault = fault;
            b->signals.brake = b->running && bench_effective_brake(b);
            snprintf(reply, size, "OK"); return true;
        }
        char *end;
        float x = strtof(value, &end);
        if (*end || !isfinite(x)) goto error;
        float *dest = NULL, lo = 0, hi = 0;
        if (!strcmp(key, "BATTERY")) { dest = &b->battery.open_circuit_v; lo = 0; hi = 60; }
        else if (!strcmp(key, "CADENCE")) { dest = &b->rider.cadence_rpm; hi = 200; }
        else if (!strcmp(key, "TORQUE")) { dest = &b->rider.torque_nm; hi = 200; }
        else if (!strcmp(key, "GRADE")) { dest = &b->grade_percent; lo = -30; hi = 30; }
        else if (!strcmp(key, "PWM")) { dest = &b->controller.pwm_percent; hi = 100; }
        else if (!strcmp(key, "BRAKE")) {
            if (x != 0 && x != 1) goto error;
            b->brake = x == 1;
            b->signals.brake = b->running && bench_effective_brake(b);
            snprintf(reply, size, "OK"); return true;
        } else goto error;
        if (x < lo || x > hi) goto error;
        *dest = x;
        b->battery.terminal_v = fmaxf(0, b->battery.open_circuit_v - b->battery.current_a * b->battery.resistance_ohm);
    } else goto error;
    snprintf(reply, size, "OK"); return true;
error:
    snprintf(reply, size, "ERR command or value out of range"); return false;
}
