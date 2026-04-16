# =============================================================================
# e-Paper ENV3 / ENV4 Monitor (5-line layout with gauges)
# -----------------------------------------------------------------------------
# 表示内容:
#
# 1. ENV4 Temperature + gauge
# 2. ENV4 Humidity    + gauge
# 3. ENV3 Temperature + gauge
# 4. ENV3 Humidity    + gauge
# 5. ENV4 Pressure / ENV3 Pressure
#
# MQTT:
#   home/env/env4/raw
#   home/env/env3/raw
#
# 機能:
# - MQTT受信
# - JSONキャッシュ保存/復元
# - stale判定
# - partial refresh対応
# - unchanged image skip
# - test mode対応
# =============================================================================

from dataclasses import dataclass
from typing import Optional
import json
import time
import os
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

DATA_STALENESS_THRESHOLD_SECONDS = int(
    os.getenv("DATA_STALENESS_THRESHOLD_SECONDS", "5400")
)
NO_CHANGE_ERROR_THRESHOLD_SECONDS = int(
    os.getenv("NO_CHANGE_ERROR_THRESHOLD_SECONDS", "3600")
)

BASE_DIRECTORY = os.getenv("BASE_DIRECTORY", "./data")
ENV3_FILE_PATH = os.path.join(BASE_DIRECTORY, "env3.json")
ENV4_FILE_PATH = os.path.join(BASE_DIRECTORY, "env4.json")

EPAPER_DISPLAY_TYPE = os.getenv("EPAPER_DISPLAY_TYPE", "epd2in13_V4")
DISPLAY_FONT_FILE_PATH = os.getenv(
    "DISPLAY_FONT_FILE_PATH",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
)
DISPLAY_FONT_SIZE_PIXELS = int(os.getenv("DISPLAY_FONT_SIZE_PIXELS", "16"))
DISPLAY_UPDATE_INTERVAL_SECONDS = int(
    os.getenv("DISPLAY_UPDATE_INTERVAL_SECONDS", "300")
)

ENABLE_PARTIAL_REFRESH = os.getenv(
    "ENABLE_PARTIAL_REFRESH", "True"
).lower() == "true"
PARTIAL_REFRESH_EVERY_N_UPDATES = int(
    os.getenv("PARTIAL_REFRESH_EVERY_N_UPDATES", "10")
)
SKIP_UPDATE_IF_IMAGE_UNCHANGED = os.getenv(
    "SKIP_UPDATE_IF_IMAGE_UNCHANGED", "True"
).lower() == "true"

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


@dataclass
class SensorGaugeRange:
    minimum_value: float
    maximum_value: float
    unit_symbol: str


class DisplayLayoutManager:
    def __init__(self, image_width: int, image_height: int):
        self.text_area_start_x = 10
        self.label_area_width = 80
        self.gauge_bar_start_x = self.label_area_width + 70
        self.gauge_bar_total_width = image_width - self.gauge_bar_start_x - 10
        self.gauge_bar_height = 16
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
    global env3, env4

    os.makedirs(BASE_DIRECTORY, exist_ok=True)

    env3_loaded = load_data_from_json_file(ENV3_FILE_PATH)
    if env3_loaded:
        env3.update(env3_loaded)

    env4_loaded = load_data_from_json_file(ENV4_FILE_PATH)
    if env4_loaded:
        env4.update(env4_loaded)


# -----------------------------------------------------------------------------
# MQTT
# -----------------------------------------------------------------------------

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        logger.info("MQTT connected successfully")
        client.subscribe(MQTT_TOPIC_ENV3)
        client.subscribe(MQTT_TOPIC_ENV4)
        logger.info(f"Subscribed: {MQTT_TOPIC_ENV3}")
        logger.info(f"Subscribed: {MQTT_TOPIC_ENV4}")
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


def on_message(client, userdata, msg):
    global env3, env4

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

        self.sensor_gauge_ranges = {
            "temperature": SensorGaugeRange(-10.0, 50.0, "°C"),
            "humidity": SensorGaugeRange(0.0, 100.0, "%"),
        }

    # -------------------------------------------------------------------------
    # Utility
    # -------------------------------------------------------------------------

    def _is_error(self, value: Optional[float], last_received_ts: Optional[float], last_changed_ts: Optional[float]) -> bool:
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

    def _convert_value_to_gauge_ratio(self, sensor_value: float, gauge_range: SensorGaugeRange) -> float:
        value_range = gauge_range.maximum_value - gauge_range.minimum_value
        if value_range == 0:
            return 0.0
        normalized_value = (sensor_value - gauge_range.minimum_value) / value_range
        return max(0.0, min(1.0, normalized_value))

    def _draw_gauge_bar_with_vertical_lines(
        self,
        drawing_context: ImageDraw.ImageDraw,
        start_x: int,
        start_y: int,
        bar_width: int,
        bar_height: int,
        fill_ratio: float,
    ):
        drawing_context.rectangle(
            [start_x, start_y, start_x + bar_width, start_y + bar_height],
            outline=0
        )
        filled_width = int(bar_width * fill_ratio)
        for line_x in range(start_x, start_x + filled_width, 2):
            drawing_context.line(
                [(line_x, start_y), (line_x, start_y + bar_height)],
                fill=0,
                width=1
            )

    def _fit_text(self, drawing_context: ImageDraw.ImageDraw, font: ImageFont.ImageFont, text: str, max_width: int) -> str:
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

    # -------------------------------------------------------------------------
    # Line builders
    # -------------------------------------------------------------------------

    def _build_temp_or_humidity_line(self, node: dict, prefix: str, field_name: str, unit: str) -> tuple[str, Optional[float], Optional[SensorGaugeRange], bool]:
        value = node[field_name]
        last_received_ts = node["last_received_timestamp"]
        last_changed_ts = node[f"{field_name}_last_changed_timestamp"]

        is_error = self._is_error(value, last_received_ts, last_changed_ts)

        if is_error:
            return f"{prefix}ERROR", None, None, True

        gauge_range = self.sensor_gauge_ranges[field_name]
        text = f"{prefix}{value:5.1f}{unit}"
        return text, value, gauge_range, False

    # def _build_pressure_line(self) -> str:
    #     with data_lock:
    #         env4_error = self._is_error(
    #             env4["pressure"],
    #             env4["last_received_timestamp"],
    #             env4["pressure_last_changed_timestamp"],
    #         )
    #         env3_error = self._is_error(
    #             env3["pressure"],
    #             env3["last_received_timestamp"],
    #             env3["pressure_last_changed_timestamp"],
    #         )
    #
    #         env4_text = "ERROR" if env4_error else f"{env4['pressure']:.1f}"
    #         env3_text = "ERROR" if env3_error else f"{env3['pressure']:.1f}"
    #
    #         return f"E4 P:{env4_text} / E3 P:{env3_text}hPa"
    
    def _build_pressure_line(self) -> str:
        env4_error = self._is_error(
            env4["pressure"],
            env4["last_received_timestamp"],
            env4["pressure_last_changed_timestamp"],
        )
        env3_error = self._is_error(
            env3["pressure"],
            env3["last_received_timestamp"],
            env3["pressure_last_changed_timestamp"],
        )

        env4_text = "ERROR" if env4_error else f"{env4['pressure']:.1f}"
        env3_text = "ERROR" if env3_error else f"{env3['pressure']:.1f}"

        return f"E4: {env4_text} / E3: {env3_text}"



    # -------------------------------------------------------------------------
    # Rendering
    # -------------------------------------------------------------------------

    def _create_display_image_for_epaper(self, epaper_device, display_font: ImageFont.ImageFont) -> Image.Image:
        image_size = (250, 122) if epaper_device is None else (epaper_device.height, epaper_device.width)

        display_image = Image.new("1", image_size, 255)
        drawing_context = ImageDraw.Draw(display_image)

        layout = DisplayLayoutManager(*image_size)
        max_text_width = image_size[0] - layout.text_area_start_x - 6

        with data_lock:
            line_specs = [
                self._build_temp_or_humidity_line(env4, "E4 T:", "temperature", "°C"),
                self._build_temp_or_humidity_line(env3, "E3 T:", "temperature", "°C"),
                self._build_temp_or_humidity_line(env4, "E4 H:", "humidity", "%"),
                self._build_temp_or_humidity_line(env3, "E3 H:", "humidity", "%"),
            ]
            pressure_line = self._build_pressure_line()

        for i, line_spec in enumerate(line_specs):
            y_pos = i * layout.single_section_height
            gauge_y = y_pos + (layout.single_section_height - layout.gauge_bar_height) // 2

            text, value, gauge_range, is_error = line_spec
            fitted_text = self._fit_text(drawing_context, display_font, text, max_text_width)
            drawing_context.text((layout.text_area_start_x, gauge_y), fitted_text, font=display_font, fill=0)

            if not is_error and value is not None and gauge_range is not None:
                self._draw_gauge_bar_with_vertical_lines(
                    drawing_context,
                    layout.gauge_bar_start_x,
                    gauge_y,
                    layout.gauge_bar_total_width,
                    layout.gauge_bar_height,
                    self._convert_value_to_gauge_ratio(value, gauge_range),
                )

            drawing_context.line(
                [(0, y_pos + layout.single_section_height), (image_size[0], y_pos + layout.single_section_height)],
                fill=0
            )

        # 5行目: pressure
        final_index = 4
        y_pos = final_index * layout.single_section_height
        gauge_y = y_pos + (layout.single_section_height - layout.gauge_bar_height) // 2
        fitted_pressure_text = self._fit_text(
            drawing_context,
            display_font,
            pressure_line,
            max_text_width,
        )
        drawing_context.text((layout.text_area_start_x, gauge_y), fitted_pressure_text, font=display_font, fill=0)

        return display_image.rotate(90, expand=True)

    # -------------------------------------------------------------------------
    # Update
    # -------------------------------------------------------------------------

    def update_display_with_current_data(self):
        try:
            try:
                font = ImageFont.truetype(
                    DISPLAY_FONT_FILE_PATH,
                    DISPLAY_FONT_SIZE_PIXELS
                )
            except OSError:
                logger.warning("Specified font not found. Using default[118;1:3u font.")
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
