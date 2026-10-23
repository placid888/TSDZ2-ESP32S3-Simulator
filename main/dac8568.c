#include "dac8568.h"
#include "board_config.h"
#include <string.h>
#include "driver/gpio.h"

static esp_err_t send_frame(Dac8568 *d, uint32_t word) {
    if (d->mode == DAC_DISABLED) return ESP_OK;
    if (d->mode == DAC_SPI) {
        spi_transaction_t t = {.length = 32, .flags = SPI_TRANS_USE_TXDATA};
        for (int i = 0; i < 4; ++i) t.tx_data[i] = word >> (24 - 8 * i);
        esp_err_t err = spi_device_transmit(d->spi, &t);
        if (err != ESP_OK) return err;
    }
    d->last_frame = word;
    return ESP_OK;
}
esp_err_t dac8568_init(Dac8568 *d, DacMode mode) {
    memset(d, 0, sizeof(*d));
    d->mode = mode;
    if (mode == DAC_SPI) {
        if (!GPIO_IS_VALID_OUTPUT_GPIO(BOARD_DAC_SCLK) ||
            !GPIO_IS_VALID_OUTPUT_GPIO(BOARD_DAC_MOSI) ||
            !GPIO_IS_VALID_OUTPUT_GPIO(BOARD_DAC_SYNC) ||
            BOARD_DAC_SCLK == BOARD_DAC_MOSI || BOARD_DAC_SCLK == BOARD_DAC_SYNC ||
            BOARD_DAC_MOSI == BOARD_DAC_SYNC) return ESP_ERR_INVALID_ARG;
        spi_bus_config_t bus = {.mosi_io_num = BOARD_DAC_MOSI, .miso_io_num = -1,
            .sclk_io_num = BOARD_DAC_SCLK, .quadwp_io_num = -1, .quadhd_io_num = -1,
            .max_transfer_sz = 4};
        esp_err_t err = spi_bus_initialize(SPI2_HOST, &bus, SPI_DMA_DISABLED);
        if (err != ESP_OK) return err;
        /* DIN is sampled on falling edges: mode 1, 1 MHz, MSB first. */
        spi_device_interface_config_t dev = {.clock_speed_hz = 1000000, .mode = 1,
            .spics_io_num = BOARD_DAC_SYNC, .queue_size = 1};
        err = spi_bus_add_device(SPI2_HOST, &dev, &d->spi);
        if (err != ESP_OK) { spi_bus_free(SPI2_HOST); return err; }
    }
    /* Reset, override LDAC on all channels, zero, then enable internal ref.
       On 16-pin parts CLR must be held high; LDAC may be tied high.
       Internal reference implies a nominal 5 V full-scale output. */
    esp_err_t err = send_frame(d, 0x07000000);
    if (err == ESP_OK) err = send_frame(d, 0x060000ff);
    if (err == ESP_OK) err = dac8568_zero(d);
    if (err == ESP_OK) err = send_frame(d, 0x08000001);
    return err;
}
esp_err_t dac8568_write(Dac8568 *d, unsigned channel, uint16_t code) {
    if (channel >= 8) return ESP_ERR_INVALID_ARG;
    esp_err_t err = send_frame(d, dac8568_frame(3, channel, code));
    if (err == ESP_OK && d->mode != DAC_DISABLED) d->codes[channel] = code;
    return err;
}
esp_err_t dac8568_zero(Dac8568 *d) {
    esp_err_t err = send_frame(d, dac8568_frame(3, 15, 0));
    if (err == ESP_OK) memset(d->codes, 0, sizeof(d->codes));
    return err;
}
