# e-Paper 環境・システム・気象監視ディスプレイ 🌦️🛰️

このプロジェクトは、Raspberry Piに接続されたe-Paper（電子ペーパー）ディスプレイに、MQTT経由で受信した各種センサーデータやシステム状態、そしてレインセンサーによる雨検知情報を定期的に表示するアプリケーションです。

低消費電力な電子ペーパーを活用し、ヘッドレス運用中のサーバーや環境・気象状態を一目で把握できます。

---

## ✨ 主な機能

* **環境データの可視化**  
  MQTTで受信した温度、湿度、CO2濃度、不快指数(THI)、CPU温度などを表示します。
* **気象監視（レインセンサー統合）**  
  降雨検知、結露検知、ノイズ異常、ケーブル接続異常、オフラインなどの状態を1行で表示します。  
  状態が正常なら「OK」表記、降雨中は「RAIN」、その他異常は簡潔なアラート表記に切り替わります。
* **システム監視**  
  `.env`で指定した`systemd`サービス（例: ADS-Bデコーダー）やPi5のCPU/MEM使用率などを監視します。
* **異常検知アラート**  
  監視対象サービスが停止すると、通常の情報表示を中断し全画面警告を表示します。
* **データ永続化**  
  最新データをJSONファイルに保存し、スクリプト再起動時に状態を復元します。
* **柔軟な設定**  
  接続先や表示内容、更新間隔などを`.env`で簡単に変更できます。

---

## 🛠️ セットアップ

### 必要条件

* **ハードウェア**
  * Raspberry Pi（Zero 2 W〜5推奨）
  * e-Paperディスプレイ（例: Waveshare 2.13inch）
  * （オプション）雨量・結露センサー
* **ソフトウェア**
  * Python 3
  * Git

### インストール手順

```bash
git clone https://github.com/omiya-bonsai/epaper_display_env_data.git
cd epaper_display_env_data
python3 -m venv eink
source eink/bin/activate
pip install -r requirements.txt
````

---

## `requirements.txt` の例

```txt
paho-mqtt
pillow
python-dotenv
# e-Paperのモデルに応じたドライバライブラリ
# 例: waveshare-epd
```

---

## `.env` 設定例

```dotenv
# --- MQTT Broker ---
MQTT_BROKER_IP_ADDRESS="192.168.x.x"
MQTT_BROKER_PORT=1883

# --- MQTT Topics ---
MQTT_TOPIC_ADS_CPU_TEMP="sensors/ads/cpu_temp"
MQTT_TOPIC_PI_CPU_TEMP="sensors/pi/cpu_temp"
MQTT_TOPIC_ENV4="sensors/environment/bme280"
MQTT_TOPIC_CO2_DATA="sensors/environment/co2"
MQTT_TOPIC_SENSOR_DATA="sensors/environment/thi"
MQTT_TOPIC_RAIN_SENSOR="home/weather/rain_sensor"

# --- System Service ---
DUMP1090_SERVICE_NAME="dump1090-fa.service"

# --- Display ---
EPAPER_DISPLAY_TYPE="epd2in13_V4"
DISPLAY_UPDATE_INTERVAL_SECONDS=300
DISPLAY_FONT_FILE_PATH="/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
DISPLAY_FONT_SIZE_PIXELS=16

# --- Data Storage ---
BASE_DIRECTORY="/home/bonsai/python3/e-ink/data"
```

---

## 🚀 実行方法

サービス登録例：

```bash
sudo vim /etc/systemd/system/epaper_disp.service
```

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

サービス起動：

```bash
sudo systemctl enable --now epaper_disp.service
```

---

## 📡 表示仕様

| 行 | 表示内容                             |
| - | -------------------------------- |
| 1 | 温度 / 湿度                          |
| 2 | CO2濃度                            |
| 3 | ADS CPU温度 / サービス稼働状況             |
| 4 | Pi5 CPU温度 / 使用率（"/"区切り）          |
| 5 | RAINステータス（雨・結露・ノイズ・ケーブル異常・オフライン） |
| 6 | THI（不快指数）                        |

---

## 🌧️ RAIN行のステータス一覧

レインセンサーは以下の状態を1行で表示します。

| 表記例            | 意味                   |
| -------------- | -------------------- |
| `RAIN`         | 雨を検知中                |
| `DEW`          | 結露を検知                |
| `NOISE`        | ノイズ多発（測定値が不安定）       |
| `CABLE MISS`   | ケーブル接続異常             |
| `OFFLINE MISS` | デバイスからのデータが途絶（オフライン） |
| `OK`           | すべて正常                |
| `INIT...`      | データ未取得だが更新間隔内（初期化中）  |

※ 異常は複合表示される場合があります（例: `RAIN / NOISE`）

---

## 💡 運用ヒント

* 湿度（Hum）はすでに上段行に表示されるため、RAIN行では重複表示しません。
* ディスプレイの文字数制限に合わせて全行はみ出さないよう調整されています。
* Pi5行は`/`で各値を区切るため、THI行と視覚的に揃います。

---

## 🙏 謝辞

このプロジェクトは、OpenAIのChatGPT（GPT-5）との対話を通じて設計・改良が行われました。
特に以下の点での貢献に感謝します。

* レインセンサー（雨・結露・ノイズ・ケーブル異常・オフライン）監視機能の設計と統合
* RAIN行の表示ロジック、異常時の簡潔な英語表記ルールの提案
* Pi5行の`/`区切り表記化による視認性向上
* e-Paperの文字数制限内での表示最適化
* README.md の構成整理と最新仕様への更新

---

## 📄 ライセンス

このプロジェクトは LICENSE ファイルの下で公開されています。
