#!/bin/sh
set -e

# dpkg calls prerm with "upgrade" during an upgrade; RPM calls it with "1".
# Keep the timers and pending state intact in that case.
case "${1:-}" in
    upgrade|1)
        exit 0
        ;;
esac

if command -v systemctl >/dev/null 2>&1; then
    systemctl disable --now jmx-update.timer >/dev/null 2>&1 || true
    systemctl stop jmx-provision.service >/dev/null 2>&1 || true
    systemctl daemon-reload || true
fi
