from __future__ import unicode_literals, print_function

import logging
import math
import os
import threading
import time

from flask import Flask
from humanize import naturalsize
from tornado import websocket

from pyrint.printcore import PrintCore
from pyrint.gcoder import LightGCode

logging.basicConfig(level=logging.INFO)


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
emit_fn = None


def set_emitter(e_fn):
    global emit_fn
    emit_fn = e_fn


def emit(msg, args={}):
    if emit_fn:
        emit_fn(msg, args)


def printer_online_cb():
    emit('online', {'port': printer.port, 'baud': printer.baud})

    # request temperature immediately
    printer.send_now("M105")


def printer_disconnect_cb():
    emit('disconnected')
    create_printer()


def printer_error_cb(error):
    emit('error', {'msg': error})
    printer.disconnect()
    create_printer()


def printer_temp_cb(temp):
    printer.update_temperature(temp)
    emit('temperature', {'temp': printer.temperature})


def printer_receive_cb(line):
    if line.startswith('T:'):
        printer.update_temperature(line)
        emit('temperature', {'temp': printer.temperature})

    emit('received', {
        'lines_sent': len(printer.sentlines),
        'x': math.ceil(printer.analyzer.abs_x),
        'y': math.ceil(printer.analyzer.abs_y),
        'z': math.ceil(printer.analyzer.abs_z)
    })


def printer_start_cb(resuming):
    emit('started')


def printer_end_cb():
    emit('ended')


def printer_layer_change_cb(layer):
    emit('layer_changed', {'msg': str(layer)})


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
    printer.layerchangecb = printer_layer_change_cb


create_printer()


# Request temperature in every 60 seconds in order to get printer temperature changes after first heating.
def refresh_printer_temperature():
    while True:
        if printer is not None and printer.online:
            try:
                printer.send_now("M105")
            except Exception:
                pass

        time.sleep(60)


threading.Thread(target=refresh_printer_temperature).start()
