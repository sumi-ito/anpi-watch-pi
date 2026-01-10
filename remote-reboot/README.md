# remote-reboot

遠隔再起動機能 - S3経由で特定のラズパイ端末を任意のタイミングで再起動し、起動確認と通知を行う。

## 概要

複数台のラズパイ端末のうち、特定の端末のみを遠隔から再起動する機能。S3の設定ファイルを介して再起動コマンドを配信し、再起動後にはpir-watcherプロセスの動作確認と起動通知を自動実行する。

## ユースケース

- 特定のラズパイの調子が悪い時、遠隔から再起動
- 起動後に自動で動作確認とメール通知

## アーキテクチャ

### データフロー

```
1. 再起動指示
   管理者 → S3設定ファイル更新 (reboot.requested_at設定)

2. 検知と実行
   check-reboot-command.service (5分間隔) → 設定ファイル読み込み
   → 再起動コマンド検知
   → sudo reboot 実行

3. 起動後確認
   起動 → verify-boot.service (oneshot)
   → pir-watcher.service が60秒間動作確認
   → S3に起動通知アップロード

4. 通知
   S3 boot-notification Put → S3イベント
   → Lambda → SES → メール送信
```

### 設定ファイル構造

**S3パス**: `s3://${S3_BUCKET}/config/devices/${DEVICE_ID}.json`

```json
{
  "services": {
    "pir-watcher": "enabled",
    "heartbeat": "enabled"
  },
  "reboot": {
    "requested_at": "2026-01-08T15:30:00+09:00"
  }
}
```

#### `reboot` フィールド仕様

| フィールド     | 型            | 説明                         |
| -------------- | ------------- | ---------------------------- |
| `requested_at` | ISO8601 (JST) | 再起動要求日時。管理者が設定 |

### 起動通知ファイル

**S3パス**: `s3://${S3_BUCKET}/devices/${DEVICE_ID}/boot-notifications/YYYY-MM-DD-HHmmss-boot-notification.json`

```json
{
  "device_id": "${DEVICE_ID}",
  "boot_time": "2026-01-08T15:43:15+09:00",
  "verified_at": "2026-01-08T15:43:30+09:00",
  "pir_watcher_status": "active",
  "uptime_seconds": 75,
  "reboot_reason": "remote_command",
  "requested_at": "2026-01-08T15:30:00+09:00"
}
```

## コンポーネント

### 1. check-reboot-command.py

再起動コマンドの検知と実行を行うスクリプト。

**実行タイミング**: systemd timer による5分間隔の定期実行

**処理フロー**:

1. `/home/anpi/anpi-watch-pi/config/local_device_config.json` を読み込み
2. `reboot` フィールドをチェック
3. `/home/anpi/anpi-watch-pi/config/last_reboot_requested_at.txt` から前回実行したタイムスタンプを読み込み
4. 以下の条件を全て満たす場合に再起動実行:
   - `requested_at` が設定されている
   - 現在時刻が `requested_at` の前後5分以内（時間窓）
   - `requested_at` が前回実行時と異なる（重複実行防止）
5. 再起動実行前に `last_reboot_requested_at.txt` に `requested_at` を記録
6. `sudo reboot` 実行

**冪等性**:

- 同じ `requested_at` での再起動は1回のみ（ローカルファイルで記録）
- 時間窓（±5分）外の古いコマンドは実行しない
- リトライは自動（5分間隔の定期実行により、時間窓内なら自然にリトライ）

### 2. verify-boot.py

起動後のpir-watcher動作確認と通知を行うスクリプト。

**実行タイミング**: 起動直後（systemd oneshot service）

**処理フロー**:

1. pir-watcher.service が `active (running)` 状態か確認
2. 60秒間待機し、プロセスが継続動作しているか確認
3. 起動通知JSONを生成
4. S3にアップロード (`devices/{DEVICE_ID}/boot-notifications/`)

### 3. systemd設定

#### check-reboot-command.service

```ini
[Unit]
Description=Check for remote reboot command
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
ExecStart=/usr/bin/python3 /home/anpi/anpi-watch-pi/remote-reboot/check-reboot-command.py
Environment="PYTHONUNBUFFERED=1"
EnvironmentFile=/etc/pir-monitor/config.env
```

#### check-reboot-command.timer

```ini
[Unit]
Description=Run check reboot command every 5 minutes

[Timer]
OnBootSec=1min
OnUnitActiveSec=5min
Persistent=true

[Install]
WantedBy=timers.target
```

#### verify-boot.service

```ini
[Unit]
Description=Verify PIR Watcher after reboot
After=network-online.target pir-watcher.service
Wants=network-online.target

[Service]
Type=oneshot
ExecStart=/usr/bin/python3 /home/anpi/anpi-watch-pi/remote-reboot/verify-boot.py
Environment="PYTHONUNBUFFERED=1"
EnvironmentFile=/etc/pir-monitor/config.env

[Install]
WantedBy=multi-user.target
```

## セットアップ

### 前提条件

- `sync_device_config` が正常に動作し、`local_device_config.json` が最新であること
- S3バケットへの書き込み権限があること（起動通知アップロード用）
- `/etc/pir-monitor/config.env` に必要な環境変数が設定されていること

### インストール

```bash
# 1. リポジトリ更新
cd /home/anpi/anpi-watch-pi
git pull origin main

# 2. systemdサービス・タイマー配置
sudo cp remote-reboot/check-reboot-command.service /etc/systemd/system/
sudo cp remote-reboot/check-reboot-command.timer /etc/systemd/system/
sudo cp remote-reboot/verify-boot.service /etc/systemd/system/

# 3. タイマー有効化・起動
sudo systemctl daemon-reload
sudo systemctl enable check-reboot-command.timer
sudo systemctl start check-reboot-command.timer
sudo systemctl enable verify-boot.service

# 4. ステータス確認
sudo systemctl status check-reboot-command.timer
sudo systemctl list-timers check-reboot-command.timer
```

## 使用方法

### 1. 再起動指示

S3設定ファイルを更新（手動またはLambda経由）:

```bash
# 現在の設定を取得
aws s3 cp s3://${S3_BUCKET}/config/devices/${DEVICE_ID}.json /tmp/config.json

# reboot フィールドを追加/更新
# {
#   "services": { ... },
#   "reboot": {
#     "requested_at": "2026-01-08T15:30:00+09:00"
#   }
# }

# S3にアップロード
aws s3 cp /tmp/config.json s3://${S3_BUCKET}/config/devices/${DEVICE_ID}.json
```

### 2. 実行確認

```bash
# ラズパイ側のログ確認
sudo journalctl -u check-reboot-command.service -n 50
sudo journalctl -u verify-boot.service -n 50

# タイマー状態確認
sudo systemctl status check-reboot-command.timer
sudo systemctl list-timers check-reboot-command.timer

# S3で起動通知確認
aws s3 ls s3://${S3_BUCKET}/devices/${DEVICE_ID}/boot-notifications/
```

### 3. ステータス確認

```bash
# 設定ファイルのステータス確認
aws s3 cp s3://${S3_BUCKET}/config/devices/${DEVICE_ID}.json - | jq .reboot
```

## トラブルシューティング

### 再起動が実行されない

- `sync_device_config` の実行ログを確認
- `local_device_config.json` が正しく更新されているか確認
- 手動で即座に実行: `sudo systemctl start sync_device_config.service`

### 起動通知が届かない

- `verify-boot.service` のログを確認: `sudo journalctl -u verify-boot.service`
- pir-watcher.service が正常に動作しているか確認
- S3に boot-notification ファイルがアップロードされているか確認

### 再起動コマンドが繰り返し実行される

- `requested_at` の時間窓（前後5分）を確認
- S3設定ファイルの `requested_at` が意図せず更新されていないか確認

## 制限事項

- 再起動検知の最大遅延: sync_device_config の実行間隔（10分）
- pir-watcher動作確認時間: 固定60秒
- 再起動コマンドの有効期限: なし（手動でクリアする必要あり）

## 将来の拡張案

- [ ] 再起動コマンドの有効期限設定
- [ ] 実際のPIRイベント検知まで待機する確認モード
- [ ] 再起動失敗時のリトライ機構
- [ ] Lambdaによる再起動指示API
- [ ] 複数台同時再起動のサポート
