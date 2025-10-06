#!/usr/bin/env python3
import os, time, threading, subprocess, json, logging
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

# ログ設定
LOG_DIR = "/home/anpi/anpi-watch/logs"
os.makedirs(LOG_DIR, exist_ok=True)

def setup_logging():
    """ログ設定（標準出力 + ファイル出力）"""
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    # 標準出力ハンドラ（既存の print 出力互換）
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter('%(message)s'))
    logger.addHandler(console_handler)

    # ファイル出力ハンドラ（logrotateでローテーション管理）
    file_handler = logging.FileHandler(
        f"{LOG_DIR}/pir-watcher.log",
        encoding='utf-8'
    )
    # ISO8601形式のタイムスタンプ + ログレベル + メッセージ
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%dT%H:%M:%S%z'
    ))
    logger.addHandler(file_handler)

    return logger

logger = setup_logging()

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
MAX_SCORE       = THRESHOLD * 2                      # スコアの上限（閾値の2倍）
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
        # ロギング設定前なので print
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
        score = min(score + INC_PER_EVENT, MAX_SCORE)
        last_detected = now
        logger.info(f"{DEVICE_MODEL}: event=RISING inc={INC_PER_EVENT} score={score} max={MAX_SCORE}")



def main():
    global score, detected

    # 起動時パラメータ表示
    logger.info("=== PIR Watcher Started ===")
    logger.info(f"version={VERSION} device_model={DEVICE_MODEL} sensitivity={SENSITIVITY}")
    logger.info(f"params: LEAK_PER_SEC={LEAK_PER_SEC} INC_PER_EVENT={INC_PER_EVENT} THRESHOLD={THRESHOLD} CLEAR_THRESHOLD={CLEAR_THRESHOLD} BUFFER_SEC={BUFFER_SEC} MAX_SCORE={MAX_SCORE}")
    logger.info("===========================")

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
                    logger.info(f"{DEVICE_MODEL}: event=CONFIRMED score={score} threshold={THRESHOLD}")
                elif detected and score < CLEAR_THRESHOLD:
                    detected = False
                    logger.info(f"{DEVICE_MODEL}: event=CLEARED score={score} clear_threshold={CLEAR_THRESHOLD}")
                    now = datetime.now(JST)
                    slot = current_slot_key(now)
                    local_flag = os.path.join(TMP_DIR, f"motion-{slot}")
                    put_s3_if_new(local_flag, slot)

                # 直近5秒以内の"最近動いた"ステータス（観測用）
                recent = 1 if (last_detected and (now - last_detected).total_seconds() < BUFFER_SEC) else 0

                logger.info(f"{DEVICE_MODEL}: score={score} recent={recent} detected={int(detected)}")

            time.sleep(1)
    finally:
        GPIO.cleanup()

if __name__ == "__main__":
    main()