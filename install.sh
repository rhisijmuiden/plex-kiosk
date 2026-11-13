#!/usr/bin/env bash
# Marquee - Plex kiosk installer for Debian 13 (trixie), x86_64.
#
# Turns a minimal Debian 13 install into an appliance that boots straight
# into Plex HTPC, fullscreen, with automatic restart and automatic updates.
#
# Usage (as root, from a checkout of this repository):
#   ./install.sh                 interactive confirmation
#   ./install.sh --unattended    no questions (used by the automatic ISO)
#
# Environment overrides:
#   KIOSK_USER   account that runs Plex (default: kiosk)
#   PLEX_APP_ID  Flatpak app id (default: tv.plex.PlexHTPC)

set -euo pipefail

SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KIOSK_USER="${KIOSK_USER:-kiosk}"
PLEX_APP_ID="${PLEX_APP_ID:-tv.plex.PlexHTPC}"
UNATTENDED=0
FORCE=0

log()  { printf '\033[1;33m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;31m!!\033[0m %s\n' "$*" >&2; }
die()  { warn "$*"; exit 1; }

for arg in "$@"; do
  case "$arg" in
    --unattended|-y) UNATTENDED=1 ;;
    --force) FORCE=1 ;;
    -h|--help) sed -n '2,15p' "$0"; exit 0 ;;
    *) die "Unknown option: $arg" ;;
  esac
done

[[ $EUID -eq 0 ]] || die "Run as root (sudo ./install.sh)."
[[ "$(dpkg --print-architecture)" == "amd64" ]] || die "Only amd64 (x86_64) is supported."

# shellcheck disable=SC1091
. /etc/os-release
if [[ "${VERSION_CODENAME:-}" != "trixie" && $FORCE -eq 0 ]]; then
  die "This is ${PRETTY_NAME:-unknown}, expected Debian 13 (trixie). Use --force to continue anyway."
fi

# True when running inside the installer's chroot (no running systemd).
in_chroot() { [[ ! -d /run/systemd/system ]]; }

if [[ $UNATTENDED -eq 0 ]]; then
  echo "This turns this machine into a Plex kiosk: it will auto-login as '$KIOSK_USER'"
  echo "and start Plex fullscreen on every boot."
  read -r -p "Continue? [y/N] " answer
  [[ "$answer" =~ ^[YyJj]$ ]] || exit 1
fi

export DEBIAN_FRONTEND=noninteractive

# --- 1. APT components (contrib, non-free, non-free-firmware) ----------------
log "Enabling contrib, non-free and non-free-firmware components"
if [[ -f /etc/apt/sources.list.d/debian.sources ]]; then
  sed -i -E 's/^Components:.*/Components: main contrib non-free non-free-firmware/' \
    /etc/apt/sources.list.d/debian.sources
fi
if [[ -f /etc/apt/sources.list ]]; then
  sed -i -E '/^deb(-src)?[[:space:]]+[^[:space:]]*(debian|security)/ s/[[:space:]]main([[:space:]].*)?$/ main contrib non-free non-free-firmware/' \
    /etc/apt/sources.list
fi
apt-get update

# --- 2. Packages ----------------------------------------------------------------
# Packages are only installed when apt knows them, so a renamed firmware
# package does not break the whole installation.
WANTED=(
  # kiosk compositor + app runtime
  cage xwayland flatpak dbus-user-session xdg-desktop-portal xdg-desktop-portal-gtk
  # audio (HDMI, analog, USB, Bluetooth-capable)
  pipewire pipewire-pulse pipewire-alsa wireplumber alsa-utils
  # GPU / video decode
  mesa-va-drivers mesa-vulkan-drivers libgl1-mesa-dri vainfo
  intel-media-va-driver-non-free i965-va-driver
  # firmware + microcode for everyday hardware
  firmware-linux-free firmware-misc-nonfree firmware-amd-graphics firmware-intel-graphics
  firmware-realtek firmware-iwlwifi firmware-atheros firmware-brcm80211
  intel-microcode amd64-microcode
  # boot splash
  plymouth plymouth-themes
  # networking + remote management
  network-manager openssh-server ca-certificates curl sudo git
  # web admin
  python3
  # automatic updates
  unattended-upgrades apt-listchanges
  # HDMI-CEC (Pulse-Eight USB adapter or boards with CEC)
  cec-utils
)
INSTALL=()
for p in "${WANTED[@]}"; do
  if apt-cache show "$p" >/dev/null 2>&1; then INSTALL+=("$p"); else warn "Package not available, skipping: $p"; fi
done
log "Installing ${#INSTALL[@]} packages"
apt-get install -y --no-install-recommends "${INSTALL[@]}"

# --- 3. Kiosk user --------------------------------------------------------------
if ! id "$KIOSK_USER" >/dev/null 2>&1; then
  log "Creating user $KIOSK_USER"
  useradd --create-home --shell /bin/bash --comment "Plex kiosk" "$KIOSK_USER"
fi
passwd --lock "$KIOSK_USER" >/dev/null   # no password login; the service starts the session
for g in audio video render input dialout; do
  getent group "$g" >/dev/null && usermod -aG "$g" "$KIOSK_USER"
done
KIOSK_UID="$(id -u "$KIOSK_USER")"

# --- 4. Flatpak + Plex HTPC -----------------------------------------------------
log "Adding Flathub and installing $PLEX_APP_ID"
flatpak remote-add --system --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo
if ! flatpak install --system -y --noninteractive flathub "$PLEX_APP_ID"; then
  warn "Plex install failed now (no network?). It will be retried automatically on first boot."
fi
# Allow access to USB CEC adapters (/dev/ttyACM*) and other devices.
flatpak override --system --device=all "$PLEX_APP_ID"

# --- 5. Configuration files -----------------------------------------------------
log "Installing configuration files"
cp -rT "$SRC_DIR/rootfs" /
chmod 0755 /usr/local/sbin/plex-kiosk-* /usr/local/sbin/marquee-ctl /usr/local/bin/plex-kiosk

install -d -m 0755 /etc/plex-kiosk
if [[ ! -f /etc/plex-kiosk/plex-kiosk.conf ]]; then
  install -m 0644 "$SRC_DIR/defaults/plex-kiosk.conf" /etc/plex-kiosk/plex-kiosk.conf
fi
# Add settings that are new in this version to an existing config.
while IFS= read -r line; do
  [[ "$line" =~ ^([A-Z_]+)= ]] || continue
  grep -q "^${BASH_REMATCH[1]}=" /etc/plex-kiosk/plex-kiosk.conf || echo "$line" >> /etc/plex-kiosk/plex-kiosk.conf
done < "$SRC_DIR/defaults/plex-kiosk.conf"
sed -i -E "s|^KIOSK_USER=.*|KIOSK_USER=$KIOSK_USER|; s|^PLEX_APP_ID=.*|PLEX_APP_ID=$PLEX_APP_ID|; s|^MARQUEE_DIR=.*|MARQUEE_DIR=$SRC_DIR|" \
  /etc/plex-kiosk/plex-kiosk.conf

# Web admin assets in the house style
install -d /usr/local/lib/marquee-admin/static/brand
install -m 0644 "$SRC_DIR/branding/tokens.css" "$SRC_DIR/branding/logo-mark.svg" /usr/local/lib/marquee-admin/static/brand/
install -m 0644 "$SRC_DIR/branding/logo.svg" /usr/local/lib/marquee-admin/static/brand/logo-dark.svg
install -d -m 0700 /var/lib/marquee-admin

# Make the install directory a git checkout so Marquee can update itself and
# switch between production (main) and test. Fails quietly for private repos.
if ! git -C "$SRC_DIR" rev-parse --git-dir >/dev/null 2>&1; then
  # shellcheck disable=SC1091
  REPO="$(. /etc/plex-kiosk/plex-kiosk.conf; echo "${MARQUEE_REPO:-}")"
  if [[ -n "$REPO" ]] && git -C "$SRC_DIR" init -q -b main \
      && git -C "$SRC_DIR" remote add origin "$REPO" \
      && git -C "$SRC_DIR" fetch -q --depth 50 origin main; then
    git -C "$SRC_DIR" reset -q origin/main      # keep files, adopt history
    git -C "$SRC_DIR" branch -q --set-upstream-to=origin/main main || true
    log "Linked $SRC_DIR to $REPO for self-updates"
  else
    rm -rf "$SRC_DIR/.git"
    warn "Could not reach $REPO; Marquee self-update is disabled (Debian and Plex updates still work)."
  fi
fi
cp "$SRC_DIR/VERSION" /etc/plex-kiosk/version
git -C "$SRC_DIR" rev-parse --abbrev-ref HEAD 2>/dev/null > /etc/plex-kiosk/branch || echo main > /etc/plex-kiosk/branch

# The kiosk unit needs the real user name and UID, so it is generated here.
cat > /etc/systemd/system/plex-kiosk.service <<EOF
[Unit]
Description=Marquee Plex kiosk (cage + Plex HTPC on tty1)
Documentation=https://github.com/rhisijmuiden/plex-kiosk
After=systemd-user-sessions.service plymouth-quit-wait.service network-online.target
Wants=network-online.target
After=getty@tty1.service
Conflicts=getty@tty1.service
# 5 failed starts within 5 minutes: stop retrying and show a login prompt with the error.
StartLimitIntervalSec=300
StartLimitBurst=5
OnFailure=plex-kiosk-fallback.service

[Service]
Type=simple
User=$KIOSK_USER
PAMName=plex-kiosk
TTYPath=/dev/tty1
TTYReset=yes
TTYVHangup=yes
TTYVTDisallocate=yes
StandardInput=tty-fail
StandardOutput=journal
StandardError=journal
UtmpIdentifier=tty1
UtmpMode=user
# No capabilities at all for the kiosk session: Flatpak's bwrap refuses to run
# ("Unexpected capabilities but not setuid") when it inherits any.
CapabilityBoundingSet=
AmbientCapabilities=
Environment=XDG_SESSION_TYPE=wayland
# Allow software rendering on GPUs without a working 3D driver.
Environment=WLR_RENDERER_ALLOW_SOFTWARE=1
Environment=XDG_RUNTIME_DIR=/run/user/$KIOSK_UID
Environment=DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/$KIOSK_UID/bus
EnvironmentFile=-/etc/plex-kiosk/plex-kiosk.conf
# Chosen GPU on PCs with more than one (written by plex-kiosk-gpu below).
EnvironmentFile=-/run/plex-kiosk/gpu.env
# Runs as root ('+'): installs Plex if it is missing (e.g. no network during install).
ExecStartPre=+/usr/local/sbin/plex-kiosk-ensure-app
ExecStartPre=+/usr/local/sbin/plex-kiosk-gpu
ExecStart=/usr/bin/cage -d -s -- /usr/bin/flatpak run \${PLEX_APP_ID}
Restart=always
RestartSec=3
TimeoutStartSec=15min

[Install]
WantedBy=graphical.target
EOF

# --- 6. Boot: quiet, no menu, splash -------------------------------------------
log "Configuring boot splash and GRUB"
install -d /usr/share/plymouth/themes/marquee
cp -r "$SRC_DIR/branding/plymouth/." /usr/share/plymouth/themes/marquee/
plymouth-set-default-theme marquee || warn "Could not set Plymouth theme"
update-initramfs -u || warn "update-initramfs failed"
update-grub || warn "update-grub failed"

# --- 7. Services ----------------------------------------------------------------
log "Enabling services"
systemctl set-default graphical.target
systemctl enable plex-kiosk.service plex-kiosk-flatpak-update.timer marquee-admin.service \
  unattended-upgrades.service NetworkManager.service ssh.service
systemctl disable getty@tty1.service 2>/dev/null || true

if ! in_chroot; then
  systemctl daemon-reload
  systemctl restart marquee-admin.service || warn "Web admin did not start; see: journalctl -u marquee-admin"
  systemctl restart plex-kiosk.service || warn "Kiosk did not start; see: journalctl -u plex-kiosk"
fi

log "Done. Marquee $(cat "$SRC_DIR/VERSION") installed. Web admin: http://$(hostname -I 2>/dev/null | awk '{print $1}'):8080"
