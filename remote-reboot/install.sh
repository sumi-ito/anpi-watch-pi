#!/usr/bin/env bash
# Remote reboot feature installation script
# This script sets up systemd services and timers for remote reboot functionality

set -e

echo "Setting up remote reboot feature..."

# Create symlinks for check-reboot-command
echo "- Installing check-reboot-command service and timer..."
sudo ln -sf ~/anpi-watch-pi/remote-reboot/check-reboot-command.py      /usr/local/bin/check-reboot-command.py
sudo ln -sf ~/anpi-watch-pi/remote-reboot/check-reboot-command.service /etc/systemd/system/check-reboot-command.service
sudo ln -sf ~/anpi-watch-pi/remote-reboot/check-reboot-command.timer   /etc/systemd/system/check-reboot-command.timer

# Create symlink for verify-boot
echo "- Installing verify-boot service..."
sudo ln -sf ~/anpi-watch-pi/remote-reboot/verify-boot.py      /usr/local/bin/verify-boot.py
sudo ln -sf ~/anpi-watch-pi/remote-reboot/verify-boot.service /etc/systemd/system/verify-boot.service

# Reload systemd daemon
echo "- Reloading systemd daemon..."
sudo systemctl daemon-reload

# Enable and start check-reboot-command timer
echo "- Enabling and starting check-reboot-command.timer..."
sudo systemctl enable check-reboot-command.timer
sudo systemctl start check-reboot-command.timer

# Enable verify-boot service (will run on next boot)
echo "- Enabling verify-boot.service..."
sudo systemctl enable verify-boot.service

# Show status
echo ""
echo "Installation completed successfully!"
echo ""
echo "Timer status:"
systemctl list-timers check-reboot-command.timer
echo ""
echo "Service status:"
sudo systemctl status check-reboot-command.timer --no-pager || true
sudo systemctl status verify-boot.service --no-pager || true
echo ""
echo "Remote reboot feature is now active."
echo "The system will check for reboot commands every 5 minutes."
