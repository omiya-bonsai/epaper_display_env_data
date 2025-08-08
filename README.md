# e-Paper 環境・システム・気象監視ディスプレイ 🌦️🛰️

このプロジェクトは、Raspberry Pi に接続した e-Paper（電子ペーパー）に、MQTT 経由で受信した **環境データ**・**システム状態**・**レインセンサー情報** を定期的に表示するアプリケーションです。  
低消費電力・常時視認・再起動復元に対応し、ヘッドレス運用のサーバーや屋外観測に最適です。

![IMG_7574](https://github.com/user-attachments/assets/8ee56f4c-62db-4ffe-b9f1-f1b768ee10b5)

---

## 📦 使用ハードウェア

- **レインセンサー**：[雨量センサモジュール（スイッチサイエンス販売品）](https://www.switch-science.com/products/8202)  
- **e-Paper ディスプレイ**：[Waveshare製 2.13inch e-Paper HAT (V4)（スイッチサイエンス販売品）](https://www.switch-science.com/products/9848)

---

## ✨ 主な機能

- **環境データの可視化**  
  温度・湿度・CO₂濃度・不快指数（THI）を見やすく表示（CO₂は THI と同じ行に併記）
- **気象監視（レインセンサー統合）**  
  雨/降り出し予兆/ケーブル異常/オフライン/エラー/再起動などを 1 行で簡潔に表示
- **システム監視**  
  Pi5 と ADS 側の **CPU温度のみ** を表示（使用率等は表示しない）
- **異常時アラート**  
  指定した systemd サービス停止時、全画面の警告表示に切り替え
- **データ永続化**  
  最新値を JSON に保存し、再起動後も直前の状態を復元
- **柔軟な設定**  
  `.env` で MQTT 接続先・トピック・表示間隔・フォントを変更可能

---

## 🛠️ セットアップ

### 必要条件

**ハードウェア**
- Raspberry Pi（Zero 2 W〜5 推奨）
- e-Paper ディスプレイ（例: Waveshare 2.13inch）
- （任意）レインセンサー

**ソフトウェア**
- Python 3
- Git

---

### インストール

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
# e-Paper のモデルに応じたドライバ（例: waveshare-epd）
```

---

## `.env` 設定例

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

## 🚀 実行方法（systemd サービス化）

サービスファイル例：

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

起動と自動起動設定：

```bash
sudo systemctl enable --now epaper_disp.service
```

運用時の便利コマンド：

```bash
systemctl status epaper_disp.service
journalctl -f -u epaper_disp.service
sudo systemctl restart epaper_disp.service
```

---

## 📡 表示仕様（5 行構成・CPUは温度のみ）

|  行 | 表示内容                                    | 備考                                           |
| -: | --------------------------------------- | -------------------------------------------- |
|  1 | **Temp:** `xx.x°C`                      | 気温（ゲージ表示あり）                                  |
|  2 | **Hum:** `yy.y%`                        | 湿度（ゲージ表示あり）                                  |
|  3 | **Pi5:** `aa.a℃` **/** **ADS:** `bb.b℃` | CPU温度のみ（スラッシュ区切り）                            |
|  4 | **RAIN 行**                              | 雨/予兆/異常/オフライン/エラー/再起動など集約                    |
|  5 | **THI:** `t.t` **/** **CO2:** `ccccppm` | 欠損時は `ERROR` 併記（例: `THI:ERROR / CO2:800ppm`） |

---

## 🌧️ RAIN 行ステータス例

| 表記例            | 意味                 |
| -------------- | ------------------ |
| `RAIN`         | 雨を検知（H/M/L付与の場合あり） |
| `RAIN→`        | 降り出し予兆             |
| `OFFLINE MISS` | データ受信なし            |
| `CAB`          | ケーブル異常             |
| `ERR`          | エラー発生              |
| `RST`          | 再起動検知              |
| `Δ:x.x%`       | 変化率（表示余裕時）         |
| `ALL CLEAR`    | 問題なし               |

---

## 🙏 謝辞

本プロジェクトは ChatGPT（GPT-5）との対話を通じて以下の改善を実現しました。

* レインセンサー監視ロジック統合
* RAIN 行の表記ルール整備
* Pi5/ADS CPU温度表示機能の特化
* e-Paper 表示文字数の最適化
* README.md の整理と最新仕様反映
