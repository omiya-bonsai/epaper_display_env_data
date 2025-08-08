# e-Paper 環境・システム・気象監視ディスプレイ 🌦️🛰️

このプロジェクトは、Raspberry Pi に接続した e-Paper（電子ペーパー）に、MQTT 経由で受信した**環境データ**・**システム状態**・**レインセンサー情報**を定期的に表示するアプリケーションです。  
低消費電力・常時視認・再起動復元に対応し、ヘッドレス運用のサーバーや屋外観測に最適です。

本プロジェクトでは以下のハードウェアを使用しています：

- **レインセンサー**：[雨量センサモジュール（スイッチサイエンス販売品）](https://www.switch-science.com/products/8202)  
- **e-Paper ディスプレイ**：[Waveshare製 2.13inch e-Paper HAT (V4)（スイッチサイエンス販売品）](https://www.switch-science.com/products/9848)

---

## ✨ 主な機能

- **環境データの可視化**  
  温度・湿度・CO₂濃度・不快指数（THI）を見やすく表示します（CO₂は THI と同じ行で併記）。
- **気象監視（レインセンサー統合）**  
  雨/降り出し予兆/ケーブル異常/オフライン/エラー/再起動などを1行で簡潔に表示します。
- **システム監視**  
  Pi5 と ADS 側の **CPU温度のみ** を表示します（使用率などは表示しません）。
- **異常時アラート**  
  指定した systemd サービスが停止すると、通常表示を中断し全画面の警告表示に切り替えます。
- **データ永続化**  
  最新値を JSON に保存し、再起動後も直前の状態を即座に復元します。
- **柔軟な設定**  
  `.env` で MQTT 接続先・トピック・表示間隔・フォントなどを変更できます。

---

## 🛠️ セットアップ

### 必要条件

- **ハードウェア**
  - Raspberry Pi（Zero 2 W〜5 推奨）
  - e-Paper ディスプレイ（例: Waveshare 2.13inch）
  - （任意）レインセンサー
- **ソフトウェア**
  - Python 3
  - Git

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

> 下記の変数名は **現在のスクリプト実装** に合わせています。

```dotenv
# --- MQTT Broker ---
MQTT_BROKER_IP_ADDRESS="192.168.x.x"
MQTT_BROKER_PORT=1883
MQTT_KEEPALIVE=60
MQTT_CLIENT_ID="epaper_display_subscriber"

# --- MQTT Topics ---
# ※ コード上では「ADS 側 CPU 温度」の環境変数名は互換のため QZSS としています
MQTT_TOPIC_QZSS_CPU_TEMP="sensors/ads/cpu_temp"  # ADS 側 CPU 温度
MQTT_TOPIC_PI_CPU_TEMP="sensors/pi/cpu_temp"     # Pi5 CPU 温度（vcgencmd 出力を想定）
MQTT_TOPIC_ENV4="sensors/environment/bme280"     # 温度・湿度
MQTT_TOPIC_CO2_DATA="sensors/environment/co2"    # CO2（pico_w_production のみ処理）
MQTT_TOPIC_SENSOR_DATA="sensors/environment/thi" # THI（pico_w_production のみ処理）
MQTT_TOPIC_RAIN="home/weather/rain_sensor"       # レインセンサー

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

本ディスプレイは **5 行** 構成です。CPU は **温度のみ** を表示します。

|  行 | 表示内容                                    | 備考                                               |
| -: | --------------------------------------- | ------------------------------------------------ |
|  1 | **Temp:** `xx.x°C`                      | 温度。ゲージ表示あり                                       |
|  2 | **Hum:** `yy.y%`                        | 湿度。ゲージ表示あり                                       |
|  3 | **Pi5:** `aa.a℃` **/** **ADS:** `bb.b℃` | Pi5/ADS の CPU温度のみ。スラッシュ区切り                       |
|  4 | **RAIN 行**                              | 雨/予兆/ケーブル異常/オフライン/エラー/再起動等を1行に集約                 |
|  5 | **THI:** `t.t` **/** **CO2:** `ccccppm` | どちらか欠損時は `ERROR` 併記（例: `THI:ERROR / CO2:800ppm`） |

---

## 🌧️ RAIN 行のステータス一覧（例）

| 表記例            | 意味                         |
| -------------- | -------------------------- |
| `RAIN`         | 雨を検知中（変化率に応じて `H/M/L` を付与） |
| `RAIN→`        | 降り出し予兆                     |
| `OFFLINE MISS` | 一定秒数データ受信なし                |
| `CAB`          | ケーブル接続異常                   |
| `ERR`          | エラーカウンタが正の値                |
| `RST`          | デバイス再起動検知                  |
| `Δ:x.x%`       | baseline 比の変化率（余裕があれば表示）   |
| `ALL CLEAR`    | 問題なし                       |

---

## 🙏 謝辞

このプロジェクトは、OpenAI の ChatGPT（GPT-5）との対話を通じて設計・改良が行われました。
特に以下の点での貢献に感謝します。

* レインセンサー監視ロジックの設計と統合
* RAIN 行の英語表記ルールと表示優先度の整理
* Pi5/ADS の CPU温度表示に特化した改善
* e-Paper の文字数制限を踏まえた自動トリミング機能
* README.md の構成整理と最新仕様への更新
