import ctypes
import sys


def get_work_area():
    if sys.platform != "win32":
        return 0, 0, 1920, 1080

    class RECT(ctypes.Structure):
        _fields_ = [
            ("left", ctypes.c_long),
            ("top", ctypes.c_long),
            ("right", ctypes.c_long),
            ("bottom", ctypes.c_long),
        ]

    rect = RECT()
    spi_get_work_area = 0x0030

    if ctypes.windll.user32.SystemParametersInfoW(
        spi_get_work_area, 0, ctypes.byref(rect), 0
    ):
        return rect.left, rect.top, rect.right, rect.bottom

    user32 = ctypes.windll.user32
    sw = user32.GetSystemMetrics(0)
    sh = user32.GetSystemMetrics(1)
    return 0, 0, sw, sh