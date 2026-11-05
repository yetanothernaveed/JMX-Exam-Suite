#!/usr/bin/env bash
#
# Publish the current JMX .deb into the public JMX-APT repository.
#
# Required environment:
#   VERSION                 package version, e.g. 26.11.4
#   APT_REPO                public repo slug, e.g. yetanothernaveed/JMX-APT
#   APT_REPO_TOKEN          token with Contents: read/write on APT_REPO
#   APT_GPG_PRIVATE_KEY     ASCII-armored private signing key
#   APT_GPG_PASSPHRASE      signing key passphrase (optional if key has none)
#   APT_GPG_KEY_ID          signing key fingerprint (optional; auto-detected)
#
# Optional environment:
#   APT_PAGES_URL           https://<owner>.github.io/<repo>
#   APT_REPO_URL            override clone URL (for a mirror or local testing)
#   DEB_DIR                 directory containing the new .deb (default: remote/dist)
#   DRY_RUN=1               generate everything but do not commit/push
#
# The script is idempotent: every run rebuilds the repository metadata from
# the .deb files already present in gh-pages plus the new .deb.

set -euo pipefail
export GIT_TERMINAL_PROMPT=0

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

log() { printf '[publish-apt] %s\n' "$*"; }
die() { printf '[publish-apt] ERROR: %s\n' "$*" >&2; exit 1; }

VERSION="${VERSION:-}"
[ -n "$VERSION" ] || die "VERSION is required"
APT_REPO="${APT_REPO:-}"
[ -n "$APT_REPO" ] || die "APT_REPO is required (for example owner/JMX-APT)"

APT_OWNER="${APT_REPO%%/*}"
APT_NAME="${APT_REPO##*/}"
APT_PAGES_URL="${APT_PAGES_URL:-https://${APT_OWNER}.github.io/${APT_NAME}}"
APT_PAGES_URL="${APT_PAGES_URL%/}"
DEB_DIR="${DEB_DIR:-$REPO_ROOT/remote/dist}"
DRY_RUN="${DRY_RUN:-0}"

[ -n "${APT_GPG_PRIVATE_KEY:-}" ] || die "APT_GPG_PRIVATE_KEY is required"
[ -d "$DEB_DIR" ] || die "DEB_DIR does not exist: $DEB_DIR"
APT_GPG_KEY_ID="${APT_GPG_KEY_ID:-}"

if [ "$DRY_RUN" != "1" ] && [ -z "${APT_REPO_TOKEN:-}" ] && [ -z "${APT_REPO_URL:-}" ]; then
  die "APT_REPO_TOKEN is required unless APT_REPO_URL or DRY_RUN=1 is set"
fi

for cmd in aptly gpg git; do
  command -v "$cmd" >/dev/null 2>&1 || die "missing required command: $cmd"
done

WORKDIR="$(mktemp -d)"
trap 'rm -rf "$WORKDIR"' EXIT

export HOME="$WORKDIR/home"
export GNUPGHOME="$WORKDIR/gnupg"
mkdir -p "$HOME" "$GNUPGHOME" "$WORKDIR/stage"
chmod 700 "$GNUPGHOME"

log "importing signing key"
printf '%s\n' "$APT_GPG_PRIVATE_KEY" | gpg --batch --import >/dev/null 2>&1

if [ -z "$APT_GPG_KEY_ID" ]; then
  APT_GPG_KEY_ID="$(gpg --list-secret-keys --with-colons | awk -F: '/^fpr:/ {print $10; exit}')"
fi
[ -n "$APT_GPG_KEY_ID" ] || die "could not determine signing key fingerprint"

if [ -n "${APT_REPO_URL:-}" ]; then
  CLONE_URL="$APT_REPO_URL"
elif [ -n "${APT_REPO_TOKEN:-}" ]; then
  CLONE_URL="https://x-access-token:${APT_REPO_TOKEN}@github.com/${APT_REPO}.git"
else
  CLONE_URL="https://github.com/${APT_REPO}.git"
fi

REPO_CLONE="$WORKDIR/repo"

if git ls-remote --exit-code --heads "$CLONE_URL" refs/heads/gh-pages >/dev/null 2>&1; then
  log "cloning existing gh-pages branch"
  git clone --quiet --branch gh-pages --single-branch "$CLONE_URL" "$REPO_CLONE"
else
  log "gh-pages branch not found; bootstrapping it"
  rm -rf "$REPO_CLONE"
  if git ls-remote --exit-code "$CLONE_URL" >/dev/null 2>&1; then
    git clone --quiet "$CLONE_URL" "$REPO_CLONE"
  else
    # Empty repository, or a repository with no commits yet.
    mkdir -p "$REPO_CLONE"
    git -C "$REPO_CLONE" init --quiet
    git -C "$REPO_CLONE" remote add origin "$CLONE_URL"
  fi
  (
    cd "$REPO_CLONE"
    git checkout --orphan gh-pages
    git rm -rf . >/dev/null 2>&1 || true
    find . -mindepth 1 -maxdepth 1 ! -name .git -exec rm -rf {} +
  )
fi

# Collect every historical .deb from gh-pages, then overlay the new build.
if [ -d "$REPO_CLONE/pool" ]; then
  while IFS= read -r -d '' deb; do
    cp -f "$deb" "$WORKDIR/stage/"
  done < <(find "$REPO_CLONE/pool" -type f -name '*.deb' -print0)
fi

shopt -s nullglob
new_debs=("$DEB_DIR"/*.deb)
shopt -u nullglob
[ "${#new_debs[@]}" -gt 0 ] || die "no .deb files found in $DEB_DIR"
for deb in "${new_debs[@]}"; do
  cp -f "$deb" "$WORKDIR/stage/"
done

log "generating APT repository metadata with aptly"
aptly repo create -distribution=stable -component=main jmx >/dev/null
aptly repo add -force-replace jmx "$WORKDIR/stage"/*.deb >/dev/null

publish_args=(
  publish repo
  -batch
  -distribution=stable
  -component=main
  -origin=JMX
  -label=JMX
  -architectures=amd64
  -skip-contents
)
if [ -n "${APT_GPG_PASSPHRASE:-}" ]; then
  publish_args+=(-passphrase="$APT_GPG_PASSPHRASE")
fi
aptly "${publish_args[@]}" jmx

PUBLIC_DIR="$HOME/.aptly/public"
[ -f "$PUBLIC_DIR/dists/stable/InRelease" ] || die "aptly did not create InRelease"
gpg --verify "$PUBLIC_DIR/dists/stable/InRelease" >/dev/null 2>&1 ||
  die "generated InRelease signature could not be verified"
grep -q '^Package: jmxremote$' "$PUBLIC_DIR/dists/stable/main/binary-amd64/Packages" ||
  die "jmxremote is missing from Packages"

log "assembling gh-pages tree"
rm -rf "$REPO_CLONE/dists" "$REPO_CLONE/pool"
cp -a "$PUBLIC_DIR/." "$REPO_CLONE/"
gpg --armor --export "$APT_GPG_KEY_ID" > "$REPO_CLONE/KEY.gpg"
touch "$REPO_CLONE/.nojekyll"

if [ ! -f "$REPO_CLONE/index.html" ]; then
  log "adding default index.html"
  sed \
    -e "s|__APT_REPO__|${APT_REPO}|g" \
    -e "s|__APT_PAGES_URL__|${APT_PAGES_URL}|g" \
    "$SCRIPT_DIR/templates/index.html" > "$REPO_CLONE/index.html"
fi

cd "$REPO_CLONE"
git add -A

if git diff --cached --quiet; then
  log "no repository changes"
  exit 0
fi

git -c user.name="github-actions[bot]" \
    -c user.email="41898282+github-actions[bot]@users.noreply.github.com" \
    commit -m "apt: jmxremote ${VERSION}"

if [ "$DRY_RUN" = "1" ]; then
  log "dry run: not pushing"
  git show --stat --oneline HEAD
  exit 0
fi

log "pushing gh-pages to ${APT_REPO}"
git push origin HEAD:gh-pages
log "published ${VERSION}; Pages URL: ${APT_PAGES_URL}"
