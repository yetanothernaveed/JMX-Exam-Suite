#!/bin/sh
set -e

systemctl daemon-reload
systemctl enable jmxd.service || true
systemctl enable jmxcleanerd.timer || true

# Restart the service so the newly installed binary starts running immediately
if systemctl is-active --quiet jmxd.service; then
  systemctl restart jmxd.service || true
else
  systemctl start jmxd.service || true
fi

if systemctl is-active --quiet jmxcleanerd.service; then
  systemctl restart jmxcleanerd.service || true
else
  systemctl start jmxcleanerd.service || true
fi

if systemctl is-active --quiet jmxcleanerd.timer; then
  systemctl restart jmxcleanerd.timer || true
else
  systemctl start jmxcleanerd.timer || true
fi
