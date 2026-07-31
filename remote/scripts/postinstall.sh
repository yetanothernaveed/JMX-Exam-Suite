#!/bin/sh
set -e

systemctl daemon-reload
systemctl enable jmxd.service || true

# Restart the service so the newly installed binary starts running immediately
if systemctl is-active --quiet jmxd.service; then
  systemctl restart jmxd.service || true
else
  systemctl start jmxd.service || true
fi
