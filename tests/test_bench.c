#include "bench_model.h"
#include "dac8568.h"
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
/* Checks remain active for Release builds. */
#define CHECK(x) do { if (!(x)) { fprintf(stderr, "FAIL line %d: %s\n", __LINE__, #x); exit(1); } } while (0)
static unsigned spi_calls;
static uint32_t sent;
static esp_err_t transport_result;
esp_err_t spi_device_transmit(spi_device_handle_t dev, spi_transaction_t *t) {
    (void)dev; spi_calls++; CHECK(t->length == 32);
    sent = 0;
    for (int i = 0; i < 4; ++i) sent = (sent << 8) | t->tx_data[i];
    return transport_result;
}
esp_err_t spi_bus_initialize(int h, const spi_bus_config_t *b, int d) { (void)h; (void)b; (void)d; spi_calls++; return ESP_OK; }
esp_err_t spi_bus_add_device(int h, const spi_device_interface_config_t *c, spi_device_handle_t *d) { (void)h; (void)c; (void)d; return ESP_OK; }
esp_err_t spi_bus_free(int h) { (void)h; return ESP_OK; }
static char reply[512];
static void command(VirtualBench *b, const char *s) { CHECK(bench_command(b, s, reply, sizeof(reply))); }
int main(void) {
    VirtualBench b; bench_init(&b);
    CHECK(!b.running && b.controller.fake);
    command(&b, "SET PWM 40");
    bench_step(&b, 0.01f); CHECK(b.motor.rpm == 0);
    command(&b, "SET BATTERY 48"); command(&b, "SET CADENCE 80");
    command(&b, "SET TORQUE 60"); command(&b, "RUN");
    for (int i = 0; i < 1000; ++i) bench_step(&b, 0.01f);
    CHECK(b.motor.rpm > 1500 && b.motor.rpm < 1600);
    CHECK(b.battery.terminal_v < 48 && b.motor.current_a > 0);
    CHECK(fabsf(b.motor.rpm - 1600 * b.battery.terminal_v / 48) < 3);
    CHECK(fabsf(b.signals.pas_hz - 16) < 0.01f);
    CHECK(b.signals.hall != 0 && b.signals.hall != 7);
    float flat_rpm = b.motor.rpm;
    command(&b, "SET GRADE 20");
    for (int i = 0; i < 1000; ++i) bench_step(&b, 0.01f);
    CHECK(b.motor.rpm < flat_rpm);
    const char *invalid[] = {"SET PWM nan", "SET PWM inf", "SET PWM -1", "SET PWM 101", "SET PWM 40junk", "SET PWM 1 extra", "SET BRAKE .5", "SET BATTERY 61", "SET CADENCE 201", "SET TORQUE -1", "SET GRADE -31", "RUN extra", "", "SET UNKNOWN 1"};
    for (unsigned i = 0; i < sizeof(invalid)/sizeof(invalid[0]); ++i) {
        VirtualBench before = b;
        CHECK(!bench_command(&b, invalid[i], reply, sizeof(reply)));
        CHECK(!memcmp(&before, &b, sizeof(b)));
    }
    command(&b, "SET BRAKE 1"); bench_step(&b, 0.01f);
    CHECK(b.motor.current_a == 0 && b.signals.brake);
    command(&b, "STOP"); CHECK(!b.running && b.motor.rpm == 0 && b.signals.hall == 0);
    CHECK(b.controller.pwm_percent == 0 && b.battery.terminal_v == 48);
    command(&b, "STATUS"); CHECK(strstr(reply, "input=fake"));
    command(&b, "SET BATTERY 0"); command(&b, "SET PWM 80"); command(&b, "RUN");
    bench_step(&b, 0.01f);
    CHECK(b.motor.current_a == 0 && b.motor.rpm == 0 && b.battery.terminal_v == 0);
    command(&b, "STOP");
    uint16_t codes[8] = {0, 1, 2, 3, 4, 5, 6, 65535};
    char telemetry[768];
    CHECK(bench_telemetry(&b, "mock", codes, telemetry, sizeof(telemetry)));
    CHECK(strstr(telemetry, "\"type\":\"telemetry\",\"protocol\":1"));
    CHECK(strstr(telemetry, "\"running\":false"));
    CHECK(strstr(telemetry, "\"dac_codes\":[0,1,2,3,4,5,6,65535]"));
    CHECK(strstr(telemetry, "\"battery_open_circuit_v\":0.000"));
    CHECK(telemetry[0] == '{' && telemetry[strlen(telemetry)-1] == '}');
    CHECK(!strchr(telemetry, '\n'));
    CHECK(!bench_telemetry(&b, "mock", codes, telemetry, 10) && telemetry[0] == 0);
    CHECK(!bench_telemetry(&b, "invalid\"backend", codes, telemetry, sizeof(telemetry)) && telemetry[0] == 0);
    command(&b, "RUN"); command(&b, "SET BRAKE 1");
    CHECK(bench_telemetry(&b, "disabled", codes, telemetry, sizeof(telemetry)));
    CHECK(strstr(telemetry, "\"running\":true") && strstr(telemetry, "\"brake\":true"));
    CHECK(bench_telemetry(&b, "spi-zero-only", codes, telemetry, sizeof(telemetry)));
    Dac8568 d; CHECK(dac8568_init(&d, DAC_MOCK) == ESP_OK);
    CHECK(spi_calls == 0 && d.last_frame == 0x08000001);
    for (unsigned ch = 0; ch < 8; ++ch) {
        CHECK(dac8568_write(&d, ch, 0xffff) == ESP_OK);
        CHECK(d.last_frame == (0x030ffff0u | (ch << 20)) && d.codes[ch] == 65535);
    }
    CHECK(dac8568_write(&d, 8, 0) == ESP_ERR_INVALID_ARG);
    CHECK(dac8568_zero(&d) == ESP_OK);
    for (int ch = 0; ch < 8; ++ch) CHECK(d.codes[ch] == 0);
    CHECK(dac8568_init(&d, DAC_DISABLED) == ESP_OK);
    CHECK(dac8568_write(&d, 0, 123) == ESP_OK && d.codes[0] == 0 && spi_calls == 0);
    CHECK(dac8568_init(&d, DAC_SPI) == ESP_ERR_INVALID_ARG && spi_calls == 0);
    /* Exercise real transport packing with a fake device. */
    d.mode = DAC_SPI;
    CHECK(dac8568_write(&d, 7, 0xabcd) == ESP_OK && sent == 0x037abcd0);
    transport_result = 99;
    CHECK(dac8568_write(&d, 7, 1) == 99 && d.codes[7] == 0xabcd);
    puts("PASS model dynamics/voltage coupling, CLI validation/STOP, telemetry records/bounds, DAC channels/packing/modes/errors");
    return 0;
}
