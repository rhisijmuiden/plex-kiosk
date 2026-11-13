#!/usr/bin/env bash
# Builds an automatic Marquee installer ISO from the official Debian 13 netinst ISO.
#
#   iso/build-iso.sh [options]
#     --iso FILE          use a local Debian 13 netinst ISO instead of downloading
#     --out FILE          output path (default: build/marquee-<version>-amd64.iso)
#     --password          ask for the admin password now and bake its hash in
#                         (default: the installer asks for it once)
#     --admin-user NAME   admin account (default: admin)
#     --hostname NAME     hostname (default: plex-kiosk)
#     --keymap MAP        keyboard layout (default: us)
#     --ssh-key FILE      public key added to the admin user's authorized_keys
#
# Requires: xorriso, curl, sha256sum, openssl (for --password)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VERSION="$(cat "$ROOT/VERSION")"
MIRROR="${DEBIAN_CD_MIRROR:-https://cdimage.debian.org/debian-cd/current/amd64/iso-cd}"
ISO=""; OUT=""; ASK_PW=0; ADMIN_USER="admin"; HOSTNAME_=plex-kiosk; KEYMAP=us; SSH_KEY=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --iso) ISO="$2"; shift 2 ;;
    --out) OUT="$2"; shift 2 ;;
    --password) ASK_PW=1; shift ;;
    --admin-user) ADMIN_USER="$2"; shift 2 ;;
    --hostname) HOSTNAME_="$2"; shift 2 ;;
    --keymap) KEYMAP="$2"; shift 2 ;;
    --ssh-key) SSH_KEY="$2"; shift 2 ;;
    -h|--help) sed -n '2,14p' "$0"; exit 0 ;;
    *) echo "Unknown option: $1" >&2; exit 1 ;;
  esac
done

for t in xorriso curl sha256sum; do command -v "$t" >/dev/null || { echo "Missing tool: $t" >&2; exit 1; }; done

BUILD="$ROOT/build"; mkdir -p "$BUILD"
OUT="${OUT:-$BUILD/marquee-$VERSION-amd64.iso}"
WORK="$(mktemp -d)"; trap 'rm -rf "$WORK"' EXIT

# 1. Get the official netinst ISO (verified against Debian's SHA256SUMS)
if [[ -z "$ISO" ]]; then
  curl -fsSL "$MIRROR/SHA256SUMS" -o "$BUILD/SHA256SUMS"
  NAME="$(awk '/debian-13[.0-9]*-amd64-netinst\.iso$/{print $2; exit}' "$BUILD/SHA256SUMS")"
  [[ -n "$NAME" ]] || { echo "No Debian 13 netinst ISO found at $MIRROR" >&2; exit 1; }
  ISO="$BUILD/$NAME"
  if [[ ! -f "$ISO" ]]; then
    echo "Downloading $NAME"
    curl -fL --progress-bar "$MIRROR/$NAME" -o "$ISO.part" && mv "$ISO.part" "$ISO"
  fi
  (cd "$BUILD" && grep " $NAME\$" SHA256SUMS | sha256sum -c -)
fi

# 2. Payload: this repository (without build output and git metadata)
mkdir -p "$WORK/plex-kiosk"
tar -C "$ROOT" --exclude=./build --exclude=./.git -cf - . | tar -C "$WORK/plex-kiosk" -xf -
if [[ -n "$SSH_KEY" ]]; then
  install -D -m 0644 "$SSH_KEY" "$WORK/plex-kiosk/defaults/authorized_keys"
fi

# 3. Preseed
if [[ $ASK_PW -eq 1 ]]; then
  read -r -s -p "Admin password: " p1; echo; read -r -s -p "Repeat: " p2; echo
  [[ "$p1" == "$p2" && -n "$p1" ]] || { echo "Passwords do not match" >&2; exit 1; }
  HASH="$(openssl passwd -6 -stdin <<<"$p1")"
  PW_LINE="d-i passwd/user-password-crypted password $HASH"
else
  PW_LINE="# admin password: asked by the installer"
fi
sed -e "s|@@HOSTNAME@@|$HOSTNAME_|g" -e "s|@@ADMIN_USER@@|$ADMIN_USER|g" -e "s|@@KEYMAP@@|$KEYMAP|g" \
    "$ROOT/iso/preseed.cfg" > "$WORK/preseed.cfg"
# Password hash contains '$' and '/', so insert it without sed.
awk -v line="$PW_LINE" '{ if ($0=="@@PASSWORD_LINE@@") print line; else print }' "$WORK/preseed.cfg" > "$WORK/preseed.tmp"
mv "$WORK/preseed.tmp" "$WORK/preseed.cfg"
if [[ -n "$SSH_KEY" ]]; then
  sed -i "s|in-target bash /opt/plex-kiosk/install.sh --unattended|in-target install -D -m 0600 -o 1000 -g 1000 /opt/plex-kiosk/defaults/authorized_keys /home/$ADMIN_USER/.ssh/authorized_keys; in-target chown 1000:1000 /home/$ADMIN_USER/.ssh; &|" "$WORK/preseed.cfg"
fi

# 4. Boot menus: automatic install as default entry (BIOS + UEFI)
KARGS="auto=true priority=critical preseed/file=/cdrom/preseed.cfg locale=en_US.UTF-8 keymap=$KEYMAP hostname=$HOSTNAME_ domain=local"
xorriso -osirrox on -indev "$ISO" -extract /boot/grub/grub.cfg "$WORK/grub.orig" >/dev/null 2>&1
chmod u+w "$WORK/grub.orig"
{
  echo 'set default=0'
  echo 'set timeout=10'
  echo 'menuentry "Marquee Plex kiosk - automatic install (ERASES the internal disk)" {'
  echo "    linux /install.amd/vmlinuz $KARGS quiet ---"
  echo '    initrd /install.amd/initrd.gz'
  echo '}'
  cat "$WORK/grub.orig"
} > "$WORK/grub.cfg"

cat > "$WORK/isolinux.cfg" <<ISOLINUX
default marquee
prompt 1
timeout 100
say Marquee Plex kiosk: automatic install in 10 seconds (ERASES the internal disk). Type 'manual' for the normal installer.
label marquee
  kernel /install.amd/vmlinuz
  append initrd=/install.amd/initrd.gz $KARGS vga=788 quiet ---
label manual
  kernel /install.amd/vmlinuz
  append initrd=/install.amd/initrd.gz vga=788 ---
ISOLINUX

# 5. Write the new ISO, keeping Debian's BIOS/UEFI hybrid boot setup
rm -f "$OUT"
xorriso -indev "$ISO" -outdev "$OUT" \
  -map "$WORK/preseed.cfg" /preseed.cfg \
  -map "$WORK/plex-kiosk" /plex-kiosk \
  -map "$WORK/grub.cfg" /boot/grub/grub.cfg \
  -map "$WORK/isolinux.cfg" /isolinux/isolinux.cfg \
  -rm_r /md5sum.txt -- \
  -boot_image any replay
(cd "$(dirname "$OUT")" && sha256sum "$(basename "$OUT")" > "$(basename "$OUT").sha256")
echo "Built: $OUT"
