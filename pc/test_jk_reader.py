import struct
import tempfile
import unittest
from pathlib import Path
from jk_reader import Frames,HEADER,query_frame,device_info,status_24s
from jk_bms import JkMonitor


INFO={'model':'JK-BD6A17S6P','hardware':'10.XW','software':'10.07'}
def seal(frame):
    frame[-1]=sum(frame[:-1])&255
    return bytes(frame)
def status():
    b=bytearray(300);b[:4]=HEADER;b[4]=2
    for i in range(13):struct.pack_into('<H',b,6+2*i,3500)
    struct.pack_into('<I',b,54,8191);struct.pack_into('<I',b,118,45500)
    struct.pack_into('<i',b,126,-1250)
    for offset,value in [(130,-15),(132,250),(134,290)]:struct.pack_into('<h',b,offset,value)
    b[141]=51
    return seal(b)


class ReaderTests(unittest.TestCase):
    def test_only_two_query_commands_can_be_encoded(self):
        for n in range(256):
            if n in (0x96,0x97):
                b=query_frame(n);self.assertEqual(len(b),20);self.assertEqual(sum(b[:-1])&255,b[-1]);self.assertEqual(b[5:19],bytes(14))
            else:
                with self.assertRaises(ValueError):query_frame(n)

    def test_fragmented_header_garbage_and_concatenated_frames(self):
        f=Frames();b=status();out=[]
        for chunk in [b'noise'+b[:2],b[2:125],b[125:]+b]:out+=f.feed(chunk)
        self.assertEqual(out,[b,b])

    def test_bad_checksum_resynchronizes_to_next_frame(self):
        b=bytearray(status());b[20]^=1;f=Frames()
        self.assertEqual(f.feed(bytes(b)+status()),[status()]);self.assertGreater(f.invalid,0)

    def test_status_signed_units_and_voltage_consistency(self):
        t=status_24s(status(),INFO)
        self.assertEqual(t['cell_count'],13);self.assertEqual(t['pack_voltage_v'],45.5)
        self.assertEqual(t['current_a'],-1.25);self.assertEqual(t['temperature_1_c'],-1.5)
        b=bytearray(status());struct.pack_into('<I',b,118,70000)
        with self.assertRaises(ValueError):status_24s(seal(b),INFO)

    def test_unknown_version_and_bad_checksum_rejected(self):
        with self.assertRaises(ValueError):status_24s(status(),{**INFO,'hardware':'11.XW'})
        b=bytearray(status());b[-1]^=1
        with self.assertRaises(ValueError):status_24s(bytes(b),INFO)

    def test_wire_resistance_balance_and_cycle_units(self):
        b=bytearray(status());struct.pack_into('<H',b,64,185)
        struct.pack_into('<H',b,64+24,141);struct.pack_into('<h',b,138,-123)
        b[140]=2;struct.pack_into('<I',b,150,12);struct.pack_into('<I',b,154,222800)
        t=status_24s(seal(b),INFO)
        self.assertEqual(t['cells'][0]['wire_resistance_ohm'],0.185)
        self.assertEqual(t['cells'][-1]['wire_resistance_ohm'],0.141)
        self.assertEqual(t['balance_current_a'],-0.123);self.assertEqual(t['balance_state_raw'],2)
        self.assertEqual(t['cycle_count'],12);self.assertEqual(t['cycle_capacity_ah'],222.8)
        self.assertEqual(t['cell_average_v'],3.5)

    def test_disabled_cells_are_excluded_from_minimum_and_resistance(self):
        t=status_24s(status(),INFO)
        self.assertEqual(t['cell_min_v'],3.5);self.assertEqual(len(t['cells']),13)
        self.assertEqual(t['cells'][-1]['cell'],13)

    def test_alarm_word_is_decoded_from_little_endian_status_bytes(self):
        b=bytearray(status());struct.pack_into('<H',b,136,(1<<5)|(1<<11))
        t=status_24s(seal(b),INFO)
        self.assertEqual(t['alarm_raw'],2080)
        self.assertEqual([x['bit'] for x in t['alarm']['entries']],[5,11])

    def test_device_version_is_from_jk_frame_not_ble_module(self):
        b=bytearray(300);b[:4]=HEADER;b[4]=3
        for off,key in [(6,'model'),(22,'hardware'),(30,'software')]:
            raw=INFO[key].encode();b[off:off+len(raw)]=raw
        self.assertEqual(device_info(seal(b)),INFO)

    def test_read_requires_registered_target_and_failed_read_preserves_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            m=JkMonitor(Path(directory)/'bms.json')
            with self.assertRaises(ValueError):m.read()
            m.selected='AA:BB:CC:DD:EE:FF'
            async def good(address):return status_24s(status(),INFO)
            self.assertTrue(m.read(good)['protocol_verified'])
            async def bad(address):raise TimeoutError('timeout')
            s=m.read(bad);self.assertTrue(s['error']);self.assertEqual(s['telemetry']['pack_voltage_v'],45.5)
            self.assertFalse(s['reading']);self.assertFalse(s['connected'])
