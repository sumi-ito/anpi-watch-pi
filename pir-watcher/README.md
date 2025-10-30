# PIR Watcher

人感センサー (HC-SR501) を監視し、検知時にS3へ記録するコンポーネントです。

## 概要

- **実行方式**: systemd service (常駐)
- **センサー**: HC-SR501 (GPIO 17)
- **検知ロジック**: スコアリング方式（チャタリング防止）
- **S3パス**: `s3://{bucket}/devices/{device_id}/motion/{ISO8601-timestamp}`

## スコアリング方式

センサーの誤検知を防ぐためスコアリングアルゴリズムを使用:

```python
# センサー反応時
score += INC_PER_EVENT  # スコア加算

# 毎秒減衰
score -= LEAK_PER_SEC  # スコア減算

# 確定判定
if score >= THRESHOLD:
    motion_confirmed()  # S3へ記録
```

### 感度プリセット

| 感度   | デバイス | THRESHOLD | 特徴                   |
| ------ | -------- | --------- | ---------------------- |
| high   | Zero 2   | 50        | 高感度・誤検知やや多   |
| medium | Zero 2   | 60        | バランス型（推奨）     |
| low    | Zero 2   | 60        | 低感度・確実な検知のみ |

環境変数 `PIR_SENSITIVITY` で変更可能 (デフォルト: `medium`)。

## ログ出力

### ログ形式

```
2025-10-05T12:34:56+0900 [INFO] zero2: event=RISING inc=20 score=40 max=120
2025-10-05T12:34:57+0900 [INFO] zero2: score=39 recent=1 detected=0
2025-10-05T12:35:10+0900 [INFO] zero2: event=CONFIRMED score=60 threshold=50
```

### ログ管理

- **ファイル**: `/home/anpi/anpi-watch-pi/logs/pir-watcher.log`
- **ローテーション**: logrotate (日次、7日保持、gzip圧縮)
- **S3アップロード**: log-upload.timer (日次3時)

詳細は [LOGGING.md](../LOGGING.md) を参照。

## センサー配線

| HC-SR501 | Raspberry Pi     |
| -------- | ---------------- |
| VCC      | 5V (Pin 2 or 4)  |
| GND      | GND (Pin 6)      |
| OUT      | GPIO 17 (Pin 11) |

## セットアップ

```bash
# サービスインストール
sudo cp pir-watcher.service /etc/systemd/system/
sudo systemctl daemon-reload

# 有効化・起動
sudo systemctl enable pir-watcher.service
sudo systemctl start pir-watcher.service

# ログ確認
sudo journalctl -u pir-watcher.service -f
```

## トラブルシューティング

### センサーが反応しない

```bash
# GPIO接続確認
gpio readall  # WiringPi必要

# サービス停止して手動実行
sudo systemctl stop pir-watcher.service
cd /home/anpi/anpi-watch-pi/pir-watcher
source /etc/pir-monitor/config.env
python3 pir-watcher.py

# センサー感度調整（ハードウェア）
# HC-SR501の可変抵抗を調整:
# - 左: 感度 (3-7m)
# - 右: 時間調整 (0.3-5分) → 最短推奨
```

### 誤検知が多い/少ない

```bash
# 感度変更
export PIR_SENSITIVITY=low  # or high, medium
python3 pir-watcher.py

# または pir-watcher.service に環境変数追加
sudo systemctl edit pir-watcher.service
# [Service]
# Environment="PIR_SENSITIVITY=low"
```

## 関連ドキュメント

- [ログ管理システム](../LOGGING.md)
- [Pi コンポーネント概要](../README.md)
- [アーキテクチャ](../../docs/ARCHITECTURE.md)
