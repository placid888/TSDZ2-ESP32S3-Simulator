import json
import math
import time
import unittest
from server import BenchLink, validate_settings


class FakeSerial:
    def __init__(self, replies):
        self.replies = list(replies)
        self.commands = []
    def write(self, data):
        self.commands.append(data.decode().strip())
    def flush(self):
        pass
    def read_until(self, *args):
        return self.replies.pop(0) if self.replies else b''


class BridgeTests(unittest.TestCase):
    def test_whole_request_validation(self):
        for bad in ({'PWM': 101}, {'PWM': math.nan}, {'BRAKE': .5}, {'PWM': True}, {'UNKNOWN': 1}, {'PWM': '40'}):
            link = BenchLink()
            link.port = FakeSerial([])
            with self.assertRaises(ValueError):
                link.apply(bad)
            self.assertEqual(link.port.commands, [])
        self.assertEqual(validate_settings({'PWM': 40, 'GRADE': -10}), ['SET PWM 40', 'SET GRADE -10'])

    def test_no_automatic_run_and_boot_log_skipped(self):
        link = BenchLink()
        link.port = FakeSerial([b'I (42) boot ready\n', b'OK\r\n'])
        link._line('STOP')
        self.assertEqual(link.port.commands, ['STOP'])

    def test_device_error_propagates(self):
        link = BenchLink()
        link.port = FakeSerial([b'ERR value out of range\n'])
        with self.assertRaisesRegex(ValueError, 'ESP32'):
            link._line('SET PWM 999')

    def test_stale_run_refused_but_stop_allowed(self):
        link = BenchLink()
        link.port = FakeSerial([])
        link.telemetry, link.updated = {}, time.monotonic() - 5
        with self.assertRaises(ValueError):
            link.command('RUN')
        self.assertEqual(link.port.commands, [])

    def test_protocol_mismatch_rejected(self):
        link = BenchLink()
        link.port = FakeSerial([json.dumps({'type':'telemetry','protocol':99}).encode()+b'\n'])
        with self.assertRaisesRegex(ValueError, '版本'):
            link._refresh()

if __name__ == '__main__':
    unittest.main()
