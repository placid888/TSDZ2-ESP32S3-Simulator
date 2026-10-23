import unittest
from server import BenchLink

class WatchdogNoticeTests(unittest.TestCase):
    def test_timeout_event_is_reported_once_and_never_sends_run(self):
        link=BenchLink();commands=[]
        data={'link_timeout':True,'link_timeout_count':1}
        def receive(command,telemetry=False):
            commands.append(command);return dict(data)
        link._line=receive
        link._refresh();link._refresh()
        self.assertEqual(len(link.events),1)
        data['link_timeout_count']=2;link._refresh()
        self.assertEqual(len(link.events),2)
        self.assertEqual(commands,['TELEMETRY']*3)
