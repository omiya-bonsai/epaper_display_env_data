# ~/python3/e-ink/epaper.py
# Adapter to use Waveshare drivers without changing your main script.

import os, sys
from pathlib import Path

# 1) GPIO は pigpio を使って安定動作
os.environ.setdefault("GPIOZERO_PIN_FACTORY", "pigpio")

# 2) Waveshare ライブラリへのパスを解決
#   - 環境変数 WAVESHARE_EPD_PATH があれば最優先
#   - なければ、よくある配置を順に探す
candidates = []

env_path = os.environ.get("WAVESHARE_EPD_PATH")
if env_path:
    candidates.append(Path(env_path))

# 代表的な配置（あなたの環境）
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
        break  # 最初に見つかった場所だけ挿入

# 3) 最低限のラッパークラス
class _EPDWrapper:
    def __init__(self, driver_module):
        self._drv = driver_module
        self._epd = self._drv.EPD()

    def init(self):            return self._epd.init()
    def display(self, buf):    return self._epd.display(buf)
    def getbuffer(self, img):  return self._epd.getbuffer(img)
    def sleep(self):           return self._epd.sleep()
    @property
    def width(self):           return self._epd.width
    @property
    def height(self):          return self._epd.height

class _Factory:
    def __init__(self, epd_type: str):
        self.epd_type = epd_type

    def EPD(self):
        # 必要に応じて他サイズを elif で追加してください
        if self.epd_type in ("epd2in13_V4", "2in13_V4", "2.13_V4"):
            from waveshare_epd import epd2in13_V4 as drv
            return _EPDWrapper(drv)
        raise ValueError(f"Unsupported EPAPER_DISPLAY_TYPE: {self.epd_type}")

def epaper(epd_type: str):
    """あなたのメインスクリプトが期待しているファクトリ互換API"""
    return _Factory(epd_type)
