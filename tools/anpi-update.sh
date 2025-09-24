#!/usr/bin/env bash
# set -euo pipefail

REPO=/home/anpi/anpi-watch

cd "$REPO"

# 念のため許可（環境により safe.directory が必要）
# git config --global --add safe.directory "$REPO" || true

# 更新（main ブランチ想定）
git fetch --prune
git reset --hard origin/main
git submodule update --init --recursive

# 依存があればここで反映（例：pip, npm など）
# /home/anpi/venv/bin/pip install -r requirements.txt || true

# リポジトリ内の unit を /etc/systemd/system にシンボリックリンクしている場合、
# 変更が反映されるように daemon-reload と必要サービスの再起動をかける
sudo /bin/systemctl daemon-reload
sudo /bin/systemctl restart pir-watcher.service
# oneshot は timer が起動するので通常は再起動不要だが、変更を即反映したいときは明示再実行
# sudo /bin/systemctl restart heartbeat.service || true
# sudo /bin/systemctl restart anpi-update.service || true

# デバイス同期デーモンの初期設定（初回のみ）
if [ ! -f /etc/systemd/system/sync_device_config.timer ]; then
  echo "Setting up device sync daemon..."
  bash ~/anpi-watch/pi/sync_device_config/install.sh
fi