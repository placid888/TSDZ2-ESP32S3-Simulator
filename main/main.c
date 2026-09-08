#include <stdio.h>
#include <math.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "driver/uart.h"
#include "esp_log.h"
#include "tsdz_utils.h"

#define TAG "TSDZ_SIM"

#define SIM_UART_NUM      UART_NUM_1
#define SIM_TX_PIN        17  // 接至 ESP32_B 的 GPIO 17
#define SIM_RX_PIN        18
#define CT_MSG_ID         0x43
#define CT_OS_MSG_BYTES   29

static float current_speed_kmh = 0.0f;
static uint8_t cadence_rpm = 0;
static uint16_t torque_adc = 120;
static uint8_t duty_cycle = 0;
static uint8_t battery_current_x10 = 0;
static uint32_t wheel_pulses = 0;
static uint16_t crank_pulses = 0;

void sim_uart_init(void) {
    uart_config_t uart_config = {
        .baud_rate = 9600,
        .data_bits = UART_DATA_8_BITS,
        .parity    = UART_PARITY_DISABLE,
        .stop_bits = UART_STOP_BITS_1,
        .flow_ctrl = UART_HW_FLOWCTRL_DISABLE
    };
    ESP_ERROR_CHECK(uart_param_config(SIM_UART_NUM, &uart_config));
    ESP_ERROR_CHECK(uart_set_pin(SIM_UART_NUM, SIM_TX_PIN, SIM_RX_PIN, UART_PIN_NO_CHANGE, UART_PIN_NO_CHANGE));
    ESP_ERROR_CHECK(uart_driver_install(SIM_UART_NUM, 256, 256, 0, NULL, 0));
}

void sim_sender_task(void *pvParameters) {
    TickType_t xLastWakeTime = xTaskGetTickCount();
    const TickType_t xPeriod = pdMS_TO_TICKS(100); // 嚴格 100ms 發送週期
    uint32_t tick_count = 0;

    while (1) {
        tick_count++;
        float time_sec = tick_count * 0.1f;

        // 模擬騎乘物理數據
        cadence_rpm = (uint8_t)(75.0f + 10.0f * sinf(time_sec * 3.14f / 2.0f));
        torque_adc = 120 + (uint16_t)(80.0f * fabsf(sinf(time_sec * 3.14f / 0.4f)));
        duty_cycle = (uint8_t)((torque_adc - 120) * (120 - 20) / 80 + 20);

        if (current_speed_kmh < 25.0f) {
            current_speed_kmh += 0.1f;
        }

        battery_current_x10 = (duty_cycle * 15) / 100;
        wheel_pulses += (uint32_t)(current_speed_kmh * 0.1f);
        crank_pulses += (cadence_rpm > 0) ? 1 : 0;

        // 組裝 29 Bytes 通訊封包
        uint8_t packet[CT_OS_MSG_BYTES] = {0};
        uint16_t speed_x10 = (uint16_t)(current_speed_kmh * 10.0f);
        uint16_t voltage_mv = 48000;
        uint16_t torque_x100 = (torque_adc - 120) * 35;
        uint16_t motor_erps = speed_x10 * 12;

        packet[0] = CT_MSG_ID;
        packet[1] = 0x00;
        packet[2] = voltage_mv & 0xFF;
        packet[3] = (voltage_mv >> 8) & 0xFF;
        packet[4] = battery_current_x10;
        packet[5] = speed_x10 & 0xFF;
        packet[6] = ((speed_x10 >> 8) & 0x07);
        packet[7] = cadence_rpm;
        packet[8] = torque_x100 & 0xFF;
        packet[9] = (torque_x100 >> 8) & 0xFF;
        packet[10] = 38;
        packet[11] = duty_cycle;
        packet[12] = motor_erps & 0xFF;
        packet[13] = (motor_erps >> 8) & 0xFF;
        packet[14] = 0x00;
        packet[15] = 20;
        packet[16] = torque_adc & 0xFF;
        packet[17] = (torque_adc >> 8) & 0xFF;
        packet[18] = 0x00;
        packet[19] = 0x00;
        packet[20] = 80;
        packet[21] = 0x00;
        packet[22] = wheel_pulses & 0xFF;
        packet[23] = (wheel_pulses >> 8) & 0xFF;
        packet[24] = (wheel_pulses >> 16) & 0xFF;
        packet[25] = crank_pulses & 0xFF;
        packet[26] = (crank_pulses >> 8) & 0xFF;

        // 計算 CRC16
        uint16_t crc = 0xFFFF;
        for (int i = 0; i < 27; i++) {
            crc16(packet[i], &crc);
        }
        packet[27] = crc & 0xFF;
        packet[28] = (crc >> 8) & 0xFF;

        // 寫入 UART
        uart_write_bytes(SIM_UART_NUM, (const char *)packet, CT_OS_MSG_BYTES);
        
        // 精準延遲
        vTaskDelayUntil(&xLastWakeTime, xPeriod);
    }
}

void app_main(void) {
    ESP_LOGI(TAG, "TSDZ2 ESP32-S3 Simulator Starting...");
    sim_uart_init();
    xTaskCreatePinnedToCore(sim_sender_task, "sim_sender", 4096, NULL, 5, NULL, 1);
}