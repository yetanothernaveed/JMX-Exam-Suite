# Cubic ISO generation for package-driven JMX kiosks

This document describes the complete, current procedure for building the JMX
exam-kiosk ISO with Cubic. It replaces the older procedure that installed
`/opt/jmx-setup/**` and `/etc/systemd/system/jmx-setup.service` into the ISO.

Read it from top to bottom. Every command is meant to be copied exactly as
written, after replacing the placeholders described below. Do not skip a step
because it looks optional.

## 1. What this ISO does and does not do

The new ISO contains **only** the `jmxsetup` APT package and its repository
configuration. The package supplies:

- `/usr/bin/jmx-setup` — the administrator CLI.
- `/usr/lib/jmx-setup/setup_script.sh` — the provisioning script.
- `/usr/lib/jmx-setup/run-provision.sh` — the guarded provisioning wrapper.
- `/usr/lib/jmx-setup/branding/**` and `/usr/lib/jmx-setup/rc.xml` — assets.
- `/etc/default/jmx-setup` — the first-install defaults conffile.
- `/lib/systemd/system/jmx-provision.service` — the first-boot trigger.
- `/lib/systemd/system/jmx-update.service` and `jmx-update.timer` — the daily
  17:05 update path.

The ISO does **not** contain, and you must not add:

- `/opt/jmx-setup/**`
- `/etc/systemd/system/jmx-setup.service`
- any enablement symlink for `jmx-setup.service`
- a manually created `/var/lib/jmx-setup/completed` marker

The old first-boot unit is obsolete. Leaving it in place can cause two
provisioning runs or an old copy of the script to shadow the packaged one.

The live ISO session never runs provisioning. Both `jmx-provision.service` and
`setup_script.sh` check for `boot=casper` on the kernel command line and exit
before doing any work. Provisioning runs once on the **first boot of the
installed system**, not while you are trying the live desktop.

## 2. Placeholders used in this document

Replace these before running any command:

| Placeholder | Meaning | Example |
|---|---|---|
| `<PROJECT_DIR>` | Empty directory for the Cubic project | `/home/admin/cubic-jmx` |
| `<SOURCE_ISO>` | Full path to the stock Lubuntu amd64 ISO | `/home/admin/Downloads/lubuntu-24.04-desktop-amd64.iso` |
| `<OUTPUT_DIR>` | Directory for the generated ISO | `/home/admin/iso-output` |
| `<OUTPUT_ISO>` | Filename of the generated ISO | `jmx-kiosk-2026-11-25.iso` |

Create the directories first:

```bash
mkdir -p <PROJECT_DIR> <OUTPUT_DIR>
```

## 3. Prerequisites

### 3.1 Host machine

You need a Linux machine with:

- root access through `sudo`;
- at least 10 GB of free disk space;
- a working internet connection;
- at least 4 GB RAM, 8 GB recommended;
- `curl`, `gpg`, and `wget` available.

Install the basic tools if missing:

```bash
sudo apt-get update
sudo apt-get install -y curl wget gnupg ca-certificates
```

### 3.2 Source ISO

Use the same stock **Lubuntu desktop amd64** ISO you have been using with
Cubic. If you need a fresh copy, download it from:

```text
https://lubuntu.me/downloads/
```

You must use an `amd64` image. The JMX APT repository is published as
`amd64` only. An `i386`, `arm64`, or `armhf` source ISO will not install
`jmxsetup`.

Verify that the filename contains `amd64`, for example:

```text
lubuntu-24.04-desktop-amd64.iso
```

If you downloaded a checksum file, verify the ISO before using it:

```bash
cd "$(dirname <SOURCE_ISO>)"
sha256sum "$(basename <SOURCE_ISO>)"
```

Compare the printed hash with the hash published next to the download. Do not
continue if they differ.

### 3.3 Architecture check on the host

Confirm the host is amd64:

```bash
dpkg --print-architecture
```

Expected output:

```text
amd64
```

## 4. Install Cubic

Cubic is normally installed from its release PPA:

```bash
sudo add-apt-repository -y ppa:cubic-wizard/release
sudo apt-get update
sudo apt-get install -y cubic
```

If the PPA is unavailable for your Ubuntu release, download the `.deb` package
from the Cubic project page and install it with:

```bash
sudo apt-get install -y ./cubic_*.deb
```

Verify the installation:

```bash
cubic --version
```

Any version output is fine; the commands in this document do not depend on a
specific Cubic release.

## 5. Create the Cubic project

1. Launch Cubic as root:

   ```bash
   sudo cubic
   ```

   Alternatively, launch it from the application menu. Cubic will request root
   privileges itself.

2. In the first page, select **New Project**.

3. For **Project Directory**, enter `<PROJECT_DIR>`.

4. For **Original ISO**, select `<SOURCE_ISO>`.

5. Click **Next**.

6. Cubic extracts the ISO. Wait until the chroot terminal opens. This can take
   several minutes. Do not close the window.

From this point onward, all commands in section 6 are typed into the **Cubic
chroot terminal**, not into your normal host terminal.

The chroot shell is already running as root. Do **not** prefix the commands
with `sudo`. If you type `sudo` and it is not installed, the command will fail.

## 6. Configure the chroot

### 6.1 Confirm the chroot architecture

Run:

```bash
dpkg --print-architecture
```

Expected output:

```text
amd64
```

If it is not `amd64`, stop. The JMX packages will not install. Delete the
project and start again with the correct source ISO.

### 6.2 Confirm network and DNS

Run:

```bash
getent hosts yetanothernaveed.github.io
curl -fsSI https://yetanothernaveed.github.io/JMX-APT/KEY.gpg | head -n 1
```

The first command must print an IP address. The second must print an HTTP
status line such as:

```text
HTTP/2 200
```

If `getent` fails, Cubic did not copy working DNS settings into the chroot. In
Cubic's project options, enable copying the host's network/resolv configuration
into the chroot, then restart the project.

If `curl` reports a certificate error, install the CA certificates in the
chroot:

```bash
apt-get update
apt-get install -y ca-certificates
```

Then repeat the check.

### 6.3 Install the JMX APT signing key

Create the keyring directory:

```bash
install -d -m 0755 /etc/apt/keyrings
```

Download and dearmor the key:

```bash
curl -fsSL --retry 5 --retry-delay 5 \
  https://yetanothernaveed.github.io/JMX-APT/KEY.gpg |
  gpg --dearmor --yes -o /etc/apt/keyrings/jmx.gpg
```

Set the permissions explicitly:

```bash
chmod 0644 /etc/apt/keyrings/jmx.gpg
```

Verify that the file is not empty:

```bash
test -s /etc/apt/keyrings/jmx.gpg && echo key-ok
```

Expected output:

```text
key-ok
```

### 6.4 Add the JMX APT repository

Write the source list exactly as shown:

```bash
cat >/etc/apt/sources.list.d/jmx.list <<'EOF'
deb [signed-by=/etc/apt/keyrings/jmx.gpg] https://yetanothernaveed.github.io/JMX-APT stable main
EOF
```

Set permissions:

```bash
chmod 0644 /etc/apt/sources.list.d/jmx.list
```

Verify the contents:

```bash
cat /etc/apt/sources.list.d/jmx.list
```

Expected output:

```text
deb [signed-by=/etc/apt/keyrings/jmx.gpg] https://yetanothernaveed.github.io/JMX-APT stable main
```

There is intentionally no `arch=amd64` filter in this line. If an installed
machine has i386 enabled, `apt update` prints a harmless warning about the
i386 `Packages` index. Do not "fix" it here by changing the line; it is not a
failure and it does not block installation.

### 6.5 Refresh APT metadata

Run:

```bash
DEBIAN_FRONTEND=noninteractive apt-get update
```

You may see JMX-related lines such as:

```text
Hit:1 https://yetanothernaveed.github.io/JMX-APT stable InRelease
```

You may also see an `i386` "Skipping acquire" warning. That is expected. The
command must still finish successfully.

### 6.6 Confirm that the package is visible

Run:

```bash
apt-cache policy jmxsetup
```

Expected output includes a candidate version, for example:

```text
jmxsetup:
  Installed: (none)
  Candidate: 26.11.5
```

If `Candidate:` is `(none)`, stop and check:

1. the source list from 6.4;
2. the key from 6.3;
3. that `apt-get update` in 6.5 completed without errors;
4. that you selected an amd64 source ISO in section 5.

Do not continue until `jmxsetup` has a candidate version.

### 6.7 Install `jmxsetup`

Run:

```bash
DEBIAN_FRONTEND=noninteractive NEEDRESTART_SUSPEND=1 \
  apt-get install -y jmxsetup
```

APT may install additional dependencies such as `curl`, `gnupg`, `psmisc`, and
`apt`. Allow this.

The package's `postinstall` script will run inside the chroot. Because there is
no running systemd instance in the chroot, it will **not** start provisioning.
It will instead:

- create `/var/lib/jmx-setup/pending`;
- enable `jmx-provision.service` by writing
  `/etc/systemd/system/graphical.target.wants/jmx-provision.service`;
- enable `jmx-update.timer` by writing
  `/etc/systemd/system/timers.target.wants/jmx-update.timer`;
- initialize `/etc/default/jmx-setup`.

Do not run `jmx-setup run` here. Do not create
`/var/lib/jmx-setup/completed`. Do not run
`/usr/lib/jmx-setup/setup_script.sh` here.

If you want a custom `server_address`, `server_port`, or
`session_duration_in_hours`, configure them later on the installed machine
with `jmx-setup config set`. Do not edit `/etc/jmxd/jmxd.conf` inside Cubic;
that file is generated on first boot.

### 6.8 Verify the installed package

Run:

```bash
dpkg-query -W -f='${Package} ${Version} ${Status}\n' jmxsetup
```

Expected output resembles:

```text
jmxsetup 26.11.5 install ok installed
```

The version may be newer. That is fine.

Check the packaged files:

```bash
ls -l /usr/bin/jmx-setup \
      /usr/lib/jmx-setup/run-provision.sh \
      /usr/lib/jmx-setup/setup_script.sh \
      /usr/lib/jmx-setup/rc.xml \
      /usr/lib/jmx-setup/branding/branding.sh
```

All paths must exist. `jmx-setup`, `run-provision.sh`, and `setup_script.sh`
must be executable.

### 6.9 Remove the legacy ISO provisioning assets

These commands remove the old first-boot unit and the old `/opt` copy of the
script. They are required even if you believe the files are not present.

```bash
systemctl disable jmx-setup.service 2>/dev/null || true
rm -f /etc/systemd/system/jmx-setup.service
rm -f /etc/systemd/system/graphical.target.wants/jmx-setup.service
rm -f /etc/systemd/system/multi-user.target.wants/jmx-setup.service
rm -rf /opt/jmx-setup
systemctl daemon-reload 2>/dev/null || true
```

Why this is safe:

- The package's provisioning script lives in `/usr/lib/jmx-setup`, not `/opt`.
- The package's first-boot trigger is `jmx-provision.service`, not
  `jmx-setup.service`.
- The package's `postinstall` also archives legacy units into
  `/var/lib/jmx-setup/legacy`, but removing them explicitly in Cubic prevents
  any chance of an old unit being generated into the final ISO.

### 6.10 Verify the boot trigger and pending marker

Run:

```bash
systemctl is-enabled jmx-provision.service
systemctl is-enabled jmx-update.timer
test -f /var/lib/jmx-setup/pending && echo pending-present
```

Expected output:

```text
enabled
enabled
pending-present
```

If `jmx-provision.service` is not enabled, enable it manually:

```bash
systemctl enable jmx-provision.service
systemctl is-enabled jmx-provision.service
```

If `jmx-update.timer` is not enabled, enable it manually:

```bash
systemctl enable jmx-update.timer
systemctl is-enabled jmx-update.timer
```

If the pending marker is missing, create it:

```bash
: >/var/lib/jmx-setup/pending
chmod 0644 /var/lib/jmx-setup/pending
```

Do not create `applied-assets.sha256` or `applied-version`. Those files must be
created by the first successful provisioning run on the installed system.

### 6.11 Confirm legacy files are gone

Run:

```bash
test ! -e /etc/systemd/system/jmx-setup.service && echo legacy-unit-removed
test ! -e /etc/systemd/system/graphical.target.wants/jmx-setup.service && echo legacy-link-removed
test ! -e /opt/jmx-setup && echo legacy-opt-removed
```

Expected output:

```text
legacy-unit-removed
legacy-link-removed
legacy-opt-removed
```

### 6.12 Leave the chroot

Type:

```bash
exit
```

This closes the chroot terminal and returns to the Cubic wizard.

## 7. Finish the Cubic wizard

Continue through the remaining Cubic pages:

1. **Packages page:** Cubic refreshes its package list. Allow it. Do not remove
   `jmxsetup`, `jmxremote`, `curl`, `gnupg`, or `apt` from the detected package
   list.
2. **Options page:** Keep your existing kernel, compression, and bootloader
   settings. Do not add `systemd.mask=jmx-setup.service` to the production ISO;
   that is only a diagnostic trick for the old black-screen problem.
3. **Generate page:**
   - set the output directory to `<OUTPUT_DIR>`;
   - set the ISO filename to `<OUTPUT_ISO>`;
   - click **Generate**;
   - wait for Cubic to finish. This can take several minutes.

When it finishes, Cubic reports the generated ISO path.

## 8. Verify the generated ISO file

On the host terminal, run:

```bash
ls -lh <OUTPUT_DIR>/<OUTPUT_ISO>
sha256sum <OUTPUT_DIR>/<OUTPUT_ISO>
```

Record the SHA-256 hash. Use it when distributing the ISO so machines can be
verified before use.

## 9. Test the live ISO in a virtual machine

Before writing the ISO to USB sticks or deploying it, boot it in a VM.

Suggested VM settings:

- 2 vCPUs;
- 4 GB RAM;
- 32 GB virtual disk;
- network adapter connected to a NAT or bridged network with internet access;
- attach `<OUTPUT_DIR>/<OUTPUT_ISO>` as the optical disk.

Boot the VM and select **Try or Install Lubuntu**. The normal live desktop must
appear. A black screen with only a cursor means something is still wrong.

Open a terminal in the live session and run:

```bash
grep -qw 'boot=casper' /proc/cmdline && echo live-iso-confirmed
systemctl status jmx-provision.service --no-pager
systemctl is-active sddm
```

Expected:

- `live-iso-confirmed` is printed;
- `jmx-provision.service` is inactive/skipped because of the `boot=casper`
  condition;
- `sddm` is active.

Also confirm the old unit is not present:

```bash
test ! -e /etc/systemd/system/jmx-setup.service && echo legacy-unit-absent
test ! -e /opt/jmx-setup && echo legacy-opt-absent
```

Do not run provisioning in the live session.

## 10. Test installation and first boot

Still in the VM, run the Lubuntu installer and install the system to the
virtual disk, exactly as you would for a normal deployment. Accept the default
partitioning unless your site has a different standard.

When the installer finishes, reboot into the installed system. Remove or
disconnect the ISO after reboot so the machine boots from disk.

The first boot will take longer than usual. `jmx-provision.service` is waiting
for the network and apt locks, then installing `jmxremote` and applying the
kiosk configuration. Do not power off the machine.

## 11. Verify the installed system

Log in and open a terminal. Run the following checks.

### 11.1 Package versions

```bash
dpkg-query -W -f='${Package} ${Version} ${Status}\n' jmxsetup jmxremote
```

Both packages must show `install ok installed`.

### 11.2 Provisioning service

```bash
systemctl status jmx-provision.service --no-pager
systemctl is-enabled jmx-provision.service
jmx-setup status
```

Expected:

- `jmx-provision.service` is `active (exited)`;
- it is enabled;
- `jmx-setup status` shows no pending provisioning.

If status reports a reboot recommendation, that is expected when apt required
one. The package never reboots automatically. Reboot at a convenient time.

### 11.3 Daily update timer

```bash
systemctl is-enabled jmx-update.timer
systemctl list-timers jmx-update.timer --no-pager
```

Expected: `enabled`, with the next run at 17:05 local time.

### 11.4 Pending and applied state

```bash
test ! -e /var/lib/jmx-setup/pending && echo no-pending
test -f /var/lib/jmx-setup/applied-assets.sha256 && echo assets-applied
cat /var/lib/jmx-setup/last-result
```

Expected:

```text
no-pending
assets-applied
success <timestamp>
```

`last-result` may instead say `unchanged <timestamp>` if the package assets
already matched a previous run. That is also a valid success state.

### 11.5 Configuration

```bash
sudo jmx-setup config show
sudo jmx-setup config validate
```

`config validate` must report that the configuration is valid.

The default phase-1 values are:

```text
server_address = 127.0.0.1
server_port = 8080
session_duration_in_hours = 2
```

To change them on a deployed machine, use the CLI. For example:

```bash
sudo jmx-setup config set server_address 10.0.0.10
sudo jmx-setup config set server_port 8080
sudo jmx-setup config set session_duration_in_hours 2
sudo jmx-setup config test
```

Do not edit `/etc/jmxd/jmxd.conf` directly; the CLI validates values, writes
atomically, and keeps backups.

### 11.6 Legacy files

```bash
test ! -e /etc/systemd/system/jmx-setup.service && echo legacy-unit-absent
test ! -e /opt/jmx-setup && echo legacy-opt-absent
test ! -e /etc/systemd/system/multi-user.target.wants/jmxremote-update.timer && echo legacy-timer-absent
```

All three `absent` messages must be printed.

### 11.7 Live session was skipped

On the installed system, `/proc/cmdline` must not contain `boot=casper`:

```bash
grep -qw 'boot=casper' /proc/cmdline || echo installed-system-confirmed
```

Expected:

```text
installed-system-confirmed
```

## 12. Troubleshooting

### 12.1 `jmxsetup` has no candidate version

In the chroot:

```bash
cat /etc/apt/sources.list.d/jmx.list
apt-cache policy jmxsetup
DEBIAN_FRONTEND=noninteractive apt-get update
```

The source line must be exactly the one from section 6.4. The key must be the
one from section 6.3.

### 12.2 `apt-get update` prints an i386 warning

This is expected and harmless:

```text
Skipping acquire of configured file 'main/binary-i386/Packages' ...
```

Do not change the source line in the ISO workflow. Installation and updates
still work on amd64 machines.

### 12.3 The live ISO still shows a black screen

Boot the live ISO, press `e` at the GRUB menu, append this to the `linux` line,
and press `Ctrl+X`:

```text
systemd.mask=jmx-setup.service
```

If the desktop now appears, an old `jmx-setup.service` is still present in the
ISO. Go back to section 6.9 and remove it, then regenerate the ISO.

If masking does not help, the problem is unrelated to JMX provisioning. Check
the display manager and graphics drivers for the base Lubuntu ISO.

### 12.4 Provisioning did not run on first boot

On the installed machine:

```bash
systemctl status jmx-provision.service --no-pager
cat /var/lib/jmx-setup/last-result 2>/dev/null || true
cat /var/lib/jmx-setup/fail-count 2>/dev/null || true
journalctl -b -u jmx-provision.service --no-pager
```

Common causes:

- `/var/lib/jmx-setup/pending` was removed before boot;
- `/etc/jmx/jmx-setup-hold` exists — remove it with `sudo jmx-setup unhold`;
- `/run/jmx/sessions/current_session.txt` existed during boot — wait until the
  exam ends or run `sudo jmx-setup run --force` as an administrator;
- the network was unavailable, so `apt-get install jmxremote` failed;
- `jmx-provision.service` was disabled — re-enable it with
  `sudo systemctl enable jmx-provision.service`.

After fixing the cause, run:

```bash
sudo jmx-setup run
```

### 12.5 `jmx-setup run` says "nothing pending"

Force a run:

```bash
sudo jmx-setup run --force
```

This bypasses the pending/hash check. It still respects the live-ISO and hold
file guards. It bypasses the exam-session guard only when `--force` is used.

### 12.6 Provisioning failed and left a pending marker

`run-provision.sh` keeps `/var/lib/jmx-setup/pending` after a failure and
increments `/var/lib/jmx-setup/fail-count`. Inspect:

```bash
cat /var/lib/jmx-setup/last-result
cat /var/lib/jmx-setup/fail-count
journalctl -u jmx-provision.service --no-pager
```

Fix the underlying problem, then:

```bash
sudo jmx-setup run
```

### 12.7 A reboot is recommended

Check:

```bash
test -f /var/lib/jmx-setup/reboot-recommended && echo reboot-recommended
```

The package never reboots automatically. Schedule a reboot at a convenient
time.

## 13. Rebuilding the ISO for a new release

When a new `jmxsetup` version is published:

1. Open the existing Cubic project.
2. Enter the chroot again.
3. Run:

   ```bash
   DEBIAN_FRONTEND=noninteractive apt-get update
   DEBIAN_FRONTEND=noninteractive NEEDRESTART_SUSPEND=1 \
     apt-get install --only-upgrade -y jmxsetup
   ```

4. Re-run the verification in sections 6.8 through 6.11.
5. Exit the chroot.
6. Generate a new ISO with a new `<OUTPUT_ISO>` name.
7. Verify it with section 8 and smoke-test it with sections 9 through 11.

Already-deployed machines do not need a new ISO. They receive the new package
through the daily 17:05 `jmx-update.timer`.

## 14. Final checklist

Before shipping an ISO, confirm every item:

- [ ] Source ISO was amd64.
- [ ] `jmxsetup` was installed inside the Cubic chroot.
- [ ] `/etc/apt/keyrings/jmx.gpg` exists and is non-empty.
- [ ] `/etc/apt/sources.list.d/jmx.list` contains the exact line from 6.4.
- [ ] `jmx-provision.service` is enabled.
- [ ] `jmx-update.timer` is enabled.
- [ ] `/var/lib/jmx-setup/pending` exists in the chroot.
- [ ] `/var/lib/jmx-setup/applied-assets.sha256` does **not** exist in the chroot.
- [ ] `/opt/jmx-setup` does not exist.
- [ ] `/etc/systemd/system/jmx-setup.service` does not exist.
- [ ] No `jmx-setup.service` symlink exists in `graphical.target.wants` or
      `multi-user.target.wants`.
- [ ] The generated ISO boots to the live desktop without a black screen.
- [ ] A test installation runs `jmx-provision.service` exactly once.
- [ ] `jmx-setup status` reports no pending provisioning after first boot.
- [ ] `jmx-update.timer` is enabled in the installed system.
- [ ] The ISO SHA-256 hash has been recorded.
