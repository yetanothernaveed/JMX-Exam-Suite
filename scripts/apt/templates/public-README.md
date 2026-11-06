# JMX-APT

Public APT repository and release mirror for the JMX remote CLI and daemon
(`jmx`, `jmxd`, `jmxcleanerd`).

The source repository is private. This repository is generated automatically
by the release workflow from the private JMX source repository.

## Install

```bash
sudo install -d -m 0755 /etc/apt/keyrings
curl -fsSL https://yetanothernaveed.github.io/JMX-APT/KEY.gpg \
  | sudo gpg --dearmor --yes -o /etc/apt/keyrings/jmx.gpg

echo "deb [signed-by=/etc/apt/keyrings/jmx.gpg] https://yetanothernaveed.github.io/JMX-APT stable main" \
  | sudo tee /etc/apt/sources.list.d/jmx.list

sudo apt update
sudo apt install jmxremote
```

## Update

```bash
sudo apt update
sudo apt upgrade
```

Or only JMX:

```bash
sudo apt update
sudo apt install --only-upgrade jmxremote
```

## Rollback

```bash
sudo apt install jmxremote=<version> --allow-downgrades
```

## Repository layout

- `gh-pages` branch: signed APT repository served by GitHub Pages.
- GitHub Releases: mirrored `.deb`, `.rpm`, `.tar.gz`, and `SHA256SUMS`.

## Notes

- Packages are currently built for `amd64`.
- Do not run unattended JMX upgrades during an active exam session.
- Install instructions and key verification are also available on the Pages
  site.
