# jmxsetup package

`jmxsetup` packages the kiosk provisioning assets and the `jmx-setup`
administration CLI. It is published from the same release tag as `jmxremote`.

## Layout

| Path | Purpose |
|---|---|
| `/usr/bin/jmx-setup` | administration CLI |
| `/usr/lib/jmx-setup/setup_script.sh` | provisioning script |
| `/usr/lib/jmx-setup/branding/**` | branding assets |
| `/usr/lib/jmx-setup/rc.xml` | Openbox configuration |
| `/usr/lib/jmx-setup/run-provision.sh` | guarded provisioning wrapper |
| `/etc/default/jmx-setup` | provisioning defaults (dpkg conffile) |
| `/lib/systemd/system/jmx-provision.service` | apply pending provisioning |
| `/lib/systemd/system/jmx-update.service` | daily apt update |
| `/lib/systemd/system/jmx-update.timer` | daily timer at 17:05 |
| `/var/lib/jmx-setup/` | pending marker, applied hash/version, failures |

There is no periodic provisioning retry timer. Provisioning is triggered by:

- the package `postinst` after an install/upgrade;
- `jmx-update.service` after the daily apt run;
- `sudo jmx-setup run`.

## Guards

A run is skipped when any of these is true:

- `/run/jmx/sessions/current_session.txt` exists (exam in progress);
- `/etc/jmx/jmx-setup-hold` exists;
- `/proc/cmdline` contains `boot=casper` (live ISO).

`jmx-setup run --force` and `jmx-setup update --force` bypass the exam-session
guard, but not the hold file or the live-ISO guard.

## Asset checksum

`run-provision.sh` hashes `setup_script.sh`, `branding/**`, and `rc.xml`. The
hash is stored in `/var/lib/jmx-setup/applied-assets.sha256`. A package
upgrade that does not change those assets clears the pending marker without
re-running provisioning. `/etc/default/jmx-setup` is deliberately not part of
the hash: changing a daemon value should not trigger a full setup run.

## Configuration CLI

Writable keys in phase 1:

- `server_address` — IPv4 literal (`jmxd` uses `inet_pton(AF_INET)`)
- `server_port` — 1–65535
- `session_duration_in_hours` — 1–168

`socket_directory` and `workspace_directory` are read-only because the socket
path is compiled into `jmx`/`jmxd` and the workspace path is shared with
`jmxcleanerd` and the generated firejail launcher.

```bash
sudo jmx-setup config show
sudo jmx-setup config get server_address
sudo jmx-setup config set server_address 10.0.0.10
sudo jmx-setup config unset server_port
sudo jmx-setup config validate
sudo jmx-setup config test
sudo jmx-setup config backups
sudo jmx-setup config restore latest
sudo jmx-setup config reset --yes
sudo jmx-setup config sync-defaults
```

Writes are atomic, keep the existing ordering/comments, preserve `root:root`
and mode `0644`, and store up to ten timestamped backups in
`/etc/jmxd/backups`. Values are mirrored into `/etc/default/jmx-setup` so a
forced re-provision does not revert them. No `jmxd` restart is required:
`remote/src/utils/connectToServer.hpp` loads the daemon settings on every
connection.

## Building locally

From the repository root (`nfpm` resolves `src` paths against the current
working directory):

```bash
VERSION=26.11.4 nfpm package --config scripts/remote-pcs/packaging/nfpm.yaml \
  --target remote/dist/jmxsetup_26.11.4_amd64.deb
```

Run the CLI regression tests before packaging:

```bash
bash scripts/remote-pcs/packaging/tests/test-jmx-setup.sh
```

The release workflow runs the tests, builds this package automatically, and
publishes it to the same signed APT repository as `jmxremote`.
