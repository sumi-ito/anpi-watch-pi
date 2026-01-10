#!/usr/bin/env python3
"""
遠隔再起動コマンドをチェックし、条件を満たす場合に実行する。

処理内容:
1. ローカルデバイス設定を読み込み
2. reboot.requested_at フィールドをチェック
3. 時間窓（requested_at の前後5分）内かを検証
4. ローカル状態ファイルを使用して重複実行を防止
5. 再起動コマンドを実行
"""

import json
import os
import sys
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

# Configuration
REPO_ROOT = Path("/home/anpi/anpi-watch-pi")
CONFIG_FILE = REPO_ROOT / "config" / "local_device_config.json"
LAST_REBOOT_FILE = REPO_ROOT / "config" / "last_reboot_requested_at.txt"
TIMEZONE = ZoneInfo("Asia/Tokyo")
TIME_WINDOW_MINUTES = 5


def log(message):
    """Print log message with timestamp."""
    now = datetime.now(TIMEZONE).isoformat()
    print(f"[{now}] {message}", flush=True)


def read_config():
    """Read local device configuration."""
    if not CONFIG_FILE.exists():
        log(f"Config file not found: {CONFIG_FILE}")
        return None

    try:
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    except Exception as e:
        log(f"Failed to read config file: {e}")
        return None


def read_last_reboot_timestamp():
    """Read the last executed reboot timestamp."""
    if not LAST_REBOOT_FILE.exists():
        return None

    try:
        with open(LAST_REBOOT_FILE, "r") as f:
            return f.read().strip()
    except Exception as e:
        log(f"Failed to read last reboot timestamp: {e}")
        return None


def write_last_reboot_timestamp(timestamp):
    """Write the executed reboot timestamp."""
    try:
        LAST_REBOOT_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(LAST_REBOOT_FILE, "w") as f:
            f.write(timestamp)
        log(f"Recorded reboot timestamp: {timestamp}")
    except Exception as e:
        log(f"Failed to write last reboot timestamp: {e}")
        raise


def parse_iso8601(timestamp_str):
    """Parse ISO8601 timestamp string to datetime object."""
    try:
        return datetime.fromisoformat(timestamp_str)
    except Exception as e:
        log(f"Failed to parse timestamp '{timestamp_str}': {e}")
        return None


def is_within_time_window(requested_at_str):
    """Check if current time is within ±5 minutes of requested_at."""
    requested_at = parse_iso8601(requested_at_str)
    if not requested_at:
        return False

    now = datetime.now(TIMEZONE)
    time_diff = abs((now - requested_at).total_seconds() / 60)

    log(f"Current time: {now.isoformat()}")
    log(f"Requested at: {requested_at.isoformat()}")
    log(f"Time difference: {time_diff:.1f} minutes")

    return time_diff <= TIME_WINDOW_MINUTES


def execute_reboot():
    """Execute system reboot command."""
    log("Executing reboot command...")
    try:
        subprocess.run(["/usr/bin/sudo", "/sbin/reboot"], check=True)
    except Exception as e:
        log(f"Failed to execute reboot: {e}")
        raise


def main():
    """Main entry point."""
    log("Starting remote reboot check")

    # Read configuration
    config = read_config()
    if not config:
        log("No valid configuration found, exiting")
        sys.exit(0)

    # Check for reboot field
    reboot_config = config.get("reboot")
    if not reboot_config:
        log("No reboot configuration found, exiting")
        sys.exit(0)

    # Get requested_at timestamp
    requested_at = reboot_config.get("requested_at")
    if not requested_at:
        log("No requested_at timestamp found, exiting")
        sys.exit(0)

    log(f"Found reboot request: {requested_at}")

    # Check if this request was already executed
    last_executed = read_last_reboot_timestamp()
    if last_executed == requested_at:
        log(f"This reboot request was already executed (timestamp: {requested_at}), skipping")
        sys.exit(0)

    # Check time window
    if not is_within_time_window(requested_at):
        log(f"Current time is outside the time window (±{TIME_WINDOW_MINUTES} minutes), skipping")
        sys.exit(0)

    # All conditions met, execute reboot
    log("All conditions met, proceeding with reboot")

    # Record timestamp before reboot
    write_last_reboot_timestamp(requested_at)

    # Execute reboot
    execute_reboot()


if __name__ == "__main__":
    main()
