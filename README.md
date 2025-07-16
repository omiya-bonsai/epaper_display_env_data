# 環境データe-Paper表示システム

このプロジェクトは、MQTT経由で受信した各種センサーの環境データを、Raspberry Piに接続されたe-Paper（電子ペーパー）ディスプレイに表示するためのPythonスクリプトです。

## 概要

複数のセンサー（温度、湿度、CO2、CPU温度など）からMQTTブローカーに送信されたデータをリアルタイムで購読し、整形してe-Paperディスプレイに表示します。設定情報は `.env` ファイルで管理するため、スクリプトを編集することなく安全に設定を変更できます。

## 主な機能 ✨

  - **MQTTデータ受信**: 複数のMQTTトピックを購読し、リアルタイムにデータを更新。
  - **データ永続化**: 受信した最新データをJSONファイルに保存し、再起動後も前回の値を表示。
  - **視覚的な表示**: 各センサー値をテキストとゲージバーで分かりやすく可視化。
  - **堅牢な設計**: データが古い場合や取得失敗時には「ERROR」と表示し、動作を継続。
  - **柔軟な設定**: IPアドレスやトピック名などを `.env` ファイルで外部管理。

-----

## 動作要件 🛠️

### ハードウェア

  - Raspberry Pi (Zero 2 W, 5 など)
  - e-Paper ディスプレイ (例: Waveshare 2.13inch e-Paper V4)
  - 各種センサー (BME688, SCD4x など) と、それらのデータをMQTTで送信する仕組み

### ソフトウェア

  - Python 3
  - 必要なPythonライブラリ (`requirements.txt`を参照)

-----

## セットアップ手順 🚀

1.  **リポジトリのクローン**

    ```zsh
    git clone https://your-repository-url/e-ink-display.git
    cd e-ink-display
    ```

2.  **Python仮想環境の作成と有効化** (推奨)

    ```zsh
    python3 -m venv eink
    source eink/bin/activate
    ```

3.  **必要なライブラリのインストール**
    `requirements.txt` を使って一括でインストールします。

    ```zsh
    pip install -r requirements.txt
    ```

    *e-Paperのライブラリは、お使いのモデルのメーカーの指示に従って別途インストールが必要な場合があります。*

4.  **設定ファイルの準備**
    サンプルをコピーして `.env` ファイルを作成します。

    ```zsh
    cp .env.sample .env
    ```

5.  **設定ファイルの編集**
    `vim` などのエディタで `.env` ファイルを開き、ご自身の環境に合わせてMQTTブローカーのIPアドレスや各種設定値を修正します。

    ```zsh
    vim .env
    ```

6.  **データ保存ディレクトリの作成**
    `.env` で指定した `BASE_DIRECTORY` を作成します。

    ```zsh
    mkdir -p data
    ```

-----

## 設定 (`.env` ファイル)

`.env` ファイルで以下の項目を設定します。

| 変数名                              | 説明                                            | 例                               |
| ----------------------------------- | ----------------------------------------------- | -------------------------------- |
| `MQTT_BROKER_IP_ADDRESS`            | MQTTブローカーのIPアドレス                      | `192.168.3.82`                   |
| `MQTT_BROKER_PORT`                  | MQTTブローカーのポート番号                      | `1883`                           |
| `MQTT_CLIENT_ID`                    | このスクリプトのMQTTクライアントID              | `epaper_display_client_01`       |
| `MQTT_TOPIC_QZSS_CPU_TEMP`          | QZSS受信機CPU温度のトピック                     | `raspberry/qzss/temperature`     |
| `MQTT_TOPIC_PI_CPU_TEMP`            | Pi本体CPU温度のトピック                         | `raspberry/temperature`          |
| `MQTT_TOPIC_ENV4`                   | BME688等の環境センサートピック                  | `env4`                           |
| `MQTT_TOPIC_CO2_DATA`               | CO2センサートピック                             | `co2_data`                       |
| `MQTT_TOPIC_SENSOR_DATA`            | THI等の計算値センサートピック                   | `sensor_data`                    |
| `BASE_DIRECTORY`                    | データ保存用ディレクトリのパス                  | `./data`                         |
| `DISPLAY_FONT_FILE_PATH`            | 表示に使うフォントのパス                        | `/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf` |
| `EPAPER_DISPLAY_TYPE`               | e-Paperのモデル名                               | `epd2in13_V4`                    |
| `DISPLAY_UPDATE_INTERVAL_SECONDS`   | 画面の更新間隔（秒）                            | `300`                            |
| `DATA_STALENESS_THRESHOLD_SECONDS`  | データが古いと判断する閾値（秒）                | `5400`                           |

-----

## 使い方 ▶️

以下のコマンドでスクリプトを実行します。

```zsh
python3 epaper_display_env_data.py
```

Ctrl+C で安全に終了できます。

バックグラウンドで常時実行させたい場合は、`systemd` や `supervisor` を使ってサービスとして登録することをお勧めします。

-----

## プロジェクト構成

```
.
├── .env                  # (作成する) 環境設定ファイル
├── .env.sample           # .env のテンプレート
├── .gitignore            # Gitの無視リスト
├── data/                 # (作成される) センサーデータ保存用ディレクトリ
│   ├── co2_data.json
│   └── ...
├── epaper_display_env_data.py # 本体スクリプト
├── README.md             # このファイル
└── requirements.txt      # Pythonライブラリリスト
```

### `requirements.txt` の内容

```txt
paho-mqtt
Pillow
python-dotenv
```
