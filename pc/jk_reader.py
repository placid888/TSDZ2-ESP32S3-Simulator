"""Bounded JK02_24S snapshot reader; only device/status queries are permitted.

Protocol facts checked against syssi/esphome-jk-bms jk_bms_ble.cpp.
No settings, MOSFET, balance, pairing, or OTA command is implemented.
"""
import asyncio
import struct
import time
from jk_alarms import decode_alarms

CHARACTERISTIC = '0000ffe1-0000-1000-8000-00805f9b34fb'
HEADER = b'\x55\xaa\xeb\x90'


def query_frame(command):
    if command not in (0x96, 0x97):raise ValueError('Only device/status queries are supported')
    packet=bytearray.fromhex('aa5590eb')+bytearray([command])+bytearray(14)
    packet.append(sum(packet)&255)
    return bytes(packet)


class Frames:
    def __init__(self):self.buffer=bytearray();self.invalid=0
    def feed(self, chunk):
        self.buffer.extend(chunk);result=[]
        while True:
            start=self.buffer.find(HEADER)
            if start<0:
                self.buffer=self.buffer[-3:];break
            del self.buffer[:start]
            if len(self.buffer)<300:break
            raw=bytes(self.buffer[:300])
            if sum(raw[:299])&255 != raw[299]:
                self.invalid+=1;del self.buffer[0];continue
            result.append(raw);del self.buffer[:300]
        return result


def validate(raw, kind):
    if len(raw)!=300 or raw[:4]!=HEADER or raw[4]!=kind or sum(raw[:-1])&255!=raw[-1]:
        raise ValueError('JK frame header/type/length/checksum mismatch')


def device_info(raw):
    validate(raw,3)
    def text(offset,length):return raw[offset:offset+length].split(b'\0',1)[0].decode('ascii',errors='strict').strip()
    return {'model':text(6,16),'hardware':text(22,8),'software':text(30,8)}


def status_24s(raw, info):
    validate(raw,2)
    if info['model']!='JK-BD6A17S6P' or info['hardware']!='10.XW' or info['software']!='10.07':
        raise ValueError('目前只啟用已核對的 JK-BD6A17S6P hw10.XW / sw10.07 格式；未猜測其他版本')
    u16=lambda n:struct.unpack_from('<H',raw,n)[0]
    u32=lambda n:struct.unpack_from('<I',raw,n)[0]
    s16=lambda n:struct.unpack_from('<h',raw,n)[0]
    mask=u32(54)
    if mask>>24 or not mask:raise ValueError('Enabled cell mask invalid')
    cells=[{'cell':i+1,'voltage_v':u16(6+2*i)/1000,'wire_resistance_ohm':u16(64+2*i)/1000}
           for i in range(24) if mask&(1<<i)]
    pack=u32(118)/1000;current=struct.unpack_from('<i',raw,126)[0]/1000
    temps=[s16(n)/10 for n in (130,132,134)]
    if any(not 1<=c['voltage_v']<=5 for c in cells) or abs(sum(c['voltage_v'] for c in cells)-pack)>1:
        raise ValueError('Cell/pack voltage consistency check failed')
    if raw[141]>100 or any(not -60<=t<=150 for t in temps) or abs(current)>300:
        raise ValueError('Status values outside validated ranges')
    values=[c['voltage_v'] for c in cells]
    return {'protocol':'JK02_24S','device_info':info,'captured_at':time.time(),
            'pack_voltage_v':pack,'current_a':current,'current_sign':'positive=charge, negative=discharge',
            'soc_percent':raw[141],'remaining_ah':u32(142)/1000,'nominal_ah':u32(146)/1000,
            'cell_count':len(cells),'cells':cells,'cell_delta_v':round(max(values)-min(values),3),
            'cell_average_v':sum(values)/len(values),'cell_min_v':min(values),'cell_max_v':max(values),
            'balance_current_a':s16(138)/1000,'balance_state_raw':raw[140],
            'cycle_count':u32(150),'cycle_capacity_ah':u32(154)/1000,
            'temperature_1_c':temps[0],'temperature_2_c':temps[1],'mos_temperature_c':temps[2],
            'alarm_raw':u16(136),'alarm':decode_alarms(u16(136)),
            'checksum_valid':True,'mode':'single_snapshot_then_disconnect'}


async def read_snapshot(address):
    from bleak import BleakScanner,BleakClient
    device=await BleakScanner.find_device_by_address(address,timeout=5)
    if device is None:raise ValueError('指定 BMS 未廣播；請確認距離與手機 App 連線狀態')
    assembler=Frames();queue=asyncio.Queue()
    def notification(sender, data):
        for frame in assembler.feed(data):queue.put_nowait(frame)
    async def wait_kind(kind):
        async def collect():
            while True:
                frame=await queue.get()
                if frame[4]==kind:return frame
        return await asyncio.wait_for(collect(),8)
    async with BleakClient(device,timeout=10,pair=False) as client:
        characteristic=client.services.get_characteristic(CHARACTERISTIC)
        if characteristic is None or 'notify' not in characteristic.properties or 'write-without-response' not in characteristic.properties:
            raise ValueError('指定 BMS 的 FFE1 查詢/通知能力不符')
        await client.start_notify(characteristic,notification)
        await client.write_gatt_char(characteristic,query_frame(0x97),response=False)
        info=device_info(await wait_kind(3))
        # Reject unsupported variants before sending the status request.
        if info['model']!='JK-BD6A17S6P' or info['hardware']!='10.XW' or info['software']!='10.07':
            raise ValueError('尚未支援此 BMS 版本：'+str(info))
        await client.write_gatt_char(characteristic,query_frame(0x96),response=False)
        return status_24s(await wait_kind(2),info)
