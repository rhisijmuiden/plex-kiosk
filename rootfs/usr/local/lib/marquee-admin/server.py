#!/usr/bin/env python3
"""Marquee web admin: a small management page for the Plex kiosk.

Standard library only. Runs as root (needed for PAM, apt, systemctl) and
listens on ADMIN_PORT (default 8080). Sign in with a Linux account that is a
member of ADMIN_GROUP (default: sudo), i.e. the admin user from the installer.
"""
import json
import os
import re
import secrets
import shutil
import socket
import subprocess
import threading
import time
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
import glob
import grp
import pwd

import pam_auth

HERE = Path(__file__).resolve().parent
STATIC = HERE / "static"
CONF_FILE = Path("/etc/plex-kiosk/plex-kiosk.conf")
STATE_DIR = Path("/var/lib/marquee-admin")
JOBS_DIR = STATE_DIR / "jobs"
AUTO_FILE = STATE_DIR / "autocheck.json"
# World-readable, so the TV popup (running as the kiosk user) can follow progress.
PUBLIC_DIR = Path("/run/marquee")
UPDATE_STATE = PUBLIC_DIR / "update-state"
POPUP = HERE / "popup.py"
STARTED_AT = time.time()
CTL = "/usr/local/sbin/marquee-ctl"
SESSION_TTL = 12 * 3600
COOKIE = "marquee_session"

MIME = {".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8",
        ".js": "text/javascript; charset=utf-8", ".svg": "image/svg+xml",
        ".png": "image/png", ".json": "application/json", ".ico": "image/x-icon"}

JOB_ACTIONS = {
    "update-all": ["update", "all"],
    "update-system": ["update", "system"],
    "update-plex": ["update", "plex"],
    "update-marquee": ["update", "marquee"],
    "channel-main": ["channel", "main"],
    "channel-test": ["channel", "test"],
}
DIRECT_ACTIONS = {"restart-kiosk", "reboot", "poweroff"}


def read_conf() -> dict:
    conf = {}
    try:
        for line in CONF_FILE.read_text().splitlines():
            m = re.match(r"^\s*([A-Z_]+)=(.*)$", line)
            if m:
                conf[m.group(1)] = m.group(2).strip().strip('"')
    except OSError:
        pass
    return conf


def write_conf(values: dict) -> None:
    """Set KEY=value lines in plex-kiosk.conf, keeping comments and order."""
    try:
        lines = CONF_FILE.read_text().splitlines()
    except OSError:
        lines = []
    todo = dict(values)
    for i, line in enumerate(lines):
        m = re.match(r"^\s*([A-Z_]+)=", line)
        if m and m.group(1) in todo:
            lines[i] = f"{m.group(1)}={todo.pop(m.group(1))}"
    lines += [f"{k}={v}" for k, v in todo.items()]
    tmp = CONF_FILE.with_suffix(".tmp")
    tmp.write_text("\n".join(lines) + "\n")
    os.chmod(tmp, 0o644)
    os.replace(tmp, CONF_FILE)


CHECK_HOURS = (0, 1, 2, 3, 6, 12, 24, 48)


def settings() -> dict:
    conf = read_conf()
    try:
        hours = int(conf.get("UPDATE_CHECK_HOURS", "6"))
    except ValueError:
        hours = 6
    return {
        "check_hours": max(0, min(hours, 168)),
        "popup": conf.get("UPDATE_POPUP", "yes") != "no",
        "kiosk_lang": conf.get("KIOSK_LANG", "en") if conf.get("KIOSK_LANG") in ("en", "nl") else "en",
    }


def save_settings(body: dict) -> dict:
    values = {}
    if "check_hours" in body:
        hours = int(body["check_hours"])
        if not 0 <= hours <= 168:
            raise ValueError("check_hours")
        values["UPDATE_CHECK_HOURS"] = str(hours)
    if "popup" in body:
        values["UPDATE_POPUP"] = "yes" if body["popup"] else "no"
    if "kiosk_lang" in body:
        if body["kiosk_lang"] not in ("en", "nl"):
            raise ValueError("kiosk_lang")
        values["KIOSK_LANG"] = body["kiosk_lang"]
    if values:
        write_conf(values)
    auto.wake.set()
    return settings()


def run(cmd, timeout=30) -> str:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return ""


def read(path, default="") -> str:
    try:
        return Path(path).read_text().strip()
    except OSError:
        return default


# --- sessions ------------------------------------------------------------------
_sessions: dict[str, tuple[str, float]] = {}
_lock = threading.Lock()
_failures: dict[str, list[float]] = {}


def new_session(user: str) -> str:
    token = secrets.token_urlsafe(32)
    with _lock:
        _sessions[token] = (user, time.time() + SESSION_TTL)
    return token


def session_user(token: str | None) -> str | None:
    if not token:
        return None
    with _lock:
        entry = _sessions.get(token)
        if not entry or entry[1] < time.time():
            _sessions.pop(token, None)
            return None
        return entry[0]


def in_admin_group(user: str, group: str) -> bool:
    try:
        g = grp.getgrnam(group)
        pw = pwd.getpwnam(user)
    except KeyError:
        return False
    return user in g.gr_mem or pw.pw_gid == g.gr_gid


def too_many_failures(ip: str) -> bool:
    now = time.time()
    with _lock:
        recent = [t for t in _failures.get(ip, []) if now - t < 300]
        _failures[ip] = recent
        return len(recent) >= 10


def record_failure(ip: str) -> None:
    with _lock:
        _failures.setdefault(ip, []).append(time.time())


# --- status ------------------------------------------------------------------------
def status() -> dict:
    conf = read_conf()
    app = conf.get("PLEX_APP_ID", "tv.plex.PlexHTPC")
    marquee_dir = conf.get("MARQUEE_DIR", "/opt/plex-kiosk")
    plex_info = run(["flatpak", "info", "--system", app])
    plex_version = re.search(r"Version:\s*(\S+)", plex_info)
    kiosk = run(["systemctl", "show", "plex-kiosk.service",
                 "-p", "ActiveState", "-p", "ActiveEnterTimestamp", "-p", "NRestarts"])
    kv = dict(line.split("=", 1) for line in kiosk.splitlines() if "=" in line)
    branch = run(["git", "-C", marquee_dir, "rev-parse", "--abbrev-ref", "HEAD"]) \
        or read("/etc/plex-kiosk/branch", "main")
    commit = run(["git", "-C", marquee_dir, "rev-parse", "--short", "HEAD"])
    du = shutil.disk_usage("/")
    mem = {k: int(v.split()[0]) for k, v in
           (line.split(":", 1) for line in read("/proc/meminfo").splitlines() if ":" in line)}
    temps = []
    for zone in Path("/sys/class/thermal").glob("thermal_zone*/temp"):
        try:
            temps.append(int(zone.read_text()) / 1000)
        except (OSError, ValueError):
            pass
    os_release = dict(re.findall(r'^(\w+)="?([^"\n]*)"?$', read("/etc/os-release"), re.M))
    return {
        "hostname": socket.gethostname(),
        "ips": run(["hostname", "-I"]).split(),
        "os": os_release.get("PRETTY_NAME", "Debian"),
        "kernel": os.uname().release,
        "uptime_s": int(float(read("/proc/uptime", "0").split()[0])),
        "load": os.getloadavg()[0],
        "mem_total_kb": mem.get("MemTotal", 0),
        "mem_avail_kb": mem.get("MemAvailable", 0),
        "disk_total": du.total, "disk_used": du.used,
        "temp_c": max(temps) if temps else None,
        "kiosk": {"state": kv.get("ActiveState", "unknown"),
                  "since": kv.get("ActiveEnterTimestamp", ""),
                  "restarts": int(kv.get("NRestarts", "0") or 0)},
        "plex": {"app": app, "version": plex_version.group(1) if plex_version else None},
        "marquee": {"version": read("/etc/plex-kiosk/version", "?"),
                    "channel": branch, "commit": commit},
    }


# --- jobs -----------------------------------------------------------------------
def start_job(action: str, public_state: bool = False) -> str:
    job_id = time.strftime("%Y%m%d-%H%M%S-") + secrets.token_hex(3)
    JOBS_DIR.mkdir(parents=True, exist_ok=True)
    log = JOBS_DIR / f"{job_id}.log"
    rc = JOBS_DIR / f"{job_id}.rc"
    meta = JOBS_DIR / f"{job_id}.json"
    meta.write_text(json.dumps({"id": job_id, "action": action, "started": time.time()}))
    args = " ".join(JOB_ACTIONS[action])
    script = f'{CTL} {args} > "{log}" 2>&1; r=$?; echo $r > "{rc}"'
    if public_state:
        # The TV popup shows progress from this file.
        PUBLIC_DIR.mkdir(parents=True, exist_ok=True)
        os.chmod(PUBLIC_DIR, 0o755)
        UPDATE_STATE.write_text("running\n")
        os.chmod(UPDATE_STATE, 0o644)
        script += f'; if [ $r = 0 ]; then echo success; else echo failed; fi > "{UPDATE_STATE}"'
    # Run outside this service so a reinstall that restarts the admin keeps going.
    subprocess.run(["systemd-run", f"--unit=marquee-job-{job_id}", "--collect", "--quiet",
                    "/bin/bash", "-c", script], check=True)
    return job_id


def job_info(job_id: str) -> dict | None:
    if not re.fullmatch(r"[0-9]{8}-[0-9]{6}-[0-9a-f]{6}", job_id):
        return None
    meta = JOBS_DIR / f"{job_id}.json"
    if not meta.exists():
        return None
    info = json.loads(meta.read_text())
    rc = read(JOBS_DIR / f"{job_id}.rc")
    log = read(JOBS_DIR / f"{job_id}.log")
    info["log"] = log[-20000:]
    info["state"] = "running" if rc == "" else ("success" if rc == "0" else "failed")
    return info


def latest_jobs(n=10) -> list:
    if not JOBS_DIR.exists():
        return []
    metas = sorted(JOBS_DIR.glob("*.json"), reverse=True)[:n]
    out = []
    for m in metas:
        info = job_info(m.stem)
        if info:
            info.pop("log", None)
            out.append(info)
    return out


_check_cache: dict = {}


def load_auto_state() -> dict:
    try:
        return json.loads(AUTO_FILE.read_text())
    except (OSError, json.JSONDecodeError):
        return {}


def save_auto_state(**changes) -> None:
    data = load_auto_state()
    data.update(changes)
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        AUTO_FILE.write_text(json.dumps(data))
    except OSError:
        pass


def check_updates(automatic: bool = False) -> dict:
    out = run([CTL, "check"], timeout=300)
    try:
        data = json.loads(out)
    except json.JSONDecodeError:
        data = {"error": "Update check failed"}
    data["checked_at"] = time.time()
    data["automatic"] = automatic
    _check_cache.clear()
    _check_cache.update(data)
    changes = {"result": data}
    if automatic:
        changes["last_auto"] = data["checked_at"]
    save_auto_state(**changes)
    return data


def has_news(data: dict) -> bool:
    """Worth a popup: a new Marquee version or a Plex/runtime update.
    (Debian packages alone install themselves every night.)"""
    return (data.get("marquee_behind") or 0) > 0 or (data.get("flatpak") or 0) > 0


def job_running() -> bool:
    return any(j.get("state") == "running" for j in latest_jobs(5))


def kiosk_session():
    """(user, uid, wayland display) of the running cage session, or None."""
    if run(["systemctl", "is-active", "plex-kiosk.service"]) != "active":
        return None
    user = read_conf().get("KIOSK_USER", "kiosk")
    try:
        uid = pwd.getpwnam(user).pw_uid
    except KeyError:
        return None
    sockets = sorted(p for p in glob.glob(f"/run/user/{uid}/wayland-*") if not p.endswith(".lock"))
    if not sockets:
        return None
    return user, uid, os.path.basename(sockets[0])


def media_playing(user: str, uid: int) -> bool:
    """True while an audio stream is running (someone is watching or listening)."""
    out = run(["runuser", "-u", user, "--", "env", f"XDG_RUNTIME_DIR=/run/user/{uid}", "pw-dump"], timeout=10)
    try:
        objects = json.loads(out)
    except json.JSONDecodeError:
        return False
    for obj in objects:
        info = obj.get("info") or {}
        props = info.get("props") or {}
        if str(props.get("media.class", "")).startswith("Stream/Output") and info.get("state") == "running":
            return True
    return False


class AutoUpdater(threading.Thread):
    """Checks for updates every UPDATE_CHECK_HOURS and offers them on the TV."""

    FIRST_DELAY = 300   # leave the device alone for 5 minutes after start
    RETRY = 300         # when the popup can't be shown yet (playing, busy)

    def __init__(self):
        super().__init__(daemon=True, name="auto-update")
        self.wake = threading.Event()
        self.pending = bool(load_auto_state().get("pending"))
        self.next_check = None
        self.next_popup_try = 0.0
        self.popup_open = False
        self.popup_lock = threading.Lock()

    def info(self) -> dict:
        st = load_auto_state()
        return {"next_check": self.next_check, "last_auto": st.get("last_auto"),
                "pending_popup": self.pending, "popup_open": self.popup_open}

    def run(self):
        while True:
            try:
                self.step()
            except Exception as exc:  # never let the scheduler die
                print(f"auto-update: {exc}", flush=True)
            self.wake.wait(60)
            self.wake.clear()

    def step(self):
        cfg = settings()
        hours = cfg["check_hours"]
        now = time.time()
        if hours <= 0:
            self.next_check = None
        else:
            last = load_auto_state().get("last_auto") or 0
            self.next_check = max(last + hours * 3600, STARTED_AT + self.FIRST_DELAY)
            if now >= self.next_check:
                data = check_updates(automatic=True)
                print(f"auto-update: checked, news={has_news(data)}", flush=True)
                self.set_pending(cfg["popup"] and has_news(data))
                self.next_check = data["checked_at"] + hours * 3600
        if self.pending and cfg["popup"] and now >= self.next_popup_try:
            if not self.show_popup(cfg, respect_playback=True):
                self.next_popup_try = now + self.RETRY

    def set_pending(self, value: bool):
        self.pending = value
        save_auto_state(pending=value)

    def show_popup(self, cfg: dict, respect_playback: bool) -> bool:
        """Start the popup on the TV. Returns False when it can't be shown now."""
        if self.popup_open or job_running():
            return False
        session = kiosk_session()
        if not session:
            return False
        user, uid, display = session
        if respect_playback and media_playing(user, uid):
            return False
        data = _check_cache or load_auto_state().get("result") or {}
        st = status_marquee()
        ips = run(["hostname", "-I"]).split()
        port = read_conf().get("ADMIN_PORT", "8080")
        cmd = ["systemd-run", f"--unit=marquee-popup-{int(time.time())}", "--uid", user,
               "--pipe", "--wait", "--collect", "--quiet",
               "-E", f"XDG_RUNTIME_DIR=/run/user/{uid}", "-E", f"WAYLAND_DISPLAY={display}",
               "-E", f"HOME={pwd.getpwnam(user).pw_dir}", "-E", "LANG=C.UTF-8",
               "-E", "GDK_BACKEND=wayland", "-E", "NO_AT_BRIDGE=1", "-E", "GTK_A11Y=none",
               "/usr/bin/python3", str(POPUP),
               "--lang", cfg["kiosk_lang"],
               "--version", str(data.get("marquee_latest") or "") if (data.get("marquee_behind") or 0) > 0 else "",
               "--current", st["version"], "--channel", st["channel"],
               "--plex", str(data.get("flatpak") or 0), "--debian", str(data.get("debian") or 0),
               "--state-file", str(UPDATE_STATE),
               "--admin-url", f"http://{ips[0]}:{port}" if ips else ""]
        try:
            proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                    text=True)  # stderr goes to the journal
        except OSError as exc:
            print(f"auto-update: popup failed: {exc}", flush=True)
            return False
        self.popup_open = True
        self.set_pending(False)
        threading.Thread(target=self._follow, args=(proc,), daemon=True).start()
        return True

    def _follow(self, proc):
        try:
            for line in proc.stdout:
                choice = line.strip()
                if choice == "update":
                    print("auto-update: viewer chose Update now", flush=True)
                    start_job("update-all", public_state=True)
                elif choice == "later":
                    print("auto-update: viewer chose Later", flush=True)
            proc.wait()
        finally:
            self.popup_open = False


def status_marquee() -> dict:
    conf = read_conf()
    marquee_dir = conf.get("MARQUEE_DIR", "/opt/plex-kiosk")
    branch = run(["git", "-C", marquee_dir, "rev-parse", "--abbrev-ref", "HEAD"]) \
        or read("/etc/plex-kiosk/branch", "main")
    return {"version": read("/etc/plex-kiosk/version", "?"), "channel": branch}


auto = AutoUpdater()


# --- HTTP --------------------------------------------------------------------------
class Handler(BaseHTTPRequestHandler):
    server_version = "Marquee"
    sys_version = ""

    def log_message(self, fmt, *args):  # quieter journal
        if not str(args[0]).startswith(("GET /static", "GET /api/jobs/")):
            super().log_message(fmt, *args)

    # helpers
    def _json(self, data, code=200, headers=None):
        body = json.dumps(data).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _token(self):
        cookie = SimpleCookie(self.headers.get("Cookie", ""))
        return cookie[COOKIE].value if COOKIE in cookie else None

    def _user(self):
        return session_user(self._token())

    def _body(self) -> dict:
        length = min(int(self.headers.get("Content-Length", 0) or 0), 65536)
        try:
            return json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            return {}

    def _static(self, rel):
        path = (STATIC / rel).resolve()
        if STATIC.resolve() not in path.parents and path != STATIC.resolve() or not path.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", MIME.get(path.suffix, "application/octet-stream"))
        self.send_header("Content-Length", str(len(data)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.end_headers()
        self.wfile.write(data)

    # routes
    def do_GET(self):
        url = urlparse(self.path)
        if url.path in ("/", "/index.html"):
            return self._static("index.html")
        if url.path.startswith("/static/"):
            return self._static(url.path[len("/static/"):])
        if url.path == "/api/session":
            user = self._user()
            return self._json({"user": user}, 200 if user else 401)
        if not url.path.startswith("/api/"):
            return self.send_error(HTTPStatus.NOT_FOUND)
        if not self._user():
            return self._json({"error": "unauthorized"}, 401)
        if url.path == "/api/status":
            return self._json(status())
        if url.path == "/api/updates":
            return self._json(_check_cache or {})
        if url.path == "/api/settings":
            return self._json({**settings(), "auto": auto.info(), "hours_options": CHECK_HOURS})
        if url.path == "/api/jobs":
            return self._json(latest_jobs())
        if url.path.startswith("/api/jobs/"):
            info = job_info(url.path.rsplit("/", 1)[-1])
            return self._json(info) if info else self._json({"error": "not found"}, 404)
        if url.path == "/api/logs":
            n = int((parse_qs(url.query).get("n") or ["300"])[0])
            n = max(10, min(n, 2000))
            return self._json({"log": run(["journalctl", "-u", "plex-kiosk.service", "-b",
                                           "--no-pager", "-o", "short-iso", "-n", str(n)])})
        return self._json({"error": "not found"}, 404)

    def do_POST(self):
        url = urlparse(self.path)
        # CSRF guard: browsers can't send this custom header cross-site without CORS.
        if self.headers.get("X-Marquee") != "1":
            return self._json({"error": "bad request"}, 400)
        ip = self.client_address[0]

        if url.path == "/api/login":
            if too_many_failures(ip):
                return self._json({"error": "too_many_attempts"}, 429)
            body = self._body()
            user, password = str(body.get("user", "")), str(body.get("password", ""))
            group = read_conf().get("ADMIN_GROUP", "sudo")
            if user and password and in_admin_group(user, group) and pam_auth.authenticate(user, password):
                token = new_session(user)
                cookie = f"{COOKIE}={token}; Path=/; HttpOnly; SameSite=Strict; Max-Age={SESSION_TTL}"
                return self._json({"user": user}, headers={"Set-Cookie": cookie})
            record_failure(ip)
            time.sleep(1.5)
            return self._json({"error": "invalid_login"}, 401)

        if url.path == "/api/logout":
            with _lock:
                _sessions.pop(self._token() or "", None)
            return self._json({"ok": True}, headers={"Set-Cookie": f"{COOKIE}=; Path=/; Max-Age=0"})

        if not self._user():
            return self._json({"error": "unauthorized"}, 401)

        if url.path == "/api/updates/check":
            return self._json(check_updates())

        if url.path == "/api/settings":
            try:
                saved = save_settings(self._body())
            except (TypeError, ValueError):
                return self._json({"error": "invalid settings"}, 400)
            time.sleep(0.2)  # let the scheduler recompute the next check
            return self._json({**saved, "auto": auto.info(), "hours_options": CHECK_HOURS})

        if url.path == "/api/popup/show":
            # Preview / "show it now" from the admin page: ignores playback.
            if auto.popup_open:
                return self._json({"error": "popup_open"}, 409)
            if job_running():
                return self._json({"error": "job_running"}, 409)
            if not auto.show_popup({**settings()}, respect_playback=False):
                return self._json({"error": "no_kiosk"}, 409)
            return self._json({"ok": True})

        if url.path == "/api/action":
            action = str(self._body().get("action", ""))
            if action in JOB_ACTIONS:
                return self._json({"job": start_job(action)})
            if action in DIRECT_ACTIONS:
                self._json({"ok": True})
                subprocess.Popen([CTL, action])
                return None
            return self._json({"error": "unknown action"}, 400)

        return self._json({"error": "not found"}, 404)


def main():
    conf = read_conf()
    port = int(conf.get("ADMIN_PORT", "8080"))
    bind = conf.get("ADMIN_BIND", "0.0.0.0")
    cached = load_auto_state().get("result")
    if cached:
        _check_cache.update(cached)
    auto.start()
    server = ThreadingHTTPServer((bind, port), Handler)
    print(f"Marquee admin listening on http://{bind}:{port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
