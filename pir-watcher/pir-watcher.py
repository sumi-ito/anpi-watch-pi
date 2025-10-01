#!/usr/bin/env python3
import os, time, subprocess, json
from datetime import datetime, timezone, timedelta
from pathlib import Path
import RPi.GPIO as GPIO

DEVICE_ID = os.environ.get("DEVICE_ID", "your-device-id")
S3_BUCKET = os.environ.get("S3_BUCKET", "your-s3-bucket")
REGION    = os.environ.get("REGION", "ap-northeast-1")
PIR_PIN   = int(os.environ.get("PIR_PIN", "17"))
SLOT_MIN  = int(os.environ.get("MOTION_SLOT_MIN", "10"))

# デバイスモデルを検出
def detect_device_model():
    try:
        with open("/proc/cpuinfo", "r") as f:
            for line in f:
                if line.startswith("Model"):
                    model = line.split(":", 1)[1].strip().lower()
                    if "pi zero 2" in model:
                        return "zero2"
                    elif "pi zero" in model:
                        return "zero"
        return "unknown"
    except Exception:
        return "unknown"

DEVICE_MODEL = detect_device_model()

# デバイスモデルごとの検知パラメータ
# Pi Zero: より厳格な検証（誤検知が多いため）
# Pi Zero 2: 標準的な検証
MOTION_PARAMS = {
    "zero": {
        "checks": 3,           # 確認回数
        "delays": [0.1, 0.2, 0.3, 0.4],  # 各確認間の待機時間(秒)
        "bouncetime": 5000     # イベント検知後の不感時間(ms)
    },
    "zero2": {
        "checks": 2,
        "delays": [0.1, 0.2, 0.3],
        "bouncetime": 1000
    },
    "unknown": {
        "checks": 2,
        "delays": [0.1, 0.2, 0.3],
        "bouncetime": 1000
    }
}

PARAMS = MOTION_PARAMS[DEVICE_MODEL]

def get_version():
    try:
        # より堅牢なパス解決
        script_dir = Path(__file__).resolve().parent
        version_file = script_dir.parent / "version.txt"
        return version_file.read_text().strip()
    except (FileNotFoundError, OSError) as e:
        # デバッグ情報をログに出力
        print(f"Version file error: {e}")
        return "unknown"

VERSION = get_version()

TMP_DIR = "/tmp/pir"
os.makedirs(TMP_DIR, exist_ok=True)

JST = timezone(timedelta(hours=9))

# references:
# https://osoyoo.com/ja/category/osoyoo-raspi-kit/osoyoo-starter-kit-v1-for-raspberry-pi/
# https://osoyoo.com/ja/2017/07/04/raspi-pir-motion-sensor/
def current_slot_key(dt: datetime) -> str:
    # 10分刻みスロットの場合: 12:03→12:00, 12:17→12:10
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
    # version情報を含むJSONデータを作成
    motion_data = {
        "timestamp": s3_key,
        "version": VERSION,
        "device_model": DEVICE_MODEL
    }
    s3_uri = f"s3://{S3_BUCKET}/devices/{DEVICE_ID}/motion/{s3_key}"
    data = json.dumps(motion_data, ensure_ascii=False).encode()
    subprocess.run(
        ["aws", "s3", "cp", "-", s3_uri, "--region", REGION],
        input=data, check=False
    )
    return True

def motion_callback(channel):
    # 誤検知対策：デバイスモデルごとに複数回確認
    for i in range(PARAMS["checks"]):
        time.sleep(PARAMS["delays"][i])
        if GPIO.input(PIR_PIN) != GPIO.HIGH:
            return  # 確認失敗、検知しない

    # すべての確認を通過した場合のみ検知
    now = datetime.now(JST)
    slot = current_slot_key(now)
    local_flag = os.path.join(TMP_DIR, f"motion-{slot}")
    put_s3_if_new(local_flag, slot)

def main():
    if not DEVICE_ID or not S3_BUCKET:
        raise SystemExit("DEVICE_ID / S3_BUCKET is not set")

    print(f"Device model: {DEVICE_MODEL}, Motion params: {PARAMS}")

    GPIO.setmode(GPIO.BCM)
    GPIO.setup(PIR_PIN, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
    # 立上りで検知（デバイスモデルごとのbouncetime）
    GPIO.add_event_detect(PIR_PIN, GPIO.RISING, callback=motion_callback, bouncetime=PARAMS["bouncetime"])

    try:
        while True:
            time.sleep(1)
    finally:
        GPIO.cleanup()

if __name__ == "__main__":
    main()