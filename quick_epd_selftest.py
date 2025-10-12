# ~/python3/e-ink/quick_epd_selftest.py
import os, time
os.environ.setdefault("GPIOZERO_PIN_FACTORY", "pigpio")

import epaper
from PIL import Image, ImageDraw

dev = epaper.epaper("epd2in13_V4").EPD()
dev.init()

# 白塗り
img = Image.new('1', (dev.height, dev.width), 255)
draw = ImageDraw.Draw(img)
draw.text((10, 10), "E-Paper OK", fill=0)
dev.display(dev.getbuffer(img))
time.sleep(2)

# 反転
img2 = Image.new('1', (dev.height, dev.width), 0)
draw2 = ImageDraw.Draw(img2)
draw2.text((10, 10), "Inverted", fill=1)
dev.display(dev.getbuffer(img2))
time.sleep(2)

dev.sleep()
print("Done")
