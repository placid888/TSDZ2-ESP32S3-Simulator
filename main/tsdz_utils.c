#include "tsdz_utils.h"

// 原作者的 Modbus CRC16 演算法
void crc16(uint8_t ui8_data, uint16_t* ui16_crc)
{
    unsigned int i;

    *ui16_crc = *ui16_crc ^(uint16_t) ui8_data;

    for (i = 8; i > 0; i--)
    {
        if (*ui16_crc & 0x0001) { *ui16_crc = (*ui16_crc >> 1) ^ 0xA001; }
        else { *ui16_crc >>= 1; }
    }
}