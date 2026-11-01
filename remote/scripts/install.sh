#!/usr/bin/env bash
set -e

# Ensure root access
if [ "$EUID" -ne 0 ]; then
  echo "Please run as root (e.g., sudo ./install.sh)"
  exit 1
fi

echo "==> Installing jmx, jmxcleanerd and jmxd..."

# 1. Install binaries
install -m 0755 bin/jmx /usr/local/bin/jmx
install -m 0755 bin/jmxd /usr/local/bin/jmxd
install -m 0755 bin/jmxcleanerd /usr/local/bin/jmxcleanerd

# 2. Install systemd service (Mode 0644)
if [ -d /etc/systemd/system ]; then
  echo "==> Installing systemd service..."
  install -m 0644 systemd/jmxd.service /etc/systemd/system/jmxd.service
  install -m 0644 systemd/jmxcleanerd.service /etc/systemd/system/jmxcleanerd.service
  install -m 0644 systemd/jmxcleanerd.timer /etc/systemd/system/jmxcleanerd.timer

  # 3. Reload systemd and enable service
  echo "==> Enabling and starting services..."
  systemctl daemon-reload
  systemctl enable --now jmxd.service
  systemctl enable --now jmxcleanerd.timer
  
  echo "==> Listing timers..."
  systemctl list-timers jmxcleanerd.timer

  echo "==> Restarting daemon to load updated binary..."
  systemctl restart jmxd.service
  systemctl restart jmxcleanerd.service
  echo "==> Service installed/updated and running!"
else
  echo "W: systemd not detected. Service file not installed."
fi

echo "==> Installation complete! Run 'jmx --help' to get started."
