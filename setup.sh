# !/bin/bash

mkdir -p /tmp/pir
sudo mkdir /etc/pir-monitor/

# vim
sudo apt-get remove --purge vim-tiny
sudo apt-get update
sudo apt-get install vim
vim --version

# awscli
sudo apt install awscli

# Deploy Keyの登録
# https://docs.github.com/ja/developers/overview/managing-deploy-keys
ssh-keygen -t ed25519 -C "raspi-anpi-watch" -f ~/.ssh/id_ed25519_github
# これをGitHubのDeploy Keyに登録する
cat ~/.ssh/id_ed25519_github.pub
vi ~/.ssh/config
# ```
# Host github-anpi
#     HostName github.com
#     User git
#     IdentityFile ~/.ssh/id_ed25519_github
#     IdentitiesOnly yes
# ```
chmod 600 ~/.ssh/config

# アプリケーションのセットアップ
cd ~
git clone github-anpi:sumi-ito/anpi-watch.git
cd anpi-watch/
cp pi/config.env.example pi/config.env
# 1. device_id, s3_bucket を設定
# 注意: 新規でIAMユーザーを作成し、アクセスキーを発行しておく
vi pi/config.env
# リンクを張る
sudo ln -s ~/anpi-watch/pi/config.env /etc/pir-monitor/config.env

# pir-watcherの設定
sudo ln -s ~/anpi-watch/pi/pir-watcher/pir-watcher.py      /usr/local/bin/pir-watcher.py
sudo ln -s ~/anpi-watch/pi/pir-watcher/pir-watcher.service /etc/systemd/system/pir-watcher.service
sudo systemctl enable --now pir-watcher.service
sudo systemctl status pir-watcher.service
# 手動起動
# sudo systemctl start pir-watcher.service

# heartbeatの設定
sudo ln -s ~/anpi-watch/pi/heartbeat/heartbeat.py      /usr/local/bin/heartbeat.py
sudo ln -s ~/anpi-watch/pi/heartbeat/heartbeat.service /etc/systemd/system/heartbeat.service
sudo ln -s ~/anpi-watch/pi/heartbeat/heartbeat.timer   /etc/systemd/system/heartbeat.timer
# sudo systemctl enable --now heartbeat.service
# sudo systemctl disable heartbeat.service
sudo systemctl enable --now heartbeat.timer
# sudo systemctl status heartbeat.service
sudo systemctl status heartbeat.timer
# 手動起動
# sudo systemctl start heartbeat.timer

# 自動デプロイの設定
sudo ln -s ~/anpi-watch/pi/tools/anpi-update.sh      /usr/local/bin/anpi-update.sh
sudo ln -s ~/anpi-watch/pi/tools/anpi-update.service /etc/systemd/system/anpi-update.service
sudo ln -s ~/anpi-watch/pi/tools/anpi-update.timer   /etc/systemd/system/anpi-update.timer
sudo systemctl daemon-reload
# sudo systemctl enable --now anpi-update.service
# sudo systemctl disable anpi-update.service
sudo systemctl enable --now anpi-update.timer
systemctl list-timers | grep anpi-update
# sudo systemctl status anpi-update.timer
# sudo systemctl start anpi-update.timer

# 設定を再読み込み
sudo systemctl daemon-reload

sudo reboot
