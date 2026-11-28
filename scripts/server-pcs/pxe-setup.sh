#!/usr/bin/env bash
# ==============================================================================
# pxe-setup.sh - install a proxy-DHCP PXE server that boots a live ISO over NFS
# Target: Ubuntu 24.04 LTS. Must be run with sudo.
# ==============================================================================

set -Eeuo pipefail
shopt -s nullglob

# ------------------------------ defaults --------------------------------------
ISO_PATH=""
IFACE=""
CLIENT_SUBNET=""
IMAGES_ROOT="/srv/pxe/images"
TFTP_ROOT="/var/lib/tftpboot"
STATE_FILE="$IMAGES_ROOT/current.json"
MOUNTD_PORT="20048"
LOCK_FILE="/run/lock/pxe-setup.lock"
BACKUP_DIR="/var/backups/pxe-setup/$(date +%Y%m%d-%H%M%S)"
EXPORT_BEGIN="# BEGIN pxe-setup.sh managed"
EXPORT_END="# END pxe-setup.sh managed"

declare -a ROLLBACK_CMDS=()
declare -a TMP_PATHS=()
MOUNT_DIR=""
MOUNTED=0
STAGING=""
NFS_TEST_DIR=""

log()  { printf '[+] %s\n' "$*"; }
warn() { printf '[!] %s\n' "$*" >&2; }
die()  { printf '[-] ERROR: %s\n' "$*" >&2; exit 1; }

usage() {
    cat <<'USAGE'
Usage: sudo pxe-setup.sh /path/to/image.iso [options]

Options:
  --interface IFACE       Network interface for PXE (default: default-route iface)
  --client-subnet CIDR    Clients subnet allowed to mount NFS (default: iface subnet)
  --images-root DIR       Root for extracted ISO versions (default: /srv/pxe/images)
  --tftp-root DIR         TFTP root (default: /var/lib/tftpboot)
  -h, --help              Show this help

DHCP mode is proxy-only: this machine does not assign IP addresses or change
gateway/DNS settings. An existing DHCP server on the LAN remains authoritative.
USAGE
}

cleanup() {
    local rc=$?
    trap - EXIT

    if (( rc != 0 )) && ((${#ROLLBACK_CMDS[@]})); then
        warn "Setup failed. Attempting rollback..."
        local i
        for (( i=${#ROLLBACK_CMDS[@]}-1; i>=0; i-- )); do
            eval "${ROLLBACK_CMDS[$i]}" 2>/dev/null || true
        done
        warn "Rollback attempted. Backups are in: $BACKUP_DIR"
    fi

    if (( MOUNTED == 1 )) && [[ -n "$MOUNT_DIR" ]]; then
        umount -l "$MOUNT_DIR" 2>/dev/null || true
    fi
    if [[ -n "$NFS_TEST_DIR" && -d "$NFS_TEST_DIR" ]]; then
        umount -l "$NFS_TEST_DIR" 2>/dev/null || true
        rmdir "$NFS_TEST_DIR" 2>/dev/null || true
    fi
    if [[ -n "$STAGING" && -d "$STAGING" ]]; then
        rm -rf -- "$STAGING" 2>/dev/null || true
    fi
    local p
    for p in "${TMP_PATHS[@]:-}"; do
        [[ -n "$p" ]] && rm -f -- "$p" 2>/dev/null || true
    done

    exit "$rc"
}
trap cleanup EXIT

register_file_rollback() {
    local path="$1"
    mkdir -p "$BACKUP_DIR"
    local n backup
    n=$(printf '%03d' "${#ROLLBACK_CMDS[@]}")
    backup="$BACKUP_DIR/${n}-$(basename "$path")"
    if [[ -e "$path" || -L "$path" ]]; then
        cp -a -- "$path" "$backup"
        ROLLBACK_CMDS+=("$(printf 'cp -a -- %q %q' "$backup" "$path")")
    else
        ROLLBACK_CMDS+=("$(printf 'rm -f -- %q' "$path")")
    fi
}

register_service_rollback() {
    local svc="$1"
    if systemctl is-active --quiet "$svc" 2>/dev/null; then
        ROLLBACK_CMDS+=("systemctl start --quiet $svc")
    else
        ROLLBACK_CMDS+=("systemctl stop --quiet $svc")
    fi
    if systemctl is-enabled --quiet "$svc" 2>/dev/null; then
        ROLLBACK_CMDS+=("systemctl enable --quiet $svc")
    else
        ROLLBACK_CMDS+=("systemctl disable --quiet $svc")
    fi
}

mktemp_tracked() {
    local p
    p=$(mktemp "$@")
    TMP_PATHS+=("$p")
    printf '%s\n' "$p"
}

atomic_install_file() {
    local src="$1" dest="$2" mode="${3:-0644}"
    mkdir -p "$(dirname "$dest")"
    install -m "$mode" -o root -g root -- "$src" "$dest"
}

# ------------------------------ arguments -------------------------------------
while (($#)); do
    case "$1" in
        --interface)
            [[ $# -ge 2 ]] || die "--interface requires a value"
            IFACE="$2"; shift 2 ;;
        --client-subnet)
            [[ $# -ge 2 ]] || die "--client-subnet requires a value"
            CLIENT_SUBNET="$2"; shift 2 ;;
        --images-root)
            [[ $# -ge 2 ]] || die "--images-root requires a value"
            IMAGES_ROOT="$2"; STATE_FILE="$IMAGES_ROOT/current.json"; shift 2 ;;
        --tftp-root)
            [[ $# -ge 2 ]] || die "--tftp-root requires a value"
            TFTP_ROOT="$2"; shift 2 ;;
        -h|--help)
            usage; exit 0 ;;
        -*)
            die "Unknown option: $1" ;;
        *)
            [[ -z "$ISO_PATH" ]] || die "Only one ISO path may be given"
            ISO_PATH="$1"; shift ;;
    esac
done

[[ -n "$ISO_PATH" ]] || { usage >&2; die "No ISO path provided"; }
[[ $EUID -eq 0 ]] || die "This script must be run as root: sudo $0 <iso-path>"
command -v python3 >/dev/null || die "python3 is required"

log "PXE setup started."
log "ISO: $ISO_PATH"

# ------------------------------ preflight -------------------------------------
exec 9>"$LOCK_FILE"
flock -n 9 || die "Another pxe-setup run is in progress"

[[ -f "$ISO_PATH" && -r "$ISO_PATH" ]] || die "ISO not found or unreadable: $ISO_PATH"
ISO_PATH=$(readlink -f -- "$ISO_PATH")
mkdir -p "$IMAGES_ROOT" "$TFTP_ROOT"
if command -v file >/dev/null 2>&1; then
    file -b "$ISO_PATH" | grep -qi 'ISO 9660' || warn "File magic did not identify an ISO 9660 image; continuing"
fi

if [[ -z "$IFACE" ]]; then
    IFACE=$(ip -4 route show default 2>/dev/null | awk '/^default /{print $5; exit}' || true)
fi
[[ -n "$IFACE" ]] || die "Could not determine default-route interface; use --interface IFACE"
ip link show dev "$IFACE" >/dev/null 2>&1 || die "Interface does not exist: $IFACE"

SERVER_IP=$(ip -4 -o addr show dev "$IFACE" 2>/dev/null | awk '{split($4,a,"/"); print a[1]; exit}')
PREFIX=$(ip -4 -o addr show dev "$IFACE" 2>/dev/null | awk '{split($4,a,"/"); print a[2]; exit}')
[[ -n "$SERVER_IP" && -n "$PREFIX" && "$SERVER_IP" != 127.* ]] || die "No IPv4 address on $IFACE"

if [[ -z "$CLIENT_SUBNET" ]]; then
    CLIENT_SUBNET=$(python3 - "$SERVER_IP/$PREFIX" <<'PY'
import ipaddress, sys
print(str(ipaddress.ip_network(sys.argv[1], strict=False)))
PY
    )
fi
if ! python3 - "$CLIENT_SUBNET" <<'PY'
import ipaddress, sys
ipaddress.ip_network(sys.argv[1], strict=False)
PY
then
    die "Invalid --client-subnet CIDR: $CLIENT_SUBNET"
fi

ISO_SIZE=$(stat -c %s "$ISO_PATH")
AVAIL=$(df -B1 --output=avail "$IMAGES_ROOT" 2>/dev/null | tail -n1 || echo 0)
NEED=$(( ISO_SIZE + 536870912 ))
(( AVAIL >= NEED )) || die "Not enough free space under $IMAGES_ROOT (need ~$(( NEED/1024/1024/1024 )) GiB)"

if mountpoint -q /mnt/custom_iso 2>/dev/null; then
    warn "Stale ISO mount at /mnt/custom_iso detected; leaving it untouched"
fi

log "Detected server IP: $SERVER_IP ($IFACE), client subnet: $CLIENT_SUBNET"

# ------------------------------ packages --------------------------------------
PACKAGES=(dnsmasq nfs-kernel-server nfs-common rpcbind pxelinux syslinux-common rsync shim-signed)
if ! dpkg-query -W -f='${Status}' grub-efi-amd64-signed 2>/dev/null | grep -q '^install ok installed$'; then
    PACKAGES+=(grub-efi-amd64-signed)
fi

declare -a MISSING=()
for p in "${PACKAGES[@]}"; do
    if ! dpkg-query -W -f='${Status}' "$p" 2>/dev/null | grep -q '^install ok installed$'; then
        MISSING+=("$p")
    fi
done
if ((${#MISSING[@]})); then
    log "Installing packages: ${MISSING[*]}"
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -qq
    apt-get install -y --no-install-recommends "${MISSING[@]}"
else
    log "Required packages are already installed"
fi

# ------------------------------ ISO staging -----------------------------------
log "Computing ISO SHA-256 (this can take a minute)..."
ISO_SHA=$(sha256sum "$ISO_PATH" | awk '{print $1}')
SHORT_SHA="${ISO_SHA:0:12}"
VERSION_DIR="$IMAGES_ROOT/$SHORT_SHA"

validate_tree() {
    local d="$1"
    [[ -d "$d" ]] || return 1
    [[ -f "$d/casper/vmlinuz" ]] || return 1
    [[ -n "$(find "$d/casper" -maxdepth 1 -type f -name 'initrd*' -print -quit 2>/dev/null)" ]] || return 1
    [[ -f "$d/casper/filesystem.squashfs" ]] || return 1
    [[ -f "$d/.disk/casper-uuid-generic" || -f "$d/.disk/casper-uuid" ]] || return 1
}

mkdir -p "$IMAGES_ROOT" "$TFTP_ROOT"
SKIP_EXTRACT=0
if [[ -f "$STATE_FILE" ]] && grep -q "\"sha256\"[[:space:]]*:[[:space:]]*\"$ISO_SHA\"" "$STATE_FILE" \
   && validate_tree "$VERSION_DIR"; then
    SKIP_EXTRACT=1
    log "ISO already staged; skipping extraction ($SHORT_SHA)"
fi

if (( SKIP_EXTRACT == 0 )); then
    STAGING=$(mktemp -d "$IMAGES_ROOT/.staging.XXXXXX")
    MOUNT_DIR=$(mktemp -d /run/pxe-setup.iso.XXXXXX)

    if mount -o loop,ro -- "$ISO_PATH" "$MOUNT_DIR" 2>/dev/null; then
        MOUNTED=1
        log "Copying ISO contents (including dotfiles) to staging..."
        rsync -a -- "$MOUNT_DIR/" "$STAGING/"
        umount "$MOUNT_DIR"
        MOUNTED=0
    else
        warn "Loop mount failed; falling back to direct extraction"
        command -v 7z >/dev/null || die "Neither loop mount nor 7z is available"
        7z x -y -o"$STAGING" "$ISO_PATH" >/dev/null
    fi
    rmdir "$MOUNT_DIR" 2>/dev/null || true
    MOUNT_DIR=""

    validate_tree "$STAGING" || die "ISO does not contain the expected casper live-boot files"

    if [[ -e "$VERSION_DIR" ]]; then
        old_version="${VERSION_DIR}.invalid.$(date +%s)"
        mv "$VERSION_DIR" "$old_version"
        ROLLBACK_CMDS+=("$(printf 'mv -- %q %q' "$old_version" "$VERSION_DIR")")
        warn "Moved pre-existing/invalid version directory aside: $VERSION_DIR"
    fi
    mv "$STAGING" "$VERSION_DIR"
    STAGING=""
    log "Staged ISO at $VERSION_DIR"
fi

INITRD_SRC=$(find "$VERSION_DIR/casper" -maxdepth 1 -type f -name 'initrd*' -print -quit)
[[ -n "$INITRD_SRC" ]] || die "No initrd found in staged ISO"

# ------------------------------ exports ---------------------------------------
log "Configuring read-only NFS export..."
EXPORT_FILE="/etc/exports"
register_file_rollback "$EXPORT_FILE"
EXPORT_TMP=$(mktemp_tracked /run/pxe-setup.exports.XXXXXX)
if [[ -f "$EXPORT_FILE" ]]; then
    awk -v b="$EXPORT_BEGIN" -v e="$EXPORT_END" '
        $0 == b { skip=1; next }
        $0 == e { skip=0; next }
        !skip { print }
    ' "$EXPORT_FILE" > "$EXPORT_TMP"
else
    : > "$EXPORT_TMP"
fi
{
    printf '%s\n' "$EXPORT_BEGIN"
    printf '%s %s(ro,sync,no_subtree_check)\n' "$IMAGES_ROOT" "$CLIENT_SUBNET"
    printf '%s\n' "$EXPORT_END"
} >> "$EXPORT_TMP"
atomic_install_file "$EXPORT_TMP" "$EXPORT_FILE"

log "Pinning rpc.mountd to port $MOUNTD_PORT..."
NFS_DEFAULT="/etc/default/nfs-kernel-server"
register_file_rollback "$NFS_DEFAULT"
NFS_DEF_TMP=$(mktemp_tracked /run/pxe-setup.nfsdefault.XXXXXX)
if [[ -f "$NFS_DEFAULT" ]]; then
    awk -v port="$MOUNTD_PORT" '
        /^[[:space:]]*RPCMOUNTDOPTS[[:space:]]*=/ { next }
        { print }
        END { print "RPCMOUNTDOPTS=\"--manage-gids --port " port "\"" }
    ' "$NFS_DEFAULT" > "$NFS_DEF_TMP"
else
    printf 'RPCMOUNTDOPTS="--manage-gids --port %s"\n' "$MOUNTD_PORT" > "$NFS_DEF_TMP"
fi
atomic_install_file "$NFS_DEF_TMP" "$NFS_DEFAULT"

# ------------------------------ dnsmasq ---------------------------------------
log "Removing stray dnsmasq drop-ins from earlier attempts..."
for conf in /etc/dnsmasq.d/*.conf; do
    [[ -e "$conf" ]] || continue
    disabled="${conf}.pxe-setup-disabled.$(date +%s)"
    mv -- "$conf" "$disabled"
    ROLLBACK_CMDS+=("$(printf 'mv -- %q %q' "$disabled" "$conf")")
    warn "Quarantined drop-in: $conf"
done

DNSMASQ_CONF="/etc/dnsmasq.conf"
register_file_rollback "$DNSMASQ_CONF"
DNS_TMP=$(mktemp_tracked /run/pxe-setup.dnsmasq.XXXXXX)
cat > "$DNS_TMP" <<EOF
# Managed by pxe-setup.sh -- DO NOT EDIT
# Proxy DHCP only: no IP leases, no gateway/DNS changes.

interface=$IFACE
bind-interfaces
port=0
local-service

dhcp-range=$SERVER_IP,proxy

pxe-prompt="PXE boot JMX OS (10s)",10
pxe-service=x86PC,"BIOS: JMX OS live installer",pxelinux,$SERVER_IP
pxe-service=x86-64_EFI,"UEFI: JMX OS live installer",bootx64.efi,$SERVER_IP

enable-tftp
tftp-root=$TFTP_ROOT

log-dhcp
EOF
dnsmasq --test -C "$DNS_TMP" >/dev/null || die "Generated dnsmasq configuration failed validation"
atomic_install_file "$DNS_TMP" "$DNSMASQ_CONF"

# ------------------------------ boot files ------------------------------------
log "Installing BIOS and UEFI boot loaders..."
NFSROOT="$SERVER_IP:$VERSION_DIR"
KERNEL_ARGS="boot=casper netboot=nfs nfsroot=$NFSROOT ip=dhcp quiet splash"

install -D -m 0644 -o root -g root "$VERSION_DIR/casper/vmlinuz" "$TFTP_ROOT/casper/vmlinuz"
install -D -m 0644 -o root -g root "$INITRD_SRC" "$TFTP_ROOT/casper/initrd.gz"

BIOS_SRC="/usr/lib/PXELINUX/pxelinux.0"
[[ -f "$BIOS_SRC" ]] || die "Missing pxelinux.0 from pxelinux package"
atomic_install_file "$BIOS_SRC" "$TFTP_ROOT/pxelinux.0"
for c32 in ldlinux.c32 libcom32.c32 libutil.c32 menu.c32 vesamenu.c32; do
    f="/usr/lib/syslinux/modules/bios/$c32"
    [[ -f "$f" ]] || continue
    atomic_install_file "$f" "$TFTP_ROOT/$c32"
done

SHIM_SRC=""
for candidate in /usr/lib/shim/shimx64.efi.signed.latest /usr/lib/shim/shimx64.efi.signed /usr/lib/shim/shimx64.efi; do
    [[ -f "$candidate" ]] && { SHIM_SRC="$candidate"; break; }
done
[[ -n "$SHIM_SRC" ]] || die "Could not find a signed shim bootloader"
atomic_install_file "$SHIM_SRC" "$TFTP_ROOT/bootx64.efi"

GRUB_SRC=""
for candidate in /usr/lib/grub/x86_64-efi-signed/grubnetx64.efi.signed \
                 /usr/lib/grub/x86_64-efi/monolithic/grubnetx64.efi; do
    [[ -f "$candidate" ]] && { GRUB_SRC="$candidate"; break; }
done
[[ -n "$GRUB_SRC" ]] || die "Could not find a network-capable GRUB EFI binary"
if [[ "$GRUB_SRC" != *signed* ]]; then
    warn "Using unsigned GRUB; Secure Boot clients may refuse to boot"
fi
atomic_install_file "$GRUB_SRC" "$TFTP_ROOT/grubx64.efi"

PXE_TMP=$(mktemp_tracked /run/pxe-setup.pxelinux.XXXXXX)
cat > "$PXE_TMP" <<EOF
DEFAULT JMXOS
PROMPT 0
TIMEOUT 100

LABEL JMXOS
    KERNEL /casper/vmlinuz
    INITRD /casper/initrd.gz
    APPEND $KERNEL_ARGS
EOF
mkdir -p "$TFTP_ROOT/pxelinux.cfg"
atomic_install_file "$PXE_TMP" "$TFTP_ROOT/pxelinux.cfg/default"

GRUB_TMP=$(mktemp_tracked /run/pxe-setup.grub.XXXXXX)
cat > "$GRUB_TMP" <<EOF
set default=0
set timeout=10

menuentry "JMX OS - live desktop / installer (NFS)" {
    linux (tftp,$SERVER_IP)/casper/vmlinuz $KERNEL_ARGS
    initrd (tftp,$SERVER_IP)/casper/initrd.gz
}
EOF
atomic_install_file "$GRUB_TMP" "$TFTP_ROOT/grub.cfg"
mkdir -p "$TFTP_ROOT/EFI/BOOT" "$TFTP_ROOT/grub"
atomic_install_file "$GRUB_TMP" "$TFTP_ROOT/EFI/BOOT/grub.cfg"
atomic_install_file "$GRUB_TMP" "$TFTP_ROOT/grub/grub.cfg"

chown -R root:root "$TFTP_ROOT" "$IMAGES_ROOT"
chmod -R a+rX "$TFTP_ROOT" "$IMAGES_ROOT"

# ------------------------------ firewall --------------------------------------
if command -v ufw >/dev/null 2>&1 && ufw status 2>/dev/null | grep -q '^Status: active'; then
    log "UFW is active: adding PXE/NFS rules on $IFACE"
    for spec in "udp 67 PXE-proxy-DHCP" "udp 69 PXE-TFTP" \
                "tcp 111 NFS-portmapper" "udp 111 NFS-portmapper" \
                "tcp 2049 NFS" "udp 2049 NFS" \
                "tcp $MOUNTD_PORT NFS-mountd" "udp $MOUNTD_PORT NFS-mountd"; do
        set -- $spec
        proto="$1"; port="$2"; comment="$3"
        ufw allow in on "$IFACE" proto "$proto" to any port "$port" comment "$comment" >/dev/null 2>&1 || true
    done
else
    log "UFW is inactive; no firewall changes needed"
fi

# ------------------------------ services --------------------------------------
log "Starting and enabling rpcbind, nfs-server and dnsmasq..."
for svc in rpcbind nfs-server dnsmasq; do
    register_service_rollback "$svc"
done
systemctl daemon-reload
systemctl enable --now rpcbind >/dev/null
systemctl enable --now nfs-server >/dev/null
systemctl enable --now dnsmasq >/dev/null
systemctl restart nfs-server
systemctl restart dnsmasq
exportfs -ra

# ------------------------------ verification ----------------------------------
log "Verifying configuration..."

dnsmasq --test -C "$DNSMASQ_CONF" >/dev/null || die "dnsmasq config verification failed"
systemctl is-active --quiet dnsmasq || die "dnsmasq is not active"
systemctl is-active --quiet nfs-server || die "nfs-server is not active"
exportfs -v 2>/dev/null | grep -Fq "$IMAGES_ROOT" || die "NFS export is not active for $IMAGES_ROOT"

for required in pxelinux.0 pxelinux.cfg/default bootx64.efi grubx64.efi grub.cfg casper/vmlinuz casper/initrd.gz; do
    [[ -r "$TFTP_ROOT/$required" ]] || die "Missing TFTP file: $required"
done

if curl --version 2>/dev/null | grep -q tftp; then
    curl -fsS --max-time 8 "tftp://$SERVER_IP/pxelinux.0" -o /dev/null 2>/dev/null \
        || warn "Local TFTP fetch test failed; check dnsmasq/TFTP logs"
else
    warn "curl lacks TFTP support; skipping local TFTP fetch test"
fi

NFS_TEST_DIR=$(mktemp -d /run/pxe-setup.nfstest.XXXXXX)
NFS_OK=0
for opts in "ro,nolock" "ro,nolock,nfsvers=4" "ro,nolock,nfsvers=3"; do
    if timeout 20 mount -t nfs -o "$opts" "$NFSROOT" "$NFS_TEST_DIR" 2>/dev/null; then
        if [[ -r "$NFS_TEST_DIR/casper/vmlinuz" ]]; then
            NFS_OK=1
            umount "$NFS_TEST_DIR"
            break
        fi
        umount "$NFS_TEST_DIR"
    fi
done
(( NFS_OK == 1 )) || die "Could not mount the NFS export locally at $NFSROOT"
rmdir "$NFS_TEST_DIR" 2>/dev/null || true
NFS_TEST_DIR=""

STATE_TMP=$(mktemp_tracked /run/pxe-setup.state.XXXXXX)
python3 - "$STATE_TMP" "$ISO_SHA" "$ISO_PATH" "$SHORT_SHA" "$KERNEL_ARGS" <<'PY'
import json, sys, datetime
path, sha, iso, short, args = sys.argv[1:6]
data = {
    "sha256": sha,
    "iso_path": iso,
    "version": short,
    "kernel_args": args,
    "updated_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
}
with open(path, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2)
    f.write("\n")
PY
atomic_install_file "$STATE_TMP" "$STATE_FILE"

log "PXE server setup completed successfully."
printf '\n'
printf '  Interface:      %s (%s)\n' "$IFACE" "$SERVER_IP"
printf '  DHCP mode:      proxy only (no leases, no gateway/DNS changes)\n'
printf '  TFTP root:      %s\n' "$TFTP_ROOT"
printf '  BIOS loader:    pxelinux.0\n'
printf '  UEFI loader:    bootx64.efi -> grubx64.efi (signed shim + signed GRUB)\n'
printf '  NFS live root:  %s\n' "$NFSROOT"
printf '  Kernel args:    %s\n' "$KERNEL_ARGS"
printf '\n'
printf 'Boot the client machine from the network (F12/F11/Esc/UEFI boot menu) and\n'
printf 'choose the "JMX OS - live desktop / installer (NFS)" entry.\n'
printf '\n'
printf 'Notes: the old setup.sh, /var/www/html/ubuntu and /mnt/custom_iso were not\n'
printf 'deleted. Original configs were backed up in: %s\n' "$BACKUP_DIR"
