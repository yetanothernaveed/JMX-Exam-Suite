# Building the JMX live ISO with Cubic

The current ISO is **package-driven**. The complete, minute-by-minute procedure
is in [`cubic_iso_generation.md`](cubic_iso_generation.md). Start there; this
page is only an overview.

## What the ISO contains

The ISO adds the following to the stock Lubuntu live system:

- `/etc/apt/keyrings/jmx.gpg` — the JMX APT repository signing key;
- `/etc/apt/sources.list.d/jmx.list` — the JMX APT source;
- the `jmxsetup` package, installed inside the Cubic chroot.

The package supplies the provisioning script, branding assets, `rc.xml`, the
`jmx-setup` CLI, the first-boot trigger, and the daily update timer. The old
`/opt/jmx-setup/**` tree and `/etc/systemd/system/jmx-setup.service` are **not**
part of the ISO anymore.

## Why the live session must not run provisioning

The live image boots with `boot=casper`. Provisioning installs packages,
rewrites the desktop session list, and rebuilds branding for an *installed*
system. In the live session those changes are discarded, and if provisioning
is pulled into the boot transaction it can hold back `graphical.target` while
`network-online.target` and `apt` run. The result is a black screen with only a
cursor after the splasher exits.

Both `jmx-provision.service` and `setup_script.sh` check:

```bash
grep -qw 'boot=casper' /proc/cmdline
```

and exit before doing any work. Installed systems do not have `boot=casper`, so
provisioning runs there.

## What happens on first boot after installation

The `jmxsetup` post-install script runs inside the Cubic chroot where systemd
is not running. It therefore creates the pending marker and enables the units,
but does not provision the chroot.

On the first boot of the installed system:

1. `graphical.target` pulls in `jmx-provision.service`.
2. The unit waits for `network-online.target` and `display-manager.service`.
3. `run-provision.sh` checks the hold file, active exam session, live-ISO
   condition, and apt locks.
4. The packaged `setup_script.sh` installs `jmxremote` and applies the kiosk
   configuration.
5. The applied asset hash is written and the pending marker is removed.

Later boots skip the service because the pending marker is gone. Daily updates
are handled by `jmx-update.timer` at 17:05.

## Quick checks

Live ISO:

```bash
grep -qw 'boot=casper' /proc/cmdline && echo live-iso-confirmed
systemctl status jmx-provision.service --no-pager
systemctl is-active sddm
```

Installed system after first boot:

```bash
jmx-setup status
systemctl status jmx-provision.service --no-pager
systemctl is-enabled jmx-update.timer
dpkg-query -W -f='${Package} ${Version} ${Status}\n' jmxsetup jmxremote
```

See [`cubic_iso_generation.md`](cubic_iso_generation.md) for the full chroot
commands, verification steps, troubleshooting, and release-rebuild procedure.
