# ~/python3/e-ink/epaper.py
# Adapter to use Waveshare drivers without changing your main script.

import os
import sys
from pathlib import Path

# 1) GPIO は pigpio を使って安定動作
os.environ.setdefault("GPIOZERO_PIN_FACTORY", "pigpio")

# 2) Waveshare ライブラリへのパスを解決
candidates = []

env_path = os.environ.get("WAVESHARE_EPD_PATH")
if env_path:
    candidates.append(Path(env_path))

candidates += [
    Path.home() / "e-Paper" / "RaspberryPi_JetsonNano" / "python" / "lib",
    Path.home() / "e-Paper" / "python" / "lib",
    Path("/usr/local/lib/python3/dist-packages"),
    Path("/usr/lib/python3/dist-packages"),
]

for p in candidates:
    lib = p / "waveshare_epd"
    if lib.exists() and str(p) not in sys.path:
        sys.path.insert(0, str(p))
        break


class _EPDWrapper:
    def __init__(self, driver_module):
        self._drv = driver_module
        self._epd = self._drv.EPD()

    def init(self):
        return self._epd.init()

    def init_fast(self):
        if hasattr(self._epd, "init_fast"):
            return self._epd.init_fast()
        return self._epd.init()

    def display(self, buf):
        return self._epd.display(buf)

    def displayPartBaseImage(self, buf):
        if hasattr(self._epd, "displayPartBaseImage"):
            return self._epd.displayPartBaseImage(buf)
        # partial refresh 非対応機では full refresh にフォールバック
        return self._epd.display(buf)

    def displayPartial(self, buf):
        if hasattr(self._epd, "displayPartial"):
            return self._epd.displayPartial(buf)
        # partial refresh 非対応機では full refresh にフォールバック
        return self._epd.display(buf)

    def getbuffer(self, img):
        return self._epd.getbuffer(img)

    def sleep(self):
        return self._epd.sleep()

    @property
    def width(self):
        return self._epd.width

    @property
    def height(self):
        return self._epd.height

    def __getattr__(self, name):
        # 未定義メソッドや属性は下流ドライバへ委譲
        return getattr(self._epd, name)


class _Factory:
    def __init__(self, epd_type: str):
        self.epd_type = epd_type

    def EPD(self):
        if self.epd_type in ("epd2in13_V4", "2in13_V4", "2.13_V4"):
            from waveshare_epd import epd2in13_V4 as drv
            return _EPDWrapper(drv)
        raise ValueError(f"Unsupported EPAPER_DISPLAY_TYPE: {self.epd_type}")


def epaper(epd_type: str):
    return _Factory(epd_type)
