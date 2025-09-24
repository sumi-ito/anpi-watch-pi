# デバイス設定の同期
sudo ln -s ~/anpi-watch/pi/sync_device_config/sync_device_config.py      /usr/local/bin/sync_device_config.py
sudo ln -s ~/anpi-watch/pi/sync_device_config/sync_device_config.service /etc/systemd/system/sync_device_config.service
sudo ln -s ~/anpi-watch/pi/sync_device_config/sync_device_config.timer   /etc/systemd/system/sync_device_config.timer
sudo systemctl daemon-reload
sudo systemctl enable --now sync_device_config.service
sudo systemctl enable --now sync_device_config.timer
systemctl list-timers | grep sync_device_config
sudo systemctl status sync_device_config.timer
sudo systemctl status sync_device_config.service
# 手動起動
# sudo systemctl start   sync_device_config.service
# sudo systemctl restart sync_device_config.service
