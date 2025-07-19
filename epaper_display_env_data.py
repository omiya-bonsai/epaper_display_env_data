#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# =========================================================================
#
#                               スクリプトの概要
#
# =========================================================================
#
# このスクリプトは、複数のセンサーから受信した環境データを電子ペーパー(e-Paper)に
# 定期的に表示するためのシステムです。
# Raspberry Piなどの小型コンピュータ上で動作し、MQTTプロトコルを通じて
# リアルタイムにデータを受け取ります。
#
# 設定情報は`.env`ファイルから読み込まれるため、スクリプトを直接編集する
# ことなく、IPアドレスやファイルパスなどを安全かつ容易に変更できます。
#
# =========================================================================


# --- ライブラリのインポート ---
from dataclasses import dataclass
from typing import Dict, Tuple, Optional
import json
import time
import os
import sys
import logging
from PIL import Image, ImageDraw, ImageFont
import paho.mqtt.client as mqtt
import threading
import re
from dotenv import load_dotenv # <<< dotenvライブラリをインポート

# --- 設定の読み込み ---
# .envファイルから環境変数を読み込む
load_dotenv()

# --- ハードウェアの確認 ---
try:
    import epaper
    EPAPER_AVAILABLE = True
except ImportError:
    EPAPER_AVAILABLE = False
    print("WARNING: epaper module not found. Running in test mode.")

# --- ログ設定 ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# --- 定数（.envファイルから読み込む設定値）の定義 ---

# データの鮮度チェック用：この秒数以上更新がないデータは「古い」と判断する
DATA_STALENESS_THRESHOLD_SECONDS = int(os.getenv('DATA_STALENESS_THRESHOLD_SECONDS', 5400))
# ▼▼▼ 修正: 値が変化しない場合にエラーと判断するまでの秒数（60分） ▼▼▼
NO_CHANGE_ERROR_THRESHOLD_SECONDS = 3600

# MQTTブローカーの接続情報
MQTT_BROKER_IP_ADDRESS = os.getenv('MQTT_BROKER_IP_ADDRESS', "localhost")
MQTT_BROKER_PORT = int(os.getenv('MQTT_BROKER_PORT', 1883))
MQTT_KEEPALIVE = int(os.getenv('MQTT_KEEPALIVE', 60))
MQTT_CLIENT_ID = os.getenv('MQTT_CLIENT_ID', "epaper_display_subscriber")

# 受信するMQTTトピック
MQTT_TOPIC_QZSS_CPU_TEMP = os.getenv('MQTT_TOPIC_QZSS_CPU_TEMP')
MQTT_TOPIC_PI_CPU_TEMP = os.getenv('MQTT_TOPIC_PI_CPU_TEMP')
MQTT_TOPIC_ENV4 = os.getenv('MQTT_TOPIC_ENV4')
MQTT_TOPIC_CO2_DATA = os.getenv('MQTT_TOPIC_CO2_DATA')
MQTT_TOPIC_SENSOR_DATA = os.getenv('MQTT_TOPIC_SENSOR_DATA')

# データを保存するファイルのパス設定
BASE_DIRECTORY = os.getenv('BASE_DIRECTORY', '.') # .envで未指定ならカレントディレクトリ
QZSS_TEMPERATURE_FILE_PATH = os.path.join(BASE_DIRECTORY, 'qzss_temperature.json')
PI_TEMPERATURE_FILE_PATH = os.path.join(BASE_DIRECTORY, 'pi_temperature.json')
ENVIRONMENT_TEMPERATURE_FILE_PATH = os.path.join(BASE_DIRECTORY, 'env_temperature.json')
ENVIRONMENT_HUMIDITY_FILE_PATH = os.path.join(BASE_DIRECTORY, 'env_humidity.json')
CO2_DATA_FILE_PATH = os.path.join(BASE_DIRECTORY, 'co2_data.json')
THI_DATA_FILE_PATH = os.path.join(BASE_DIRECTORY, 'thi_data.json')

# --- グローバル変数（プログラムのどこからでもアクセスできる変数）の定義 ---
current_mqtt_qzss_cpu_temperature: Optional[float] = None
mqtt_qzss_cpu_last_received_timestamp: Optional[float] = None
# ▼▼▼ 修正: 値の最終変化時刻を記録する変数を追加 ▼▼▼
mqtt_qzss_cpu_last_changed_timestamp: Optional[float] = None

current_pi_cpu_temperature: Optional[float] = None
pi_cpu_last_received_timestamp: Optional[float] = None
# ▼▼▼ 修正: 値の最終変化時刻を記録する変数を追加 ▼▼▼
pi_cpu_last_changed_timestamp: Optional[float] = None

current_environment_temperature: Optional[float] = None
environment_temperature_last_received_timestamp: Optional[float] = None
# ▼▼▼ 修正: 値の最終変化時刻を記録する変数を追加 ▼▼▼
environment_temperature_last_changed_timestamp: Optional[float] = None

current_environment_humidity: Optional[float] = None
environment_humidity_last_received_timestamp: Optional[float] = None
# ▼▼▼ 修正: 値の最終変化時刻を記録する変数を追加 ▼▼▼
environment_humidity_last_changed_timestamp: Optional[float] = None

current_co2_concentration: Optional[float] = None
co2_data_last_received_timestamp: Optional[float] = None
co2_data_source_timestamp: Optional[float] = None
# ▼▼▼ 修正: 値の最終変化時刻を記録する変数を追加 ▼▼▼
co2_concentration_last_changed_timestamp: Optional[float] = None

current_thi_value: Optional[float] = None
thi_data_last_received_timestamp: Optional[float] = None
thi_data_source_timestamp: Optional[float] = None
# ▼▼▼ 修正: 値の最終変化時刻を記録する変数を追加 ▼▼▼
thi_value_last_changed_timestamp: Optional[float] = None

data_lock = threading.Lock()

# --- MQTT関連の関数 ---

def handle_mqtt_connection(client, userdata, flags, result_code):
    """MQTTブローカーに接続したときに自動的に呼び出される関数"""
    if result_code == 0:
        logger.info(f"MQTT connection successful: result code {result_code}")
        # .envでトピックが指定されている場合のみ購読する
        if MQTT_TOPIC_QZSS_CPU_TEMP: client.subscribe(MQTT_TOPIC_QZSS_CPU_TEMP)
        if MQTT_TOPIC_PI_CPU_TEMP: client.subscribe(MQTT_TOPIC_PI_CPU_TEMP)
        if MQTT_TOPIC_ENV4: client.subscribe(MQTT_TOPIC_ENV4)
        if MQTT_TOPIC_CO2_DATA: client.subscribe(MQTT_TOPIC_CO2_DATA)
        if MQTT_TOPIC_SENSOR_DATA: client.subscribe(MQTT_TOPIC_SENSOR_DATA)
        logger.info("Started subscribing to all specified topics")
    else:
        logger.error(f"MQTT connection failed, return code: {result_code}")

def handle_mqtt_message_received(client, userdata, message):
    """MQTTメッセージを受信したときに自動的に呼び出される関数"""
    global current_mqtt_qzss_cpu_temperature, mqtt_qzss_cpu_last_received_timestamp, mqtt_qzss_cpu_last_changed_timestamp
    global current_pi_cpu_temperature, pi_cpu_last_received_timestamp, pi_cpu_last_changed_timestamp
    global current_environment_temperature, environment_temperature_last_received_timestamp, environment_temperature_last_changed_timestamp
    global current_environment_humidity, environment_humidity_last_received_timestamp, environment_humidity_last_changed_timestamp
    global current_co2_concentration, co2_data_last_received_timestamp, co2_data_source_timestamp, co2_concentration_last_changed_timestamp
    global current_thi_value, thi_data_last_received_timestamp, thi_data_source_timestamp, thi_value_last_changed_timestamp

    received_timestamp = time.time()

    try:
        payload_str = message.payload.decode('utf-8', errors='ignore')

        with data_lock:
            # message.topicがNoneでないことを確認
            if not message.topic:
                return

            if message.topic == MQTT_TOPIC_QZSS_CPU_TEMP:
                payload_dict = json.loads(payload_str)
                new_temp = payload_dict.get("temperature")
                # ▼▼▼ 修正: 値が変化したら最終変化時刻を更新 ▼▼▼
                if new_temp is not None and new_temp != current_mqtt_qzss_cpu_temperature:
                    mqtt_qzss_cpu_last_changed_timestamp = received_timestamp
                current_mqtt_qzss_cpu_temperature = new_temp
                mqtt_qzss_cpu_last_received_timestamp = received_timestamp
                save_data_to_json_file(QZSS_TEMPERATURE_FILE_PATH, {"temperature": current_mqtt_qzss_cpu_temperature, "timestamp": received_timestamp, "last_changed_timestamp": mqtt_qzss_cpu_last_changed_timestamp})
                logger.info(f"MQTT QZSS CPU temperature received: {current_mqtt_qzss_cpu_temperature}°C")

            elif message.topic == MQTT_TOPIC_PI_CPU_TEMP:
                match = re.search(r"temp=(\d+\.?\d*)", payload_str)
                if match:
                    new_temp = float(match.group(1))
                    # ▼▼▼ 修正: 値が変化したら最終変化時刻を更新 ▼▼▼
                    if new_temp != current_pi_cpu_temperature:
                        pi_cpu_last_changed_timestamp = received_timestamp
                    current_pi_cpu_temperature = new_temp
                    pi_cpu_last_received_timestamp = received_timestamp
                    save_data_to_json_file(PI_TEMPERATURE_FILE_PATH, {"temperature": current_pi_cpu_temperature, "timestamp": received_timestamp, "last_changed_timestamp": pi_cpu_last_changed_timestamp})
                    logger.info(f"MQTT Pi CPU temperature received: {current_pi_cpu_temperature}°C")

            elif message.topic == MQTT_TOPIC_ENV4:
                payload_dict = json.loads(payload_str)
                
                new_temp = payload_dict.get("temperature")
                # ▼▼▼ 修正: 値が変化したら最終変化時刻を更新 ▼▼▼
                if new_temp is not None and new_temp != current_environment_temperature:
                    environment_temperature_last_changed_timestamp = received_timestamp
                current_environment_temperature = new_temp
                environment_temperature_last_received_timestamp = received_timestamp
                save_data_to_json_file(ENVIRONMENT_TEMPERATURE_FILE_PATH, {"temperature": current_environment_temperature, "timestamp": received_timestamp, "last_changed_timestamp": environment_temperature_last_changed_timestamp})

                new_humidity = payload_dict.get("humidity")
                # ▼▼▼ 修正: 値が変化したら最終変化時刻を更新 ▼▼▼
                if new_humidity is not None and new_humidity != current_environment_humidity:
                    environment_humidity_last_changed_timestamp = received_timestamp
                current_environment_humidity = new_humidity
                environment_humidity_last_received_timestamp = received_timestamp
                save_data_to_json_file(ENVIRONMENT_HUMIDITY_FILE_PATH, {"humidity": current_environment_humidity, "timestamp": received_timestamp, "last_changed_timestamp": environment_humidity_last_changed_timestamp})
                
                logger.info(f"MQTT environment data received - Temperature: {current_environment_temperature}°C, Humidity: {current_environment_humidity}%")

            elif message.topic == MQTT_TOPIC_CO2_DATA:
                payload_dict = json.loads(payload_str)
                if payload_dict.get("device_id") == "pico_w_production":
                    new_co2 = payload_dict.get("co2")
                    # ▼▼▼ 修正: 値が変化したら最終変化時刻を更新 ▼▼▼
                    if new_co2 is not None and new_co2 != current_co2_concentration:
                        co2_concentration_last_changed_timestamp = received_timestamp
                    current_co2_concentration = new_co2
                    co2_data_last_received_timestamp = received_timestamp
                    co2_data_source_timestamp = payload_dict.get("timestamp", received_timestamp)
                    save_data_to_json_file(CO2_DATA_FILE_PATH, {"co2": current_co2_concentration, "timestamp": co2_data_source_timestamp, "last_update": co2_data_last_received_timestamp, "last_changed_timestamp": co2_concentration_last_changed_timestamp})
                    logger.info(f"MQTT CO2 concentration received: {current_co2_concentration} ppm")

            elif message.topic == MQTT_TOPIC_SENSOR_DATA:
                payload_dict = json.loads(payload_str)
                if payload_dict.get("device_id") == "pico_w_production":
                    new_thi = payload_dict.get("thi")
                    # ▼▼▼ 修正: 値が変化したら最終変化時刻を更新 ▼▼▼
                    if new_thi is not None and new_thi != current_thi_value:
                        thi_value_last_changed_timestamp = received_times[118;1:3utamp
                    current_thi_value = new_thi
                    thi_data_last_received_timestamp = received_timestamp
                    thi_data_source_timestamp = payload_dict.get("timestamp", received_timestamp)
                    save_data_to_json_file(THI_DATA_FILE_PATH, {"thi": current_thi_value, "timestamp": thi_data_source_timestamp, "last_update": thi_data_last_received_timestamp, "last_changed_timestamp": thi_value_last_changed_timestamp})
                    logger.info(f"MQTT THI data received: {current_thi_value}")

    except Exception as e:
        logger.error(f"Error during MQTT message processing: {e}")

def on_disconnect(client, userdata, rc):
    """MQTTブローカーから切断されたときに呼び出される関数"""
    if rc != 0:
        logger.warning(f"Unexpectedly disconnected from MQTT broker. Return code: {rc}")
    else:
        logger.info("Normally disconnected from MQTT broker")

def initialize_mqtt_client_connection():
    """MQTTクライアントを初期化し、接続を開始する関数"""
    mqtt_client = mqtt.Client(client_id=MQTT_CLIENT_ID)
    mqtt_client.on_connect = handle_mqtt_connection
    mqtt_client.on_message = handle_mqtt_message_received
    mqtt_client.on_disconnect = on_disconnect

    try:
        mqtt_client.connect(MQTT_BROKER_IP_ADDRESS, MQTT_BROKER_PORT, MQTT_KEEPALIVE)
        mqtt_client.loop_start()
        logger.info("Started MQTT communication in background")
        return mqtt_client
    except Exception as e:
        logger.error(f"MQTT connection error: {e}")
        return None

def load_saved_all_mqtt_data():
    """
    保存されたデータを復元する。
    戻り値: bool - どのデータも復元できなかった場合にTrue（＝初期状態）を返す。
    """
    global current_mqtt_qzss_cpu_temperature, mqtt_qzss_cpu_last_received_timestamp, mqtt_qzss_cpu_last_changed_timestamp
    global current_pi_cpu_temperature, pi_cpu_last_received_timestamp, pi_cpu_last_changed_timestamp
    global current_environment_temperature, environment_temperature_last_received_timestamp, environment_temperature_last_changed_timestamp
    global current_environment_humidity, environment_humidity_last_received_timestamp, environment_humidity_last_changed_timestamp
    global current_co2_concentration, co2_data_last_received_timestamp, co2_data_source_timestamp, co2_concentration_last_changed_timestamp
    global current_thi_value, thi_data_last_received_timestamp, thi_data_source_timestamp, thi_value_last_changed_timestamp

    os.makedirs(BASE_DIRECTORY, exist_ok=True)
    data_was_loaded = False

    try:
        if os.path.exists(QZSS_TEMPERATURE_FILE_PATH):
            loaded_data = load_data_from_json_file(QZSS_TEMPERATURE_FILE_PATH)
            if loaded_data:
                current_mqtt_qzss_cpu_temperature = loaded_data.get("temperature")
                mqtt_qzss_cpu_last_received_timestamp = loaded_data.get("timestamp")
                # ▼▼▼ 修正: 最終変化時刻も復元 ▼▼▼
                mqtt_qzss_cpu_last_changed_timestamp = loaded_data.get("last_changed_timestamp", mqtt_qzss_cpu_last_received_timestamp)
                logger.info(f"QZSS CPU temperature restored: {current_mqtt_qzss_cpu_temperature}°C")
                data_was_loaded = True
    except Exception as e:
        logger.error(f"QZSS CPU temperature data restoration error: {e}")

    try:
        if os.path.exists(PI_TEMPERATURE_FILE_PATH):
            loaded_data = load_data_from_json_file(PI_TEMPERATURE_FILE_PATH)
            if loaded_data:
                current_pi_cpu_temperature = loaded_data.get("temperature")
                pi_cpu_last_received_timestamp = loaded_data.get("timestamp")
                # ▼▼▼ 修正: 最終変化時刻も復元 ▼▼▼
                pi_cpu_last_changed_timestamp = loaded_data.get("last_changed_timestamp", pi_cpu_last_received_timestamp)
                logger.info(f"Pi CPU temperature restored: {current_pi_cpu_temperature}°C")
                data_was_loaded = True
    except Exception as e:
        logger.error(f"Pi CPU temperature data restoration error: {e}")

    try:
        if os.path.exists(ENVIRONMENT_TEMPERATURE_FILE_PATH):
            loaded_data = load_data_from_json_file(ENVIRONMENT_TEMPERATURE_FILE_PATH)
            if loaded_data:
                current_environment_temperature = loaded_data.get("temperature")
                environment_temperature_last_received_timestamp = loaded_data.get("timestamp")
                # ▼▼▼ 修正: 最終変化時刻も復元 ▼▼▼
                environment_temperature_last_changed_timestamp = loaded_data.get("last_changed_timestamp", environment_temperature_last_received_timestamp)
                logger.info(f"Environment temperature restored: {current_environment_temperature}°C")
                data_was_loaded = True
    except Exception as e:
        logger.error(f"Environment temperature data restoration error: {e}")

    try:
        if os.path.exists(ENVIRONMENT_HUMIDITY_FILE_PATH):
            loaded_data = load_data_from_json_file(ENVIRONMENT_HUMIDITY_FILE_PATH)
            if loaded_data:
                current_environment_humidity = loaded_data.get("humidity")
                environment_humidity_last_received_timestamp = loaded_data.get("timestamp")
                # ▼▼▼ 修正: 最終変化時刻も復元 ▼▼▼
                environment_humidity_last_changed_timestamp = loaded_data.get("last_changed_timestamp", environment_humidity_last_received_timestamp)
                logger.info(f"Environment humidity restored: {current_environment_humidity}%")
                data_was_loaded = True
    except Exception as e:
        logger.error(f"Environment humidity data restoration error: {e}")

    try:
        if os.path.exists(CO2_DATA_FILE_PATH):
            loaded_data = load_data_from_json_file(CO2_DATA_FILE_PATH)
            if loaded_data:
                current_co2_concentration = loaded_data.get("co2")
                co2_data_source_timestamp = loaded_data.get("timestamp")
                co2_data_last_received_timestamp = loaded_data.get("last_update")
                # ▼▼▼ 修正: 最終変化時刻も復元 ▼▼▼
                co2_concentration_last_changed_timestamp = loaded_data.get("last_changed_timestamp", co2_data_last_received_timestamp)
                logger.info(f"CO2 concentration restored: {current_co2_concentration} ppm")
                data_was_loaded = True
    except Exception as e:
        logger.error(f"CO2 concentration data restoration error: {e}")

    try:
        if os.path.exists(THI_DATA_FILE_PATH):
            loaded_data = load_data_from_json_file(THI_DATA_FILE_PATH)
            if loaded_data:
                current_thi_value = loaded_data.get("thi")
                thi_data_source_timestamp = loaded_data.get("timestamp")
                thi_data_last_received_timestamp = loaded_data.get("last_update")
                # ▼▼▼ 修正: 最終変化時刻も復元 ▼▼▼
                thi_value_last_changed_timestamp = loaded_data.get("last_changed_timestamp", thi_data_last_received_timestamp)
                logger.info(f"THI restored: {current_thi_value}")
                data_was_loaded = True
    except Exception as e:
        logger.error(f"THI data restoration error: {e}")

    return not data_was_loaded

def save_data_to_json_file(file_path: str, data_dict: dict):
    """データをJSON形式でファイルに保存する関数"""
    try:
        with open(file_path, 'w', encoding='utf-8') as file:
            json.dump(data_dict, file, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"File save error {file_path}: {e}")

def load_data_from_json_file(file_path: str) -> dict:
    """JSONファイルを読み込んでデータを返す関数"""
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            return json.load(file)
    except (json.JSONDecodeError, FileNotFoundError) as e:
        logger.error(f"File load error {file_path}: {e}")
        return {}
    except Exception as e:
        logger.error(f"An unexpected error occurred while loading {file_path}: {e}")
        return {}


# --- 設定・レイアウト関連のクラス ---
@dataclass
class SystemConfiguration:
    """システム全体の設定をまとめて管理するクラス"""
    epaper_display_type: str = os.getenv('EPAPER_DISPLAY_TYPE', 'epd2in13_V4')
    display_font_file_path: str = os.getenv('DISPLAY_FONT_FILE_PATH', '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf')
    display_font_size_pixels: int = int(os.getenv('DISPLAY_FONT_SIZE_PIXELS', 16))
    display_update_interval_seconds: int = int(os.getenv('DISPLAY_UPDATE_INTERVAL_SECONDS', 300))

@dataclass
class SensorGaugeRange:
    """センサー値のゲージ表示の範囲を定義するクラス"""
    minimum_value: float
    maximum_value: float
    unit_symbol: str

class DisplayLayoutManager:
    """ディスプレイのレイアウト（どこに何を表示するか）を管理するクラス"""
    def __init__(self, display_height_pixels: int, display_width_pixels: int):
        self.text_area_start_x = 10
        self.label_area_width = 80
        self.gauge_bar_start_x = self.label_area_width + 70
        self.gauge_bar_total_width = display_height_pixels - self.gauge_bar_start_x - 10
        self.gauge_bar_height = 16
        self.single_section_height = display_width_pixels // 5

# --- メイン処理クラス ---

class EnvironmentalDataDisplaySystem:
    """このプログラムのすべての機能をまとめたメインクラス"""

    def __init__(self):
        """クラスが作成されたとき（プログラム起動時）に実行される初期化処理"""
        self.is_initial_startup = load_saved_all_mqtt_data()

        self.mqtt_communication_client = initialize_mqtt_client_connection()
        if self.mqtt_communication_client is None:
            logger.error("MQTT connection failed. Exiting program.")
            sys.exit(1)

        self.system_config = SystemConfiguration()

        self.epaper_device = None
        if EPAPER_AVAILABLE:
            try:
                self.epaper_device = epaper.epaper(self.system_config.epaper_display_type).EPD()
                self.epaper_device.init()
                logger.info("e-Paper display initialized")
            except Exception as e:
                logger.error(f"e-Paper display initialization failed: {e}")
                self.epaper_device = None
        else:
            logger.warning("e-Paper display not available (test mode)")

        self.sensor_gauge_ranges = {
            "Temperature": SensorGaugeRange(-10.0, 40.0, "°C"),
            "Humidity": SensorGaugeRange(0.0, 100.0, "%"),
            "QZSS_CPU": SensorGaugeRange(30.0, 60.0, "°C"),
            "Pi_CPU": SensorGaugeRange(30.0, 60.0, "°C")
        }

        self.display_item_definitions = [
            ("Temperature", "Temp:", "current_environment_temperature", "environment_temperature_last_changed_timestamp", "°C", "{:5.1f}"),
            ("Humidity", "Hum:", "current_environment_humidity", "environment_humidity_last_changed_timestamp", "%", "{:5.1f}"),
            ("QZSS_CPU", "QZSS:", "current_mqtt_qzss_cpu_temperature", "mqtt_qzss_cpu_last_changed_timestamp", "°C", "{:5.1f}"),
            ("Pi_CPU", "Pi5:", "current_pi_cpu_temperature", "pi_cpu_last_changed_timestamp", "°C", "{:5.1f}"),
            ("THI_CO2", "THI:", "combined_thi_co2", "", "", "")
        ]

    def _extract_sensor_value_from_data(self, data_path: str) -> Optional[float]:
        with data_lock:
            # globals() を使って動的にグローバル変数の値を取得
            return globals().get(data_path)

    def _get_combined_thi_and_co2_data(self, display_label: str) -> str:
        with data_lock:
            is_thi_data_error = False
            is_co2_data_error = False

            # ▼▼▼ 修正: エラー判定条件を追加 ▼▼▼
            # 1. データ自体がない (None)
            # 2. 最終受信から一定時間経過 (DATA_STALENESS_THRESHOLD_SECONDS)
            # 3. 値が一定時間変化していない (NO_CHANGE_ERROR_THRESHOLD_SECONDS)
            
            # THIのエラーチェック
            thi_stale_by_no_receive = thi_data_last_received_timestamp is None or time.time() - thi_data_last_received_timestamp >= DATA_STALENESS_THRESHOLD_SECONDS
            thi_stale_by_no_change = thi_value_last_changed_timestamp is None or time.time() - thi_value_last_changed_timestamp > NO_CHANGE_ERROR_THRESHOLD_SECONDS
            if current_thi_value is None or thi_stale_by_no_receive or thi_stale_by_no_change:
                is_thi_data_error = True

            # CO2のエラーチェック
            co2_stale_by_no_receive = co2_data_last_received_timestamp is None or time.time() - co2_data_last_received_timestamp >= DATA_STALENESS_THRESHOLD_SECONDS
            co2_stale_by_no_change = co2_concentration_last_changed_timestamp is None or time.time() - co2_concentration_last_changed_timestamp > NO_CHANGE_ERROR_THRESHOLD_SECONDS
            if current_co2_concentration is None or co2_stale_by_no_receive or co2_stale_by_no_change:
                is_co2_data_error = True

            # 表示文字列の生成
            if is_thi_data_error and is_co2_data_error:
                return f"{display_label}ERROR / CO2:ERROR"
            elif is_thi_data_error:
                return f"{display_label}ERROR / CO2:{current_co2_concentration:.0f}ppm"
            elif is_co2_data_error:
                return f"{display_label}{current_thi_value:.1f} / CO2:ERROR"
            else:
                return f"{display_label}{current_thi_value:.1f} / CO2:{current_co2_concentration:.0f}ppm"

    def _convert_value_to_gauge_ratio(self, sensor_value: float, gauge_range: SensorGaugeRange) -> float:
        value_range = gauge_range.maximum_value - gauge_range.minimum_value
        if value_range == 0: return 0.0
        normalized_value = (sensor_value - gauge_range.minimum_value) / value_range
        return max(0.0, min(1.0, normalized_value))

    def _draw_gauge_bar_with_vertical_lines(self, drawing_context: ImageDraw, start_x: int, start_y: int, bar_width: int, bar_height: int, fill_ratio: float):
        drawing_context.rectangle([start_x, start_y, start_x + bar_width, start_y + bar_height], outline=0)
        filled_width = int(bar_width * fill_ratio)
        for line_x in range(start_x, start_x + filled_width, 2):
            drawing_context.line([(line_x, start_y), (line_x, start_y + bar_height)], fill=0, width=1)

    def _create_display_image_for_epaper(self, epaper_device, display_font: ImageFont) -> Image:
        """電子ペーパーに表示するための画像を生成する中心的な関数"""
        image_size = (250, 122) if epaper_device is None else (epaper_device.height, epaper_device.width)
        display_image = Image.new('1', image_size, 255)
        drawing_context = ImageDraw.Draw(display_image)

        if self.is_initial_startup:
            # --- 初期起動時のメッセージ表示 ---
            next_update_timestamp = time.time() + self.system_config.display_update_interval_seconds
            next_update_time_str = time.strftime('%H:%M', time.localtime(next_update_timestamp))
            message = f"Please wait until {next_update_time_str}"

            try:
                bbox = drawing_context.textbbox((0, 0), message, font=display_font)
                text_pos = ((image_size[0] - (bbox[2] - bbox[0])) / 2, (image_size[1] - (bbox[3] - bbox[1])) / 2)
            except AttributeError:
                text_w, text_h = drawing_context.textsize(message, font=display_font)
                text_pos = ((image_size[0] - text_w) / 2, (image_size[1] - text_h) / 2)

            drawing_context.text(text_pos, message, font=display_font, fill=0)
            self.is_initial_startup = False

        else:
            # --- 通常時のセンサーデータ表示 ---
            layout = DisplayLayoutManager(*image_size)
            # ▼▼▼ 修正: display_item_definitions のアンパックを変更 ▼▼▼
            for i, (key, label, path, last_changed_ts_path, unit, fmt) in enumerate(self.display_item_definitions):
                y_pos = i * layout.single_section_height
                gauge_y = y_pos + (layout.single_section_height - layout.gauge_bar_height) // 2

                if key == "THI_CO2":
                    text = self._get_combined_thi_and_co2_data(label)
                else:
                    value = self._extract_sensor_value_from_data(path)
                    last_changed_ts = self._extract_sensor_value_from_data(last_changed_ts_path)

                    # ▼▼▼ 修正: 値が変化しない場合のエラー判定を追加 ▼▼▼
                    is_stale_by_no_change = (last_changed_ts is not None and time.time() - last_changed_ts > NO_CHANGE_ERROR_THRESHOLD_SECONDS)
                    
                    if value is None or is_stale_by_no_change:
                        text = f"{label}ERROR"
                    else:
                        text = f"{label}{fmt.format(value)}{unit}"
                        self._draw_gauge_bar_with_vertical_lines(drawing_context, layout.gauge_bar_start_x, gauge_y, layout.gauge_bar_total_width, layout.gauge_bar_height, self._convert_value_to_gauge_ratio(value, self.sensor_gauge_ranges[key]))

                drawing_context.text((layout.text_area_start_x, gauge_y), text, font=display_font, fill=0)

                if i < len(self.display_item_definitions) - 1:
                    drawing_context.line([(0, y_pos + layout.single_section_height), (image_size[0], y_pos + layout.single_section_height)], fill=0)

        return display_image.rotate(90, expand=True)

    def update_display_with_current_data(self):
        """現在のデータでディスプレイを1回更新する関数"""
        try:
            try:
                font = ImageFont.truetype(self.system_config.display_font_file_path, self.system_config.display_font_size_pixels)
            except OSError:
                logger.warning("Specified font not found. Using default font.")
                font = ImageFont.load_default()

            display_image = self._create_display_image_for_epaper(self.epaper_device, font)

            if self.epaper_device is not None:
                self.epaper_device.init()
                self.epaper_device.display(self.epaper_device.getbuffer(display_image))
                self.epaper_device.sleep()
                logger.info("Display update completed")
            else:
                logger.info("Test mode: Display update simulated")
                # テスト用に画像を保存する場合
                # display_image.save("test_output.png")

        except Exception as e:
            logger.error(f"Display update error: {e}", exc_info=True)

    def start_continuous_display_updates(self):
        """ディスプレイの定周期更新を開始するメインループ関数"""
        logger.info(f"Starting continuous display updates (update interval: {self.system_config.display_update_interval_seconds} seconds)")
        while True:
            try:
                self.update_display_with_current_data()
                time.sleep(self.system_config.display_update_interval_seconds)
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

# --- プログラムのエントリーポイント（ここから実行が始まる） ---

def main():
    """メイン関数"""
    try:
        logger.info("Starting environmental sensor data display system...")
        display_system = EnvironmentalDataDisplaySystem()
        logger.info("System initialization completed")
        display_system.start_continuous_display_updates()
    except Exception as e:
        logger.error(f"System startup error: {e}", exc_info=True)
    finally:
        logger.info("Environmental sensor data display system terminated")

if __name__ == '__main__':
    main()
