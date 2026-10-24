import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from android_device import AndroidMonitor
from android_app import launch_selected, PACKAGE, COMPONENT


class AppTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.calls=[];self.devices='PHONE device';self.installed=True;self.output='Status: ok\n'
        def run(args,**kwargs):
            self.calls.append(args)
            if args[-1]=='version':out='ADB test'
            elif args[-1]=='-l':out='List of devices attached\n'+self.devices+'\n'
            elif 'path' in args:out='package:/data/app/base.apk\n' if self.installed else ''
            else:out=self.output
            return SimpleNamespace(returncode=0,stdout=out,stderr='')
        self.monitor=AndroidMonitor(Path(self.tmp.name)/'target.json',finder=lambda:'adb',runner=run)

    def test_unselected_phone_never_runs_adb(self):
        with self.assertRaises(ValueError):launch_selected(self.monitor)
        self.assertEqual(self.calls,[])

    def test_launch_uses_fixed_app_and_explicit_selected_serial(self):
        self.monitor.selected='PHONE';result=launch_selected(self.monitor)
        self.assertEqual(self.calls[-2],['adb','-s','PHONE','shell','pm','path',PACKAGE])
        self.assertEqual(self.calls[-1],['adb','-s','PHONE','shell','am','start','-W','-n',COMPONENT])
        self.assertFalse(result['ble_verified']);self.assertEqual(result['status'],'started')

    def test_disconnected_unauthorized_duplicate_never_launches(self):
        self.monitor.selected='PHONE'
        for devices in ['OTHER device','PHONE unauthorized','PHONE device\nPHONE device']:
            self.devices=devices;self.calls=[]
            with self.assertRaises(ValueError):launch_selected(self.monitor)
            self.assertFalse(any('shell' in args for args in self.calls))

    def test_missing_app_is_not_installed_or_started(self):
        self.monitor.selected='PHONE';self.installed=False
        with self.assertRaisesRegex(ValueError,'尚未安裝'):launch_selected(self.monitor)
        self.assertFalse(any('start' in args or 'install' in args for args in self.calls))

    def test_unconfirmed_start_is_failure(self):
        self.monitor.selected='PHONE';self.output='Error: Activity not found'
        with self.assertRaisesRegex(ValueError,'未確認'):launch_selected(self.monitor)
