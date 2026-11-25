# Releasing JMX Remote

This document covers the private-source / public-APT release flow.

## Overview

A single tag push does everything:

```text
jmxremote-<codename>-v<version>
  -> build jmx, jmxd, jmxcleanerd
  -> package jmxremote .deb / .rpm / .tar.gz
  -> package jmxsetup .deb (provisioning assets + jmx-setup CLI)
  -> private GitHub Release
  -> signed APT repository pushed to JMX-APT/gh-pages
  -> mirrored public GitHub Release
```

`jmxremote` contains the exam client and daemon. `jmxsetup` contains the kiosk
provisioning script, branding assets, the daily update units, and the
`jmx-setup` administration CLI. Both packages are built from the same tag and
published together.

The source repository stays private. `JMX-APT` contains only generated
artifacts and is safe to keep public.

## One-time setup

### 1. Create the public repository

Create `yetanothernaveed/JMX-APT` as a public GitHub repository.

- Default branch: `main`
- Add a README. Copy `scripts/apt/templates/public-README.md` and replace
  `__APT_OWNER__` and `__APT_NAME__` with `yetanothernaveed` and `JMX-APT`.
- Create a `gh-pages` branch containing at least:
  - `.nojekyll`
  - `index.html` (copy `scripts/apt/templates/index.html` and replace
    `__APT_REPO__` and `__APT_PAGES_URL__`)

Enable GitHub Pages:

1. Repository Settings -> Pages
2. Source: **Deploy from a branch**
3. Branch: `gh-pages`, folder: `/(root)`

The usual URL is:

```text
https://yetanothernaveed.github.io/JMX-APT
```

The publish script can bootstrap the `gh-pages` branch if it is missing, but
Pages still has to be enabled once in the repository settings.

### 2. Create the APT signing key

Use a dedicated key, not a personal GPG key. Example:

```bash
gpg --full-generate-key
# RSA 4096, sign-only is sufficient
# UID: JMX APT Repository <apt@your-domain>
# Set a strong passphrase
```

Export the key material:

```bash
FPR=$(gpg --list-secret-keys --with-colons | awk -F: '/^fpr:/ {print $10; exit}')

gpg --armor --export-secret-keys "$FPR" > jmx-apt-private.asc
gpg --armor --export "$FPR"             > KEY.gpg
gpg --output revoke.asc --gen-revoke "$FPR"
```

Keep `jmx-apt-private.asc`, `revoke.asc`, and the passphrase backed up
offline.

### 3. Create the cross-repo token

Create a fine-grained personal access token:

- Repository access: only `yetanothernaveed/JMX-APT`
- Permissions: **Contents: Read and write**
- Expiration: one year (set a reminder to rotate it)

The default `GITHUB_TOKEN` in the private repository cannot write to another
repository, so this token is required.

### 4. Add repository secrets and variables

In the private `JMX-Exam-Suite` repository:

Secrets:

| Name | Value |
|---|---|
| `APT_REPO_TOKEN` | fine-grained PAT from step 3 |
| `APT_GPG_PRIVATE_KEY` | contents of `jmx-apt-private.asc` |
| `APT_GPG_PASSPHRASE` | signing key passphrase |

Variables:

| Name | Example |
|---|---|
| `APT_REPO` | `yetanothernaveed/JMX-APT` |
| `APT_PAGES_URL` | `https://yetanothernaveed.github.io/JMX-APT` |
| `APT_GPG_KEY_ID` | signing key fingerprint (optional; auto-detected) |

## Normal release

```bash
git tag jmxremote-austerealpaca-v26.11.4
git push origin jmxremote-austerealpaca-v26.11.4
```

The workflow `.github/workflows/release-remote.yml` runs automatically.

It publishes:

- private release assets in the source repository (`jmxremote` and
  `jmxsetup`)
- `dists/stable/...` and `pool/...` in `JMX-APT/gh-pages`
- a public release tagged `v<version>` in `JMX-APT`

The publish script refuses to update the repository unless both
`Package: jmxremote` and `Package: jmxsetup` are present in `Packages`.

The package version is the numeric part of the tag (`26.11.4`). The codename
is not part of the Debian version.

## Dry run

Use **Actions -> Release JMX Remote Component -> Run workflow**:

- enter a version
- leave `publish` unchecked

This builds and packages without pushing to `JMX-APT` or creating releases.

## Testing a published repository

```bash
APT_URL="https://yetanothernaveed.github.io/JMX-APT"

curl -fsSL "$APT_URL/dists/stable/InRelease" -o /tmp/InRelease
curl -fsSL "$APT_URL/KEY.gpg" | gpg --import
gpg --verify /tmp/InRelease
```

Install on a clean Ubuntu VM:

```bash
sudo install -d -m 0755 /etc/apt/keyrings
curl -fsSL "$APT_URL/KEY.gpg" | sudo gpg --dearmor --yes -o /etc/apt/keyrings/jmx.gpg
echo "deb [signed-by=/etc/apt/keyrings/jmx.gpg] $APT_URL stable main" |
  sudo tee /etc/apt/sources.list.d/jmx.list

sudo apt update
sudo apt install jmxremote jmxsetup

apt-cache policy jmxremote jmxsetup
systemctl status jmxd
systemctl list-timers jmxcleanerd.timer jmx-update.timer
jmx hello
```

Test the commands that write to the workspace (`jmx get`, `jmx submit`, etc.)
so the `jmxd.service` sandbox paths are exercised.

Verify the setup package and its CLI:

```bash
sudo jmx-setup status
sudo jmx-setup config show
sudo jmx-setup config validate
sudo jmx-setup auto-update status
```

`jmx-setup config set` changes `server_address`, `server_port`, or
`session_duration_in_hours` without restarting `jmxd`. A restart is avoided on
purpose: `jmxd.service` uses `RuntimeDirectory=jmx`, so restarting the daemon
would remove `/run/jmx`, including the active session marker.

## Updating clients

```bash
sudo apt update
sudo apt upgrade
```

Or only JMX:

```bash
sudo apt update
sudo apt install --only-upgrade jmxremote jmxsetup
```

Do not run unattended upgrades during an active exam. The `jmxsetup` package
installs `jmx-update.timer`, which runs once per day at 17:05 and skips both
the update and provisioning while
`/run/jmx/sessions/current_session.txt` exists, while
`/etc/jmx/jmx-setup-hold` exists, or on a live ISO.

```bash
sudo jmx-setup auto-update status
sudo jmx-setup auto-update disable
sudo jmx-setup auto-update enable
sudo jmx-setup hold
sudo jmx-setup unhold
```

The first `jmxsetup` install also disables and archives the legacy
`jmx-setup.service` and `jmxremote-update.*` units so only one update path
remains active.

### Provisioning on an existing machine

Package installation marks the packaged assets as pending and starts
`jmx-provision.service`. The wrapper compares a checksum of
`setup_script.sh`, `branding/**`, and `rc.xml`; an upgrade that does not
change those assets is a no-op.

```bash
sudo jmx-setup status
sudo jmx-setup run          # apply now, respecting the exam-session guard
sudo jmx-setup run --force  # ignore the exam-session guard
```

`jmx-setup config set` edits `/etc/jmxd/jmxd.conf` atomically, keeps a
timestamped backup in `/etc/jmxd/backups`, and mirrors the value into
`/etc/default/jmx-setup` so a forced re-provision does not undo it.

```bash
sudo jmx-setup config show
sudo jmx-setup config set server_address 10.0.0.10
sudo jmx-setup config set server_port 8080
sudo jmx-setup config set session_duration_in_hours 2
sudo jmx-setup config test
sudo jmx-setup config backups
sudo jmx-setup config restore latest
```

Only `server_address`, `server_port`, and `session_duration_in_hours` are
writable in phase 1. `socket_directory` and `workspace_directory` are
provisioning-managed because the socket path is compiled into `jmx`/`jmxd`
and the workspace path is shared with `jmxcleanerd` and the firejail launcher.

### Setup script options

`scripts/remote-pcs/setup_script.sh` supports these environment variables:

| Variable | Default | Purpose |
|---|---|---|
| `JMX_APT_URL` | `https://yetanothernaveed.github.io/JMX-APT` | APT repository base URL |
| `JMX_SERVER_ADDRESS` | `127.0.0.1` | `server_address` in `/etc/jmxd/jmxd.conf` |
| `JMX_SERVER_PORT` | `8080` | `server_port` in `/etc/jmxd/jmxd.conf` |
| `JMX_SESSION_DURATION_HOURS` | `2` | Session duration |
| `JMX_FORCE_CONFIG` | `0` | Set to `1` to rewrite an existing `/etc/jmxd/jmxd.conf` (backup kept) |
| `JMX_PRUNE_SESSIONS` | `1` | Remove non-exam desktop sessions from `/usr/share/xsessions` |
| `JMX_SETUP_FORCE` | `0` | Set to `1` to bypass the pending/asset checksum in the wrapper |
| `JMX_ALLOW_ACTIVE_SESSION` | `0` | Set to `1` to allow provisioning during an exam |

The script resolves branding and `rc.xml` relative to its own directory, so it
can be run from any working directory:

```bash
JMX_SERVER_ADDRESS=10.0.0.10 JMX_SERVER_PORT=8080 ./scripts/remote-pcs/setup_script.sh
```

Prefer the package and CLI on installed machines:

```bash
sudo jmx-setup config set server_address 10.0.0.10
sudo jmx-setup run
```

## Rollback

Old `.deb` files stay in the repository pool:

```bash
sudo apt install jmxremote=<previous-version> jmxsetup=<previous-version> --allow-downgrades
```

A downgrade restores the packaged files, but it does not automatically undo OS
changes that the provisioning script already applied. Use
`jmx-setup config restore <name>` for daemon configuration rollback, or
re-provision a specific version with `JMX_FORCE_CONFIG=1`.

To block updates during an exam:

```bash
sudo jmx-setup hold
# or
sudo apt-mark hold jmxremote jmxsetup
# later
sudo jmx-setup unhold
sudo apt-mark unhold jmxremote jmxsetup
```

## Key rotation

1. Generate a new signing key following step 2.
2. Update `APT_GPG_PRIVATE_KEY`, `APT_GPG_PASSPHRASE`, and `APT_GPG_KEY_ID`.
3. Publish a release so `KEY.gpg` in `gh-pages` contains the new key.
4. Re-run the client source-setup block on existing machines so they install
   the new public key.
5. Keep the old public key available until every client has been migrated.

Expiring or losing the signing key makes `apt update` fail on clients. Keep
the offline backup and revocation certificate safe.

## Troubleshooting

- **`apt update` says `NO_PUBKEY`**: the client has not installed the current
  `KEY.gpg`, or the key was rotated.
- **`404` on `InRelease`**: GitHub Pages is not enabled, the `gh-pages`
  branch is missing, or Pages has not finished deploying (usually 1-2 minutes).
- **Workflow fails cloning `JMX-APT`**: check `APT_REPO_TOKEN` scope and
  expiration, and confirm the repository/`gh-pages` branch exist.
- **`jmxd` fails immediately after install**: verify the `jmx` group exists
  and that `ReadWritePaths` in `jmxd.service` matches the configured
  `workspace_directory`. On an upgraded machine whose
  `/etc/jmxd/jmxd.conf` still points at an old path, either update the
  config or add a `jmxd.service.d/override.conf` with the matching
  `ReadWritePaths=` entry, then run `systemctl daemon-reload`.

  ```bash
  sudo systemctl edit jmxd.service
  # [Service]
  # ReadWritePaths=/old/workspace/path
  ```

- **`systemctl status jmxd` shows `status=226/NAMESPACE`**: the configured
  workspace directory does not exist or is not writable by the service
  sandbox. Create it, fix `workspace_directory`, and restart `jmxd`.
- **A package is not visible after a release**: re-run the workflow; the
  publish script rebuilds metadata from every `.deb` in the pool and is
  idempotent.
