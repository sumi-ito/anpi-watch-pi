import json
from pathlib import Path
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

REPO_ROOT = Path(__file__).parent.parent
CONFIG_FILE = REPO_ROOT / "config" / "local_device_config.json"


def read_config():
    if not CONFIG_FILE.exists():
        raise FileNotFoundError(f"Config file not found: {CONFIG_FILE}")
    with open(CONFIG_FILE) as f:
        return json.load(f)


_config = read_config()
_slack_config = _config["bluetooth"]["slack"]

SLACK_BOT_TOKEN = _slack_config["bot_token"]
SLACK_APP_TOKEN = _slack_config["app_token"]
ALLOWED_USER_IDS = _config["bluetooth"]["allowed_user_ids"]

app = App(token=SLACK_BOT_TOKEN)


# ボットへのメンション（@ボット名）に反応する処理
@app.event("app_mention")
def handle_mention(event, say):
    user_id = event.get("user")
    if user_id not in ALLOWED_USER_IDS:
        say(f"<@{user_id}> 申し訳ありません、あなたはこのボットを操作する権限がありません。")
        return

    text = event.get("text")

    if "プラグオン" in text:
        # ここにスマートプラグをONにするコードを書く
        say("了解！スマートプラグをONにしました。")

    elif "プラグオフ" in text:
        # ここにスマートプラグをOFFにするコードを書く
        say("了解！スマートプラグをOFFにしました。")

    elif "状態" in text:
        # Bluetooth接続の確認など、現在の状態を返す
        say("現在は[在宅]モードで動作中です。")

    else:
        say("「プラグオン」「プラグオフ」「状態」のいずれかを送ってください。")

if __name__ == "__main__":
    # ソケットモードで起動
    handler = SocketModeHandler(app, SLACK_APP_TOKEN)
    handler.start()
