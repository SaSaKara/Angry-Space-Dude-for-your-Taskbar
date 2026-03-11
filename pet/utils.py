import ctypes
import subprocess
import sys

from pet.consts import OS_DARWIN, OS_WIN32

def get_work_area():
    # Check for Darwin OS to avoid breaking Windows
    if sys.platform == OS_DARWIN:
        # Get the macOS visible frame excluding menu bar and dock
        try:
            from AppKit import NSScreen
            frame = NSScreen.mainScreen().visibleFrame()
            origin = frame.origin
            size = frame.size
            screen_h = NSScreen.mainScreen().frame().size.height
            top = int(screen_h - origin.y - size.height)
            return int(origin.x), top, int(origin.x + size.width), int(top + size.height)
        except ImportError:
            pass

        # Introduce a fallback in case our first attempt fails
        try:
            out = subprocess.check_output(
                ["system_profiler", "SPDisplaysDataType"],
                text=True, timeout=5,
            )
            for line in out.splitlines():
                if "Resolution" in line:
                    parts = line.split()
                    w = int(parts[1])
                    h = int(parts[3])
                    # An internet search showed the menu is ~25px and the dock is ~70px normally
                    # we need to take this into account or our marine will be shifted out of bounds of the screen.
                    return 0, 25, w, h - 70
        except Exception:
            pass
        return 0, 25, 1920, 1010

    # Continue with SaSaKara's original implementation to ensure Windows continues working.
    if sys.platform != OS_WIN32:
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
