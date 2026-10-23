#pragma once
#include <stdint.h>
#include "esp_err.h"
typedef void *spi_device_handle_t;
typedef struct { int mosi_io_num, miso_io_num, sclk_io_num, quadwp_io_num, quadhd_io_num, max_transfer_sz; } spi_bus_config_t;
typedef struct { int clock_speed_hz, mode, spics_io_num, queue_size; } spi_device_interface_config_t;
typedef struct { int length, flags; uint8_t tx_data[4]; } spi_transaction_t;
#define SPI_TRANS_USE_TXDATA 1
#define SPI2_HOST 2
#define SPI_DMA_DISABLED 0
esp_err_t spi_device_transmit(spi_device_handle_t dev, spi_transaction_t *t);
esp_err_t spi_bus_initialize(int host, const spi_bus_config_t *bus, int dma);
esp_err_t spi_bus_add_device(int host, const spi_device_interface_config_t *cfg, spi_device_handle_t *dev);
esp_err_t spi_bus_free(int host);
