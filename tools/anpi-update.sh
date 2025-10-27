#!/usr/bin/env bash
# set -euo pipefail

REPO=/home/anpi/anpi-watch-pi

cd "$REPO"

# 念のため許可（環境により safe.directory が必要）
# git config --global --add safe.directory "$REPO" || true

# 更新（main ブランチ想定）
git fetch --prune
git reset --hard origin/main

if [ ! -f /etc/systemd/system/pir-watcher.service ]; then
  echo "Setting up pir-watcher daemon..."
  sudo ln -s ~/anpi-watch-pi/pir-watcher/pir-watcher.py      /usr/local/bin/pir-watcher.py
  sudo ln -s ~/anpi-watch-pi/pir-watcher/pir-watcher.service /etc/systemd/system/pir-watcher.service
  sudo systemctl daemon-reload
  sudo systemctl enable --now pir-watcher.service
  echo "pir-watcher daemon setup completed."
fi

if [ ! -f /etc/systemd/system/heartbeat.timer ]; then
  echo "Setting up heartbeat daemon..."
  sudo ln -s ~/anpi-watch-pi/heartbeat/heartbeat.py      /usr/local/bin/heartbeat.py
  sudo ln -s ~/anpi-watch-pi/heartbeat/heartbeat.service /etc/systemd/system/heartbeat.service
  sudo ln -s ~/anpi-watch-pi/heartbeat/heartbeat.timer   /etc/systemd/system/heartbeat.timer
  sudo systemctl daemon-reload
  sudo systemctl enable --now heartbeat.service
  sudo systemctl enable --now heartbeat.timer
  echo "heartbeat daemon setup completed."
fi

if [ ! -f /etc/systemd/system/anpi-update.timer ]; then
  echo "Setting up deploy automation daemon..."
  sudo ln -s ~/anpi-watch-pi/tools/anpi-update.sh      /usr/local/bin/anpi-update.sh
  sudo ln -s ~/anpi-watch-pi/tools/anpi-update.service /etc/systemd/system/anpi-update.service
  sudo ln -s ~/anpi-watch-pi/tools/anpi-update.timer   /etc/systemd/system/anpi-update.timer
  sudo systemctl daemon-reload
  # sudo systemctl enable --now anpi-update.service
  sudo systemctl enable --now anpi-update.timer
  # systemctl list-timers | grep anpi-update
  # sudo systemctl status anpi-update.timer
  # sudo systemctl status anpi-update.service
  echo "deploy automation daemon setup completed."
fi

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
  bash ~/anpi-watch-pi/sync_device_config/install.sh
fi

# ログ管理の初期設定（初回のみ）
if [ ! -f /etc/systemd/system/log-upload.timer ]; then
  echo "Setting up log management (S3 + logrotate + systemd timer)..."

  # S3アップロードスクリプトのファイルコピー
  sudo cp "$REPO/scripts/upload-logs-to-s3.sh" /usr/local/bin/upload-logs-to-s3.sh
  sudo chmod +x /usr/local/bin/upload-logs-to-s3.sh

  # logrotate設定のコピー
  sudo cp "$REPO/config/logrotate-anpi-watcher" /etc/logrotate.d/anpi-watcher

  # ログディレクトリの作成
  mkdir -p "$REPO/logs"
  chmod 755 "$REPO/logs"

  # systemd timer + service のファイルコピー
  sudo cp "$REPO/log-upload/log-upload.service" /etc/systemd/system/log-upload.service
  sudo cp "$REPO/log-upload/log-upload.timer" /etc/systemd/system/log-upload.timer
  sudo systemctl daemon-reload
  sudo systemctl enable --now log-upload.timer
  # sudo systemctl start log-upload.timer

  echo "Log management setup completed."
fi

CURRENT_HOUR=$(date +%H)
if [ "$CURRENT_HOUR" = "06" ]; then
  logger "anpi-watch: Scheduled reboot at 6:00"
  sudo reboot
fi