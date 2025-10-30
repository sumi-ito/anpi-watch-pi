# PIR Watcher ログ管理

S3 + Athena によるログ管理システムのセットアップガイド

## アーキテクチャ

```
Raspberry Pi (Zero/Zero2)
  └─ pir-test.py (ログ出力)
      └─ /home/anpi/anpi-watch-pi/logs/pir-watcher.log
          └─ logrotate (日次ローテーション、午前0時)
              └─ *.log.gz (圧縮済みログ)
                  └─ systemd timer (log-upload.timer、午前3時)
                      └─ upload-logs-to-s3.sh
                          └─ S3: s3://bucket/logs/{device_id}/{date}/
                              └─ Athena (SQLクエリで分析)
```

## セットアップ手順

### 自動セットアップ（推奨）

`anpi-update.sh` を実行すると、初回のみ自動的にセットアップされます:

```bash
# anpi-update を実行（初回のみセットアップが走る）
/usr/local/bin/anpi-update.sh
```

以下が自動でインストールされます:

- `/usr/local/bin/upload-logs-to-s3.sh` - S3アップロードスクリプト
- `/etc/logrotate.d/anpi-watcher` - logrotate設定
- `/etc/systemd/system/log-upload.service` - S3アップロードサービス
- `/etc/systemd/system/log-upload.timer` - 日次実行タイマー（午前3時）
- `/home/anpi/anpi-watch-pi/logs/` - ログディレクトリ

### 手動セットアップ

自動セットアップを使わない場合は、以下を手動で実行:

```bash
# スクリプトのインストール
sudo cp pi/scripts/upload-logs-to-s3.sh /usr/local/bin/
sudo chmod +x /usr/local/bin/upload-logs-to-s3.sh

# logrotate 設定
sudo cp pi/config/logrotate-anpi-watcher /etc/logrotate.d/anpi-watcher

# systemd timer + service のインストール
sudo cp pi/log-upload/log-upload.service /etc/systemd/system/
sudo cp pi/log-upload/log-upload.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable log-upload.timer
sudo systemctl start log-upload.timer

# ログディレクトリの作成
mkdir -p /home/anpi/anpi-watch-pi/logs
```

### 環境変数の設定

`/etc/pir-monitor/config.env` に以下を設定:

```bash
S3_BUCKET=your-s3-bucket
DEVICE_ID=$(hostname)
REGION=ap-northeast-1
AWS_ACCESS_KEY_ID=your-access-key
AWS_SECRET_ACCESS_KEY=your-secret-key
```

### 動作確認

```bash
# timer の状態確認
sudo systemctl status log-upload.timer

# 次回実行予定時刻を確認
sudo systemctl list-timers log-upload.timer

# 手動実行（テスト）
sudo systemctl start log-upload.service

# ログ確認
sudo journalctl -u log-upload.service -f
```

**設定内容:**

- **logrotate**: 毎日午前0時にローテーション、7日分保持、gzip圧縮
- **log-upload.timer**: 毎日午前3時に圧縮済みログをS3へアップロード
- **upload-logs-to-s3.sh**: アップロード成功後に `.gz` ファイルを削除

### IAM ポリシー設定

Raspberry Pi の IAM ロール/ユーザーに以下の権限を付与:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["s3:PutObject", "s3:PutObjectAcl"],
      "Resource": "arn:aws:s3:::your-s3-bucket/logs/*"
    }
  ]
}
```

### 4. Athena テーブル作成

AWS Console > Athena で以下を実行:

```bash
# SQLファイルを編集（S3バケット名、デバイスIDリストを修正）
vi aws/config/athena/athena-table.sql

# Athena でテーブル作成
# (AWSコンソールから athena-table.sql の内容を実行)
```

**重要:** 以下を環境に合わせて編集

- `LOCATION 's3://your-s3-bucket/logs/'`
- `projection.device_id.values` にデバイスIDリストを設定

## ログフォーマット

### 出力例

```
2025-10-05T12:34:56+0900 [INFO] zero2: event=RISING inc=20 score=40 max=120
2025-10-05T12:34:57+0900 [INFO] zero2: score=39 recent=1 detected=0
2025-10-05T12:35:10+0900 [INFO] zero2: event=CONFIRMED score=60 threshold=50
```

### フィールド

| フィールド     | 説明                  | 例                               |
| -------------- | --------------------- | -------------------------------- |
| `timestamp`    | ISO8601タイムスタンプ | `2025-10-05T12:34:56+0900`       |
| `log_level`    | ログレベル            | `INFO`, `ERROR`                  |
| `device_model` | デバイスモデル        | `zero`, `zero2`                  |
| `event`        | イベント種別          | `RISING`, `CONFIRMED`, `CLEARED` |
| `score`        | 現在のスコア          | `60`                             |
| `inc`          | 加算量                | `20`                             |
| `max`          | スコア上限            | `120`                            |
| `threshold`    | 確定閾値              | `50`                             |
| `recent`       | 最近動いたフラグ      | `0` or `1`                       |
| `detected`     | 検知中フラグ          | `0` or `1`                       |

## Athena クエリ例

### 最近1日の検知イベント

```sql
SELECT timestamp, device_id, device_model, score
FROM pir_watcher_logs
WHERE log_date >= date_format(current_date - interval '1' day, '%Y-%m-%d')
  AND event_type = 'CONFIRMED'
ORDER BY timestamp DESC;
```

### デバイスごとの検知回数（日別）

```sql
SELECT device_id, device_model, log_date, COUNT(*) as detection_count
FROM pir_watcher_logs
WHERE event_type = 'CONFIRMED'
  AND log_date >= '2025-10-01'
GROUP BY device_id, device_model, log_date
ORDER BY log_date DESC, detection_count DESC;
```

### スコア推移（時系列分析）

```sql
SELECT timestamp, score, detected
FROM pir_watcher_logs
WHERE log_date = '2025-10-05'
  AND device_id = 'device-1'
ORDER BY timestamp;
```

## トラブルシューティング

### ログが S3 にアップロードされない

```bash
# timer の状態確認
sudo systemctl status log-upload.timer

# service の状態確認
sudo systemctl status log-upload.service

# スクリプトの手動実行
sudo /usr/local/bin/upload-logs-to-s3.sh

# AWS CLI の動作確認
aws s3 ls s3://your-bucket/logs/

# IAM権限の確認
aws sts get-caller-identity

# 環境変数の確認
source /etc/pir-monitor/config.env && env | grep -E '(S3_BUCKET|DEVICE_ID|REGION|AWS_)'
```

### logrotate が動作しない

```bash
# logrotate の状態確認
sudo cat /var/lib/logrotate/status

# 手動実行（デバッグモード）
sudo logrotate -d /etc/logrotate.d/anpi-watcher

# 強制実行
sudo logrotate -f /etc/logrotate.d/anpi-watcher
```

### Athena でデータが見えない

```bash
# パーティション修復（projection 無効時のみ）
MSCK REPAIR TABLE pir_watcher_logs;

# S3 のファイル構造確認
aws s3 ls s3://your-bucket/logs/ --recursive

# テーブル定義確認
SHOW CREATE TABLE pir_watcher_logs;
```

## コスト見積もり

**前提:**

- デバイス数: 3台
- ログ量: 1台あたり 1MB/日 (圧縮後)
- 保持期間: S3に永続保存

**月間コスト (ap-northeast-1):**

- S3ストレージ: 3台 × 1MB × 30日 = 90MB → **$0.002/月**
- S3 PUT: 3台 × 30回 = 90回 → **$0.00045/月**
- Athena: 10GB スキャン/月 → **$0.05/月**

**合計: 約 $0.05/月 (約7円/月)**

非常に低コストで運用可能です。

## メモリ使用量

- **Python ロギング**: +1MB 程度
- **logrotate**: 実行時のみ（数秒）
- **AWS CLI**: 実行時のみ（S3アップロード時）

Zero/Zero2 でも問題なく動作します。
