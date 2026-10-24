import unittest
from jk_alarms import decode_alarms


class AlarmTests(unittest.TestCase):
    def test_zero_means_no_reported_flags(self):
        a=decode_alarms(0);self.assertEqual(a['entries'],[]);self.assertFalse(a['has_alarm']);self.assertEqual(a['raw_hex'],'0x0000')
    def test_multiple_flags_are_all_reported(self):
        a=decode_alarms((1<<1)|(1<<11)|(1<<14))
        self.assertEqual([x['bit'] for x in a['entries']],[1,11,14]);self.assertTrue(a['has_alarm'])
        self.assertEqual(a['entries'][1]['message'],'單串電芯欠壓')
    def test_full_charge_is_a_status_not_overvoltage(self):
        a=decode_alarms(16);self.assertFalse(a['has_alarm']);self.assertEqual(a['entries'][0]['kind'],'status')
        self.assertEqual(a['entries'][0]['message'],'電池已充滿')
    def test_unknown_bit_is_visible(self):
        a=decode_alarms(8);self.assertEqual(a['unknown_bits'],[3]);self.assertTrue(a['has_alarm'])
    def test_all_bits_preserved(self):
        a=decode_alarms(65535);self.assertEqual(len(a['entries']),16);self.assertEqual(a['unknown_bits'],[3])
    def test_other_widths_types_and_negative_values_rejected(self):
        for raw in [-1,65536,1.0,True,None]:
            with self.assertRaises(ValueError):decode_alarms(raw)
