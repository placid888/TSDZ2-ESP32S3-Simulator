"""JK02_24S 16-bit status flags, translated from the checked protocol mapping.

Reference: syssi/esphome-jk-bms components/jk_bms_ble/__init__.py
Bit 3 is deliberately unknown; bit 4 is a full-charge status, not a fault.
"""
FLAGS = {
    0:'均衡線電阻異常',1:'MOS 過溫',2:'電芯串數與設定不符',
    4:'電池已充滿',5:'電池總壓過高',6:'充電過流',7:'充電短路',
    8:'充電溫度過高',9:'充電溫度過低',10:'協處理器通訊異常',
    11:'單串電芯欠壓',12:'電池總壓過低',13:'放電過流',14:'放電短路',15:'放電溫度過高',
}


def decode_alarms(raw):
    if type(raw) is not int or not 0<=raw<=65535:raise ValueError('JK02_24S 告警必須是 16-bit 整數')
    entries=[]
    for bit in range(16):
        if raw&(1<<bit):
            entries.append({'bit':bit,'kind':'status' if bit==4 else 'alarm' if bit in FLAGS else 'unknown',
                            'message':FLAGS.get(bit,f'未知告警位元 {bit}（待確認）')})
    return {'format':'JK02_24S_16bit','raw_hex':f'0x{raw:04X}','entries':entries,
            'has_alarm':any(x['kind']!='status' for x in entries),
            'unknown_bits':[x['bit'] for x in entries if x['kind']=='unknown']}
