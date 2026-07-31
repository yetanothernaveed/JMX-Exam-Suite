#!/usr/bin/env bash
set -e

# Ensure root access
if [ "$EUID" -ne 0 ]; then
  echo "Please run as root (e.g., sudo ./install.sh)"
  exit 1
fi

echo "==> Installing my-cli and my-daemon..."

# 1. Install binaries
install -m 0755 bin/jmx /usr/local/bin/jmx
install -m 0755 bin/jmxd /usr/local/bin/jmxd

# 2. Install systemd service
if [ -d /etc/systemd/system ]; then
  echo "==> Installing systemd service..."
  install -m 0744 systemd/jmxd.service /etc/systemd/system/jmxd.service
  
  # 3. Reload systemd and enable service
  systemctl daemon-reload
  systemctl enable --now jmxd.service
  
  echo "==> Restarting daemon to load updated binary..."
  systemctl restart jmxd.service
  echo "==> Service installed/updated and running!"
else
  echo "W: systemd not detected. Service file not installed."
fi

echo "==> Installation complete! Run 'my-cli --help' to get started."
