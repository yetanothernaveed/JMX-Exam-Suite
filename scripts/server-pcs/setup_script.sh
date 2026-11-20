#!/usr/bin/env bash
#
# Provision an Ubuntu server PC for the JMX exam server.
#
# Run this script from a copied location (not from inside JMX-Mono), because
# GitHub CLI authentication is required before the private repo can be cloned.
#
# Optional overrides:
#   JMX_TARGET_USER     User to provision (default: SUDO_USER, or current user)
#   JMX_PROJECTS_DIR    Parent directory for JMX-Mono and piston checkouts
#   JMX_DEMO_EXAM_ID    Exam ID used for the examplesetup demonstration folders

set -euo pipefail

log()  { printf '\n>>> %s\n' "$*"; }
warn() { printf '\n[WARN] %s\n' "$*" >&2; }
die()  { printf '\n[ERROR] %s\n' "$*" >&2; exit 1; }

# ---------------------------------------------------------------------------
# Privilege / target-user setup
# ---------------------------------------------------------------------------

if [ "$EUID" -ne 0 ]; then
    command -v sudo >/dev/null 2>&1 || die "sudo is required to provision this machine."
    sudo -v || die "sudo authentication failed."
    SUDO="sudo"
else
    SUDO=""
fi

CURRENT_USER="$(id -un)"

if [ -n "${JMX_TARGET_USER:-}" ]; then
    TARGET_USER="$JMX_TARGET_USER"
elif [ -n "${SUDO_USER:-}" ] && [ "$SUDO_USER" != "root" ]; then
    TARGET_USER="$SUDO_USER"
else
    TARGET_USER="$CURRENT_USER"
fi

id "$TARGET_USER" >/dev/null 2>&1 || die "Target user '$TARGET_USER' does not exist."
TARGET_HOME="$(getent passwd "$TARGET_USER" | cut -d: -f6)"
[ -n "$TARGET_HOME" ] || die "Could not determine home directory for '$TARGET_USER'."

TARGET_GROUP="$(id -gn "$TARGET_USER")"
PROJECTS_DIR="${JMX_PROJECTS_DIR:-$TARGET_HOME/Projects}"
JMX_DIR="$PROJECTS_DIR/JMX-Mono"
PISTON_DIR="$PROJECTS_DIR/piston"
SERVER_DIR="$JMX_DIR/server"

as_target() {
    if [ "$CURRENT_USER" = "$TARGET_USER" ]; then
        env HOME="$TARGET_HOME" "$@"
    elif [ "$EUID" -eq 0 ]; then
        runuser -u "$TARGET_USER" -- env HOME="$TARGET_HOME" "$@"
    else
        sudo -H -u "$TARGET_USER" -- "$@"
    fi
}

run_in_dir() {
    local dir="$1"
    shift
    ( cd "$dir" && as_target "$@" )
}

apt_update() {
    $SUDO apt-get update
}

apt_install() {
    $SUDO env DEBIAN_FRONTEND=noninteractive apt-get install -y "$@"
}

sql_quote() {
    printf "'%s'" "$(printf '%s' "$1" | sed "s/'/''/g")"
}

log "Target user: $TARGET_USER ($TARGET_HOME)"
log "Projects directory: $PROJECTS_DIR"

# ---------------------------------------------------------------------------
# 1. Preflight
# ---------------------------------------------------------------------------

log "[1/9] Preflight checks"

OS_ID="$(. /etc/os-release && printf '%s' "$ID")"
OS_CODENAME="$(. /etc/os-release && printf '%s' "$VERSION_CODENAME")"
[ "$OS_ID" = "ubuntu" ] || warn "This script is intended for Ubuntu; detected '$OS_ID'."

CGROUP_FSTYPE="$(stat -fc %T /sys/fs/cgroup 2>/dev/null || true)"
[ "$CGROUP_FSTYPE" = "cgroup2fs" ] || die "cgroup v2 not detected at /sys/fs/cgroup (found '$CGROUP_FSTYPE')."
[ -e /sys/fs/cgroup/cgroup.subtree_control ] || die "cgroup v2 subtree control file is missing; Piston cannot run."

# ---------------------------------------------------------------------------
# 2. Base packages and GitHub CLI
# ---------------------------------------------------------------------------

log "[2/9] Installing base packages and GitHub CLI"

apt_update
apt_install ca-certificates curl gnupg git build-essential lsb-release \
    nodejs npm mysql-server

$SUDO install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg |
    $SUDO tee /etc/apt/keyrings/githubcli-archive-keyring.gpg >/dev/null
$SUDO chmod go+r /etc/apt/keyrings/githubcli-archive-keyring.gpg
printf 'deb [arch=%s signed-by=/etc/apt/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main\n' \
    "$(dpkg --print-architecture)" |
    $SUDO tee /etc/apt/sources.list.d/github-cli.list >/dev/null

apt_update
apt_install gh

# ---------------------------------------------------------------------------
# 3. GitHub authentication
# ---------------------------------------------------------------------------

log "[3/9] Checking GitHub CLI authentication"

if ! as_target gh auth status >/dev/null 2>&1; then
    echo "GitHub CLI is not authenticated. Starting interactive login..."
    as_target gh auth login --git-protocol https --web
fi

as_target gh auth status >/dev/null 2>&1 || die "GitHub CLI authentication failed."
as_target gh auth setup-git

# ---------------------------------------------------------------------------
# 4. Repository bootstrap (private-aware)
# ---------------------------------------------------------------------------

log "[4/9] Cloning repositories if needed"

clone_repo() {
    local repo="$1"
    local dest="$2"

    if [ -d "$dest/.git" ]; then
        echo "$dest already exists; leaving it untouched."
        return
    fi

    if [ -e "$dest" ]; then
        die "$dest exists but is not a git checkout. Move it out of the way first."
    fi

    as_target mkdir -p "$(dirname "$dest")"
    as_target gh repo clone "$repo" "$dest" --
}

clone_repo "yetanothernaveed/JMX-Exam-Suite" "$JMX_DIR"
clone_repo "yetanothernaveed/custom-piston" "$PISTON_DIR"

[ -f "$SERVER_DIR/server.py" ] || die "server.py not found in $SERVER_DIR"
[ -f "$PISTON_DIR/docker-compose.yaml" ] || die "custom docker-compose.yaml not found in $PISTON_DIR"

# ---------------------------------------------------------------------------
# 5. Docker Engine and Compose
# ---------------------------------------------------------------------------

log "[5/9] Installing Docker Engine and Compose plugin"

$SUDO install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg |
    $SUDO tee /etc/apt/keyrings/docker.asc >/dev/null
$SUDO chmod a+r /etc/apt/keyrings/docker.asc
printf 'deb [arch=%s signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu %s stable\n' \
    "$(dpkg --print-architecture)" "$OS_CODENAME" |
    $SUDO tee /etc/apt/sources.list.d/docker.list >/dev/null

apt_update
apt_install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

$SUDO systemctl enable --now docker

getent group docker >/dev/null 2>&1 || $SUDO groupadd docker
$SUDO usermod -aG docker "$TARGET_USER"

if as_target docker info >/dev/null 2>&1 && as_target docker compose version >/dev/null 2>&1; then
    echo "Docker and Docker Compose are usable without sudo."
else
    warn "Docker was installed, but the new docker group membership may require a fresh login."
fi

# ---------------------------------------------------------------------------
# 6. Python environment via Conda
# ---------------------------------------------------------------------------

log "[6/9] Creating the jmxenv Conda environment"

case "$(dpkg --print-architecture)" in
    amd64) CONDA_ARCH="x86_64" ;;
    arm64) CONDA_ARCH="aarch64" ;;
    *) die "Unsupported architecture for Miniconda." ;;
esac

MINICONDA_DIR="$TARGET_HOME/miniconda3"
CONDA_BIN="$MINICONDA_DIR/bin/conda"

if [ ! -x "$CONDA_BIN" ]; then
    CONDA_TMP="$(mktemp -d)"
    curl -fsSL "https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-${CONDA_ARCH}.sh" \
        -o "$CONDA_TMP/miniconda.sh"
    # The installer runs as the target user, so make the temp files readable.
    chmod 755 "$CONDA_TMP" "$CONDA_TMP/miniconda.sh"
    as_target bash "$CONDA_TMP/miniconda.sh" -b -p "$MINICONDA_DIR"
    rm -rf "$CONDA_TMP"
fi

# Newer Conda versions require accepting Anaconda defaults ToS.
as_target "$CONDA_BIN" tos accept \
    --override-channels \
    --channel https://repo.anaconda.com/pkgs/main \
    --channel https://repo.anaconda.com/pkgs/r >/dev/null 2>&1 || true

# environment.yml has a machine-specific prefix; strip it so the env is created
# under this user's Miniconda installation.
TMP_ENV="$SERVER_DIR/.environment.setup.yml"
grep -v '^[[:space:]]*prefix:' "$SERVER_DIR/environment.yml" | as_target tee "$TMP_ENV" >/dev/null

if as_target "$CONDA_BIN" env list | awk '{print $1}' | grep -Fxq "jmxenv"; then
    run_in_dir "$SERVER_DIR" "$CONDA_BIN" env update -n jmxenv -f "$TMP_ENV" --prune
else
    run_in_dir "$SERVER_DIR" "$CONDA_BIN" env create -n jmxenv -f "$TMP_ENV"
fi

as_target rm -f "$TMP_ENV"
as_target "$CONDA_BIN" init bash >/dev/null

# ---------------------------------------------------------------------------
# 7. MySQL
# ---------------------------------------------------------------------------

log "[7/9] Configuring local MySQL"

$SUDO systemctl enable --now mysql

for _ in $(seq 1 30); do
    if $SUDO mysqladmin ping >/dev/null 2>&1; then
        break
    fi
    sleep 1
done
$SUDO mysqladmin ping >/dev/null 2>&1 || die "MySQL did not become ready."

env_value() {
    local key="$1"
    local file="$2"
    local value
    value="$(sed -n "s/^[[:space:]]*${key}[[:space:]]*=[[:space:]]*//p" "$file" | head -n 1 | tr -d '\r')"
    case "$value" in
        \"*\") value="${value#\"}"; value="${value%\"}" ;;
        \'*\') value="${value#\'}"; value="${value%\'}";;
    esac
    printf '%s' "$value"
}

DB_USER="$(env_value DB_USER "$SERVER_DIR/.env")"
DB_PASSWORD="$(env_value DB_PASSWORD "$SERVER_DIR/.env")"
DB_HOST="$(env_value DB_HOST "$SERVER_DIR/.env")"

[ -n "$DB_USER" ] || die "DB_USER is missing from $SERVER_DIR/.env"
[ -n "$DB_PASSWORD" ] || die "DB_PASSWORD is missing from $SERVER_DIR/.env"
[ -n "$DB_HOST" ] || die "DB_HOST is missing from $SERVER_DIR/.env"

DB_USER_SQL="$(sql_quote "$DB_USER")"
DB_PASSWORD_SQL="$(sql_quote "$DB_PASSWORD")"

$SUDO mysql <<SQL
CREATE USER IF NOT EXISTS ${DB_USER_SQL}@'localhost' IDENTIFIED BY ${DB_PASSWORD_SQL};
GRANT ALL PRIVILEGES ON *.* TO ${DB_USER_SQL}@'localhost' WITH GRANT OPTION;
CREATE USER IF NOT EXISTS ${DB_USER_SQL}@'127.0.0.1' IDENTIFIED BY ${DB_PASSWORD_SQL};
GRANT ALL PRIVILEGES ON *.* TO ${DB_USER_SQL}@'127.0.0.1' WITH GRANT OPTION;
CREATE USER IF NOT EXISTS ${DB_USER_SQL}@'%' IDENTIFIED BY ${DB_PASSWORD_SQL};
GRANT ALL PRIVILEGES ON *.* TO ${DB_USER_SQL}@'%' WITH GRANT OPTION;
FLUSH PRIVILEGES;
SQL

echo "MySQL user '$DB_USER' is ready (DB_HOST=$DB_HOST)."

# ---------------------------------------------------------------------------
# 8. Questions / responses folders
# ---------------------------------------------------------------------------

log "[8/9] Creating questions and responses folders"

# Roots for real exams. Each exam will later get its own <exam_id>/ folder.
REAL_QUESTIONS_ROOT="$TARGET_HOME/questions"
REAL_RESPONSES_ROOT="$TARGET_HOME/responses"
as_target mkdir -p "$REAL_QUESTIONS_ROOT" "$REAL_RESPONSES_ROOT"
as_target touch "$REAL_QUESTIONS_ROOT/.gitkeep" "$REAL_RESPONSES_ROOT/.gitkeep"

# Demonstration folders matching the paths hard-coded in server.py.
DEMO_EXAM_ID="${JMX_DEMO_EXAM_ID:-cse221_summer2026_section1_quiz0}"
DEMO_QUESTIONS_ROOT="$JMX_DIR/examplesetup/questions"
DEMO_RESPONSES_ROOT="$JMX_DIR/examplesetup/responses"
DEMO_QUESTIONS_EXAM="$DEMO_QUESTIONS_ROOT/$DEMO_EXAM_ID"

as_target mkdir -p "$DEMO_QUESTIONS_ROOT" "$DEMO_RESPONSES_ROOT"

if [ ! -d "$DEMO_QUESTIONS_EXAM" ]; then
    echo "Seeding demonstration questions for exam '$DEMO_EXAM_ID'."
    for qid in Q110 Q111; do
        for subdir in '~judge' '~testcases' '~wrapper'; do
            as_target mkdir -p "$DEMO_QUESTIONS_EXAM/$qid/$subdir"
            as_target touch "$DEMO_QUESTIONS_EXAM/$qid/$subdir/.gitkeep"
        done
    done
fi

as_target mkdir -p "$DEMO_RESPONSES_ROOT/$DEMO_EXAM_ID"

# ---------------------------------------------------------------------------
# 9. Piston with the custom docker-compose settings
# ---------------------------------------------------------------------------

log "[9/9] Building and starting Piston"

as_target chmod +x "$PISTON_DIR/piston"
run_in_dir "$PISTON_DIR" ./piston rebuild
run_in_dir "$PISTON_DIR" ./piston start

API_READY=0
for _ in $(seq 1 60); do
    if curl -fsS http://127.0.0.1:2000/api/v2/runtimes >/dev/null 2>&1; then
        API_READY=1
        break
    fi
    sleep 2
done
[ "$API_READY" -eq 1 ] || die "Piston API did not become ready on port 2000."

# Install the pinned versions whose package scripts are customized in this repo.
run_in_dir "$PISTON_DIR" ./piston ppman install gcc=10.2.0 java=15.0.2 python=3.12.0

RUNTIMES_JSON="$(curl -fsS http://127.0.0.1:2000/api/v2/runtimes)"
for language in 'c++' java python; do
    printf '%s' "$RUNTIMES_JSON" | grep -q "\"language\":\"$language\"" ||
        warn "Piston does not report '$language' as installed."
done

# ---------------------------------------------------------------------------
# Done
# ---------------------------------------------------------------------------

log "JMX server setup complete."
cat <<EOF

Real exam roots:
  $REAL_QUESTIONS_ROOT
  $REAL_RESPONSES_ROOT

Demo roots (used by the current server.py defaults):
  $DEMO_QUESTIONS_ROOT/$DEMO_EXAM_ID
  $DEMO_RESPONSES_ROOT/$DEMO_EXAM_ID

Start the server:
  source ~/miniconda3/etc/profile.d/conda.sh
  conda activate jmxenv
  cd $SERVER_DIR
  python server.py

If docker commands report a permission error, log out and back in once so the
new docker group membership takes effect.
EOF
