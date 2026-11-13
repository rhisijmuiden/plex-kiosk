# Changelog

## 0.2.2 - 2026-11-13
- PCs with two GPUs: the kiosk now picks the GPU the TV is connected to, and
  prefers Intel/AMD over NVIDIA's nouveau driver. Override with `KIOSK_GPU` in
  `/etc/plex-kiosk/plex-kiosk.conf`.
- Docs: hardware advice for older NVIDIA cards (use the CPU's graphics instead).

## 0.2.1 - 2026-11-13
- Fix: Plex never appeared (black screen) because Flatpak's bwrap refused to
  start with inherited capabilities. The kiosk session now runs with none.
- No more silent black screen: while Plex downloads on the first start the TV
  shows a message, and when the kiosk fails 5 times within 5 minutes it falls
  back to a login prompt that shows the error and the web admin address.
- Software rendering allowed as a fallback for GPUs without a working 3D driver.
- New `sudo plex-kiosk repair` command: reinstalls Marquee and restarts Plex.
- CI installs Marquee in a clean Debian 13 container on every change.

## 0.2.0 - 2026-11-13
- Web admin on port 8080 (sign in with the installer's admin account): status
  dashboard, update check and install for Debian, Plex and Marquee, switch
  between production (`main`) and test, kiosk log, restart/reboot/shut down,
  Info dialog. English with Dutch translation, Marquee house style.
- Installer never picks a USB disk as target, so ISO-boot sticks (Ventoy, IODD)
  are safe.
- Install directory becomes a git checkout for self-updates.

## 0.1.0 - 2026-11-13
- First version: automatic Debian 13 installer ISO, install script, cage kiosk
  with Plex HTPC, auto-restart, PipeWire audio, nightly updates, Marquee house
  style and boot splash.
