#include <stdio.h>
#include <math.h>
#include <string.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "driver/uart.h"
#include "esp_log.h"
#include "nvs_flash.h"
#include "tsdz_utils.h"

// 藍牙 NimBLE 相關標頭檔
#include "esp_nimble_hci.h"
#include "nimble/nimble_port.h"
#include "nimble/nimble_port_freertos.h"
#include "host/ble_hs.h"
#include "services/gap/ble_svc_gap.h"
#include "services/gatt/ble_svc_gatt.h"

#define TAG "TSDZ_SIM"

#define SIM_UART_NUM      UART_NUM_1
#define SIM_TX_PIN        17
#define SIM_RX_PIN        18
#define CT_MSG_ID         0x43
#define CT_OS_MSG_BYTES   29

// --- 物理模型變數 ---
static float current_speed_kmh = 0.0f;
static uint8_t cadence_rpm = 0;
static uint16_t torque_adc = 120;
static uint8_t duty_cycle = 0;
static uint8_t battery_current_x10 = 0;
static uint32_t wheel_pulses = 0;
static uint16_t crank_pulses = 0;

// --- 藍牙覆寫控制變數 ---
static bool ble_override = false;
static uint8_t ble_cadence = 0;
static uint16_t ble_torque = 120;
static uint32_t last_ble_rx_time = 0;

// --- UART 初始化 ---
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

// --- UART 發送與物理運算任務 ---
void sim_sender_task(void *pvParameters) {
    TickType_t xLastWakeTime = xTaskGetTickCount();
    const TickType_t xPeriod = pdMS_TO_TICKS(100);
    uint32_t tick_count = 0;

    while (1) {
        tick_count++;
        float time_sec = tick_count * 0.1f;

        // 若 BLE 超過 5 秒未收到新指令，切回自動模式
        if (ble_override && (xTaskGetTickCount() - last_ble_rx_time > pdMS_TO_TICKS(5000))) {
            ble_override = false;
            ESP_LOGI(TAG, "BLE 指令超時，切回自動正弦波模擬");
        }

        // 決定使用 BLE 遙控值 或 自動產生的正弦波
        if (ble_override) {
            cadence_rpm = ble_cadence;
            torque_adc = ble_torque;
        } else {
            cadence_rpm = (uint8_t)(75.0f + 10.0f * sinf(time_sec * 3.14f / 2.0f));
            torque_adc = 120 + (uint16_t)(80.0f * fabsf(sinf(time_sec * 3.14f / 0.4f)));
        }

        duty_cycle = (uint8_t)((torque_adc > 120 ? torque_adc - 120 : 0) * (120 - 20) / 80 + 20);
        if(duty_cycle > 120) duty_cycle = 120; 

        if (current_speed_kmh < 25.0f) current_speed_kmh += 0.1f;

        battery_current_x10 = (duty_cycle * 15) / 100;
        wheel_pulses += (uint32_t)(current_speed_kmh * 0.1f);
        crank_pulses += (cadence_rpm > 0) ? 1 : 0;

        uint8_t packet[CT_OS_MSG_BYTES] = {0};
        uint16_t speed_x10 = (uint16_t)(current_speed_kmh * 10.0f);
        uint16_t voltage_mv = 48000;
        uint16_t torque_x100 = (torque_adc > 120 ? torque_adc - 120 : 0) * 35;
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

        uint16_t crc = 0xFFFF;
        for (int i = 0; i < 27; i++) {
            crc16(packet[i], &crc);
        }
        packet[27] = crc & 0xFF;
        packet[28] = (crc >> 8) & 0xFF;

        uart_write_bytes(SIM_UART_NUM, (const char *)packet, CT_OS_MSG_BYTES);
        vTaskDelayUntil(&xLastWakeTime, xPeriod);
    }
}

// --- 藍牙 GATT 伺服器設定 ---
static const ble_uuid16_t gatt_svr_svc_uuid = BLE_UUID16_INIT(0xFFF0);
static const ble_uuid16_t gatt_svr_chr_uuid = BLE_UUID16_INIT(0xFFF1);

static int gatt_svr_chr_access(uint16_t conn_handle, uint16_t attr_handle,
                               struct ble_gatt_access_ctxt *ctxt, void *arg) {
    if (ctxt->op == BLE_GATT_ACCESS_OP_WRITE_CHR) {
        char buf[64] = {0};
        int len = ctxt->om->om_len > 63 ? 63 : ctxt->om->om_len;
        memcpy(buf, ctxt->om->om_data, len);
        
        int parse_c = 0, parse_t = 0;
        // 解析格式 "C:踏頻,T:扭力" (例如 "C:90,T:180")
        if (sscanf(buf, "C:%d,T:%d", &parse_c, &parse_t) == 2) {
            ble_cadence = (uint8_t)parse_c;
            ble_torque = (uint16_t)parse_t;
            ble_override = true;
            last_ble_rx_time = xTaskGetTickCount();
            ESP_LOGI(TAG, "收到 BLE 遙控: Cadence=%d, Torque=%d", ble_cadence, ble_torque);
        }
    }
    return 0;
}

static const struct ble_gatt_svc_def gatt_svr_svcs[] = {
    {
        .type = BLE_GATT_SVC_TYPE_PRIMARY,
        .uuid = &gatt_svr_svc_uuid.u,
        .characteristics = (struct ble_gatt_chr_def[]) {
            {
                .uuid = &gatt_svr_chr_uuid.u,
                .access_cb = gatt_svr_chr_access,
                .flags = BLE_GATT_CHR_F_WRITE,
            },
            { 0 }
        },
    },
    { 0 }
};

static uint8_t own_addr_type;

static void ble_app_advertise(void) {
    struct ble_gap_adv_params adv_params;
    struct ble_hs_adv_fields fields;
    
    memset(&fields, 0, sizeof fields);
    fields.flags = BLE_HS_ADV_F_DISC_GEN | BLE_HS_ADV_F_BREDR_UNSUP;
    fields.name = (uint8_t *)"TSDZ2_SIM";
    fields.name_len = strlen("TSDZ2_SIM");
    fields.name_is_complete = 1;
    ble_gap_adv_set_fields(&fields);

    memset(&adv_params, 0, sizeof adv_params);
    adv_params.conn_mode = BLE_GAP_CONN_MODE_UND;
    adv_params.disc_mode = BLE_GAP_DISC_MODE_GEN;
    ble_gap_adv_start(own_addr_type, NULL, BLE_HS_FOREVER, &adv_params, NULL, NULL);
}

static void ble_app_on_sync(void) {
    ble_hs_id_infer_auto(0, &own_addr_type);
    ble_app_advertise();
}

void ble_host_task(void *param) {
    ESP_LOGI(TAG, "BLE Host Task Started");
    nimble_port_run();
    nimble_port_freertos_deinit();
}

void app_main(void) {
    ESP_ERROR_CHECK(nvs_flash_init());
    sim_uart_init();
    
    // 初始化 NimBLE 藍牙協議棧
    nimble_port_init();
    ble_hs_cfg.sync_cb = ble_app_on_sync;
    ble_svc_gap_device_name_set("TSDZ2_SIM");
    ble_svc_gap_init();
    ble_svc_gatt_init();
    ble_gatts_count_cfg(gatt_svr_svcs);
    ble_gatts_add_svcs(gatt_svr_svcs);
    nimble_port_freertos_init(ble_host_task);

    // 啟動物理模型發送任務
    xTaskCreatePinnedToCore(sim_sender_task, "sim_sender", 4096, NULL, 5, NULL, 1);
    ESP_LOGI(TAG, "TSDZ2 ESP32-S3 Simulator (BLE Enabled) Ready!");
}