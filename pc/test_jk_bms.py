import tempfile
import unittest
from pathlib import Path
from jk_bms import JkMonitor


class JkTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'bms.json';self.calls=0
        self.rows=[{'address':'aa:bb:cc:dd:ee:ff','name':'JK-test','rssi':-50}]
        async def scan():self.calls+=1;return self.rows
        self.monitor=JkMonitor(self.path,scanner=scan)

    def test_state_never_scans_or_claims_connection(self):
        s=self.monitor.snapshot();self.assertEqual(self.calls,0)
        self.assertFalse(s['connected']);self.assertFalse(s['protocol_verified']);self.assertIsNone(s['telemetry'])

    def test_scan_never_auto_selects(self):
        s=self.monitor.scan();self.assertEqual(self.calls,1)
        self.assertIsNone(s['selected_address']);self.assertTrue(s['devices'][0]['jk_name_hint'])
        self.assertFalse(self.path.exists())

    def test_select_only_unique_recent_advertisement_and_persists(self):
        with self.assertRaises(ValueError):self.monitor.select('AA:BB:CC:DD:EE:FF')
        self.monitor.scan();s=self.monitor.select('aa:bb:cc:dd:ee:ff')
        self.assertEqual(s['selected_address'],'AA:BB:CC:DD:EE:FF')
        restored=JkMonitor(self.path);self.assertEqual(restored.selected,s['selected_address'])
        self.assertFalse(restored.snapshot()['scan_recent'])

    def test_stale_duplicate_and_unknown_addresses_rejected(self):
        self.monitor.scan()
        with self.assertRaises(ValueError):self.monitor.select('11:22:33:44:55:66')
        self.monitor.updated-=61
        with self.assertRaises(ValueError):self.monitor.select('aa:bb:cc:dd:ee:ff')
        self.rows*=2;self.monitor.scan()
        with self.assertRaises(ValueError):self.monitor.select('aa:bb:cc:dd:ee:ff')

    def test_scan_failure_is_not_successful_empty_inventory(self):
        async def failed():raise RuntimeError('Bluetooth adapter unavailable')
        self.monitor.scanner=failed;s=self.monitor.scan()
        self.assertTrue(s['error']);self.assertFalse(s['scan_recent']);self.assertEqual(s['devices'],[])

    def test_corrupt_settings_preserved(self):
        self.path.write_text('broken');m=JkMonitor(self.path,scanner=self.monitor.scanner);m.scan()
        with self.assertRaises(ValueError):m.select('aa:bb:cc:dd:ee:ff')
        self.assertEqual(self.path.read_text(),'broken')
