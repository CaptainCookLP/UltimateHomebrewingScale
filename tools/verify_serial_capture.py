"""Host logger tests; no serial device or pyserial installation required."""
import io
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock
sys.path.insert(0,str(Path(__file__).resolve().parent))
from serial_capture import Capture, identity, select_port, open_port, monitor


def port(device, number='dial', vid=1234):
    return types.SimpleNamespace(device=device,serial_number=number,vid=vid,pid=5678)


class CaptureTests(unittest.TestCase):
    def test_unique_serial_follows_changed_com_port(self):
        known=identity(port('COM7'))
        self.assertEqual(select_port([port('COM9')],'COM7',known),('COM9',known))

    def test_different_device_on_same_port_is_not_selected(self):
        known=identity(port('COM7'))
        self.assertIsNone(select_port([port('COM7','other')],'COM7',known)[0])

    def test_no_serial_number_does_not_guess_among_boards(self):
        self.assertEqual(select_port([port('COM9',None)],'COM7'),(None,None))

    def test_duplicate_serial_number_is_ambiguous(self):
        known=identity(port('COM7'))
        self.assertIsNone(select_port([port('COM8'),port('COM9')],'COM7',known)[0])

    def test_split_utf8_and_boot_lines_are_preserved(self):
        file,console=io.StringIO(),io.StringIO()
        capture=Capture(file,console)
        body='BOOT\nGröße\n'.encode()
        for byte in body:
            capture.feed(bytes([byte]))
        capture.disconnect()
        self.assertIn('[DEVICE] BOOT',file.getvalue())
        self.assertIn('[DEVICE] Größe',file.getvalue())
        self.assertEqual(file.getvalue(),console.getvalue())

    def test_partial_crash_line_is_flushed_on_disconnect(self):
        file=io.StringIO();capture=Capture(file,io.StringIO())
        capture.feed(b'Guru Meditation: partial')
        capture.disconnect()
        self.assertIn('Guru Meditation: partial',file.getvalue())

    def test_control_lines_are_set_before_open_and_no_data_is_written(self):
        connection=types.SimpleNamespace(open=Mock(),close=Mock(),write=Mock())
        def check():
            self.assertFalse(connection.dtr)
            self.assertFalse(connection.rts)
            self.assertEqual(connection.port,'COM7')
        connection.open.side_effect=check
        self.assertIs(open_port(lambda **kw:connection,'COM7',115200),connection)
        connection.write.assert_not_called()

    def test_capture_reconnects_and_keeps_both_boots(self):
        file=io.StringIO();capture=Capture(file,io.StringIO())
        done=[False];connections=[]
        class FakeSerial:
            def __init__(self,**kw):
                self.number=len(connections);self.calls=0;connections.append(self)
            def open(self): pass
            def close(self): pass
            def read(self,count):
                self.calls+=1
                if self.calls==1:return ('BOOT {}\n'.format(self.number)).encode()
                if self.number==0:raise OSError('USB reset')
                done[0]=True
                return b'end\n'
        monitor('COM7',capture,FakeSerial,lambda:[port('COM7')],stop=lambda:done[0],pause=lambda n:None)
        self.assertEqual(len(connections),2)
        for text in ('BOOT 0','BOOT 1','USB reset','Capture stopped'):
            self.assertIn(text,file.getvalue())


if __name__=='__main__':
    unittest.main(verbosity=2)
