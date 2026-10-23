#pragma once
#include <stdbool.h>
#include <stdint.h>
#include "esp_err.h"
#include "driver/spi_master.h"

typedef enum { DAC_DISABLED, DAC_MOCK, DAC_SPI } DacMode;
typedef struct {
    DacMode mode;
    spi_device_handle_t spi;
    uint16_t codes[8];
    uint32_t last_frame;
} Dac8568;
/* Frame helpers also used by host tests. CH1=A=0 through CH8=H=7. */
static inline uint32_t dac8568_frame(unsigned command, unsigned channel, uint16_t code) {
    return ((command & 15u) << 24) | ((channel & 15u) << 20) | ((uint32_t)code << 4);
}
esp_err_t dac8568_init(Dac8568 *d, DacMode mode);
esp_err_t dac8568_write(Dac8568 *d, unsigned channel, uint16_t code);
esp_err_t dac8568_zero(Dac8568 *d);
