#!/bin/sh
set -e

# dpkg calls prerm with "upgrade" during an upgrade; RPM calls it with "1".
# Do not stop the daemon in that case: the new postinstall restarts it.
case "${1:-}" in
  upgrade|1)
    exit 0
    ;;
esac

if command -v systemctl >/dev/null 2>&1; then
  systemctl disable --now jmxd.service || true
  systemctl disable --now jmxcleanerd.timer || true
  systemctl disable --now jmxcleanerd.service || true
  systemctl daemon-reload || true
fi
