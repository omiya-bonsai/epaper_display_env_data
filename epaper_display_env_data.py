# =============================================================================
# e-Paper ENV3 / ENV4 + Indoor Monitor
# -----------------------------------------------------------------------------
# Display:
#
# 1. Temperature  (env4 main + delta env3-env4)
# 2. Humidity     (env4 main + delta env3-env4)
# 3. Pressure     (env4 main + delta env3-env4)
# 4. IN THI / E4 THI   (highlight with inversion when ventilation is beneficial)
# 5. VENT action line (English)
#
# MQTT:
#   home/env/env4/raw
#   home/env/env3/raw
#   sensor_data
#
# Notes:
# - Temperature / Humidity use both "no receive" and "no change" checks
# - Pressure uses only "no receive" check
# - Line 5 uses CO2 + dew point + THI for a simple ventilation decision
# - Partial refresh can be enabled / disabled from .env
# =============================================================================

from typing import Optional, Tuple
import json
import time
import os
import math
import logging
import threading

from PIL import Image, ImageDraw, ImageFont
import paho.mqtt.client as mqtt
from dotenv import load_dotenv

load_dotenv()

try:
    import epaper
    EPAPER_AVAILABLE = True
except ImportError:
    EPAPER_AVAILABLE = False
    print("WARNING: epaper module not found. Running in test mode.")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------------
# SETTINGS
# -----------------------------------------------------------------------------

MQTT_BROKER_IP_ADDRESS = os.getenv("MQTT_BROKER_IP_ADDRESS", "192.168.3.82")
MQTT_BROKER_PORT = int(os.getenv("MQTT_BROKER_PORT", "1883"))
MQTT_KEEPALIVE = int(os.getenv("MQTT_KEEPALIVE", "60"))

MQTT_TOPIC_ENV3 = os.getenv("MQTT_TOPIC_ENV3", "home/env/env3/raw")
MQTT_TOPIC_ENV4 = os.getenv("MQTT_TOPIC_ENV4", "home/env/env4/raw")
MQTT_TOPIC_SENSOR_DATA = os.getenv("MQTT_TOPIC_SENSOR_DATA", "sensor_data")

INDOOR_DEVICE_ID = os.getenv("INDOOR_DEVICE_ID", "pico_w_production")

DATA_STALENESS_THRESHOLD_SECONDS = int(
    os.getenv("DATA_STALENESS_THRESHOLD_SECONDS", "5400")
)
NO_CHANGE_ERROR_THRESHOLD_SECONDS = int(
    os.getenv("NO_CHANGE_ERROR_THRESHOLD_SECONDS", "3600")
)

BASE_DIRECTORY = os.getenv("BASE_DIRECTORY", "./data")
ENV3_FILE_PATH = os.path.join(BASE_DIRECTORY, "env3.json")
ENV4_FILE_PATH = os.path.join(BASE_DIRECTORY, "env4.json")
INDOOR_FILE_PATH = os.path.join(BASE_DIRECTORY, "indoor.json")

EPAPER_DISPLAY_TYPE = os.getenv("EPAPER_DISPLAY_TYPE", "epd2in13_V4")
DISPLAY_FONT_FILE_PATH = os.getenv(
    "DISPLAY_FONT_FILE_PATH",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
)
DISPLAY_FONT_SIZE_PIXELS = int(os.getenv("DISPLAY_FONT_SIZE_PIXELS", "14"))
DISPLAY_UPDATE_INTERVAL_SECONDS = int(
    os.getenv("DISPLAY_UPDATE_INTERVAL_SECONDS", "30")
)

ENABLE_PARTIAL_REFRESH = os.getenv(
    "ENABLE_PARTIAL_REFRESH", "True"
).lower() == "true"

PARTIAL_REFRESH_EVERY_N_UPDATES = int(
    os.getenv("PARTIAL_REFRESH_EVERY_N_UPDATES", "6")
)

SKIP_UPDATE_IF_IMAGE_UNCHANGED = os.getenv(
    "SKIP_UPDATE_IF_IMAGE_UNCHANGED", "True"
).lower() == "true"

THI_HIGHLIGHT_THRESHOLD = float(
    os.getenv("THI_HIGHLIGHT_THRESHOLD", "3.0")
)

DELTA_TEMP_WARN = float(os.getenv("DELTA_TEMP_WARN", "0.5"))
DELTA_HUM_WARN = float(os.getenv("DELTA_HUM_WARN", "3.0"))
DELTA_PRESS_WARN = float(os.getenv("DELTA_PRESS_WARN", "1.0"))

# -----------------------------------------------------------------------------
# SHARED STATE
# -----------------------------------------------------------------------------

data_lock = threading.Lock()

env3 = {
    "temperature": None,
    "humidity": None,
    "pressure": None,
    "last_received_timestamp": None,
    "temperature_last_changed_timestamp": None,
    "humidity_last_changed_timestamp": None,
    "pressure_last_changed_timestamp": None,
}

env4 = {
    "temperature": None,
    "humidity": None,
    "pressure": None,
    "last_received_timestamp": None,
    "temperature_last_changed_timestamp": None,
    "humidity_last_changed_timestamp": None,
    "pressure_last_changed_timestamp": None,
}

indoor = {
    "temperature": None,
    "humidity": None,
    "thi": None,
    "co2": None,
    "last_received_timestamp": None,
    "temperature_last_changed_timestamp": None,
    "humidity_last_changed_timestamp": None,
    "thi_last_changed_timestamp": None,
    "co2_last_changed_timestamp": None,
}


class DisplayLayoutManager:
    def __init__(self, image_width: int, image_height: int):
        self.text_area_start_x = 8
        self.single_section_height = image_height // 5


# -----------------------------------------------------------------------------
# JSON CACHE
# -----------------------------------------------------------------------------

def save_data_to_json_file(file_path: str, data_dict: dict):
    try:
        dir_path = os.path.dirname(file_path) or "."
        os.makedirs(dir_path, exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as file:
            json.dump(data_dict, file, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"File save error {file_path}: {e}")


def load_data_from_json_file(file_path: str) -> dict:
    try:
        with open(file_path, "r", encoding="utf-8") as file:
            return json.load(file)
    except (json.JSONDecodeError, FileNotFoundError) as e:
        logger.warning(f"File load error {file_path}: {e}")
        return {}
    except Exception as e:
        logger.error(f"Unexpected load error {file_path}: {e}")
        return {}


def restore_cached_data():
    global env3, env4, indoor

    os.makedirs(BASE_DIRECTORY, exist_ok=True)

    env3_loaded = load_data_from_json_file(ENV3_FILE_PATH)
    if env3_loaded:
        env3.update(env3_loaded)

    env4_loaded = load_data_from_json_file(ENV4_FILE_PATH)
    if env4_loaded:
        env4.update(env4_loaded)

    indoor_loaded = load_data_from_json_file(INDOOR_FILE_PATH)
    if indoor_loaded:
        indoor.update(indoor_loaded)


# -----------------------------------------------------------------------------
# MQTT
# -----------------------------------------------------------------------------

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        logger.info("MQTT connected successfully")
        client.subscribe(MQTT_TOPIC_ENV3)
        client.subscribe(MQTT_TOPIC_ENV4)
        client.subscribe(MQTT_TOPIC_SENSOR_DATA)
        logger.info(f"Subscribed: {MQTT_TOPIC_ENV3}")
        logger.info(f"Subscribed: {MQTT_TOPIC_ENV4}")
        logger.info(f"Subscribed: {MQTT_TOPIC_SENSOR_DATA}")
    else:
        logger.error(f"MQTT connection failed: rc={rc}")


def update_env_state(target: dict, payload: dict, received_timestamp: float):
    new_temp = payload.get("temperature")
    if new_temp is not None:
        if new_temp != target["temperature"]:
            target["temperature_last_changed_timestamp"] = received_timestamp
        target["temperature"] = new_temp

    new_humidity = payload.get("humidity")
    if new_humidity is not None:
        if new_humidity != target["humidity"]:
            target["humidity_last_changed_timestamp"] = received_timestamp
        target["humidity"] = new_humidity

    new_pressure = payload.get("pressure")
    if new_pressure is not None:
        if new_pressure != target["pressure"]:
            target["pressure_last_changed_timestamp"] = received_timestamp
        target["pressure"] = new_pressure

    target["last_received_timestamp"] = received_timestamp


def update_indoor_state(target: dict, payload: dict, received_timestamp: float):
    new_temp = payload.get("temperature")
    if new_temp is not None:
        if new_temp != target["temperature"]:
            target["temperature_last_changed_timestamp"] = received_timestamp
        target["temperature"] = new_temp

    new_humidity = payload.get("humidity")
    if new_humidity is not None:
        if new_humidity != target["humidity"]:
            target["humidity_last_changed_timestamp"] = received_timestamp
        target["humidity"] = new_humidity

    new_thi = payload.get("thi")
    if new_thi is not None:
        if new_thi != target["thi"]:
            target["thi_last_changed_timestamp"] = received_timestamp
        target["thi"] = new_thi

    new_co2 = payload.get("co2")
    if new_co2 is not None:
        if new_co2 != target["co2"]:
            target["co2_last_changed_timestamp"] = received_timestamp
        target["co2"] = new_co2

    target["last_received_timestamp"] = received_timestamp


def on_message(client, userdata, msg):
    global env3, env4, indoor

    received_timestamp = time.time()

    try:
        payload_str = msg.payload.decode("utf-8", errors="ignore")
        payload = json.loads(payload_str)

        with data_lock:
            if msg.topic == MQTT_TOPIC_ENV3:
                update_env_state(env3, payload, received_timestamp)
                save_data_to_json_file(ENV3_FILE_PATH, env3)
                logger.info(
                    f"ENV3 received: T={env3['temperature']} "
                    f"H={env3['humidity']} P={env3['pressure']}"
                )

            elif msg.topic == MQTT_TOPIC_ENV4:
                update_env_state(env4, payload, received_timestamp)
                save_data_to_json_file(ENV4_FILE_PATH, env4)
                logger.info(
                    f"ENV4 received: T={env4['temperature']} "
                    f"H={env4['humidity']} P={env4['pressure']}"
                )

            elif msg.topic == MQTT_TOPIC_SENSOR_DATA:
                device_id = payload.get("device_id")
                if device_id is None or device_id == INDOOR_DEVICE_ID:
                    update_indoor_state(indoor, payload, received_timestamp)
                    save_data_to_json_file(INDOOR_FILE_PATH, indoor)
                    logger.info(
                        f"INDOOR received: T={indoor['temperature']} "
                        f"H={indoor['humidity']} THI={indoor['thi']} CO2={indoor['co2']}"
                    )

    except Exception as e:
        logger.error(f"Error during MQTT message processing: {e}", exc_info=True)


def on_disconnect(client, userdata, rc):
    if rc != 0:
        logger.warning(f"Unexpectedly disconnected from MQTT broker. rc={rc}")
    else:
        logger.info("Normally disconnected from MQTT broker")


def initialize_mqtt_client_connection():
    mqtt_client = mqtt.Client()
    mqtt_client.on_connect = on_connect
    mqtt_client.on_message = on_message
    mqtt_client.on_disconnect = on_disconnect

    try:
        mqtt_client.connect(MQTT_BROKER_IP_ADDRESS, MQTT_BROKER_PORT, MQTT_KEEPALIVE)
        mqtt_client.loop_start()
        logger.info("Started MQTT communication in background")
        return mqtt_client
    except Exception as e:
        logger.error(f"MQTT connection error: {e}")
        return None


# -----------------------------------------------------------------------------
# DISPLAY SYSTEM
# -----------------------------------------------------------------------------

class EnvironmentalDataDisplaySystem:
    def __init__(self):
        restore_cached_data()

        self.mqtt_communication_client = initialize_mqtt_client_connection()
        if self.mqtt_communication_client is None:
            raise RuntimeError("MQTT connection failed")

        self.epaper_device = None
        self.partial_refresh_supported = False
        self.partial_refresh_base_initialized = False
        self.partial_refresh_count = 0
        self.last_display_buffer = None

        if EPAPER_AVAILABLE:
            try:
                self.epaper_device = epaper.epaper(EPAPER_DISPLAY_TYPE).EPD()
                self.epaper_device.init()
                logger.info("e-Paper display initialized")
            except Exception as e:
                logger.error(f"e-Paper display initialization failed: {e}")
                self.epaper_device = None
        else:
            logger.warning("e-Paper display not available (test mode)")

        if self.epaper_device is not None:
            self.partial_refresh_supported = (
                hasattr(self.epaper_device, "displayPartBaseImage")
                and hasattr(self.epaper_device, "displayPartial")
            )
            logger.info(f"Partial refresh supported: {self.partial_refresh_supported}")

    # -------------------------------------------------------------------------
    # Utility
    # -------------------------------------------------------------------------

    def _is_error(
        self,
        value: Optional[float],
        last_received_ts: Optional[float],
        last_changed_ts: Optional[float]
    ) -> bool:
        now = time.time()

        stale_by_no_receive = (
            last_received_ts is None
            or (now - last_received_ts) >= DATA_STALENESS_THRESHOLD_SECONDS
        )
        stale_by_no_change = (
            last_changed_ts is None
            or (now - last_changed_ts) > NO_CHANGE_ERROR_THRESHOLD_SECONDS
        )

        return value is None or stale_by_no_receive or stale_by_no_change

    def _is_pressure_error(
        self,
        value: Optional[float],
        last_received_ts: Optional[float]
    ) -> bool:
        now = time.time()

        stale_by_no_receive = (
            last_received_ts is None
            or (now - last_received_ts) >= DATA_STALENESS_THRESHOLD_SECONDS
        )

        return value is None or stale_by_no_receive

    def _fit_text(
        self,
        drawing_context: ImageDraw.ImageDraw,
        font: ImageFont.ImageFont,
        text: str,
        max_width: int
    ) -> str:
        try:
            bbox = drawing_context.textbbox((0, 0), text, font=font)
            width = bbox[2] - bbox[0]
        except AttributeError:
            width, _ = drawing_context.textsize(text, font=font)

        if width <= max_width:
            return text

        ellipsis = "…"
        trimmed = text
        while trimmed:
            trimmed = trimmed[:-1]
            try:
                bbox = drawing_context.textbbox((0, 0), trimmed + ellipsis, font=font)
                w = bbox[2] - bbox[0]
            except AttributeError:
                w, _ = drawing_context.textsize(trimmed + ellipsis, font=font)
            if w <= max_width:
                return trimmed + ellipsis
        return ellipsis

    def _buffer_changed(self, new_buffer) -> bool:
        if self.last_display_buffer is None:
            return True
        return bytes(new_buffer) != bytes(self.last_display_buffer)

    def _remember_buffer(self, buffer_data):
        self.last_display_buffer = bytes(buffer_data)

    def _calc_thi(self, temp: Optional[float], hum: Optional[float]) -> Optional[float]:
        if temp is None or hum is None:
            return None
        try:
            return round(0.81 * temp + 0.01 * hum * (0.99 * temp - 14.3) + 46.3, 1)
        except Exception:
            return None

    def _calc_dew_point(self, temp: Optional[float], hum: Optional[float]) -> Optional[float]:
        if temp is None or hum is None:
            return None
        try:
            a = 17.62
            b = 243.12
            gamma = (a * temp) / (b + temp) + math.log(hum / 100.0)
            return round((b * gamma) / (a - gamma), 1)
        except Exception:
            return None

    # -------------------------------------------------------------------------
    # Line builders
    # -------------------------------------------------------------------------

    def _fmt_dynamic_delta_line(
        self,
        label: str,
        e4_value: Optional[float],
        e4_last_received_ts: Optional[float],
        e4_last_changed_ts: Optional[float],
        e3_value: Optional[float],
        e3_last_received_ts: Optional[float],
        e3_last_changed_ts: Optional[float],
        unit: str,
        warn_threshold: float,
    ) -> str:
        e4_error = self._is_error(e4_value, e4_last_received_ts, e4_last_changed_ts)
        e3_error = self._is_error(e3_value, e3_last_received_ts, e3_last_changed_ts)

        if e4_error:
            return f"{label} ERROR"

        if e3_error:
            return f"{label} {e4_value:.1f}{unit} ?"

        delta = round(e3_value - e4_value, 1)
        warn = "!" if abs(delta) >= warn_threshold else " "

        return f"{label} {e4_value:.1f}{unit} {warn}{delta:+.1f}"

    def _build_temperature_line(self) -> str:
        return self._fmt_dynamic_delta_line(
            "Temp:",
            env4["temperature"],
            env4["last_received_timestamp"],
            env4["temperature_last_changed_timestamp"],
            env3["temperature"],
            env3["last_received_timestamp"],
            env3["temperature_last_changed_timestamp"],
            "°C",
            DELTA_TEMP_WARN,
        )

    def _build_humidity_line(self) -> str:
        return self._fmt_dynamic_delta_line(
            "Hum:",
            env4["humidity"],
            env4["last_received_timestamp"],
            env4["humidity_last_changed_timestamp"],
            env3["humidity"],
            env3["last_received_timestamp"],
            env3["humidity_last_changed_timestamp"],
            "%",
            DELTA_HUM_WARN,
        )

    def _build_pressure_line(self) -> str:
        env4_error = self._is_pressure_error(
            env4["pressure"],
            env4["last_received_timestamp"],
        )
        env3_error = self._is_pressure_error(
            env3["pressure"],
            env3["last_received_timestamp"],
        )

        if env4_error:
            return "Press: ERROR"

        if env3_error:
            return f"Press: {env4['pressure']:.1f} ?"

        delta = round(env3["pressure"] - env4["pressure"], 1)
        warn = "!" if abs(delta) >= DELTA_PRESS_WARN else " "

        return f"Press: {env4['pressure']:.1f} {warn}{delta:+.1f}"

    def _build_thi_line(self) -> Tuple[str, bool]:
        indoor_error = self._is_error(
            indoor["thi"],
            indoor["last_received_timestamp"],
            indoor["thi_last_changed_timestamp"],
        )

        e4_thi = self._calc_thi(env4["temperature"], env4["humidity"])
        e4_error = self._is_error(
            e4_thi,
            env4["last_received_timestamp"],
            env4["humidity_last_changed_timestamp"],
        )

        indoor_text = "ERROR" if indoor_error else f"{indoor['thi']:.1f}"
        e4_text = "ERROR" if e4_error or e4_thi is None else f"{e4_thi:.1f}"

        if indoor_error or e4_error or e4_thi is None or indoor["thi"] is None:
            return f"THI IN:{indoor_text} ? E4:{e4_text}", False

        if indoor["thi"] > e4_thi:
            symbol = ">"
        elif indoor["thi"] < e4_thi:
            symbol = "<"
        else:
            symbol = "="

        delta_thi = indoor["thi"] - e4_thi
        ventilation_beneficial = delta_thi >= THI_HIGHLIGHT_THRESHOLD

        return f"THI IN:{indoor_text} {symbol} E4:{e4_text}", ventilation_beneficial

    def _build_ventilation_line(self) -> str:
        indoor_co2 = indoor["co2"]
        indoor_temp = indoor["temperature"]
        indoor_hum = indoor["humidity"]
        outdoor_temp = env4["temperature"]
        outdoor_hum = env4["humidity"]

        indoor_temp_error = self._is_error(
            indoor_temp,
            indoor["last_received_timestamp"],
            indoor["temperature_last_changed_timestamp"],
        )
        indoor_hum_error = self._is_error(
            indoor_hum,
            indoor["last_received_timestamp"],
            indoor["humidity_last_changed_timestamp"],
        )
        indoor_co2_error = self._is_error(
            indoor_co2,
            indoor["last_received_timestamp"],
            indoor["co2_last_changed_timestamp"],
        )

        outdoor_temp_error = self._is_error(
            outdoor_temp,
            env4["last_received_timestamp"],
            env4["temperature_last_changed_timestamp"],
        )
        outdoor_hum_error = self._is_error(
            outdoor_hum,
            env4["last_received_timestamp"],
            env4["humidity_last_changed_timestamp"],
        )

        if indoor_temp_error or indoor_hum_error or outdoor_temp_error or outdoor_hum_error:
            return "VENT: UNKNOWN NO DATA"

        if indoor_co2_error:
            return "VENT: UNKNOWN NO CO2"

        dp_in = self._calc_dew_point(indoor_temp, indoor_hum)
        dp_out = self._calc_dew_point(outdoor_temp, outdoor_hum)
        thi_in = self._calc_thi(indoor_temp, indoor_hum)
        thi_out = self._calc_thi(outdoor_temp, outdoor_hum)

        if None in (dp_in, dp_out, thi_in, thi_out, indoor_co2):
            return "VENT: UNKNOWN CALC ERR"

        delta_dp = dp_in - dp_out
        delta_thi = thi_in - thi_out

        if indoor_co2 >= 2000:
            return "VENT: FORCE CO2 HIGH"

        if indoor_co2 >= 1500:
            if delta_dp > 0:
                return "VENT: OPEN CO2 HIGH"
            return "VENT: SHORT CO2 HIGH"

        if delta_dp < -1:
            if thi_out >= thi_in:
                return "VENT: AC HUMID OUT"
            return "VENT: CLOSE HUMID OUT"

        if delta_dp > 1:
            return "VENT: OPEN DRY AIR"

        if delta_thi > 1:
            return "VENT: OPEN COOL OUT"

        if indoor_co2 >= 1000:
            return "VENT: SHORT CO2 MID"

        return "VENT: CLOSE SMALL DIFF"

    # -------------------------------------------------------------------------
    # Rendering
    # -------------------------------------------------------------------------

    def _create_display_image_for_epaper(
        self,
        epaper_device,
        display_font: ImageFont.ImageFont
    ) -> Image.Image:
        image_size = (250, 122) if epaper_device is None else (epaper_device.height, epaper_device.width)

        display_image = Image.new("1", image_size, 255)
        drawing_context = ImageDraw.Draw(display_image)

        layout = DisplayLayoutManager(*image_size)
        max_text_width = image_size[0] - layout.text_area_start_x - 6

        with data_lock:
            thi_line, thi_highlight = self._build_thi_line()

            lines = [
                self._build_temperature_line(),
                self._build_humidity_line(),
                self._build_pressure_line(),
                thi_line,
                self._build_ventilation_line(),
            ]

        for i, line_text in enumerate(lines):
            y_pos = i * layout.single_section_height
            text_y = y_pos + 4

            fitted_text = self._fit_text(
                drawing_context,
                display_font,
                line_text,
                max_text_width,
            )

            if i == 3 and thi_highlight:
                drawing_context.rectangle(
                    [
                        (0, y_pos),
                        (image_size[0], y_pos + layout.single_section_height)
                    ],
                    fill=0
                )
                if fitted_text:
                    drawing_context.text(
                        (layout.text_area_start_x, text_y),
                        fitted_text,
                        font=display_font,
                        fill=255
                    )
            else:
                if fitted_text:
                    drawing_context.text(
                        (layout.text_area_start_x, text_y),
                        fitted_text,
                        font=display_font,
                        fill=0
                    )

            if i < 4:
                drawing_context.line(
                    [
                        (0, y_pos + layout.single_section_height),
                        (image_size[0], y_pos + layout.single_section_height)
                    ],
                    fill=0
                )

        return display_image.rotate(90, expand=True)

    # -------------------------------------------------------------------------
    # Update
    # -------------------------------------------------------------------------

    def update_display_with_current_data(self):
        try:
            try:
                font = ImageFont.truetype(
                    DISPLAY_FONT_FILE_PATH,
                    DISPLAY_FONT_SIZE_PIXELS,
                    index=0
                )
            except OSError:
                logger.warning("Specified font not found. Using default font.")
                font = ImageFont.load_default()

            display_image = self._create_display_image_for_epaper(self.epaper_device, font)

            if self.epaper_device is None:
                logger.info("Test mode: Display update simulated")
                return

            buffer_data = self.epaper_device.getbuffer(display_image)

            if SKIP_UPDATE_IF_IMAGE_UNCHANGED and not self._buffer_changed(buffer_data):
                logger.info("Display image unchanged. Skipping refresh.")
                return

            use_partial = (
                ENABLE_PARTIAL_REFRESH
                and self.partial_refresh_supported
                and self.partial_refresh_base_initialized
                and self.partial_refresh_count < PARTIAL_REFRESH_EVERY_N_UPDATES
            )

            if use_partial:
                if hasattr(self.epaper_device, "init_fast"):
                    self.epaper_device.init_fast()
                else:
                    self.epaper_device.init()

                self.epaper_device.displayPartial(buffer_data)
                self.partial_refresh_count += 1
                logger.info(
                    f"Partial refresh completed "
                    f"({self.partial_refresh_count}/{PARTIAL_REFRESH_EVERY_N_UPDATES})"
                )

            else:
                self.epaper_device.init()

                if ENABLE_PARTIAL_REFRESH and self.partial_refresh_supported:
                    self.epaper_device.displayPartBaseImage(buffer_data)
                    self.partial_refresh_base_initialized = True
                    self.partial_refresh_count = 0
                    logger.info("Full refresh completed with new partial-refresh base image")
                else:
                    self.epaper_device.display(buffer_data)
                    logger.info("Full refresh completed")

            self._remember_buffer(buffer_data)
            self.epaper_device.sleep()

        except Exception as e:
            logger.error(f"Display update error: {e}", exc_info=True)
            self.partial_refresh_base_initialized = False
            self.partial_refresh_count = 0

    def start_continuous_display_updates(self):
        logger.info(
            f"Starting continuous display updates "
            f"(interval: {DISPLAY_UPDATE_INTERVAL_SECONDS} seconds)"
        )
        while True:
            try:
                self.update_display_with_current_data()
                time.sleep(DISPLAY_UPDATE_INTERVAL_SECONDS)
            except KeyboardInterrupt:
                logger.info("Received stop request from user")
                break
            except Exception as e:
                logger.error(f"Main loop error: {e}", exc_info=True)
                logger.info("Retrying in 60 seconds...")
                time.sleep(60)

        if self.mqtt_communication_client:
            self.mqtt_communication_client.loop_stop()
            self.mqtt_communication_client.disconnect()
            logger.info("Disconnected MQTT connection")


# -----------------------------------------------------------------------------
# ENTRY POINT
# -----------------------------------------------------------------------------

def main():
    try:
        logger.info("Starting ENV3 / ENV4 display system...")
        display_system = EnvironmentalDataDisplaySystem()
        logger.info("System initialization completed")
        display_system.start_continuous_display_updates()
    except Exception as e:
        logger.error(f"System startup error: {e}", exc_info=True)
    finally:
        logger.info("ENV3 / ENV4 display system terminated")


if __name__ == "__main__":
    main()
