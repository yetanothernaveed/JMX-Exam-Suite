# Building the JMX live ISO with Cubic

The live ISO is built from the stock Lubuntu ISO with Cubic. The only files the
ISO adds to the live system are:

- `/opt/jmx-setup/**` — setup script, branding, and Openbox config
- `/etc/systemd/system/jmx-setup.service` — first-boot provisioning unit, and
  its enablement symlink

## Why the live session must not run the setup unit

The live image boots with `boot=casper`. `jmx-setup.service` installs packages,
rewrites the desktop session list, and rebuilds branding for an *installed*
system. In the live session those changes are discarded, and because the unit
is pulled into the boot transaction, it holds back `graphical.target` while
`network-online.target` and `apt` run. SDDM never starts, so the screen goes
black with only a cursor after the splasher exits.

The unit therefore has:

```ini
ConditionKernelCommandLine=!boot=casper
```

Installed systems do not have `boot=casper` on the kernel command line, so the
unit still runs on the first boot after installation. `setup_script.sh` has the
same guard as a second line of defence.

## One-time fix in the Cubic project (chroot terminal)

Run inside the Cubic chroot. Replace the unit with the version from
`scripts/remote-pcs/jmx-setup.service`:

```bash
cat >/etc/systemd/system/jmx-setup.service <<'EOF'
[Unit]
Description=Provision JMX exam kiosk on first boot
Documentation=https://github.com/yetanothernaveed/JMX-Exam-Suite
ConditionKernelCommandLine=!boot=casper
ConditionPathExists=!/var/lib/jmx-setup/completed
Wants=network-online.target
After=network-online.target display-manager.service

[Service]
Type=oneshot
StateDirectory=jmx-setup
WorkingDirectory=/opt/jmx-setup
ExecStart=/bin/bash /opt/jmx-setup/setup_script.sh
ExecStartPost=/usr/bin/touch /var/lib/jmx-setup/completed
ExecStartPost=-/usr/bin/systemctl try-restart sddm.service
RemainAfterExit=yes

[Install]
WantedBy=graphical.target
EOF
```

Keep the copy under `/opt` in sync (some build notes copy it from there):

```bash
install -m 0644 /etc/systemd/system/jmx-setup.service \
  /opt/jmx-setup/jmx-setup.service
```

Move the enablement from `multi-user.target` (which blocks the display manager)
to `graphical.target` (starts alongside SDDM):

```bash
systemctl disable jmx-setup.service 2>/dev/null || true
rm -f /etc/systemd/system/multi-user.target.wants/jmx-setup.service
mkdir -p /etc/systemd/system/graphical.target.wants
ln -sfn /etc/systemd/system/jmx-setup.service \
  /etc/systemd/system/graphical.target.wants/jmx-setup.service
```

Update the script copy in the ISO as well. The only change is the guard at the
top of `scripts/remote-pcs/setup_script.sh`:

```bash
sed -i '/^SCRIPT_DIR=/a\
\
if grep -qw "boot=casper" /proc/cmdline 2>/dev/null; then\
    echo "Live ISO environment detected (boot=casper); skipping JMX setup."\
    exit 0\
fi' /opt/jmx-setup/setup_script.sh
```

Verify the result in the chroot:

```bash
grep -n 'ConditionKernelCommandLine' /etc/systemd/system/jmx-setup.service
ls -l /etc/systemd/system/graphical.target.wants/jmx-setup.service
test ! -e /etc/systemd/system/multi-user.target.wants/jmx-setup.service && echo "not blocking multi-user"
```

Then finish the Cubic wizard and rebuild the ISO.

## Quick check on an already-built ISO

Boot the existing ISO, and at the GRUB menu press `e` on "Try or Install
Lubuntu". Append this to the `linux` line and press `Ctrl+X`:

```
systemd.mask=jmx-setup.service
```

If the Lubuntu live desktop now appears, the diagnosis is confirmed. This
kernel argument is a one-off test only; the rebuilt ISO does not need it.

## Verifying the rebuilt ISO

1. Boot the ISO and choose "Try or Install Lubuntu". The normal Lubuntu live
   desktop must appear.
2. Confirm the live session skipped provisioning:

   ```bash
   systemctl status jmx-setup.service      # inactive (condition skipped)
   systemctl is-active sddm                # active
   ```

3. Install to a VM, boot the installed system, and confirm that provisioning
   runs there:

   ```bash
   systemctl status jmx-setup.service      # active (exited)
   grep boot /proc/cmdline                 # must NOT contain boot=casper
   ```

   If the boot appears to hang, switch to a TTY with `Ctrl+Alt+F3` and inspect
   `journalctl -b -u jmx-setup.service`.
