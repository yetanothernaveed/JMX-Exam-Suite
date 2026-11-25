#!/bin/bash
#
# Apply the packaged JMX kiosk provisioning script.
#
# This wrapper is deliberately separate from setup_script.sh:
#   - it is the only place that decides whether a run is allowed
#   - it records the applied asset checksum so an unchanged upgrade is a no-op
#   - it serialises concurrent runs and waits for apt/dpkg locks to clear
#
# The systemd unit provides the normal guards. This script repeats them so a
# manual invocation has the same safety properties.

set -euo pipefail

ASSET_DIR="/usr/lib/jmx-setup"
STATE_DIR="/var/lib/jmx-setup"
DEFAULTS_FILE="/etc/default/jmx-setup"
HOLD_FILE="/etc/jmx/jmx-setup-hold"
SESSION_FILE="/run/jmx/sessions/current_session.txt"
PENDING_FILE="$STATE_DIR/pending"
APPLIED_HASH_FILE="$STATE_DIR/applied-assets.sha256"
APPLIED_VERSION_FILE="$STATE_DIR/applied-version"
LAST_RESULT_FILE="$STATE_DIR/last-result"
FAIL_COUNT_FILE="$STATE_DIR/fail-count"
REBOOT_MARKER="$STATE_DIR/reboot-recommended"
LOCK_FILE="/run/jmx-setup.lock"

log() { printf '[jmx-provision] %s\n' "$*"; }
die() { printf '[jmx-provision] ERROR: %s\n' "$*" >&2; exit 1; }

if [ "${EUID}" -ne 0 ]; then
    die "must run as root"
fi

install -d -m 0755 "$STATE_DIR"

# Load first-install/forced-reconfigure defaults. Values already present in
# the environment win, matching the previous setup-script behaviour.
if [ -r "$DEFAULTS_FILE" ]; then
    set -a
    # shellcheck disable=SC1090
    . "$DEFAULTS_FILE"
    set +a
fi

export DEBIAN_FRONTEND="${DEBIAN_FRONTEND:-noninteractive}"
export NEEDRESTART_SUSPEND="${NEEDRESTART_SUSPEND:-1}"
export JMX_ALLOW_ACTIVE_SESSION="${JMX_ALLOW_ACTIVE_SESSION:-0}"

FORCE_RUN="${JMX_SETUP_FORCE:-0}"

if grep -qw 'boot=casper' /proc/cmdline 2>/dev/null; then
    log "live ISO environment detected (boot=casper); skipping"
    exit 0
fi

if [ -f "$HOLD_FILE" ]; then
    log "hold file $HOLD_FILE exists; skipping"
    exit 0
fi

if [ ! -f "$PENDING_FILE" ] && [ "$FORCE_RUN" != "1" ]; then
    log "nothing pending"
    exit 0
fi

check_session_guard() {
    if [ -f "$SESSION_FILE" ] && [ "$JMX_ALLOW_ACTIVE_SESSION" != "1" ]; then
        log "active exam session detected ($SESSION_FILE); deferring"
        exit 0
    fi
}

wait_for_apt_lock() {
    local i
    if ! command -v fuser >/dev/null 2>&1; then
        return 0
    fi
    for i in $(seq 1 120); do
        if ! fuser -s \
            /var/lib/dpkg/lock-frontend \
            /var/lib/dpkg/lock \
            /var/cache/apt/archives/lock 2>/dev/null; then
            return 0
        fi
        sleep 5
    done
    log "timed out waiting for the apt/dpkg lock"
    return 1
}

compute_assets_hash() {
    (
        cd "$ASSET_DIR"
        find setup_script.sh branding rc.xml -type f -print0 2>/dev/null |
            LC_ALL=C sort -z |
            xargs -0 -r sha256sum
    ) | sha256sum | awk '{print $1}'
}

# Serialise runs. The systemd unit already prevents duplicates, but a manual
# `jmx-setup run` must not race the timer or the daily updater.
exec 9>"$LOCK_FILE"
if ! flock -w 300 9; then
    log "another provisioning run holds $LOCK_FILE; skipping"
    exit 0
fi

check_session_guard
wait_for_apt_lock || exit 1

fail_count=0
if [ -r "$FAIL_COUNT_FILE" ]; then
    fail_count="$(cat "$FAIL_COUNT_FILE" 2>/dev/null || echo 0)"
fi
case "$fail_count" in
    ''|*[!0-9]*) fail_count=0 ;;
esac

current_hash="$(compute_assets_hash)"

if [ "$FORCE_RUN" != "1" ] && [ -r "$APPLIED_HASH_FILE" ] &&
   [ "$(cat "$APPLIED_HASH_FILE" 2>/dev/null || true)" = "$current_hash" ]; then
    log "provisioning assets unchanged; clearing pending marker"
    rm -f "$PENDING_FILE"
    printf 'unchanged %s\n' "$(date -Is)" > "$LAST_RESULT_FILE"
    exit 0
fi

rm -f "$REBOOT_MARKER"

log "applying JMX provisioning (asset hash $current_hash)"
cd "$ASSET_DIR"

if bash "$ASSET_DIR/setup_script.sh"; then
    printf '%s\n' "$current_hash" > "$APPLIED_HASH_FILE"
    if package_version="$(dpkg-query -W -f='${Version}' jmxsetup 2>/dev/null)"; then
        printf '%s\n' "$package_version" > "$APPLIED_VERSION_FILE"
    fi
    rm -f "$PENDING_FILE" "$FAIL_COUNT_FILE"
    printf 'success %s\n' "$(date -Is)" > "$LAST_RESULT_FILE"
    log "provisioning applied successfully"

    # Never reboot automatically. Record the advisory so `jmx-setup status`
    # and the next administrator can see that a reboot is pending.
    if [ -f /run/reboot-required ] || [ -f /var/run/reboot-required ]; then
        date -Is > "$REBOOT_MARKER"
        log "a reboot is recommended (/run/reboot-required is present)"
    fi

    # Provisioning may have rewritten the exam session or display-manager
    # configuration. Restart SDDM only when no exam is active (already
    # guaranteed above).
    if command -v systemctl >/dev/null 2>&1; then
        systemctl try-restart sddm.service >/dev/null 2>&1 || true
    fi
    exit 0
else
    rc=$?
    fail_count=$(( fail_count + 1 ))
    printf '%s\n' "$fail_count" > "$FAIL_COUNT_FILE"
    printf 'failure %s rc=%s\n' "$(date -Is)" "$rc" > "$LAST_RESULT_FILE"
    log "provisioning failed with status $rc; pending marker kept for a later retry"
    exit "$rc"
fi
