#!/usr/bin/env python3
"""Marquee TV popup: "a new version is available" on the kiosk screen.

Started by the web admin (as the kiosk user, inside the running cage session)
when the automatic update check finds something new. cage shows the newest
window on top, so this covers Plex until it is closed; Plex keeps running
underneath and gets the screen back afterwards.

Controls: arrow keys / Tab to move, Enter / OK to choose, Esc / Back = Later.
Anything a TV remote sends as keyboard keys works (USB/IR remotes, air mice).

Output (stdout, one line each):
  update   the viewer chose "Update now" (the popup then shows progress)
  later    the viewer chose "Later", pressed Back, or the popup timed out
"""
import argparse
import sys
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, GLib, Gtk  # noqa: E402

HERE = Path(__file__).resolve().parent
MARK = HERE / "static" / "brand" / "logo-mark.svg"

T = {
    "en": {
        "eyebrow": "Update available",
        "title_version": "Marquee {v} is ready",
        "title_plain": "New updates are ready",
        "item_marquee": "Marquee {cur} → {v}",
        "item_plex": "Plex: {n} update(s)",
        "item_debian": "System: {n} update(s)",
        "channel_main": "Channel: Production",
        "channel_test": "Channel: Test",
        "body": "Updating takes a few minutes. Plex closes during the update and comes back by itself.",
        "now": "Update now",
        "later": "Later",
        "hint": "← → to choose · OK to confirm · Back for later",
        "closes": "Closes in {s} s",
        "busy_title": "Updating…",
        "busy_body": "Please don't turn off the device. Plex restarts by itself when the update is done.",
        "done_title": "Update complete",
        "done_body": "Returning to Plex…",
        "fail_title": "The update did not finish",
        "fail_body": "Plex keeps working. See the web admin for details: {url}",
        "ok": "OK",
    },
    "nl": {
        "eyebrow": "Update beschikbaar",
        "title_version": "Marquee {v} staat klaar",
        "title_plain": "Er staan nieuwe updates klaar",
        "item_marquee": "Marquee {cur} → {v}",
        "item_plex": "Plex: {n} update(s)",
        "item_debian": "Systeem: {n} update(s)",
        "channel_main": "Kanaal: Productie",
        "channel_test": "Kanaal: Test",
        "body": "Bijwerken duurt een paar minuten. Plex sluit tijdens de update en komt daarna vanzelf terug.",
        "now": "Nu bijwerken",
        "later": "Later",
        "hint": "← → om te kiezen · OK om te bevestigen · Terug voor later",
        "closes": "Sluit over {s} s",
        "busy_title": "Bezig met bijwerken…",
        "busy_body": "Zet het apparaat niet uit. Plex start vanzelf opnieuw als de update klaar is.",
        "done_title": "Update voltooid",
        "done_body": "Terug naar Plex…",
        "fail_title": "De update is niet gelukt",
        "fail_body": "Plex blijft gewoon werken. Kijk in de webbeheerpagina voor details: {url}",
        "ok": "OK",
    },
}

CSS = """
window.marquee { background-color: rgba(14, 17, 22, 0.94); color: #E8EAED;
  font-family: Inter, "Inter Variable", system-ui, sans-serif; }
.card { background-color: #171B22; border: 1px solid #2A3140; border-radius: 28px;
  padding: 56px 64px; box-shadow: 0 24px 64px rgba(0,0,0,.55); }
.eyebrow { color: #F5A524; font-size: 22px; font-weight: 700; letter-spacing: 2px; }
.title { font-size: 52px; font-weight: 800; letter-spacing: -1px; }
.body { color: #8B93A1; font-size: 24px; }
.item { font-size: 26px; }
.item-dot { color: #FF6B5A; font-size: 26px; }
.meta { color: #8B93A1; font-size: 20px; }
.mono { font-family: "JetBrains Mono", "DejaVu Sans Mono", monospace; }
button.mq { font-size: 28px; font-weight: 700; padding: 20px 44px; border-radius: 16px;
  background-image: none; background-color: #202632; color: #E8EAED;
  border: 3px solid transparent; box-shadow: none; min-width: 260px; }
button.mq.primary { background-color: #F5A524; color: #0E1116; }
button.mq:focus, button.mq:focus-visible, button.mq:hover { border-color: #FFFFFF;
  outline: 4px solid rgba(245,165,36,.55); outline-offset: 4px; }
button.mq.primary:focus, button.mq.primary:hover { background-color: #FFB743; }
.hint { color: #8B93A1; font-size: 18px; }
.fail { color: #F2555A; }
.ok { color: #3DD68C; }
spinner.big { min-width: 72px; min-height: 72px; color: #F5A524; }
"""


def label(text, css, wrap=False, xalign=0.0):
    w = Gtk.Label(label=text, xalign=xalign)
    for c in css.split():
        w.add_css_class(c)
    if wrap:
        w.set_wrap(True)
        w.set_max_width_chars(46)
    return w


class Popup(Gtk.Application):
    def __init__(self, args):
        super().__init__(application_id=None)
        self.a = args
        self.t = T.get(args.lang, T["en"])
        self.left = args.timeout
        self.chosen = False
        self.connect("activate", self.on_activate)

    # -- helpers -------------------------------------------------------------
    def emit(self, word):
        print(word, flush=True)

    def finish(self, word):
        if not self.chosen:
            self.chosen = True
            self.emit(word)
        self.quit()

    # -- build ---------------------------------------------------------------
    def on_activate(self, app):
        provider = Gtk.CssProvider()
        provider.load_from_data(CSS.encode())
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        win = Gtk.ApplicationWindow(application=app, title="Marquee update")
        win.add_css_class("marquee")
        win.set_decorated(False)
        win.set_default_size(1920, 1080)
        self.win = win

        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE,
                               vhomogeneous=False, interpolate_size=True)
        self.stack.add_named(self.build_offer(), "offer")
        self.stack.add_named(self.build_busy(), "busy")
        self.stack.add_named(self.build_result(), "result")

        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, halign=Gtk.Align.CENTER,
                       valign=Gtk.Align.CENTER)
        card.add_css_class("card")
        card.set_size_request(900, -1)
        card.append(self.stack)
        win.set_child(card)

        keys = Gtk.EventControllerKey()
        keys.connect("key-pressed", self.on_key)
        win.add_controller(keys)
        win.connect("close-request", lambda *_: (self.finish("later"), True)[1])

        win.fullscreen()
        win.present()
        self.btn_now.grab_focus()
        if self.left > 0:
            GLib.timeout_add_seconds(1, self.tick)

    def build_offer(self):
        t, a = self.t, self.a
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20)
        head = Gtk.Box(spacing=28)
        if MARK.exists():
            pic = Gtk.Picture.new_for_filename(str(MARK))
            pic.set_size_request(104, 104)
            pic.set_can_shrink(True)
            head.append(pic)
        titles = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, valign=Gtk.Align.CENTER)
        titles.append(label(t["eyebrow"].upper(), "eyebrow"))
        title = t["title_version"].format(v=a.version) if a.version else t["title_plain"]
        titles.append(label(title, "title", wrap=True))
        head.append(titles)
        box.append(head)

        items = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, margin_top=12)
        rows = []
        if a.version:
            rows.append(t["item_marquee"].format(cur=a.current or "?", v=a.version))
        if a.plex > 0:
            rows.append(t["item_plex"].format(n=a.plex))
        if a.debian > 0:
            rows.append(t["item_debian"].format(n=a.debian))
        for r in rows:
            row = Gtk.Box(spacing=16)
            row.append(label("●", "item-dot"))
            row.append(label(r, "item"))
            items.append(row)
        box.append(items)
        box.append(label(t["body"], "body", wrap=True))
        box.append(label(t["channel_test" if a.channel == "test" else "channel_main"], "meta"))

        btns = Gtk.Box(spacing=24, margin_top=24)
        self.btn_now = Gtk.Button(label=t["now"])
        self.btn_now.add_css_class("mq")
        self.btn_now.add_css_class("primary")
        self.btn_now.connect("clicked", self.on_update)
        self.btn_later = Gtk.Button(label=t["later"])
        self.btn_later.add_css_class("mq")
        self.btn_later.connect("clicked", lambda *_: self.finish("later"))
        btns.append(self.btn_now)
        btns.append(self.btn_later)
        box.append(btns)

        foot = Gtk.Box(spacing=24, margin_top=8)
        foot.append(label(t["hint"], "hint"))
        spacer = Gtk.Box(hexpand=True)
        foot.append(spacer)
        self.countdown = label("", "hint")
        foot.append(self.countdown)
        box.append(foot)
        self.update_countdown()
        return box

    def build_busy(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24)
        top = Gtk.Box(spacing=28)
        spin = Gtk.Spinner(spinning=True)
        spin.add_css_class("big")
        top.append(spin)
        top.append(label(self.t["busy_title"], "title"))
        box.append(top)
        box.append(label(self.t["busy_body"], "body", wrap=True))
        return box

    def build_result(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24)
        self.res_title = label("", "title", wrap=True)
        self.res_body = label("", "body", wrap=True)
        box.append(self.res_title)
        box.append(self.res_body)
        self.btn_ok = Gtk.Button(label=self.t["ok"], halign=Gtk.Align.START, margin_top=16)
        self.btn_ok.add_css_class("mq")
        self.btn_ok.add_css_class("primary")
        self.btn_ok.connect("clicked", lambda *_: self.quit())
        box.append(self.btn_ok)
        return box

    # -- behaviour -----------------------------------------------------------
    def update_countdown(self):
        self.countdown.set_text(self.t["closes"].format(s=self.left) if self.left > 0 else "")

    def tick(self):
        if self.chosen:
            return False
        self.left -= 1
        self.update_countdown()
        if self.left <= 0:
            self.finish("later")
            return False
        return True

    def on_key(self, _ctrl, keyval, _code, _state):
        name = Gdk.keyval_name(keyval) or ""
        page = self.stack.get_visible_child_name()
        if name in ("Escape", "Back", "XF86Back", "BackSpace"):
            if page == "offer":
                self.finish("later")
            elif page == "result":
                self.quit()
            return True
        # Any key stops the auto-close countdown: someone is watching.
        if page == "offer" and self.left > 0:
            self.left = 0
            self.update_countdown()
        if page == "offer" and name in ("Left", "Right", "Up", "Down"):
            target = self.btn_now if name in ("Left", "Up") else self.btn_later
            target.grab_focus()
            return True
        return False

    def on_update(self, *_):
        if self.chosen:
            return
        self.chosen = True
        self.emit("update")
        if not self.a.state_file:
            self.quit()
            return
        self.stack.set_visible_child_name("busy")
        GLib.timeout_add_seconds(2, self.poll)

    def poll(self):
        try:
            st = Path(self.a.state_file).read_text().strip()
        except OSError:
            st = "running"
        if st == "running" or st == "":
            return True
        if st == "success":
            self.res_title.set_text(self.t["done_title"])
            self.res_title.add_css_class("ok")
            self.res_body.set_text(self.t["done_body"])
            self.btn_ok.set_visible(False)
            self.stack.set_visible_child_name("result")
            GLib.timeout_add_seconds(4, lambda: (self.quit(), False)[1])
        else:
            self.res_title.set_text(self.t["fail_title"])
            self.res_title.add_css_class("fail")
            self.res_body.set_text(self.t["fail_body"].format(url=self.a.admin_url or "http://<device>:8080"))
            self.stack.set_visible_child_name("result")
            self.btn_ok.grab_focus()
        return False


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--lang", default="en")
    p.add_argument("--version", default="", help="new Marquee version, empty when only Plex/system")
    p.add_argument("--current", default="")
    p.add_argument("--channel", default="main")
    p.add_argument("--plex", type=int, default=0)
    p.add_argument("--debian", type=int, default=0)
    p.add_argument("--timeout", type=int, default=90, help="auto-close after N seconds (0 = never)")
    p.add_argument("--state-file", default="", help="file with running/success/failed for progress")
    p.add_argument("--admin-url", default="")
    args = p.parse_args()
    app = Popup(args)
    app.run([])
    if not app.chosen:
        print("later", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
