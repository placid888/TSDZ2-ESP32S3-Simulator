import io
import json
import struct
import subprocess
import tempfile
import unittest
import zlib
from pathlib import Path
from types import SimpleNamespace
from android_device import AndroidMonitor
from android_capture import CaptureStore,capture_selected,png_size

def png():
 def chunk(kind,data):return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data)&0xffffffff)
 return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',1,1,8,6,0,0,0))+chunk(b'IDAT',zlib.compress(b'\x00\xff\x00\x00\xff'))+chunk(b'IEND',b'')

class CaptureTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
  self.store=CaptureStore(self.root/'captures');self.calls=[];self.state='device';self.payload=png();self.returncode=0
  self.monitor=AndroidMonitor(self.root/'target.json',finder=lambda:'adb.exe',runner=self.adb_run);self.monitor.selected='ONE'
 def adb_run(self,args,**kwargs):
  self.calls.append((args,kwargs))
  if args[-1]=='version':return SimpleNamespace(returncode=0,stdout='adb test\n',stderr='')
  if args[-1]=='-l':return SimpleNamespace(returncode=0,stdout=f'List of devices attached\nOTHER device\nONE {self.state} model:Test_Phone\n',stderr='')
  return SimpleNamespace(returncode=self.returncode,stdout=self.payload,stderr=b'')
 def test_png_checks_signature_truncation_and_crc(self):
  self.assertEqual(png_size(png()),(1,1))
  for data in (b'not an image',png()[:-3],png()[:40]+b'x'+png()[41:]):
   with self.assertRaises(ValueError):png_size(data)
 def test_store_roundtrip_integrity_and_paths(self):
  info=self.store.save(png(),{'serial':'ONE'});self.assertEqual(self.store.image(info['id']),png())
  self.assertEqual(self.store.listing()['captures'][0]['id'],info['id'])
  for id in ('../secret','C:/secret','a'*32+'/../x'):
   with self.assertRaises(ValueError):self.store.read(id)
  (self.root/'captures'/(info['id']+'.png')).write_bytes(b'changed')
  with self.assertRaises(ValueError):self.store.image(info['id'])
 def test_only_explicit_target_and_binary_command_used(self):
  info=capture_selected(self.monitor,self.store,{'source_sha256':'abc'})
  self.assertEqual(info['serial'],'ONE');self.assertEqual(info['pc_identity']['source_sha256'],'abc')
  command,options=self.calls[-1]
  self.assertEqual(command,['adb.exe','-s','ONE','exec-out','screencap','-p'])
  self.assertNotIn('text',options);self.assertNotIn('shell',options)
 def test_no_target_never_runs_adb(self):
  self.monitor.selected=None
  with self.assertRaises(ValueError):capture_selected(self.monitor,self.store,{})
  self.assertEqual(self.calls,[]);self.assertEqual(self.store.listing()['captures'],[])
 def test_unready_target_never_captures_other_device(self):
  for state in ('offline','unauthorized'):
   self.state=state;self.calls=[]
   with self.assertRaises(ValueError):capture_selected(self.monitor,self.store,{})
   self.assertFalse(any('exec-out' in args for args,_ in self.calls))
 def test_invalid_image_and_adb_failure_never_save(self):
  self.payload=b'ERR not png'
  with self.assertRaises(ValueError):capture_selected(self.monitor,self.store,{})
  self.payload=png();self.returncode=1
  with self.assertRaises(ValueError):capture_selected(self.monitor,self.store,{})
  self.assertEqual(self.store.listing()['captures'],[])
 def test_timeout_never_saves(self):
  run=self.monitor.runner
  def timeout(args,**kwargs):
   if 'exec-out' in args:raise subprocess.TimeoutExpired(args,10)
   return run(args,**kwargs)
  self.monitor.runner=timeout
  with self.assertRaisesRegex(ValueError,'逾時'):capture_selected(self.monitor,self.store,{})
  self.assertEqual(self.store.listing()['captures'],[])
 def test_incomplete_or_invalid_records_skipped(self):
  folder=self.root/'captures';folder.mkdir();(folder/('a'*32+'.json')).write_text('{}')
  self.assertEqual(self.store.listing()['skipped'],1)
