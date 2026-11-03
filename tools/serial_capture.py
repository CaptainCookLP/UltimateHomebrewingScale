"""Windows/Mac/Linux USB logger with reconnect; never enters the device REPL.

Install: py -3.13 -m pip install pyserial
Run:     py -3.13 tools/serial_capture.py --port COM7
"""
import argparse
import codecs
from datetime import datetime
from pathlib import Path
import sys
import time


def identity(info):
    number = getattr(info, 'serial_number', None)
    return (number, getattr(info, 'vid', None), getattr(info, 'pid', None)) if number else None


def select_port(ports, requested, known=None):
    """Follow a unique USB serial number; never guess among other ESP boards."""
    ports = list(ports)
    if known:
        matches = [p for p in ports if identity(p) == known]
        if len(matches) == 1:
            return matches[0].device, known
        return None, known
    for item in ports:
        if item.device.lower() == requested.lower():
            return item.device, identity(item)
    return None, known


class Capture:
    def __init__(self, file, console=None):
        self.file = file
        self.console = console or sys.stdout
        self.decoder = codecs.getincrementaldecoder('utf-8')('replace')
        self.pending = ''

    def line(self, text, origin='DEVICE'):
        stamp = datetime.now().astimezone().isoformat(timespec='milliseconds')
        result = '[{}] [{}] {}\n'.format(stamp, origin, text.rstrip('\r\n'))
        self.file.write(result)
        self.file.flush()
        self.console.write(result)
        self.console.flush()

    def feed(self, data):
        self.pending += self.decoder.decode(data)
        while '\n' in self.pending:
            line, self.pending = self.pending.split('\n', 1)
            self.line(line)
        if len(self.pending) > 16384:
            self.flush_partial()

    def flush_partial(self):
        if self.pending:
            self.line(self.pending)
            self.pending = ''

    def disconnect(self):
        self.pending += self.decoder.decode(b'', final=True)
        self.flush_partial()
        self.decoder = codecs.getincrementaldecoder('utf-8')('replace')


def open_port(factory, port, baud):
    connection = factory(port=None, baudrate=baud, timeout=0.5,
                         xonxoff=False, rtscts=False, dsrdtr=False)
    # Set these before open; never pulse EN/BOOT or send Ctrl-C/Ctrl-D.
    # Some USB drivers can still change lines during open at the OS level.
    connection.dtr = False
    connection.rts = False
    connection.port = port
    try:
        connection.open()
        return connection
    except Exception:
        connection.close()
        raise


def monitor(requested, capture, factory, enumerate_ports, baud=115200,
            stop=lambda: False, pause=time.sleep):
    known = None
    previous_error = None
    try:
        while not stop():
            connection = None
            try:
                port, known = select_port(enumerate_ports(), requested, known)
                if not port:
                    if previous_error != 'waiting':
                        capture.line('Waiting for {} to appear; Ctrl+C stops logging.'.format(requested), 'HOST')
                    previous_error = 'waiting'
                    pause(0.5)
                    continue
                connection = open_port(factory, port, baud)
                capture.line('Connected to {} at {} baud'.format(port, baud), 'HOST')
                previous_error = None
                while not stop():
                    data = connection.read(4096)
                    if data:
                        capture.feed(data)
                    else:
                        capture.flush_partial()
                        available, _ = select_port(enumerate_ports(), requested, known)
                        if available != port:
                            raise OSError('USB device disappeared or changed COM port')
            except (OSError, IOError) as error:
                capture.disconnect()
                message = '{}: {}'.format(type(error).__name__, error)
                if message != previous_error:
                    capture.line('Disconnected/unavailable: ' + message, 'HOST')
                previous_error = message
            finally:
                if connection is not None:
                    try:
                        connection.close()
                    except Exception:
                        pass
            if not stop():
                pause(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        capture.disconnect()
        capture.line('Capture stopped', 'HOST')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', required=True, help='Initial port, for example COM7')
    parser.add_argument('--baud', type=int, default=115200)
    parser.add_argument('--output', type=Path, help='Append to this file; default: unique log in Downloads')
    args = parser.parse_args(argv)
    try:
        import serial
        from serial.tools import list_ports
    except ImportError:
        parser.error('Install pyserial first: py -3.13 -m pip install pyserial')
    directory = Path.home() / 'Downloads'
    if not directory.is_dir():
        directory = Path.cwd()
    output = args.output or directory / ('M5Dial-debug-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f') + '.log')
    print('Log file:', output.resolve(), flush=True)
    # Append explicitly, even if an existing filename was supplied.
    with output.open('a', encoding='utf-8', buffering=1) as file:
        capture = Capture(file)
        capture.line('Passive serial capture; no REPL/reset commands are sent.', 'HOST')
        monitor(args.port, capture, serial.Serial, list_ports.comports, args.baud)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
