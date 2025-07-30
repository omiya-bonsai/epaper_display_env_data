# e-Paper 環境・システム監視ディスプレイ 🛰️

このプロジェクトは、Raspberry Piに接続されたe-Paper（電子ペーパー）ディスプレイに、MQTT経由で受信した各種センサーデータと、指定したシステムサービスの状態を定期的に表示するアプリケーションです。

ヘッドレスで運用しているサーバーの状態を、低消費電力なディスプレイで視覚的に一目で把握することを目的としています。

![IMG_7547](https://github.com/user-attachments/assets/b0db008a-307a-4fb2-8fb7-a8c1216abc48)

---

## ✨ 主な機能

* **環境データの可視化**: MQTTで受信した温度、湿度、CPU温度、CO2濃度、不快指数(THI)などのデータを表示します。
* **システム監視**: `.env`ファイルで指定した`systemd`サービス（例: `dump1090-fa.service`）の稼働状況を監視します。
* **異常検知アラート**: 監視対象のサービスが停止した場合、通常の表示を中断し、画面全体で警告メッセージを表示します。
* **データ永続化**: 受信した最新データをJSONファイルに保存し、スクリプト再起動時に状態を復元します。
* **柔軟な設定**: 接続先や監視対象、表示間隔などを`.env`ファイルで簡単に変更できます。

---

## 🛠️ セットアップ

### 1. 必要条件

* **ハードウェア**:
    * Raspberry Pi （または同様のLinux環境）
    * e-Paper ディスプレイ（[Waveshare](https://www.waveshare.com/product/displays/e-paper.htm)製など）
* **ソフトウェア**:
    * Python 3
    * Git

### 2. インストール手順

1.  **リポジトリをクローンします。**
    ```bash
    git clone [https://github.com/omiya-bonsai/epaper_display_env_data.git](https://github.com/omiya-bonsai/epaper_display_env_data.git)
    cd epaper_display_env_data
    ```

2.  **Python仮想環境を作成し、有効化します。**
    ```bash
    python3 -m venv eink
    source eink/bin/activate
    ```

3.  **必要なライブラリをインストールします。**
    ```bash
    pip install -r requirements.txt
    ```

### 3. `requirements.txt` の内容

このプロジェクトで使われる主なライブラリです。`requirements.txt`という名前で保存してください。

```txt
paho-mqtt
pillow
python-dotenv
# e-Paperのモデルに応じたドライバライブラリ
# 例: waveshare-epd
````

### 4\. 設定ファイルの作成

`.env.example`を参考に、`.env`ファイルを作成します。

1.  設定ファイルを作成します。

    ```bash
    cp .env.example .env
    ```

2.  `vim`エディタで`.env`ファイルを開き、ご自身の環境に合わせて値を編集します。

    ```bash
    vim .env
    ```

#### `.env.example` （設定例）

```dotenv
# --- MQTT Broker Settings ---
MQTT_BROKER_IP_ADDRESS="192.168.1.10"
MQTT_BROKER_PORT=1883

# --- MQTT Topics ---
MQTT_TOPIC_QZSS_CPU_TEMP="sensors/qzss/cpu_temp"
MQTT_TOPIC_PI_CPU_TEMP="sensors/pi/cpu_temp"
MQTT_TOPIC_ENV4="sensors/environment/bme280"
MQTT_TOPIC_CO2_DATA="sensors/environment/co2"
MQTT_TOPIC_SENSOR_DATA="sensors/environment/thi"

# --- System Service Monitoring ---
# 監視したいsystemdサービスの名前
DUMP1090_SERVICE_NAME="dump1090-fa.service"

# --- Display Settings ---
# e-Paperのモデル名（例: epd2in13_V4）
EPAPER_DISPLAY_TYPE="epd2in13_V4"
# 表示更新の間隔（秒）
DISPLAY_UPDATE_INTERVAL_SECONDS=300
# 使用するフォントのパス
DISPLAY_FONT_FILE_PATH="/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
DISPLAY_FONT_SIZE_PIXELS=16

# --- Data Persistence ---
# データ保存先のベースディレクトリ
BASE_DIRECTORY="/home/bonsai/python3/e-ink/data"
```

-----

## 🚀 使い方

このスクリプトは、`systemd`を使ってバックグラウンドで常時実行させることを想定しています。

### サービスとして登録

1.  `systemd`のサービスファイルを作成します。

    ```bash
    sudo vim /etc/systemd/system/epaper_disp.service
    ```

2.  以下の内容を貼り付け、`User`と`WorkingDirectory`/`ExecStart`のパスを環境に合わせて修正します。

    ```ini
    [Unit]
    Description=E-Paper Display Environment Data Service
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

    *注意: `ExecStart`には仮想環境内のPythonを指定するのが確実です。*

### サービスの操作

  * **サービスの有効化と初回起動:**
    ```bash
    sudo systemctl enable --now epaper_disp.service
    ```
  * **サービスの停止:**
    ```bash
    sudo systemctl stop epaper_disp.service
    ```
  * **サービスの再起動:**
    ```bash
    sudo systemctl restart epaper_disp.service
    ```
  * **サービスの稼働状況確認:**
    ```bash
    systemctl status epaper_disp.service
    ```
  * **ログのリアルタイム確認:**
    ```bash
    journalctl -f -u epaper_disp.service
    ```

-----

## 📄 ライセンス

このプロジェクトは LICENSE ファイルの下で公開されています。

```
```
