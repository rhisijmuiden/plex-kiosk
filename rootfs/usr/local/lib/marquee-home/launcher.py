#!/usr/bin/env python3
"""Marquee Home: the home screen on the TV.

Runs as the kiosk user inside cage (started by marquee-session). Shows
ui/index.html fullscreen in a WebKitGTK window and starts the chosen app
(Plex, later Jellyfin and Live TV) as a child process. cage puts the newest
window on top, so the app covers the home screen; when the app closes, the
home screen is visible again.

The Home key brings you back from any app: the Super ("Windows") key, the
Home/HomePage key of remotes and media keyboards, or holding Esc/Back for
2 seconds. Those keys are read straight from /dev/input (the kiosk user is in
the input group), because the app on top has the keyboard focus.
"""
import json
import os
import signal
import socket
import subprocess
import threading
import time
import urllib.request
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("WebKit", "6.0")
from gi.repository import Gdk, Gio, GLib, Gtk, WebKit  # noqa: E402

try:
    import evdev
    from evdev import ecodes
except ImportError:  # the home screen still works, only the Home key does not
    evdev = None

HERE = Path(__file__).resolve().parent
UI = HERE / "ui" / "index.html"
CONF_FILE = Path("/etc/plex-kiosk/plex-kiosk.conf")
TOKEN_FILE = Path("/run/marquee/kiosk-token")
STATE_DIR = Path(GLib.get_user_state_dir()) / "marquee"
LAST_APP = STATE_DIR / "last-app"

# Every app the home screen knows. "available": shipped in this version.
APPS = [
    {"id": "plex", "name": "Plex", "flatpak": "PLEX_APP_ID", "default_flatpak": "tv.plex.PlexHTPC", "available": True},
    {"id": "jellyfin", "name": "Jellyfin", "flatpak": None, "default_flatpak": "org.jellyfin.JellyfinDesktop", "available": False},
    {"id": "livetv", "name": "Live TV", "flatpak": None, "default_flatpak": None, "available": False},
]


def log(msg: str) -> None:
    print(f"marquee-home: {msg}", flush=True)


def read_conf() -> dict:
    conf = {}
    try:
        for line in CONF_FILE.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                conf[k.strip()] = v.strip().strip('"')
    except OSError:
        pass
    return conf


def app_list(conf: dict) -> list:
    enabled = [a.strip() for a in conf.get("HOME_APPS", "plex").split(",") if a.strip()]
    out = []
    for app in APPS:
        if not app["available"]:
            continue
        out.append({"id": app["id"], "name": app["name"], "enabled": app["id"] in enabled,
                    "order": enabled.index(app["id"]) if app["id"] in enabled else 99})
    out.sort(key=lambda a: a["order"])
    return out


def app_command(app_id: str, conf: dict):
    app = next((a for a in APPS if a["id"] == app_id and a["available"]), None)
    if not app:
        return None, None
    flatpak_id = conf.get(app["flatpak"], app["default_flatpak"]) if app["flatpak"] else app["default_flatpak"]
    return ["/usr/bin/flatpak", "run", flatpak_id], flatpak_id


def local_ip() -> str:
    """Address of the interface with the default route ('' when offline). Sends nothing."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("192.0.2.1", 9))
            return s.getsockname()[0]
    except OSError:
        return ""


def admin_call(path: str, body: dict, timeout: float = 300) -> dict:
    """POST to the web admin's kiosk-only endpoints on this machine."""
    port = read_conf().get("ADMIN_PORT", "8080")
    token = TOKEN_FILE.read_text().strip()
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "X-Marquee": "1", "X-Marquee-Kiosk": token})
    with urllib.request.urlopen(req, timeout=timeout) as res:
        return json.loads(res.read() or b"{}")


class AppRunner:
    """Starts one app at a time and notices when it closes."""

    def __init__(self, on_exit):
        self.on_exit = on_exit
        self.proc = None
        self.app_id = None
        self.flatpak_id = None
        self.started = 0.0

    @property
    def running(self) -> bool:
        return self.proc is not None

    def start(self, app_id: str) -> bool:
        if self.proc:
            return False
        conf = read_conf()
        cmd, flatpak_id = app_command(app_id, conf)
        if not cmd:
            return False
        log(f"starting {app_id}: {' '.join(cmd)}")
        try:
            self.proc = subprocess.Popen(cmd, start_new_session=True, stdin=subprocess.DEVNULL)
        except OSError as exc:
            log(f"could not start {app_id}: {exc}")
            GLib.idle_add(self.on_exit, app_id, {"crashed": True})
            return False
        self.app_id, self.flatpak_id, self.started = app_id, flatpak_id, time.monotonic()
        try:
            STATE_DIR.mkdir(parents=True, exist_ok=True)
            LAST_APP.write_text(app_id)
        except OSError:
            pass
        threading.Thread(target=self._wait, args=(self.proc, app_id), daemon=True).start()
        return True

    def _wait(self, proc, app_id):
        rc = proc.wait()
        ran = time.monotonic() - self.started
        log(f"{app_id} closed (exit {rc}, after {ran:.0f}s)")
        self.proc = None
        info = {}
        if rc not in (0, -signal.SIGTERM, -signal.SIGKILL, 143, 137) and ran < 20:
            info["crashed"] = True
        GLib.idle_add(self.on_exit, app_id, info)

    def stop(self):
        """Close the running app: politely first, then firmly."""
        proc = self.proc
        if not proc:
            return
        log(f"closing {self.app_id}")
        if self.flatpak_id:
            subprocess.run(["/usr/bin/flatpak", "kill", self.flatpak_id], capture_output=True, timeout=10)

        def force():
            # flatpak kill normally does it; otherwise SIGTERM, then SIGKILL.
            for sig in (signal.SIGTERM, signal.SIGKILL):
                try:
                    proc.wait(timeout=4)
                    return
                except subprocess.TimeoutExpired:
                    pass
                try:
                    os.killpg(proc.pid, sig)
                except OSError:
                    return
        threading.Thread(target=force, daemon=True).start()


class HomeKeys(threading.Thread):
    """Watches all keyboards and remotes for the Home key."""

    HOLD_SECONDS = 2.0

    def __init__(self, on_home):
        super().__init__(daemon=True, name="home-keys")
        self.on_home = on_home
        self.devices = {}
        self.lock = threading.Lock()
        self.super_clean = False
        self.hold_timer = None
        self.home_keys = {ecodes.KEY_HOMEPAGE}
        self.super_keys = {ecodes.KEY_LEFTMETA, ecodes.KEY_RIGHTMETA}
        self.hold_keys = {ecodes.KEY_ESC, ecodes.KEY_BACK}

    def run(self):
        while True:
            try:
                self.scan()
            except Exception as exc:  # keep watching whatever happens
                log(f"input scan: {exc}")
            time.sleep(3)

    def scan(self):
        for path in evdev.list_devices():
            with self.lock:
                if path in self.devices:
                    continue
            try:
                dev = evdev.InputDevice(path)
            except OSError:
                continue
            keys = set(dev.capabilities().get(ecodes.EV_KEY, []))
            if not keys & (self.home_keys | self.super_keys | self.hold_keys):
                dev.close()
                continue
            with self.lock:
                self.devices[path] = dev
            log(f"watching {dev.name} ({path}) for the Home key")
            threading.Thread(target=self.read, args=(path, dev), daemon=True).start()

    def read(self, path, dev):
        try:
            for ev in dev.read_loop():
                if ev.type == ecodes.EV_KEY:
                    self.key(ev.code, ev.value)
        except OSError:
            pass  # unplugged
        finally:
            with self.lock:
                self.devices.pop(path, None)
            try:
                dev.close()
            except OSError:
                pass

    def key(self, code, value):
        # value: 1 = down, 0 = up, 2 = auto-repeat
        if code in self.home_keys and value == 1:
            self.fire()
        elif code in self.super_keys:
            if value == 1:
                self.super_clean = True
            elif value == 0 and self.super_clean:
                self.fire()  # Super pressed and released on its own
        elif code in self.hold_keys:
            if value == 1:
                self.cancel_hold()
                self.hold_timer = threading.Timer(self.HOLD_SECONDS, self.fire)
                self.hold_timer.start()
            elif value == 0:
                self.cancel_hold()
        elif value == 1:
            self.super_clean = False  # Super used in a combination: not Home
            self.cancel_hold()

    def cancel_hold(self):
        if self.hold_timer:
            self.hold_timer.cancel()
            self.hold_timer = None

    def fire(self):
        self.cancel_hold()
        self.super_clean = False
        GLib.idle_add(self.on_home)


class Home(Gtk.Application):
    def __init__(self):
        super().__init__(application_id="nl.marquee.Home", flags=Gio.ApplicationFlags.NON_UNIQUE)
        self.view = None
        self.runner = AppRunner(self.app_exited)
        self.conf_mtime = 0.0
        self.last_state = None
        self.started_once = False

    def do_activate(self):
        win = Gtk.ApplicationWindow(application=self, title="Marquee")
        manager = WebKit.UserContentManager()
        manager.register_script_message_handler("marquee", None)
        manager.connect("script-message-received::marquee", self.on_message)
        self.view = WebKit.WebView(user_content_manager=manager)
        ink = Gdk.RGBA()
        ink.parse("#0E1116")
        self.view.set_background_color(ink)
        s = self.view.get_settings()
        s.set_enable_developer_extras(False)
        s.set_allow_file_access_from_file_urls(True)
        s.set_enable_back_forward_navigation_gestures(False)
        self.view.connect("context-menu", lambda *a: True)
        self.view.connect("decide-policy", self.on_policy)
        self.view.load_uri(UI.as_uri())
        win.set_child(self.view)
        win.fullscreen()
        win.present()
        GLib.timeout_add_seconds(5, self.refresh)
        if evdev:
            HomeKeys(self.go_home).start()
        else:
            log("python3-evdev missing: the Home key will not work")

    # only our own page may load
    def on_policy(self, view, decision, kind):
        if kind == WebKit.PolicyDecisionType.NAVIGATION_ACTION:
            uri = decision.get_navigation_action().get_request().get_uri()
            if not uri.startswith("file://" + str(HERE)):
                decision.ignore()
                return True
        if kind == WebKit.PolicyDecisionType.NEW_WINDOW_ACTION:
            decision.ignore()
            return True
        return False

    def js(self, fn: str, *args):
        if self.view:
            script = f"window.marquee && window.marquee.{fn}({', '.join(json.dumps(a) for a in args)})"
            self.view.evaluate_javascript(script, -1, None, None, None, None, None)

    def state(self) -> dict:
        conf = read_conf()
        ip = local_ip()
        port = conf.get("ADMIN_PORT", "8080")
        branch = "main"
        try:
            branch = Path("/etc/plex-kiosk/branch").read_text().strip() or "main"
        except OSError:
            pass
        try:
            version = Path("/etc/plex-kiosk/version").read_text().strip()
        except OSError:
            version = "?"
        return {"lang": conf.get("KIOSK_LANG", "en") if conf.get("KIOSK_LANG") in ("en", "nl") else "en",
                "apps": app_list(conf), "version": version, "channel": branch,
                "host": socket.gethostname(), "ip": ip, "admin_url": f"http://{ip}:{port}" if ip else ""}

    def refresh(self):
        """Push settings to the page when the config or the network changed."""
        st = self.state()
        if st != self.last_state:
            self.last_state = st
            self.js("update", st)
        return True

    def on_message(self, manager, value):
        try:
            msg = json.loads(value.to_json(0))
        except (ValueError, AttributeError):
            return
        cmd = msg.get("cmd")
        if cmd == "ready":
            self.last_state = None
            self.refresh()
            if not self.started_once:
                self.started_once = True
                self.autostart()
        elif cmd == "launch":
            if not self.runner.start(str(msg.get("app", ""))):
                if not self.runner.running:
                    self.js("appExited", msg.get("app"), {})
        elif cmd == "check":
            threading.Thread(target=self.check_updates, daemon=True).start()
        elif cmd == "power" and msg.get("action") in ("reboot", "poweroff"):
            threading.Thread(target=self.power, args=(msg["action"],), daemon=True).start()

    def autostart(self):
        """HOME_START: home (stay here), last (last used app) or an app id."""
        conf = read_conf()
        start = conf.get("HOME_START", "home")
        if start == "last":
            try:
                start = LAST_APP.read_text().strip()
            except OSError:
                start = "home"
        if start != "home" and any(a["id"] == start and a["enabled"] for a in app_list(conf)):
            log(f"starting {start} automatically")
            self.js("launch", start)

    def check_updates(self):
        try:
            result = admin_call("/api/kiosk/check", {})
        except Exception as exc:
            log(f"update check failed: {exc}")
            result = {"error": True}
        GLib.idle_add(self.js, "checkResult", result)

    def power(self, action):
        try:
            admin_call("/api/kiosk/power", {"action": action}, timeout=15)
        except Exception as exc:
            log(f"{action} failed: {exc}")
            GLib.idle_add(self.js, "powerFailed")

    def app_exited(self, app_id, info):
        self.js("appExited", app_id, info)
        return False

    def go_home(self):
        if self.runner.running:
            self.runner.stop()
        else:
            self.js("home")
        return False


if __name__ == "__main__":
    raise SystemExit(Home().run(None))
