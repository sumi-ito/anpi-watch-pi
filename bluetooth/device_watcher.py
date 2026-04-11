import subprocess
import urllib.request
import json
import time
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
CONFIG_FILE = REPO_ROOT / "config" / "local_device_config.json"
CHECK_INTERVAL = 10  # チェック間隔（秒）


def read_config():
    if not CONFIG_FILE.exists():
        raise FileNotFoundError(f"Config file not found: {CONFIG_FILE}")
    with open(CONFIG_FILE) as f:
        return json.load(f)


_config = read_config()
DEVICE_MAC = _config["bluetooth"]["device_mac"]
SLACK_URL = _config["notification"]["slack"]["webhook_url"]

def send_slack(message):
    payload = json.dumps({"text": message}).encode("utf-8")
    req = urllib.request.Request(SLACK_URL, data=payload, headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req)
    except Exception as e:
        print(f"Slack送信失敗: {e}")

def is_connected():
    """bluetoothctlを使用して接続状態を確認する"""
    cmd = f"bluetoothctl info {DEVICE_MAC}"
    result = subprocess.run(cmd.split(), capture_output=True, text=True)
    return "Connected: yes" in result.stdout

DISCONNECT_DELAY = 60  # 切断通知を送るまでの猶予時間（秒）

def main():
    print("監視を開始します...")
    last_state = is_connected() # 初期状態を取得

    while True:
        current_state = is_connected()

        if current_state != last_state:
            if current_state:
                send_slack("🏠 【帰宅検知】スマホがBluetoothに接続されました。")
                last_state = current_state
            else:
                # 切断検知: 60秒間様子を見て、まだ切断中なら通知する
                print(f"切断を検知。{DISCONNECT_DELAY}秒後に確認します...")
                time.sleep(DISCONNECT_DELAY)
                if not is_connected():
                    send_slack("🚪 【外出検知】スマホの接続が切れました。")
                    last_state = False
                else:
                    print("瞬断と判断。通知をスキップします。")
                    last_state = True
                continue

        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()