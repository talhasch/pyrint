from __future__ import unicode_literals, print_function

import logging
import math
import os
import tempfile
import threading
import time
import webbrowser

import requests
from flask import Flask, render_template, jsonify, url_for, request, abort
from flask_babel import Babel
from tornado import websocket
from tornado.ioloop import IOLoop
from tornado.web import Application, FallbackHandler
from tornado.wsgi import WSGIContainer

os.sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../")))

from pyrint.helper import get_serial_port_list
from pyrint.printer import set_emitter, printer

logging.basicConfig(level=logging.INFO)

app = Flask(__name__)

app.config['DEVELOPMENT'] = False
app.config['DEBUG'] = False

server_host = '127.0.0.1'
server_port = 5007

clients = []


class SocketHandler(websocket.WebSocketHandler):
    def check_origin(self, origin):
        return True

    def open(self):
        if self not in clients:
            clients.append(self)

    def on_close(self):
        if self in clients:
            clients.remove(self)


def emit_clients(msg, args={}):
    for c in clients:
        c.write_message({'event': msg, 'args': args})


set_emitter(emit_clients)


def __flask_setup():
    Babel(app)


def __route_setup():
    """
    Flask routing setup
    """

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
        ret_val = {
            'online': printer.online,
            'printing': printer.printing,
            'paused': printer.paused,
            'port': printer.port,
            'baud': printer.baud,
            'temperature': printer.temperature,
            'gcode': None,
            'pos': {
                'x': math.ceil(printer.analyzer.abs_z),
                'y': math.ceil(printer.analyzer.abs_y),
                'z': math.ceil(printer.analyzer.abs_z),
            }
        }

        if len(printer.gcode.lines):
            ret_val['gcode'] = {
                'file_name': printer.gcode_raw.name,
                'file_size': printer.gcode_raw.size_hr,
                'lines': len(printer.gcode.lines),
                'lines_sent': len(printer.sentlines),
            }

        return jsonify(ret_val)

    @app.route('/connect', methods=('POST',))
    def connect_printer():
        data = request.json
        assert 'port' in data and 'baud' in data
        port = data['port'].strip()
        baud = data['baud']

        # disconnect if printer already connected
        if printer is not None and printer.online:
            printer.disconnect()

        printer.connect(port, baud=baud)

        return 'OK'

    @app.route('/start', methods=('POST',))
    def start_printing():
        if printer.paused:
            printer.resume()
        else:
            printer.startprint(printer.gcode)

        return 'OK'

    @app.route('/pause', methods=('POST',))
    def pause_printing():
        if printer.printing:
            printer.pause()
        emit_clients('paused')

        return 'OK'

    @app.route('/cancel', methods=('POST',))
    def cancel_printing():
        if printer is not None:
            printer.cancelprint()
        emit_clients('cancelled')

        return 'OK'

    @app.route('/disconnect', methods=('POST',))
    def disconnect_printer():
        if printer is not None:
            printer.disconnect()

        return 'OK'

    @app.route('/run_gcode', methods=('POST',))
    def run_gcode():
        data = request.json
        if 'code' not in data:
            abort(400)

        if printer is not None:
            gcode = data['code'].strip()
            printer.send_now(gcode)

        return 'OK'


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
    cont = WSGIContainer(app)

    application = Application([
        (r'/ws', SocketHandler),
        (r".*", FallbackHandler, dict(fallback=cont)),
    ])

    application.listen(server_port, address=server_host)
    IOLoop.instance().start()


if __name__ == '__main__':
    __flask_setup()
    __route_setup()
    __template_setup()
    __run_server()
