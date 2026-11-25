#!/bin/sh
set -e

STATE_DIR="/var/lib/jmx-setup"
LEGACY_DIR="$STATE_DIR/legacy"
OLD_UPDATE_ENABLED=0
LEGACY_ACTIVE=0

install -d -m 0755 "$STATE_DIR"
install -d -m 0755 "$LEGACY_DIR"

if command -v systemctl >/dev/null 2>&1; then
    if systemctl is-enabled --quiet jmxremote-update.timer 2>/dev/null; then
        OLD_UPDATE_ENABLED=1
    fi

    # The ISO and older manual instructions installed these units directly in
    # /etc/systemd/system. Archive them so they cannot shadow the packaged
    # units or keep running the old update path.
    for unit in jmx-setup.service jmxremote-update.service jmxremote-update.timer; do
        unit_path="/etc/systemd/system/$unit"
        [ -e "$unit_path" ] || continue

        case "$unit" in
            *.timer)
                systemctl disable --now "$unit" >/dev/null 2>&1 || true
                ;;
            *)
                # Do not kill a provisioning or apt run that is in progress.
                # Disable it now and archive the file on a later upgrade.
                if systemctl is-active --quiet "$unit"; then
                    systemctl disable "$unit" >/dev/null 2>&1 || true
                    LEGACY_ACTIVE=1
                    continue
                fi
                systemctl disable --now "$unit" >/dev/null 2>&1 || true
                ;;
        esac
        mv -f "$unit_path" "$LEGACY_DIR/$unit" || true
    done
    rm -f /etc/systemd/system/graphical.target.wants/jmx-setup.service
    rm -f /etc/systemd/system/multi-user.target.wants/jmxremote-update.timer
    rm -f /etc/systemd/system/timers.target.wants/jmxremote-update.timer

    systemctl daemon-reload || true
fi

# Keep /etc/default/jmx-setup aligned with the values that are actually live
# in /etc/jmxd/jmxd.conf. Without this, a later forced re-provision would
# silently reset an existing machine to the packaged defaults.
if command -v jmx-setup >/dev/null 2>&1; then
    jmx-setup config sync-defaults >/dev/null 2>&1 || true
fi

# Mark the packaged assets as pending. run-provision.sh compares the asset
# hash and clears this without doing anything when the assets are unchanged.
: > "$STATE_DIR/pending"
chmod 0644 "$STATE_DIR/pending"

if command -v systemctl >/dev/null 2>&1; then
    case "${1:-}" in
        configure)
            if [ -z "${2:-}" ]; then
                # First install: enable the daily update timer.
                systemctl enable --now jmx-update.timer >/dev/null 2>&1 || true
            elif [ "$OLD_UPDATE_ENABLED" = "1" ]; then
                # Upgrade from the legacy unit that was enabled: carry the
                # administrator's choice forward.
                systemctl enable --now jmx-update.timer >/dev/null 2>&1 || true
            elif systemctl is-enabled --quiet jmx-update.timer 2>/dev/null; then
                # Preserve an enabled jmx-update.timer across upgrades.
                systemctl start jmx-update.timer >/dev/null 2>&1 || true
            fi

            # Apply pending provisioning after apt releases its locks. The
            # wrapper waits for the dpkg lock, so starting it here does not
            # deadlock the install. If the legacy first-boot unit is still
            # running, leave the pending marker for the daily update or a
            # manual `jmx-setup run` instead of running two copies.
            if [ "$LEGACY_ACTIVE" = "1" ]; then
                echo "Legacy JMX provisioning is still running; new provisioning is pending."
            else
                systemctl start --no-block jmx-provision.service >/dev/null 2>&1 || true
            fi
            ;;
    esac
fi

cat <<'EOF'
JMX kiosk setup package installed.

  Status:  sudo jmx-setup status
  Apply:   sudo jmx-setup run
  Update:  sudo jmx-setup update
  Config:  sudo jmx-setup config show
EOF
