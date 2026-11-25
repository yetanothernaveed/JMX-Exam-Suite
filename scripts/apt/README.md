# APT publishing scripts

- `publish-apt-repo.sh` — rebuilds the signed APT repository in `JMX-APT`'s
  `gh-pages` branch from every `.deb` already in the pool plus the new builds.
  It publishes both `jmxremote` and `jmxsetup`.
- `templates/index.html` — default public Pages landing page.
- `templates/public-README.md` — README template for the `JMX-APT` `main`
  branch.

The old `systemd/jmxremote-update.*` units were replaced by the
`jmx-update.service` / `jmx-update.timer` units inside the `jmxsetup` package.
Installing `jmxsetup` disables and archives the legacy units on existing
machines.

See [`../../docs/RELEASING.md`](../../docs/RELEASING.md) for the full setup
and release procedure.

## Local dry run

```bash
export VERSION=26.11.4
export APT_REPO=yetanothernaveed/JMX-APT
export APT_GPG_PRIVATE_KEY="$(cat /path/to/jmx-apt-private.asc)"
export APT_GPG_PASSPHRASE='...'
export DRY_RUN=1

./scripts/apt/publish-apt-repo.sh
```

A dry run generates the repository and prints the commit, but does not push.
`DEB_DIR` defaults to `remote/dist`, which must contain both
`jmxremote_<version>_amd64.deb` and `jmxsetup_<version>_amd64.deb`.
