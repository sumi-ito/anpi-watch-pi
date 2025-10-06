#!/bin/bash
# PIR Watcher ログを S3 へアップロード
# logrotate の postrotate スクリプトから呼ばれる

set -euo pipefail

# 環境変数を読み込み
if [ -f /etc/pir-monitor/config.env ]; then
    set +u  # 未定義変数エラーを一時的に無効化
    source /etc/pir-monitor/config.env
    set -u
fi

LOG_DIR="/home/anpi/anpi-watch/logs"
S3_BUCKET="${S3_BUCKET:-your-s3-bucket}"
REGION="${REGION:-ap-northeast-1}"
DEVICE_ID="${DEVICE_ID:-$(hostname)}"

# ログディレクトリが存在しない場合は終了
[ -d "$LOG_DIR" ] || exit 0

# .gz ファイル（ローテーション済み）のみアップロード
for gz_file in "$LOG_DIR"/*.gz; do
    # ファイルが存在しない場合はスキップ
    [ -f "$gz_file" ] || continue

    # ファイル名から日付を推測（pir-watcher.log.YYYY-MM-DD.gz）
    filename=$(basename "$gz_file")

    # 日付抽出（ファイル名パターン: pir-watcher.log.2025-10-05.gz）
    if [[ "$filename" =~ ([0-9]{4}-[0-9]{2}-[0-9]{2}) ]]; then
        log_date="${BASH_REMATCH[1]}"
    else
        # 日付が取れない場合はファイルの最終更新日を使用
        log_date=$(date -r "$gz_file" +%Y-%m-%d)
    fi

    # S3パス: s3://bucket/logs/device-id/YYYY-MM-DD/pir-watcher.log.gz
    s3_path="s3://${S3_BUCKET}/logs/${DEVICE_ID}/${log_date}/${filename}"

    echo "Uploading $gz_file to $s3_path"

    # S3へアップロード
    if aws s3 cp "$gz_file" "$s3_path" --region "$REGION"; then
        echo "Successfully uploaded $gz_file"
        # アップロード成功したら削除
        rm -f "$gz_file"
    else
        echo "Failed to upload $gz_file" >&2
    fi
done

echo "Log upload completed"
