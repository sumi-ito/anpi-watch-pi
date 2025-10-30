#!/usr/bin/env python3
"""
ラズパイ用スクリプト: S3からデバイス設定を同期
devices/{device_id}.json を取得してローカルに保存
"""

import json
import subprocess
import os
import sys
from datetime import datetime
from typing import Dict, Any, Optional

DEVICE_ID = os.environ.get("DEVICE_ID", "your-device-id")
S3_BUCKET = os.environ.get("S3_BUCKET", "your-s3-bucket")
REGION    = os.environ.get("REGION", "ap-northeast-1")

class DeviceConfigSyncer:
    def __init__(self, bucket_name: str, config_dir: str = '/home/anpi/anpi-watch-pi/config', region: str = 'ap-northeast-1'):
        self.bucket_name = bucket_name
        self.config_dir = config_dir
        self.region = region
        self.local_config_file = os.path.join(config_dir, 'local_device_config.json')
        self.runtime_status_file = os.path.join(config_dir, 'runtime_status.json')

    def ensure_config_dir(self):
        """設定ディレクトリを作成"""
        os.makedirs(self.config_dir, exist_ok=True)

    def download_device_config(self, device_id: str) -> Dict[str, Any]:
        """S3からデバイス設定をダウンロード"""
        try:
            s3_uri = f"s3://{self.bucket_name}/config/devices/{device_id}.json"
            result = subprocess.run(
                ["aws", "s3", "cp", s3_uri, "-", "--region", self.region],
                capture_output=True,
                text=True,
                check=True
            )
            config = json.loads(result.stdout)
            print(f"Downloaded config for {device_id}")
            return config
        except subprocess.CalledProcessError as e:
            if "NoSuchKey" in str(e.stderr) or "404" in str(e.stderr):
                print(f"Error: Configuration not found for device {device_id}")
                print(f"Make sure config/devices/{device_id}.json exists in S3 bucket {self.bucket_name}")
            else:
                print(f"Error downloading config for {device_id}: {e.stderr}")
            raise
        except json.JSONDecodeError as e:
            print(f"Error parsing config JSON for {device_id}: {e}")
            raise

    def save_local_config(self, config: Dict[str, Any]):
        """ローカル設定ファイルを保存"""
        with open(self.local_config_file, 'w') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        print(f"Saved local config to {self.local_config_file}")

    def load_local_config(self) -> Optional[Dict[str, Any]]:
        """ローカル設定ファイルを読み込み"""
        if not os.path.exists(self.local_config_file):
            return None

        try:
            with open(self.local_config_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading local config: {e}")
            return None

    def is_device_enabled(self, config: Dict[str, Any]) -> bool:
        """デバイスが有効かどうかチェック"""
        # enabledフラグのチェック
        if not config.get('enabled', False):
            return False

        # 有効期限のチェック
        expires = config.get('expires')
        if expires:
            try:
                from datetime import datetime, timezone, timedelta
                import re

                # ISO 8601形式 (2026-11-31T23:59:59+09:00) のパース
                iso_pattern = r'^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})([+-]\d{2}):(\d{2})$'
                match = re.match(iso_pattern, expires)

                if match:
                    year, month, day, hour, minute, second, tz_hour, tz_minute = match.groups()

                    # タイムゾーンオフセット計算
                    tz_offset_hours = int(tz_hour)
                    tz_offset_minutes = int(tz_minute) if tz_offset_hours >= 0 else -int(tz_minute)
                    tz_offset = timedelta(hours=tz_offset_hours, minutes=tz_offset_minutes)
                    tz = timezone(tz_offset)

                    # datetime オブジェクト作成
                    expire_date = datetime(
                        int(year), int(month), int(day),
                        int(hour), int(minute), int(second),
                        tzinfo=tz
                    )

                    # 現在時刻と比較
                    now = datetime.now(tz)
                    if now > expire_date:
                        print(f"Device expired: {expires}")
                        return False
                else:
                    print(f"Invalid date format: {expires}")
                    return False

            except Exception as e:
                print(f"Error parsing expiry date {expires}: {e}")
                return False

        return True

    def init_runtime_status(self):
        """実行時ステータスファイルを初期化"""
        default_status = {
            "last_sync": datetime.now().isoformat(),
            "heartbeat": {
                "enabled": False,
                "last_sent": None,
                "next_scheduled": None
            },
            "pir_watcher": {
                "enabled": False,
                "last_motion": None,
                "process_id": None
            },
            "activity_report": {
                "enabled": False,
                "last_sent": None,
                "next_scheduled": None
            }
        }

        with open(self.runtime_status_file, 'w') as f:
            json.dump(default_status, f, indent=2, ensure_ascii=False)
        print(f"Initialized runtime status: {self.runtime_status_file}")

    def update_runtime_status(self, updates: Dict[str, Any]):
        """実行時ステータスを更新"""
        if os.path.exists(self.runtime_status_file):
            with open(self.runtime_status_file, 'r') as f:
                status = json.load(f)
        else:
            self.init_runtime_status()
            with open(self.runtime_status_file, 'r') as f:
                status = json.load(f)

        # 更新を適用
        for key, value in updates.items():
            status[key] = value

        status['last_sync'] = datetime.now().isoformat()

        with open(self.runtime_status_file, 'w') as f:
            json.dump(status, f, indent=2, ensure_ascii=False)

    def sync_config(self):
        """設定を同期"""
        self.ensure_config_dir()

        # デバイスIDを取得
        device_id = DEVICE_ID
        print(f"Device ID: {device_id}")

        # S3から設定をダウンロード
        config = self.download_device_config(device_id)

        # ローカルに保存
        self.save_local_config(config)

        # デバイス有効性をチェック
        enabled = self.is_device_enabled(config)
        print(f"Device enabled: {enabled}")

        # 実行時ステータスを更新
        if not os.path.exists(self.runtime_status_file):
            self.init_runtime_status()

        self.update_runtime_status({
            "device_enabled": enabled,
            "last_config_sync": datetime.now().isoformat()
        })

        return config, enabled

    def get_current_config(self) -> tuple[Optional[Dict[str, Any]], bool]:
        """現在の設定と有効性を取得"""
        config = self.load_local_config()
        if config is None:
            return None, False

        enabled = self.is_device_enabled(config)
        return config, enabled

def main():
    import argparse

    parser = argparse.ArgumentParser(description='Sync device configuration from S3')
    # parser.add_argument('--bucket', required=True, help='S3 bucket name')
    # parser.add_argument('--region', default='ap-northeast-1', help='AWS region (default: ap-northeast-1)')
    parser.add_argument('--config-dir', default='/home/anpi/anpi-watch-pi/config',
                        help='Local config directory path')
    parser.add_argument('--check-only', action='store_true',
                        help='Only check current status without syncing')

    args = parser.parse_args()

    syncer = DeviceConfigSyncer(S3_BUCKET, args.config_dir, REGION)

    try:
        if args.check_only:
            config, enabled = syncer.get_current_config()
            if config:
                print(f"Current config: {config.get('name', 'Unknown')}")
                print(f"Enabled: {enabled}")
            else:
                print("No local configuration found")
        else:
            config, enabled = syncer.sync_config()
            print(f"Sync completed - Device: {config.get('name', 'Unknown')}, Enabled: {enabled}")

    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()