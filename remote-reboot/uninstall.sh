#!/usr/bin/env bash
# Remote reboot feature uninstallation script
# This script removes systemd services and timers for remote reboot functionality

set -e

echo "Uninstalling remote reboot feature..."

# Stop and disable check-reboot-command timer
echo "- Stopping and disabling check-reboot-command.timer..."
sudo systemctl stop check-reboot-command.timer || true
sudo systemctl disable check-reboot-command.timer || true

# Stop and disable verify-boot service
echo "- Disabling verify-boot.service..."
sudo systemctl disable verify-boot.service || true

# Remove symlinks from /usr/local/bin
echo "- Removing binaries from /usr/local/bin..."
sudo rm -f /usr/local/bin/check-reboot-command.py
sudo rm -f /usr/local/bin/verify-boot.py

# Remove symlinks from /etc/systemd/system
echo "- Removing systemd service files..."
sudo rm -f /etc/systemd/system/check-reboot-command.service
sudo rm -f /etc/systemd/system/check-reboot-command.timer
sudo rm -f /etc/systemd/system/verify-boot.service

# Reload systemd daemon
echo "- Reloading systemd daemon..."
sudo systemctl daemon-reload
sudo systemctl reset-failed || true

# Show status
echo ""
echo "Uninstallation completed successfully!"
echo ""
echo "Remaining timers:"
systemctl list-timers | grep check-reboot-command || echo "  (none - successfully removed)"
echo ""
echo "Remote reboot feature has been removed."
echo ""
echo "Note: The local state file (/home/anpi/anpi-watch-pi/config/last_reboot_requested_at.txt)"
echo "      has NOT been removed. Delete it manually if needed."
