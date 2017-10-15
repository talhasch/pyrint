from __future__ import unicode_literals, print_function

import logging
import os
import tempfile
import threading
import time
import requests
import webbrowser

from flask import Flask, render_template, jsonify, url_for, request
from flask_babel import Babel
from flask_socketio import SocketIO, emit
from humanize import naturalsize

os.sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../")))

from pyrint.helper import get_serial_port_list
from pyrint.printcore import PrintCore
from pyrint.gcoder import LightGCode

logging.basicConfig(level=logging.INFO)

app = Flask(__name__)
socket_io = SocketIO(app)

app.config['DEVELOPMENT'] = False
app.config['DEBUG'] = False


class GCodeRaw:
    def __init__(self):
        self._path = None
        self._size = None
        self._size_hr = None
        self._name = None

    @property
    def path(self):
        return self._path

    @property
    def size(self):
        return self._size

    @property
    def size_hr(self):
        return self._size_hr

    @property
    def name(self):
        return self._name

    def update(self, file_path):
        self._path = file_path
        self._name = os.path.basename(file_path)
        self._size = os.path.getsize(file_path)
        self._size_hr = naturalsize(self._size)


class PrintCoreWrapper(PrintCore):
    def __init__(self, port=None, baud=None, dtr=None, p_handler=[]):
        super(PrintCoreWrapper, self).__init__(port, baud, dtr, p_handler)

        self._temperature = 0
        self.gcode_raw = GCodeRaw()
        self.gcode = LightGCode()

    @property
    def temperature(self):
        return self._temperature

    def update_temperature(self, raw_temp):
        t = raw_temp.replace('ok', '').replace('T:', '').strip()
        self._temperature = t


printer = None


def printer_online_cb():
    socket_io.emit('online', {'port': printer.port, 'baud': printer.baud})
    printer.send_now("M105")


def printer_disconnect_cb():
    socket_io.emit('disconnected')
    create_printer()


def printer_error_cb(error):
    socket_io.emit('error', {'msg': error})
    printer.disconnect()
    create_printer()


def printer_temp_cb(temp):
    printer.update_temperature(temp)
    socket_io.emit('temperature', {'temp': printer.temperature})


def printer_receive_cb(line):
    if line.startswith('T:'):
        printer.update_temperature(line)
        socket_io.emit('temperature', {'temp': printer.temperature})


def printer_start_cb(resuming):
    socket_io.emit('started')


def printer_end_cb():
    socket_io.emit('ended')


def create_printer():
    global printer

    # remove last uploaded file if exists
    if printer and printer.gcode_raw.path and os.path.isfile(printer.gcode_raw.path):
        os.remove(printer.gcode_raw.path)

    printer = PrintCoreWrapper()
    printer.onlinecb = printer_online_cb
    printer.disconnectcb = printer_disconnect_cb
    printer.errorcb = printer_error_cb
    printer.tempcb = printer_temp_cb
    printer.recvcb = printer_receive_cb
    printer.startcb = printer_start_cb
    printer.endcb = printer_end_cb


create_printer()


def __flask_setup():
    Babel(app)


@socket_io.on('connect_printer')
def connect_printer(data, *args, **kwargs):
    assert 'port' in data and 'baud' in data
    port = data['port'].strip()
    baud = data['baud']

    global printer

    # disconnect if printer already connected
    if printer.online:
        printer.disconnect()

    printer.connect(port, baud=baud)


@socket_io.on('disconnect_printer')
def disconnect_printer(data, *args, **kwargs):
    global printer
    if printer.printing:
        printer.cancelprint()
    printer.disconnect()


@socket_io.on('start_printing')
def start_printing(data, *args, **kwargs):
    global printer
    if printer.paused:
        printer.resume()
    else:
        printer.startprint(printer.gcode)


@socket_io.on('pause_printing')
def start_printing(data, *args, **kwargs):
    global printer
    if printer.printing:
        printer.pause()
        emit('paused')


@socket_io.on('cancel_printing')
def start_printing(data, *args, **kwargs):
    global printer
    printer.cancelprint()
    emit('cancelled')


@socket_io.on('send_gcode')
def send_gcode(data, *args, **kwargs):
    if 'code' not in data:
        return

    global printer

    gcode = data['code'].strip()

    printer.send_now(gcode)


def __route_setup():
    @app.route('/')
    def index():
        return render_template('index.html')

    @app.route('/ports.json')
    def ports():
        return jsonify(get_serial_port_list())

    @app.route('/upload_file', methods=('POST',))
    def upload_file():
        data = request.json

        assert 'file_name' in data and 'file_contents' in data

        file_name = data['file_name']
        file_contents = data['file_contents']

        save_path = os.path.join(tempfile.gettempdir(), file_name)
        with open(save_path, 'w', encoding='UTF-8') as f:
            f.write(file_contents)
            f.close()

        global printer

        printer.gcode_raw.update(save_path)
        printer.gcode.prepare(open(save_path, 'rU'))

        ret_val = {
            'file_name': printer.gcode_raw.name,
            'file_size': printer.gcode_raw.size_hr,
            'lines': len(printer.gcode.lines)
        }

        return jsonify(ret_val)

    @app.route('/state.json')
    def state():
        global printer

        ret_val = {
            'online': printer.online,
            'printing': printer.printing,
            'paused': printer.paused,
            'port': printer.port,
            'baud': printer.baud,
            'temperature': printer.temperature,
            'gcode': None
        }

        if len(printer.gcode.lines):
            ret_val['gcode'] = {
                'file_name': printer.gcode_raw.name,
                'file_size': printer.gcode_raw.size_hr,
                'lines': len(printer.gcode.lines)
            }

        return jsonify(ret_val)


def __template_setup():
    def s_url_for(path, file):
        """
        Adds version (file last modification timestamp) query strings files under static folder.
        """
        st_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', path, file)
        if os.path.exists(st_file):
            file_last_mod = os.path.getmtime(st_file)
            path = url_for('static', filename='{}/{}'.format(path, file), v=str(int(file_last_mod)))
        else:
            path = url_for('static', filename='{}/{}'.format(path, file))

        return path

    app.jinja_env.globals['s_url_for'] = s_url_for


server_host = '127.0.0.1'
server_port = 5007


def startup_message():
    def start_loop():
        not_started = True
        while not_started:
            server_url = 'http://{}:{}'.format(server_host, server_port)
            try:
                r = requests.get(server_url)
                if r.status_code == 200:
                    print('Pyrint started at {}'.format(server_url))
                    not_started = False
                    webbrowser.open(server_url)
            except:
                pass
            time.sleep(1)

    thread = threading.Thread(target=start_loop)
    thread.start()


def __run_server():
    host = '127.0.0.1'
    port = 5007
    startup_message()
    socket_io.run(app, host=host, port=port)


if __name__ == '__main__':
    __flask_setup()
    __route_setup()
    __template_setup()
    __run_server()
