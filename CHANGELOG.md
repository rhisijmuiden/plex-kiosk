# Changelog

## 0.4.1 - 2026-11-27
- NO-Flix as an optional app on the home screen. Enter your NO-Flix server's
  address on the admin's *Home screen* page and press Install: Marquee
  downloads the Linux app from the server's download page (checksum checked),
  installs the libraries it needs and keeps its sign-in on the device. Switch
  it on in the app list; the Home key closes it like any other app.

## 0.4.0 - 2026-11-22
- New TV home screen: the TV now starts in a Marquee start page with big tiles
  to choose an app (Plex for now; Jellyfin and Live TV follow in 0.5.0 and
  0.6.0). Works with arrow keys + OK, remotes that send keyboard keys, and the
  mouse. English and Dutch (follows the TV language setting).
- Back to the home screen from any app with the Windows key, a remote's Home
  key, or by holding Esc for two seconds.
- Settings, Info (version + update check) and Power (restart / turn off) on
  the TV.
- Web admin: new *Home screen* page to choose the apps and their order, what
  opens at start (home screen, last used app or Plex), or switch the home
  screen off to go straight into Plex like before.
- If the home screen can't start, the TV opens Plex directly so it keeps working.

## 0.3.0 - 2026-11-21
- Automatic update check: every 6 hours by default (1-48 hours or off, set on
  the admin's Updates page). Follows the selected channel (Production / Test).
- When a new Marquee version or a Plex update is found, a popup appears on the
  TV with "Update now" and "Later". Works with the keyboard and remotes that
  send arrow/OK/Back keys. It waits while something is playing and closes by
  itself after 90 seconds when nobody responds. "Update now" shows progress
  on the TV; Plex comes back by itself afterwards.
- Admin: TV language setting (English/Dutch) and a "Show popup on TV now"
  button to try it out.

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
