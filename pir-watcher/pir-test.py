#!/usr/bin/env python3
import os, time, threading, subprocess, json
from datetime import datetime, timezone, timedelta
from pathlib import Path
import RPi.GPIO as GPIO

# ====== 設定 ======
PIR_PIN = 17
JST = timezone(timedelta(hours=9))

# AWS
DEVICE_ID = os.environ.get("DEVICE_ID", "your-device-id")
S3_BUCKET = os.environ.get("S3_BUCKET", "your-s3-bucket")
REGION    = os.environ.get("REGION", "ap-northeast-1")

# 一時保存先
TMP_DIR = "/tmp/pir"
os.makedirs(TMP_DIR, exist_ok=True)

# 計測単位の設定 デフォルト: 10分毎
SLOT_MIN = int(os.environ.get("MOTION_SLOT_MIN", "10"))

# デバイスモデル検出（パラメータ設定で使用）
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

# 感度プリセット: {device_model: {sensitivity: {param: value}}}
SENSITIVITY_PRESETS = {
    "zero2": {
        "high": {
            "LEAK_PER_SEC": 1,
            "INC_PER_EVENT": 25,   # BUFFER_SEC * 5
            "THRESHOLD": 50,       # BUFFER_SEC * 10
            "CLEAR_THRESHOLD": 30, # THRESHOLD * .6
            "BUFFER_SEC": 5,
        },
        "medium": {
            "LEAK_PER_SEC": 1,
            "INC_PER_EVENT": 20,   # BUFFER_SEC * 4
            "THRESHOLD": 60,       # BUFFER_SEC * 12
            "CLEAR_THRESHOLD": 36, # THRESHOLD * .6
            "BUFFER_SEC": 5,
        },
        "low": {
            "LEAK_PER_SEC": 1,
            "INC_PER_EVENT": 15,   # BUFFER_SEC * 3
            "THRESHOLD": 60,       # BUFFER_SEC * 12
            "CLEAR_THRESHOLD": 36, # THRESHOLD * .6
            "BUFFER_SEC": 5,
        },
    },
    "zero": {
        "high": {
            "LEAK_PER_SEC": 1,
            "INC_PER_EVENT": 24,   # BUFFER_SEC * 6
            "THRESHOLD": 32,       # BUFFER_SEC * 8
            "CLEAR_THRESHOLD": 42, # THRESHOLD * .6
            "BUFFER_SEC": 4,
        },
        "medium": {
            "LEAK_PER_SEC": 1,
            "INC_PER_EVENT": 20,   # BUFFER_SEC * 5
            "THRESHOLD": 36,       # BUFFER_SEC * 9
            "CLEAR_THRESHOLD": 21, # THRESHOLD * .6
            "BUFFER_SEC": 4,
        },
        "low": {
            "LEAK_PER_SEC": 1,
            "INC_PER_EVENT": 16,   # BUFFER_SEC * 4
            "THRESHOLD": 40,       # BUFFER_SEC * 10
            "CLEAR_THRESHOLD": 21, # THRESHOLD * .6
            "BUFFER_SEC": 4,
        },
    },
}

# 感度レベルの取得（環境変数またはデフォルト）
SENSITIVITY = os.environ.get("SENSITIVITY", "medium").lower()

# パラメータの決定（プリセットまたは環境変数で個別指定）
def get_param(param_name, default_value):
    """環境変数が指定されていればそれを使用、なければプリセットから取得"""
    env_value = os.environ.get(param_name)
    if env_value:
        return int(env_value)

    # プリセットから取得
    if DEVICE_MODEL in SENSITIVITY_PRESETS:
        if SENSITIVITY in SENSITIVITY_PRESETS[DEVICE_MODEL]:
            return SENSITIVITY_PRESETS[DEVICE_MODEL][SENSITIVITY].get(param_name, default_value)

    return default_value

# "リーキーバケット"のパラメータ
LEAK_PER_SEC    = get_param("LEAK_PER_SEC", 1)      # 1秒毎の減衰量
INC_PER_EVENT   = get_param("INC_PER_EVENT", 20)    # 立ち上がり1回の加点
THRESHOLD       = get_param("THRESHOLD", 60)        # これ以上で確定
CLEAR_THRESHOLD = get_param("CLEAR_THRESHOLD", 36)  # 解除域（ヒステリシス）
BUFFER_SEC      = get_param("BUFFER_SEC", 5)        # 1回検知後の"最近動いた"判定バッファ
# ==================

lock = threading.Lock()
score = 0
detected = False
last_detected = None

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
    global score, last_detected
    now = datetime.now(JST)
    with lock:
        score += INC_PER_EVENT
        last_detected = now
        print(f"{now.isoformat()}, {DEVICE_MODEL}: RISING (+{INC_PER_EVENT}) score={score}", flush=True)



def main():
    global score, detected

    # 起動時パラメータ表示
    print(f"=== PIR Watcher Started ===", flush=True)
    print(f"Device Model: {DEVICE_MODEL}", flush=True)
    print(f"Sensitivity: {SENSITIVITY}", flush=True)
    print(f"Parameters:", flush=True)
    print(f"  LEAK_PER_SEC: {LEAK_PER_SEC}", flush=True)
    print(f"  INC_PER_EVENT: {INC_PER_EVENT}", flush=True)
    print(f"  THRESHOLD: {THRESHOLD}", flush=True)
    print(f"  CLEAR_THRESHOLD: {CLEAR_THRESHOLD}", flush=True)
    print(f"  BUFFER_SEC: {BUFFER_SEC}", flush=True)
    print(f"==========================", flush=True)

    GPIO.setmode(GPIO.BCM)
    GPIO.setup(PIR_PIN, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)

    # RISINGのみ拾い、5秒チャタリング抑制（Zero側のチラつきを抑える）
    GPIO.add_event_detect(PIR_PIN, GPIO.RISING, callback=motion_callback, bouncetime=BUFFER_SEC * 1000)

    try:
        while True:
            now = datetime.now(JST)
            with lock:
                # 1秒ごとにリーク（0未満は禁止）
                if score > 0:
                    score = max(0, score - LEAK_PER_SEC)

                # ヒステリシスつきの確定/解除
                if not detected and score >= THRESHOLD:
                    detected = True
                    print(
                        f"{now.isoformat()}, {DEVICE_MODEL}: CONFIRMED score={score} "
                        f"(>= {THRESHOLD})", flush=True
                    )
                    now = datetime.now(JST)
                    slot = current_slot_key(now)
                    local_flag = os.path.join(TMP_DIR, f"motion-{slot}")
                    put_s3_if_new(local_flag, slot)
                elif detected and score < CLEAR_THRESHOLD:
                    detected = False
                    print(
                        f"{now.isoformat()}, {DEVICE_MODEL}: CLEARED score={score} "
                        f"(< {CLEAR_THRESHOLD})", flush=True
                    )

                # 直近5秒以内の“最近動いた”ステータス（観測用）
                recent = 1 if (last_detected and (now - last_detected).total_seconds() < BUFFER_SEC) else 0

                print(
                    f"{now.isoformat()}, {DEVICE_MODEL}: score={score} recent={recent} detected={int(detected)}",
                    flush=True
                )

            time.sleep(1)
    finally:
        GPIO.cleanup()

if __name__ == "__main__":
    main()