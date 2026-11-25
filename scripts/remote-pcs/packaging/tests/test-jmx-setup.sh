#!/usr/bin/env bash
# Lightweight regression tests for jmx-setup config handling.
#
# The tests run as an unprivileged user by patching a copy of the CLI:
# root checks and chown calls are no-ops, and all state lives in a temp dir.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
CLI_SRC="$REPO_ROOT/scripts/remote-pcs/packaging/bin/jmx-setup"

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

mkdir -p "$work/etc/jmxd" "$work/etc/default" "$work/run/sessions"
cat > "$work/etc/jmxd/jmxd.conf" <<'EOF'
# JMX daemon configuration
socket_directory = /run/jmx
workspace_directory = /home/examkiosk/exam_workspace
server_address = 127.0.0.1
server_port = 8080
session_duration_in_hours = 2
EOF
printf 'JMX_SERVER_ADDRESS=127.0.0.1\nJMX_SERVER_PORT=8080\nJMX_SESSION_DURATION_HOURS=2\n' \
  > "$work/etc/default/jmx-setup"

cli="$work/jmx-setup-test"
cp "$CLI_SRC" "$cli"
sed -i 's/if \[ "${EUID}" -ne 0 \]; then/if false; then/' "$cli"
sed -i 's/chown root:root/:/g' "$cli"
sed -i "s|SESSION_FILE=\"/run/jmx/sessions/current_session.txt\"|SESSION_FILE=\"$work/run/sessions/current_session.txt\"|" "$cli"
chmod +x "$cli"

export JMX_CONFIG_FILE="$work/etc/jmxd/jmxd.conf"
export JMX_SETUP_DEFAULTS_FILE="$work/etc/default/jmx-setup"

run() { bash "$cli" "$@"; }
expect_fail() {
    if run "$@" >"$work/out" 2>&1; then
        echo "FAIL: expected failure for: $*" >&2
        cat "$work/out" >&2
        exit 1
    fi
}
assert_config_has() {
    grep -qx "$1" "$JMX_CONFIG_FILE" || {
        echo "FAIL: missing config line: $1" >&2
        exit 1
    }
}

echo '== invalid values are rejected =='
expect_fail config set server_address exam.example.com
expect_fail config set server_address 999.1.1.1
expect_fail config set server_port 0
expect_fail config set server_port 65536
expect_fail config set session_duration_in_hours 0
expect_fail config set session_duration_in_hours abc
expect_fail config set server_address '10.0.0.1 = evil'

echo '== managed keys are read-only =='
expect_fail config set socket_directory /tmp/jmx
expect_fail config set workspace_directory /tmp/workspace

echo '== valid values are written and mirrored =='
run config set server_address 10.0.0.10
run config set server_port 0080
run config set session_duration_in_hours 6
assert_config_has 'server_address = 10.0.0.10'
assert_config_has 'server_port = 80'
assert_config_has 'session_duration_in_hours = 6'
grep -qx 'JMX_SERVER_ADDRESS=10.0.0.10' "$JMX_SETUP_DEFAULTS_FILE"
grep -qx 'JMX_SERVER_PORT=80' "$JMX_SETUP_DEFAULTS_FILE"
grep -qx 'JMX_SESSION_DURATION_HOURS=6' "$JMX_SETUP_DEFAULTS_FILE"

echo '== show/get/validate =='
[ "$(run config get server_address)" = "10.0.0.10" ]
run config show > "$work/show"
grep -q 'server_address.*10.0.0.10' "$work/show"
run config validate > "$work/validate"
grep -q 'Configuration is valid' "$work/validate"

echo '== backup and restore =='
run config backups > "$work/backups"
grep -q 'jmxd.conf.' "$work/backups"
run config restore latest >/dev/null
[ "$(run config get server_address)" = "10.0.0.10" ]

echo '== unset falls back to the compiled default =='
run config unset server_port >/dev/null
[ "$(run config get server_port)" = "8080" ]
! grep -qx 'JMX_SERVER_PORT=.*' "$JMX_SETUP_DEFAULTS_FILE"

echo '== reset restores all defaults =='
run config reset --yes >/dev/null
[ "$(run config get server_address)" = "127.0.0.1" ]
[ "$(run config get server_port)" = "8080" ]
[ "$(run config get session_duration_in_hours)" = "2" ]

echo '== active session blocks writes =='
run config set server_address 10.1.2.3 >/dev/null
touch "$work/run/sessions/current_session.txt"
expect_fail config set server_address 10.9.9.9
expect_fail config unset server_address
rm -f "$work/run/sessions/current_session.txt"
[ "$(run config get server_address)" = "10.1.2.3" ]

echo "PASS: jmx-setup CLI tests"
