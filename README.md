<p align="center"><img src="branding/png/logo-840.png" width="420" alt="Marquee"></p>

# Marquee: Debian 13 Plex kiosk

**English** · [Nederlands](README.nl.md)

Marquee turns an everyday x86 PC (Intel or AMD, old desktops and mini PCs
included) into a Plex appliance: power on, a short splash screen, and
**Plex HTPC starts fullscreen**. No desktop, no login screen.

## What you get

| | |
|---|---|
| OS | Debian 13 "trixie", minimal |
| Plex client | [Plex HTPC](https://flathub.org/apps/tv.plex.PlexHTPC) from Flathub (TV interface, remote/keyboard friendly) |
| Kiosk | [`cage`](https://github.com/cage-kiosk/cage) Wayland kiosk compositor, started by `plex-kiosk.service` on tty1 |
| Self-healing | Plex crashes or is closed: restarted within 3 seconds (`Restart=always`) |
| Audio | PipeWire + WirePlumber (HDMI, analog, USB) |
| Video | Mesa VA-API drivers for Intel and AMD hardware decoding |
| Updates | Debian: `unattended-upgrades` daily, reboot at 04:00 only when needed. Plex: nightly at 03:30, kiosk restarts only when Plex actually changed |
| Boot | GRUB menu hidden, Marquee splash (Plymouth) |
| Remote management | SSH as the admin user, `plex-kiosk` helper command |
| HDMI-CEC | Supported with a Pulse-Eight USB-CEC adapter (most PC GPUs have no CEC) |

<p align="center"><img src="docs/splash-preview.png" width="480" alt="Boot splash"></p>

## Hardware

- 64-bit x86 CPU (Intel Core 4th gen / AMD Ryzen or newer recommended for 4K/HEVC hardware decoding; older works for 1080p)
- 2 GB RAM minimum, 4 GB recommended
- 16 GB storage minimum
- Wired network during installation (Wi-Fi can be set up afterwards)
- NVIDIA: works with the open `nouveau` driver, but hardware decoding is limited. Intel/AMD are recommended.

## Option A: automatic installer ISO (recommended)

> **Warning:** the automatic entry **erases the first internal disk** without asking.

1. Build the ISO (on any Linux machine with `xorriso` and `curl`):
   ```bash
   git clone https://github.com/rhisijmuiden/plex-kiosk && cd plex-kiosk
   iso/build-iso.sh                       # installer asks the admin password once
   # or: iso/build-iso.sh --password --ssh-key ~/.ssh/id_ed25519.pub
   ```
   The ISO lands in `build/marquee-<version>-amd64.iso`. Tagged releases
   (`v*`) also get a ready-made ISO attached by GitHub Actions.
2. Write it to a USB stick (balenaEtcher, Rufus in DD mode, or
   `sudo dd if=build/marquee-*.iso of=/dev/sdX bs=4M status=progress conv=fsync`).
3. Boot the PC from the stick. After 10 seconds the automatic install starts.
   Choose *manual* (BIOS) or a regular entry (UEFI) for the normal Debian installer.
4. Enter the admin password when asked, wait about 10 to 20 minutes, the PC reboots into Plex.

## Option B: install script on an existing Debian 13

Install Debian 13 with no desktop environment ("standard system utilities" and
"SSH server" only), then:

```bash
sudo apt install -y git
git clone https://github.com/rhisijmuiden/plex-kiosk /opt/plex-kiosk
sudo /opt/plex-kiosk/install.sh
sudo reboot
```

## First start

Plex HTPC asks you to sign in once (it shows a code to enter at
<https://plex.tv/link>). After that it remembers your account.

## Everyday management

Over SSH (`ssh admin@plex-kiosk.local` or the IP address):

| Command | Does |
|---|---|
| `plex-kiosk status` | Is the kiosk running? |
| `plex-kiosk restart` | Restart Plex |
| `plex-kiosk logs` | Kiosk log of this boot |
| `plex-kiosk update` | Update Debian and Plex now |
| `plex-kiosk version` | Marquee and Plex version |
| `sudo nmtui` | Set up Wi-Fi |

Local console: `Ctrl+Alt+F2` gives a login prompt, `Ctrl+Alt+F1` returns to Plex.

Settings: `/etc/plex-kiosk/plex-kiosk.conf`.

## Branches

- `main`: production, what you install on your TVs.
- `test`: new changes land here first.

Switch a device: `cd /opt/plex-kiosk && sudo git checkout test && sudo ./install.sh -y`.

## House style

See [`branding/BRAND.md`](branding/BRAND.md). Regenerate PNGs with
`python3 branding/render.py`.

## Troubleshooting

| Problem | Fix |
|---|---|
| Black screen, no Plex | `plex-kiosk logs`. On first boot without network Plex is installed in the background; wait a few minutes. |
| No sound over HDMI | In Plex HTPC: *Settings > Audio* and pick the HDMI device. |
| Stuttering 4K | Check hardware decoding: `vainfo` must list your GPU. |
| Splash not shown | Some old GPUs only show it after the driver loads; harmless. |

## Repository layout

```
install.sh                turns Debian 13 into the kiosk
defaults/                 default config
rootfs/                   files copied onto the system (systemd, PAM, apt, grub, helpers)
iso/preseed.cfg           automatic installer answers
iso/build-iso.sh          builds the installer ISO
branding/                 Marquee house style + Plymouth theme
.github/workflows/        lint + ISO builds
```
