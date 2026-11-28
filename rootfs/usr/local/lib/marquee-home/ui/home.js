// Marquee Home - TV home screen front-end.
// Talks to launcher.py through window.webkit.messageHandlers.marquee; launcher.py
// calls window.marquee.* back. Opened in a normal browser it runs with demo data.
(() => {
  "use strict";
  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => [...el.querySelectorAll(s)];

  const T = {
    en: {
      ask: "What would you like to watch?", morning: "Good morning", afternoon: "Good afternoon", evening: "Good evening", night: "Hello",
      online: "Online", offline: "No network", settings: "Settings", power: "Power", h_open: "Open",
      h_home: "Home key brings you back here", no_apps: "No apps are switched on. Turn them on in the web admin.",
      plex_sub: "Movies and series from your Plex server", jellyfin_sub: "Your own media library", noflix_sub: "Films, series, music and live TV", livetv_sub: "Live channels and TV guide",
      livetv: "Live TV", live: "Live",
      settings_body: "Choose apps, language and updates in the web admin. Open this address on your phone or computer:",
      close: "Close", cancel: "Cancel", i_version: "Version", i_channel: "Channel", i_name: "Device name", i_ip: "Address",
      prod: "Production", test: "Test", check: "Check for updates", checking: "Checking for updates…",
      uptodate: "Marquee is up to date.", found: "An update is available. Choose “Update now” in the message on screen.",
      check_failed: "Could not check for updates. Is the device online?",
      power_title: "Turn off or restart?", power_body: "Restarting takes about a minute.", reboot: "Restart", poweroff: "Turn off",
      opening: "Opening {app}…", crashed: "{app} closed unexpectedly. Try again, or restart the device if it keeps happening.",
      not_installed: "{app} is being installed. Try again in a few minutes.", power_failed: "That did not work. Use the web admin instead.",
      noaddr: "Not connected"
    },
    nl: {
      ask: "Waar wil je naar kijken?", morning: "Goedemorgen", afternoon: "Goedemiddag", evening: "Goedenavond", night: "Hallo",
      online: "Online", offline: "Geen netwerk", settings: "Instellingen", power: "Aan/uit", h_open: "Openen",
      h_home: "Met de Home-toets kom je hier terug", no_apps: "Er staan geen apps aan. Zet ze aan in het webbeheer.",
      plex_sub: "Films en series van je Plex-server", jellyfin_sub: "Je eigen mediabibliotheek", noflix_sub: "Films, series, muziek en live tv", livetv_sub: "Live zenders en tv-gids",
      livetv: "Live tv", live: "Live",
      settings_body: "Apps, taal en updates stel je in via het webbeheer. Open dit adres op je telefoon of computer:",
      close: "Sluiten", cancel: "Annuleren", i_version: "Versie", i_channel: "Kanaal", i_name: "Apparaatnaam", i_ip: "Adres",
      prod: "Productie", test: "Test", check: "Controleren op updates", checking: "Bezig met controleren…",
      uptodate: "Marquee is up-to-date.", found: "Er is een update. Kies “Nu bijwerken” in de melding op het scherm.",
      check_failed: "Controleren is mislukt. Is het apparaat online?",
      power_title: "Uitzetten of herstarten?", power_body: "Herstarten duurt ongeveer een minuut.", reboot: "Herstarten", poweroff: "Uitzetten",
      opening: "{app} wordt geopend…", crashed: "{app} is onverwacht gesloten. Probeer het opnieuw, of herstart het apparaat als het blijft gebeuren.",
      not_installed: "{app} wordt nog geïnstalleerd. Probeer het over een paar minuten opnieuw.", power_failed: "Dat lukte niet. Gebruik het webbeheer.",
      noaddr: "Niet verbonden"
    }
  };

  const GLYPH = {
    plex: '<svg width="48" height="48" viewBox="0 0 48 48"><path d="M14 6h12l12 18-12 18H14l12-18z" fill="#E5A00D"/></svg>',
    jellyfin: '<svg width="50" height="50" viewBox="0 0 48 48"><defs><linearGradient id="jg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#AA5CC3"/><stop offset="1" stop-color="#00A4DC"/></linearGradient></defs><path d="M24 6C17 6 5 28 8 34s29 6 32 0S31 6 24 6zm0 12c3 0 9 11 7.5 14s-13.5 3-15 0S21 18 24 18z" fill="url(#jg)"/></svg>',
    noflix: '<svg width="56" height="56" viewBox="96 96 320 320"><circle cx="256" cy="256" r="176" fill="none" stroke="#FFB23F" stroke-opacity=".28" stroke-width="10"/><circle cx="256" cy="256" r="140" fill="#FFB23F"/><path d="M233.2 191.6 L329.8 256 L233.2 320.4 Z" fill="#06070B" stroke="#06070B" stroke-width="16.8" stroke-linejoin="round"/></svg>',
    livetv: '<svg width="48" height="48" viewBox="0 0 48 48" fill="none" stroke="#FF6B5A" stroke-width="3.5" stroke-linecap="round" stroke-linejoin="round"><rect x="6" y="14" width="36" height="25" rx="5"/><path d="M17 6l7 8 7-8"/><path d="M14 44h20"/></svg>',
  };

  // ---------- state ----------
  let S = { lang: "en", apps: [], version: "", channel: "main", host: "", ip: "", admin_url: "" };
  let row = 0, idx = 0, panel = null, panelRow = 0, panelIdx = 0, opening = null;
  const t = (k, v = {}) => (T[S.lang]?.[k] ?? T.en[k] ?? k).replace(/\{(\w+)\}/g, (_, n) => v[n] ?? "");

  const native = window.webkit?.messageHandlers?.marquee;
  const send = msg => native ? native.postMessage(msg) : demo(msg);

  // ---------- layout ----------
  const stage = $("#stage");
  const fit = () => {
    const s = Math.min(innerWidth / 1920, innerHeight / 1080);
    stage.style.transform = `translate(${(innerWidth - 1920 * s) / 2}px, ${(innerHeight - 1080 * s) / 2}px) scale(${s})`;
  };
  addEventListener("resize", fit); fit();

  // ---------- rendering ----------
  function render() {
    document.documentElement.lang = S.lang;
    $$("[data-i]").forEach(el => { el.textContent = t(el.dataset.i); });
    const apps = S.apps.filter(a => a.enabled);
    $("#apps").innerHTML = apps.map(a => `
      <button class="app ${a.id} f" data-go="app" data-app="${a.id}">
        ${a.id === "livetv" ? `<span class="badge">${t("live")}</span>` : ""}
        <span class="glyph">${GLYPH[a.id] || ""}</span>
        <span><h2>${a.id === "livetv" ? t("livetv") : a.name}</h2><span class="sub">${t(a.id + "_sub")}</span></span>
      </button>`).join("");
    $("#no-apps").hidden = apps.length > 0;
    $("#i-version").textContent = S.version || "-";
    $("#i-channel").textContent = S.channel === "test" ? t("test") : t("prod");
    $("#i-host").textContent = S.host || "-";
    $("#i-ip").textContent = S.ip || t("noaddr");
    $("#admin-url").textContent = S.admin_url || t("noaddr");
    $("#net").classList.toggle("off", !S.ip);
    $("#net-label").textContent = S.ip ? t("online") : t("offline");
    tick();
    clampFocus(); paint();
  }

  function tick() {
    const d = new Date(), h = d.getHours(), loc = S.lang === "nl" ? "nl-NL" : "en-GB";
    $("#clock").textContent = d.toLocaleTimeString(loc, { hour: "2-digit", minute: "2-digit" });
    const date = d.toLocaleDateString(loc, { weekday: "long", day: "numeric", month: "long" });
    $("#date").textContent = date.charAt(0).toUpperCase() + date.slice(1);
    $("#greet").textContent = t(h < 5 ? "night" : h < 12 ? "morning" : h < 18 ? "afternoon" : "evening");
  }
  setInterval(tick, 10000);

  // ---------- focus ----------
  const rows = () => (panel ? $$("[data-row]", panel) : $$("#home [data-row]")).map(r => $$(".f", r)).filter(r => r.length);
  function clampFocus() {
    const r = rows();
    if (panel) { panelRow = Math.min(panelRow, r.length - 1); panelIdx = Math.min(panelIdx, (r[panelRow] || []).length - 1); return; }
    row = Math.max(0, Math.min(row, r.length - 1));
    idx = Math.max(0, Math.min(idx, (r[row] || []).length - 1));
  }
  function current() { const r = rows(); return panel ? r[panelRow]?.[panelIdx] : r[row]?.[idx]; }
  function paint() { $$(".f.on").forEach(e => e.classList.remove("on")); current()?.classList.add("on"); }
  function nearest(list, x) {
    let best = 0, d = Infinity;
    list.forEach((e, i) => { const b = e.getBoundingClientRect(), c = Math.abs(b.left + b.width / 2 - x); if (c < d) { d = c; best = i; } });
    return best;
  }
  function move(dx, dy) {
    const r = rows(); if (!r.length) return;
    let ri = panel ? panelRow : row, ii = panel ? panelIdx : idx;
    if (dx) ii = Math.max(0, Math.min(r[ri].length - 1, ii + dx));
    if (dy) {
      const nr = Math.max(0, Math.min(r.length - 1, ri + dy));
      if (nr !== ri) { const b = r[ri][ii].getBoundingClientRect(); ii = nearest(r[nr], b.left + b.width / 2); ri = nr; }
    }
    if (panel) { panelRow = ri; panelIdx = ii; } else { row = ri; idx = ii; }
    paint();
  }

  // ---------- actions ----------
  function activate(el) {
    if (!el) return;
    const go = el.dataset.go;
    if (go === "app") return launch(el.dataset.app);
    if (go === "settings" || go === "info" || go === "power") return openPanel(go);
    if (go === "close") return closePanel();
    if (go === "check") { $("#check-status").textContent = t("checking"); return send({ cmd: "check" }); }
    if (go === "reboot" || go === "poweroff") return send({ cmd: "power", action: go });
  }
  function launch(id) {
    const app = S.apps.find(a => a.id === id); if (!app) return;
    opening = id;
    $("#opening-glyph").innerHTML = GLYPH[id] || "";
    $("#opening-title").textContent = t("opening", { app: id === "livetv" ? t("livetv") : app.name });
    $("#opening").hidden = false;
    send({ cmd: "launch", app: id });
  }
  function openPanel(name) {
    panel = $(`#panel-${name}`); panelRow = 0; panelIdx = 0;
    $$(".panel").forEach(p => { p.hidden = p !== panel; });
    $("#scrim").hidden = false;
    if (name === "info") $("#check-status").textContent = "";
    paint();
  }
  function closePanel() { panel = null; $("#scrim").hidden = true; paint(); }
  function toast(msg) {
    const el = $("#toast"); el.textContent = msg; el.hidden = false;
    clearTimeout(el._t); el._t = setTimeout(() => { el.hidden = true; }, 6000);
  }

  addEventListener("keydown", e => {
    if (opening) return;
    const k = e.key;
    if (k === "ArrowLeft") move(-1, 0);
    else if (k === "ArrowRight") move(1, 0);
    else if (k === "ArrowUp") move(0, -1);
    else if (k === "ArrowDown") move(0, 1);
    else if (k === "Enter" || k === " ") activate(current());
    else if ((k === "Escape" || k === "Backspace" || k === "BrowserBack") && panel) closePanel();
    else return;
    e.preventDefault();
  });

  // mouse: hover focuses, click opens; hide the pointer when it is not used
  let idleTimer;
  addEventListener("mousemove", e => {
    document.body.classList.remove("idle");
    clearTimeout(idleTimer); idleTimer = setTimeout(() => document.body.classList.add("idle"), 4000);
    const f = e.target.closest(".f"); if (!f || f.classList.contains("on")) return;
    const r = rows();
    r.forEach((list, ri) => { const i = list.indexOf(f); if (i >= 0) { if (panel) { panelRow = ri; panelIdx = i; } else { row = ri; idx = i; } } });
    paint();
  });
  addEventListener("click", e => {
    if (opening) return;
    const f = e.target.closest(".f");
    if (f) activate(f);
    else if (panel && e.target === $("#scrim")) closePanel();
  });
  addEventListener("contextmenu", e => e.preventDefault());

  // ---------- called by launcher.py ----------
  window.marquee = {
    update(state) { S = { ...S, ...state }; render(); },
    appExited(id, info) {
      opening = null; $("#opening").hidden = true;
      const app = S.apps.find(a => a.id === id), name = id === "livetv" ? t("livetv") : (app?.name || id);
      if (info?.crashed) toast(t("crashed", { app: name }));
      if (info?.missing) toast(t("not_installed", { app: name }));
      paint();
    },
    checkResult(r) {
      $("#check-status").textContent = r.error ? t("check_failed") : r.news ? t("found") : t("uptodate");
      if (r.news) setTimeout(closePanel, 1500);
    },
    powerFailed() { toast(t("power_failed")); },
    home() { if (panel) closePanel(); },
    launch(id) { if (!opening) launch(id); },
  };

  // ---------- demo mode (opened in a normal browser) ----------
  function demo(msg) {
    if (msg.cmd === "launch") setTimeout(() => window.marquee.appExited(msg.app, {}), 2500);
    if (msg.cmd === "check") setTimeout(() => window.marquee.checkResult({ news: false }), 1200);
    if (msg.cmd === "power") setTimeout(() => window.marquee.powerFailed(), 500);
  }
  if (!native) {
    const lang = new URLSearchParams(location.search).get("lang") === "nl" ? "nl" : "en";
    window.marquee.update({ lang, version: "0.4.0", channel: "test", host: "marquee", ip: "192.168.1.42", admin_url: "http://192.168.1.42:8080",
      apps: [{ id: "plex", name: "Plex", enabled: true }, { id: "noflix", name: "NO-Flix", enabled: true }, { id: "livetv", name: "Live TV", enabled: true }] });
  } else {
    render();
    send({ cmd: "ready" });
  }
})();
