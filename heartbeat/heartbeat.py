#!/usr/bin/env python3
import os, subprocess, json
from datetime import datetime, timezone, timedelta
from pathlib import Path

DEVICE_ID = os.environ.get("DEVICE_ID", "your-device-id")
S3_BUCKET = os.environ.get("S3_BUCKET", "your-s3-bucket")
REGION    = os.environ.get("REGION", "ap-northeast-1")
def get_version():
    try:
        version_file = Path(__file__).parent.parent / "version.txt"
        return version_file.read_text().strip()
    except (FileNotFoundError, OSError):
        return "unknown"

VERSION = get_version()

TMP_DIR = "/tmp/pir"
Path(TMP_DIR).mkdir(parents=True, exist_ok=True)
JST = timezone(timedelta(hours=9))

def get_cpu_temperature():
    try:
        with open('/sys/class/thermal/thermal_zone0/temp', 'r') as f:
            temp_millidegree = int(f.read().strip())
            return round(temp_millidegree / 1000.0, 1)
    except (FileNotFoundError, ValueError, OSError):
        return None

def main():
    if not DEVICE_ID or not S3_BUCKET:
        raise SystemExit("DEVICE_ID / S3_BUCKET is not set")
    now = datetime.now(JST)
    # 分・秒・マイクロ秒をゼロにリセット
    rounded = now.replace(minute=0, second=0, microsecond=0)
    # ISO8601形式（時まで、タイムゾーン付き）
    key = rounded.isoformat(timespec="seconds")
    flag = Path(TMP_DIR) / f"hb-{key}"
    if flag.exists():
        return
    flag.write_text("1")

    # ハートビートデータにCPU温度を含める
    heartbeat_data = {
        "timestamp": key,
        "temperature": get_cpu_temperature(),
        "version": VERSION
    }

    s3_uri = f"s3://{S3_BUCKET}/devices/{DEVICE_ID}/heartbeat/{key}"
    data = json.dumps(heartbeat_data, ensure_ascii=False).encode()
    subprocess.run(["aws", "s3", "cp", "-", s3_uri, "--region", REGION], input=data, check=False)

if __name__ == "__main__":
    main()