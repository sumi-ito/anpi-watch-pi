#!/usr/bin/env python3
import os, time, subprocess
from datetime import datetime, timezone, timedelta
import RPi.GPIO as GPIO

DEVICE_ID = os.environ.get("DEVICE_ID", "your-device-id")
S3_BUCKET = os.environ.get("S3_BUCKET", "your-s3-bucket")
REGION    = os.environ.get("REGION", "ap-northeast-1")
PIR_PIN   = int(os.environ.get("PIR_PIN", "17"))
SLOT_MIN  = int(os.environ.get("MOTION_SLOT_MIN", "10"))

TMP_DIR = "/tmp/pir"
os.makedirs(TMP_DIR, exist_ok=True)

JST = timezone(timedelta(hours=9))

# references:
# https://osoyoo.com/ja/category/osoyoo-raspi-kit/osoyoo-starter-kit-v1-for-raspberry-pi/
# https://osoyoo.com/ja/2017/07/04/raspi-pir-motion-sensor/
def current_slot_key(dt: datetime) -> str:
    # 10分刻みスロット: 12:03→12:00, 12:17→12:10
    minute_slot = (dt.minute // SLOT_MIN) * SLOT_MIN
    rounded = dt.replace(minute=minute_slot, second=0, microsecond=0)
    # ISO8601風: YYYY-MM-DDTHH:MM:00+09:00 のように出力
    return rounded.isoformat(timespec="seconds")

def put_s3_if_new(local_flag_path: str, s3_key: str):
    if os.path.exists(local_flag_path):
        return False
    # ローカルフラグ作成
    with open(local_flag_path, "w") as f:
        f.write("1")
    # 中身不要 → 空オブジェクトをPUT
    s3_uri = f"s3://{S3_BUCKET}/devices/{DEVICE_ID}/motion/{s3_key}"
    subprocess.run(
        ["aws", "s3", "cp", "-", s3_uri, "--region", REGION],
        input=b"", check=False
    )
    return True

def motion_callback(channel):
    now = datetime.now(JST)
    slot = current_slot_key(now)
    local_flag = os.path.join(TMP_DIR, f"motion-{slot}")
    put_s3_if_new(local_flag, slot)

def main():
    if not DEVICE_ID or not S3_BUCKET:
        raise SystemExit("DEVICE_ID / S3_BUCKET is not set")

    GPIO.setmode(GPIO.BCM)
    GPIO.setup(PIR_PIN, GPIO.IN)

    # 立上りで検知
    GPIO.add_event_detect(PIR_PIN, GPIO.RISING, callback=motion_callback, bouncetime=1000)

    try:
        while True:
            time.sleep(1)
    finally:
        GPIO.cleanup()

if __name__ == "__main__":
    main()