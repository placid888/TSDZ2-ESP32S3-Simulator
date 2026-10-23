#pragma once

/* Existing legacy UART wiring only; these are NOT STM8 HIL assignments. */
#define BOARD_LEGACY_TX 17
#define BOARD_LEGACY_RX 18
#define BOARD_RGB_LED 48

/* Unassigned until the actual board and interface circuitry are verified. */
#define BOARD_DAC_SCLK (-1)
#define BOARD_DAC_MOSI (-1)
#define BOARD_DAC_SYNC (-1)
#define BOARD_HALL_A (-1)
#define BOARD_HALL_B (-1)
#define BOARD_HALL_C (-1)
#define BOARD_PAS (-1)
#define BOARD_WHEEL (-1)
#define BOARD_BRAKE (-1)
#define BOARD_CONTROLLER_PWM (-1)

/* Illustrative model parameters, not measured TSDZ motor constants. */
#define BENCH_POLE_PAIRS 8
#define BENCH_PAS_PULSES 12
#define BENCH_WHEEL_METERS 2.1f
#define BENCH_GEAR_RATIO 20.0f

enum bench_dac_channel {
    DAC_BATTERY_CURRENT = 0, /* CH1 / A */
    DAC_TORQUE = 1,          /* CH2 / B */
    DAC_BATTERY_VOLTAGE = 2, /* CH3 / C */
    DAC_THROTTLE = 3,        /* CH4 / D */
    DAC_RESERVED_5 = 4, DAC_RESERVED_6, DAC_RESERVED_7, DAC_RESERVED_8
};
