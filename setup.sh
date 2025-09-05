# !/bin/bash

mkdir -p /tmp/pir
sudo mkdir /etc/pir-monitor/

# アプリケーションの
cd ~
git clone xxxx.git anpi-watch
cd anpi-watch/
cp pi/config.env.example pi/config.env
# AWSのアクセスキーを設定
vi pi/config.env
# リンクを張る
sudo ln -s ~/anpi-watch/pi/config.env /etc/pir-monitor/config.env

# systemd にリンクを張る
sudo ln -s ~/anpi-watch/pi/pir-watcher/pir-watcher.py      /usr/local/bin/pir-watcher.py
sudo ln -s ~/anpi-watch/pi/pir-watcher/pir-watcher.service /etc/systemd/system/pir-watcher.service
sudo ln -s ~/anpi-watch/pi/heartbeat/heartbeat.py          /usr/local/bin/heartbeat.py
sudo ln -s ~/anpi-watch/pi/heartbeat/heartbeat.service     /etc/systemd/system/heartbeat.service
sudo ln -s ~/anpi-watch/pi/heartbeat/heartbeat.timer       /etc/systemd/system/heartbeat.timer

# 設定を再読み込み
sudo systemctl daemon-reload

# 有効化＆起動
sudo systemctl enable --now heartbeat.service
sudo systemctl enable --now heartbeat.timer
sudo systemctl enable --now pir-watcher.service
# 確認
sudo systemctl status heartbeat.service
sudo systemctl status heartbeat.timer
sudo systemctl status pir-watcher.service

# 手動起動
sudo systemctl start heartbeat.service
sudo systemctl start pir-watcher.service

sudo reboot
