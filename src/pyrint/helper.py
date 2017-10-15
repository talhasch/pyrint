import os
import glob

try:
    import _winreg
except ImportError:
    pass


def get_serial_port_list():
    serial_list = []

    if os.name == "nt":
        try:
            key = _winreg.OpenKey(_winreg.HKEY_LOCAL_MACHINE, "HARDWARE\\DEVICEMAP\\SERIALCOMM")
            i = 0
            while (1):
                serial_list += [_winreg.EnumValue(key, i)[1]]
                i += 1
        except:
            pass

    serial_list = serial_list \
               + glob.glob("/dev/ttyUSB*") \
               + glob.glob("/dev/ttyACM*") \
               + glob.glob("/dev/tty.usb*") \
               + glob.glob("/dev/cu.*") \
               + glob.glob("/dev/cuaU*") \
               + glob.glob("/dev/rfcomm*")

    return serial_list
