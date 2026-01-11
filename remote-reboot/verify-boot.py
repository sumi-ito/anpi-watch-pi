#!/usr/bin/env python3
"""
再起動後にPIR Watcherサービスを検証し、起動通知を送信する。

処理内容:
1. pir-watcher.service がactive (running)状態かをチェック
2. 60秒間待機して継続動作を検証
3. 起動情報を収集
4. S3に起動通知をアップロード
"""

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

# Configuration
DEVICE_ID = os.environ.get("DEVICE_ID", "unknown-device")
S3_BUCKET = os.environ.get("S3_BUCKET", "your-s3-bucket")
REGION = os.environ.get("REGION", "ap-northeast-1")
TIMEZONE = ZoneInfo("Asia/Tokyo")
VERIFICATION_WAIT_SECONDS = 60
REPO_ROOT = Path("/home/anpi/anpi-watch-pi")
CONFIG_FILE = REPO_ROOT / "config" / "local_device_config.json"


def log(message):
    """タイムスタンプ付きでログメッセージを出力する。"""
    now = datetime.now(TIMEZONE).isoformat()
    print(f"[{now}] {message}", flush=True)


def get_service_status(service_name):
    """systemdサービスがアクティブかをチェックする。"""
    try:
        result = subprocess.run(
            ["systemctl", "is-active", service_name],
            capture_output=True,
            text=True,
            check=False
        )
        status = result.stdout.strip()
        log(f"Service {service_name} status: {status}")
        return status == "active"
    except Exception as e:
        log(f"Failed to check service status: {e}")
        return False


def get_uptime_seconds():
    """システムの稼働時間を秒単位で取得する。"""
    try:
        with open("/proc/uptime", "r") as f:
            uptime_str = f.read().split()[0]
            return int(float(uptime_str))
    except Exception as e:
        log(f"Failed to get uptime: {e}")
        return None


def get_boot_time():
    """システムの起動時刻を取得する。"""
    try:
        uptime_seconds = get_uptime_seconds()
        if uptime_seconds is None:
            return None
        now = datetime.now(TIMEZONE)
        boot_time = now - timedelta(seconds=uptime_seconds)
        return boot_time.isoformat()
    except Exception as e:
        log(f"Failed to calculate boot time: {e}")
        return None


def read_config():
    """ローカルデバイス設定を読み込み、reboot.requested_atを取得する。"""
    if not CONFIG_FILE.exists():
        log(f"Config file not found: {CONFIG_FILE}")
        return None

    try:
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    except Exception as e:
        log(f"Failed to read config file: {e}")
        return None


def create_boot_notification():
    """起動通知JSONデータを生成する。"""
    now = datetime.now(TIMEZONE)
    boot_time = get_boot_time()
    uptime = get_uptime_seconds()

    # Read config to get reboot.requested_at if available
    config = read_config()
    requested_at = None
    if config and "reboot" in config:
        requested_at = config["reboot"].get("requested_at")

    notification = {
        "device_id": DEVICE_ID,
        "boot_time": boot_time,
        "verified_at": now.isoformat(),
        "pir_watcher_status": "active" if get_service_status("pir-watcher.service") else "inactive",
        "uptime_seconds": uptime,
        "reboot_reason": "remote_command" if requested_at else "unknown",
    }

    if requested_at:
        notification["requested_at"] = requested_at

    return notification


def upload_to_s3(notification):
    """起動通知をS3にアップロードする。"""
    now = datetime.now(TIMEZONE)
    timestamp = now.strftime("%Y-%m-%d-%H%M%S")
    s3_key = f"devices/notifications/{DEVICE_ID}/{timestamp}-boot-notification.json"
    s3_uri = f"s3://{S3_BUCKET}/{s3_key}"

    try:
        # Create temporary file
        tmp_file = Path("/tmp") / f"boot-notification-{timestamp}.json"
        with open(tmp_file, "w") as f:
            json.dump(notification, f, indent=2)

        # Upload to S3
        log(f"Uploading boot notification to {s3_uri}")
        result = subprocess.run(
            ["aws", "s3", "cp", str(tmp_file), s3_uri, "--region", REGION],
            capture_output=True,
            text=True,
            check=True
        )
        log(f"Upload successful: {s3_uri}")

        # Clean up
        tmp_file.unlink()
        return True

    except subprocess.CalledProcessError as e:
        log(f"Failed to upload to S3: {e.stderr}")
        return False
    except Exception as e:
        log(f"Failed to upload to S3: {e}")
        return False


def main():
    """メインエントリーポイント。"""
    log("Starting PIR watcher verification after reboot")

    # 初回チェック
    if not get_service_status("pir-watcher.service"):
        log("ERROR: pir-watcher.service is not active!")
        sys.exit(1)

    log(f"pir-watcher.service is active, waiting {VERIFICATION_WAIT_SECONDS} seconds to verify stability...")

    # 検証期間待機
    time.sleep(VERIFICATION_WAIT_SECONDS)

    # 待機後に再度チェック
    if not get_service_status("pir-watcher.service"):
        log("ERROR: pir-watcher.service stopped during verification period!")
        sys.exit(1)

    log(f"pir-watcher.service is still active after {VERIFICATION_WAIT_SECONDS} seconds")

    # 起動通知を生成
    notification = create_boot_notification()
    log(f"Boot notification data: {json.dumps(notification, indent=2)}")

    # S3にアップロード
    if upload_to_s3(notification):
        log("Boot verification completed successfully")
        sys.exit(0)
    else:
        log("Boot verification completed but S3 upload failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
