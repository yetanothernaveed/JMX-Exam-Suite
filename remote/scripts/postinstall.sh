#!/bin/sh
set -e

# jmxd.service uses Group=jmx. Create the group before systemd tries to start
# the service, otherwise a fresh apt install fails on first boot.
if ! getent group jmx >/dev/null 2>&1; then
  groupadd --system jmx
fi

# The daemon writes its generated config here. Create it before starting the
# service so ProtectSystem=strict + ReadWritePaths=/etc/jmxd can work.
install -d -m 0755 /etc/jmxd

if command -v systemctl >/dev/null 2>&1; then
  systemctl daemon-reload || true

  # jmxd must always be running so sandboxed clients can reach the socket.
  systemctl enable jmxd.service || true
  if systemctl is-active --quiet jmxd.service; then
    systemctl restart jmxd.service || true
  else
    systemctl start jmxd.service || true
  fi

  # jmxcleanerd is a oneshot unit driven by the timer. Do not run it directly
  # here: on upgrade that could archive files in the active exam workspace.
  systemctl enable jmxcleanerd.timer || true
  if systemctl is-active --quiet jmxcleanerd.timer; then
    systemctl restart jmxcleanerd.timer || true
  else
    systemctl start jmxcleanerd.timer || true
  fi
fi
