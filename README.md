[English](README.md) | [日本語](README_ja.md)

# e-Paper Environmental, System & Weather Monitoring Display 🌦️🛰️

This project is software that displays **environmental data**, **system status**, and **rain sensor information** received via MQTT on an e-Paper (electronic paper) connected to a Raspberry Pi.
It supports low power consumption, constant visibility, and restart recovery, making it ideal for headless server operation and outdoor monitoring.

<img width="642" height="642" alt="b" src="https://github.com/user-attachments/assets/2f6fd7ae-9be0-4672-86d8-9b4b31e0d997" />

---

## 📦 Hardware Used

- **Rain Sensor**: [Rain Sensor Module (sold by Switch Science)](https://www.switch-science.com/products/8202)
- **e-Paper Display**: [Waveshare 2.13inch e-Paper HAT (V4) (sold by Switch Science)](https://www.switch-science.com/products/9848)

---

## ✨ Main Features

- **Environmental Data Visualization**
  Clear display of temperature, humidity, CO₂ concentration, and discomfort index (THI) (CO₂ is displayed alongside THI on the same line)
- **Weather Monitoring (Rain Sensor Integration)**
  Concise display of rain/rain onset signs/cable abnormalities/offline/errors/restart status in one line
- **System Monitoring**
  Displays **CPU temperature only** for Pi5 and ADS-B (Automatic Dependent Surveillance–Broadcast) sides (does not display usage rates, etc.)
- **Abnormal Alerts**
  Switches to full-screen warning display when specified systemd services stop
- **Data Persistence**
  Saves latest values to JSON and restores previous state after restart
- **Flexible Configuration**
  Change MQTT connection destination, topics, display intervals, and fonts via `.env`

---

## 🛠️ Setup

💡 **For rain sensor installation, wiring, and configuration methods**, please refer to the following repository:  
[https://github.com/omiya-bonsai/atomS3-capacitive-rain-sensor](https://github.com/omiya-bonsai/atomS3-capacitive-rain-sensor)

### Requirements

**Hardware**
- Raspberry Pi (Zero 2 W to 5 recommended)
- e-Paper display (e.g., Waveshare 2.13inch)
- (Optional) Rain sensor

**Software**
- Python 3
- Git

---

### Installation

```bash
git clone https://github.com/omiya-bonsai/epaper_display_env_data.git
cd epaper_display_env_data
python3 -m venv eink
source eink/bin/activate
pip install -r requirements.txt
```

---

## `requirements.txt` Example

```txt
paho-mqtt
pillow
python-dotenv
# e-Paper model-specific driver (e.g., waveshare-epd)
```

---

## `.env` Configuration Example

```dotenv
# --- MQTT Broker ---
MQTT_BROKER_IP_ADDRESS="192.168.x.x"
MQTT_BROKER_PORT=1883
MQTT_KEEPALIVE=60
MQTT_CLIENT_ID="epaper_display_subscriber"

# --- MQTT Topics ---
MQTT_TOPIC_QZSS_CPU_TEMP="sensors/ads/cpu_temp"
MQTT_TOPIC_PI_CPU_TEMP="sensors/pi/cpu_temp"
MQTT_TOPIC_ENV4="sensors/environment/bme280"
MQTT_TOPIC_CO2_DATA="sensors/environment/co2"
MQTT_TOPIC_SENSOR_DATA="sensors/environment/thi"
MQTT_TOPIC_RAIN="home/weather/rain_sensor"

# --- System Service ---
DUMP1090_SERVICE_NAME="dump1090-fa.service"

# --- Display ---
EPAPER_DISPLAY_TYPE="epd2in13_V4"
DISPLAY_UPDATE_INTERVAL_SECONDS=300
DISPLAY_FONT_FILE_PATH="/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
DISPLAY_FONT_SIZE_PIXELS=16

# --- Data Storage ---
BASE_DIRECTORY="/home/bonsai/python3/e-ink/data"

# --- Thresholds (optional) ---
DATA_STALENESS_THRESHOLD_SECONDS=5400
NO_CHANGE_ERROR_THRESHOLD_SECONDS=3600
RAIN_ONLINE_THRESHOLD_SECONDS=90
PRERAIN_THRESHOLD_PERCENT=3.0
DEW_THRESHOLD_PERCENT=2.0
```

---

## 🚀 Execution Method (systemd Service)

Service file example:

```ini
[Unit]
Description=E-Paper Display Environment & Weather Monitor
After=network.target

[Service]
Type=simple
User=bonsai
WorkingDirectory=/home/bonsai/python3/e-ink
ExecStart=/home/bonsai/python3/e-ink/eink/bin/python /home/bonsai/python3/e-ink/epaper_display_env_data.py
Restart=always

[Install]
WantedBy=multi-user.target
```

Startup and automatic startup configuration:

```bash
sudo systemctl enable --now epaper_disp.service
```

Useful commands for operation:

```bash
systemctl status epaper_disp.service
journalctl -f -u epaper_disp.service
sudo systemctl restart epaper_disp.service
```

---

## 📡 Display Specifications (5-line configuration, CPU temperature only)

| Line | Display Content                         | Notes                                          |
| ---: | --------------------------------------- | ---------------------------------------------- |
|    1 | **Temp:** `xx.x°C`                     | Temperature (with gauge display)               |
|    2 | **Hum:** `yy.y%`                       | Humidity (with gauge display)                  |
|    3 | **Pi5:** `aa.a℃` **/** **ADS:** `bb.b℃` | CPU temperature only (slash separated)        |
|    4 | **RAIN Line**                           | Consolidated rain/signs/abnormal/offline/error/restart status |
|    5 | **THI:** `t.t` **/** **CO2:** `ccccppm` | When missing, displays `ERROR` (e.g., `THI:ERROR / CO2:800ppm`) |

---

## 🌧️ RAIN Line Status Examples

| Display Example | Meaning                    |
| --------------- | -------------------------- |
| `RAIN`          | Rain detected (may include H/M/L) |
| `RAIN→`         | Rain onset signs           |
| `OFFLINE MISS`  | No data received           |
| `CAB`           | Cable abnormality          |
| `ERR`           | Error occurred             |
| `RST`           | Restart detected           |
| `Δ:x.x%`        | Change rate (when display allows) |
| `ALL CLEAR`     | No problems                |

---

## 🙏 Acknowledgments

This project achieved the following improvements through dialogue with ChatGPT (GPT-5):

* Rain sensor monitoring logic integration
* RAIN line notation rule organization  
* Specialization of Pi5/ADS CPU temperature display functionality
* Optimization of e-Paper display character count
* README.md organization and latest specification reflection
