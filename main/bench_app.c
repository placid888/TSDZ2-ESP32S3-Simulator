#include "bench_app.h"
#include "bench_model.h"
#include "dac8568.h"
#include "board_config.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/semphr.h"
#include "esp_timer.h"
#include "esp_log.h"
#include <stdio.h>
#include <math.h>
#include <string.h>

static VirtualBench bench;
static Dac8568 dac;
static SemaphoreHandle_t mutex;

/* Mock-only normalized code preview, NOT a TSDZ sensor transfer function.
   Real SPI stays at zero until calibrated sensor mappings are implemented. */
static uint16_t preview_code(float x, float full_scale) {
    return (uint16_t)lroundf(fminf(1, fmaxf(0, x / full_scale)) * 65535);
}
static void model_task(void *arg) {
    int64_t previous = esp_timer_get_time();
    while (1) {
        vTaskDelay(pdMS_TO_TICKS(10));
        int64_t now = esp_timer_get_time();
        float dt = (now - previous) / 1000000.0f;
        previous = now;
        xSemaphoreTake(mutex, portMAX_DELAY);
        /* Split long scheduler gaps so model integration stays bounded. */
        dt = fminf(dt, 0.1f);
        bench_step(&bench, dt);
        if (dac.mode == DAC_MOCK && bench.running) {
            dac8568_write(&dac, DAC_BATTERY_CURRENT, preview_code(bench.motor.current_a, 40));
            dac8568_write(&dac, DAC_TORQUE, preview_code(bench.rider.torque_nm, 200));
            dac8568_write(&dac, DAC_BATTERY_VOLTAGE, preview_code(bench.battery.terminal_v, 60));
            dac8568_write(&dac, DAC_THROTTLE, 0);
        }
        xSemaphoreGive(mutex);
    }
}
static void console_task(void *arg) {
    char line[128], reply[512];
    size_t used = 0;
    bool overflow = false;
    while (1) {
        int c = getchar();
        if (c == EOF) { clearerr(stdin); vTaskDelay(pdMS_TO_TICKS(10)); continue; }
        if (c == '\r' || c == '\n') {
            if (overflow) puts("ERR line too long");
            else if (used) {
                line[used] = 0;
                xSemaphoreTake(mutex, portMAX_DELAY);
                bench_command(&bench, line, reply, sizeof(reply));
                if (!bench.running) ESP_ERROR_CHECK(dac8568_zero(&dac));
                puts(reply);
                if (!strncmp(line, "STATUS", 6)) {
                    printf("DAC backend=%s codes=", dac.mode == DAC_MOCK ? "mock" : dac.mode == DAC_SPI ? "spi-zero-only" : "disabled");
                    for (int i = 0; i < 8; ++i) printf("%s%u", i ? "," : "", dac.codes[i]);
                    puts(" GPIO=logical-only");
                }
                xSemaphoreGive(mutex);
            }
            used = 0; overflow = false;
        } else if (c == 0) overflow = true;
        else if (used + 1 < sizeof(line)) line[used++] = (char)c;
        else overflow = true;
    }
}
void bench_app_start(void) {
    bench_init(&bench);
    mutex = xSemaphoreCreateMutex();
    configASSERT(mutex);
    DacMode mode = DAC_MOCK;
#if CONFIG_BENCH_DAC_DISABLED
    mode = DAC_DISABLED;
#elif CONFIG_BENCH_DAC_SPI
    mode = DAC_SPI;
#endif
    ESP_ERROR_CHECK(dac8568_init(&dac, mode));
    configASSERT(xTaskCreate(model_task, "bench_model", 4096, NULL, 5, NULL) == pdPASS);
    configASSERT(xTaskCreate(console_task, "bench_console", 4096, NULL, 4, NULL) == pdPASS);
    ESP_LOGI("BENCH", "Stopped; fake PWM; logical GPIO; SET ... / RUN / STATUS / STOP");
}
