// Marquee admin front-end (no build step, no external libraries).
(() => {
  "use strict";
  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => [...el.querySelectorAll(s)];

  // ---------- i18n ----------
  let lang = "en";
  try { lang = localStorage.getItem("marquee.lang") || (navigator.language || "en").slice(0, 2); } catch (_) {}
  if (!I18N[lang]) lang = "en";
  const t = (key, vars = {}) =>
    (I18N[lang][key] ?? I18N.en[key] ?? key).replace(/\{(\w+)\}/g, (_, k) => vars[k] ?? "");

  function applyLang() {
    document.documentElement.lang = lang;
    $$("[data-i18n]").forEach(el => { el.textContent = t(el.dataset.i18n); });
    $$(".lang-switch button").forEach(b => b.classList.toggle("active", b.dataset.lang === lang));
    if (state.page) setTitle(state.page);
    if (state.status) renderStatus(state.status);
    if (state.updates) renderUpdates(state.updates);
  }
  $$(".lang-switch button").forEach(b => b.addEventListener("click", () => {
    lang = b.dataset.lang;
    try { localStorage.setItem("marquee.lang", lang); } catch (_) {}
    applyLang();
  }));

  // ---------- api ----------
  async function api(path, body) {
    const opts = body === undefined ? {} : {
      method: "POST", headers: { "Content-Type": "application/json", "X-Marquee": "1" },
      body: JSON.stringify(body),
    };
    const res = await fetch(path, { credentials: "same-origin", ...opts });
    if (res.status === 401 && path !== "/api/login") { showLogin(); throw new Error("unauthorized"); }
    const data = await res.json().catch(() => ({}));
    if (!res.ok) { const e = new Error(data.error || res.statusText); e.status = res.status; throw e; }
    return data;
  }

  const state = { page: null, status: null, updates: null, timer: null };

  function toast(msg) {
    const el = $("#toast"); el.textContent = msg; el.hidden = false;
    clearTimeout(el._t); el._t = setTimeout(() => { el.hidden = true; }, 3500);
  }

  // ---------- auth ----------
  function showLogin() {
    $("#app").hidden = true; $("#login").hidden = false;
    clearInterval(state.timer);
  }
  async function showApp(user) {
    $("#login").hidden = true; $("#app").hidden = false;
    $("#user-name").textContent = user;
    route();
    refreshStatus();
    loadUpdates();
    clearInterval(state.timer);
    state.timer = setInterval(() => { if (state.page === "dashboard") refreshStatus(); }, 10000);
  }
  $("#login-form").addEventListener("submit", async e => {
    e.preventDefault();
    const f = e.target, err = $("#login-error"), btn = $("button[type=submit]", f);
    err.hidden = true; btn.disabled = true;
    try {
      const r = await api("/api/login", { user: f.user.value.trim(), password: f.password.value });
      f.password.value = "";
      showApp(r.user);
    } catch (ex) {
      err.textContent = t(ex.status === 429 ? "login.locked" : "login.invalid"); err.hidden = false;
    } finally { btn.disabled = false; }
  });
  $("#logout").addEventListener("click", async () => { await api("/api/logout", {}).catch(() => {}); showLogin(); });

  // ---------- routing ----------
  const titles = { dashboard: "nav.dashboard", updates: "nav.updates", channel: "nav.channel", logs: "nav.logs", power: "nav.power" };
  function setTitle(page) { $("#page-title").textContent = t(titles[page]); document.title = `${t(titles[page])} · Marquee`; }
  function route() {
    const page = titles[location.hash.slice(1)] ? location.hash.slice(1) : "dashboard";
    state.page = page;
    $$(".page").forEach(p => { p.hidden = p.id !== `page-${page}`; });
    $$("nav a").forEach(a => a.classList.toggle("active", a.dataset.page === page));
    setTitle(page);
    $("#sidebar").classList.remove("open");
    if (page === "logs") loadLogs();
    if (page === "updates") loadJobs();
    if (page === "dashboard" || page === "channel") refreshStatus();
  }
  window.addEventListener("hashchange", route);
  $("#menu-btn").addEventListener("click", () => $("#sidebar").classList.toggle("open"));

  // ---------- dashboard ----------
  const fmtBytes = b => { const u = ["B", "KB", "MB", "GB", "TB"]; let i = 0; while (b >= 1024 && i < 4) { b /= 1024; i++; } return `${b.toFixed(i > 2 ? 1 : 0)} ${u[i]}`; };
  const fmtUptime = s => { const d = Math.floor(s / 86400), h = Math.floor(s % 86400 / 3600), m = Math.floor(s % 3600 / 60);
    return [d && `${d}${t("unit.d")}`, (d || h) && `${h}${t("unit.h")}`, `${m}${t("unit.m")}`].filter(Boolean).join(" "); };

  async function refreshStatus() {
    try { state.status = await api("/api/status"); renderStatus(state.status); } catch (_) {}
  }
  function renderStatus(s) {
    const pill = $("#kiosk-pill"), st = s.kiosk.state;
    pill.className = "status-pill " + (st === "active" ? "ok" : st === "activating" ? "warn" : "bad");
    pill.textContent = t(`state.${st}`) !== `state.${st}` ? t(`state.${st}`) : st;
    $("#hostname").textContent = s.hostname;
    $("#ips").textContent = s.ips.length ? `http://${s.ips[0]}:${location.port || 80}` + (s.ips.length > 1 ? `  ·  ${s.ips.slice(1).join(", ")}` : "") : "";
    $("#plex-version").textContent = s.plex.version || "-";
    $("#marquee-version").textContent = `${s.marquee.version} · ${s.marquee.channel === "test" ? t("ch.test") : t("ch.prod")}`;
    $("#uptime").textContent = fmtUptime(s.uptime_s);
    $("#temp").textContent = s.temp_c == null ? "-" : `${Math.round(s.temp_c)} °C`;
    const memUsed = s.mem_total_kb - s.mem_avail_kb;
    $("#memory").textContent = `${fmtBytes(memUsed * 1024)} / ${fmtBytes(s.mem_total_kb * 1024)}`;
    $("#memory-bar").style.width = `${Math.round(memUsed / s.mem_total_kb * 100)}%`;
    $("#disk").textContent = `${fmtBytes(s.disk_used)} / ${fmtBytes(s.disk_total)}`;
    $("#disk-bar").style.width = `${Math.round(s.disk_used / s.disk_total * 100)}%`;
    $("#os").textContent = s.os; $("#kernel").textContent = s.kernel;
    $("#restarts").textContent = s.kiosk.restarts; $("#load").textContent = s.load.toFixed(2);
    $$(".channel").forEach(c => c.classList.toggle("active", c.dataset.channel === s.marquee.channel));
    $("#info-version").textContent = s.marquee.version;
    $("#info-channel").textContent = s.marquee.channel === "test" ? t("ch.test") : t("ch.prod");
    $("#info-commit").textContent = s.marquee.commit || "-";
    $("#info-plex").textContent = s.plex.version || "-";
  }

  // ---------- updates ----------
  async function loadUpdates() { try { const u = await api("/api/updates"); if (u.checked_at) { state.updates = u; renderUpdates(u); } } catch (_) {} }
  async function checkUpdates(btn) {
    btn.disabled = true; $("#checked-at").textContent = t("upd.checking");
    try { state.updates = await api("/api/updates/check", {}); renderUpdates(state.updates); }
    catch (_) { toast(t("toast.error")); }
    finally { btn.disabled = false; }
  }
  function renderUpdates(u) {
    const time = new Date(u.checked_at * 1000).toLocaleString(lang === "nl" ? "nl-NL" : "en-GB", { dateStyle: "medium", timeStyle: "short" });
    $("#checked-at").textContent = t("upd.checked", { time });
    const cnt = n => n > 0 ? t("upd.count", { n }) : t("upd.none");
    $("#upd-debian").textContent = cnt(u.debian || 0);
    $("#upd-plex").textContent = cnt(u.flatpak || 0);
    const mq = u.marquee_error ? u.marquee_error
      : u.marquee_behind > 0 ? t("upd.marquee_new", { n: u.marquee_behind, v: u.marquee_latest }) : t("upd.none");
    $("#upd-marquee").textContent = mq;
    $("#update-dot").hidden = !((u.debian || 0) + (u.flatpak || 0) + (u.marquee_behind || 0));
    const newer = u.marquee_behind > 0;
    $("#info-update").textContent = newer ? t("info.available", { v: u.marquee_latest }) : (u.marquee_error || t("info.latest"));
    $("#info-update-btn").hidden = !newer;
  }
  $("#check-btn").addEventListener("click", e => checkUpdates(e.currentTarget));
  $("#info-check").addEventListener("click", e => checkUpdates(e.currentTarget));

  async function loadJobs() {
    try {
      const jobs = await api("/api/jobs"), ul = $("#jobs"); ul.innerHTML = "";
      if (!jobs.length) { ul.innerHTML = `<li class="muted">${t("upd.no_jobs")}</li>`; return; }
      for (const j of jobs) {
        const li = document.createElement("li");
        const when = new Date(j.started * 1000).toLocaleString(lang === "nl" ? "nl-NL" : "en-GB", { dateStyle: "short", timeStyle: "short" });
        li.innerHTML = `<span></span><span class="muted"></span>`;
        li.children[0].textContent = t(`job.${j.action}`);
        li.children[1].textContent = `${when} · ${t(`job.${j.state}`)}`;
        li.addEventListener("click", () => openJob(j.id, j.action));
        ul.appendChild(li);
      }
    } catch (_) {}
  }

  // ---------- jobs ----------
  async function openJob(id, action) {
    const dlg = $("#job-dialog"), log = $("#job-log"), pill = $("#job-state");
    $("#job-title").textContent = t(`job.${action}`); log.textContent = ""; dlg.showModal();
    let done = false;
    while (!done && dlg.open) {
      try {
        const j = await api(`/api/jobs/${id}`);
        const atBottom = log.scrollTop + log.clientHeight >= log.scrollHeight - 20;
        log.textContent = j.log || "...";
        if (atBottom) log.scrollTop = log.scrollHeight;
        pill.className = "status-pill " + (j.state === "success" ? "ok" : j.state === "failed" ? "bad" : "warn");
        pill.textContent = t(`job.${j.state}`);
        done = j.state !== "running";
      } catch (_) { /* admin may restart during self-update; keep polling */ }
      if (!done) await new Promise(r => setTimeout(r, 1500));
    }
    if (done) { refreshStatus(); loadJobs(); }
  }
  $("#job-close").addEventListener("click", () => $("#job-dialog").close());

  // ---------- actions ----------
  function confirmBox(text) {
    return new Promise(resolve => {
      const dlg = $("#confirm-dialog"); $("#confirm-text").textContent = text;
      const done = v => { dlg.close(); resolve(v); };
      $("#confirm-yes").onclick = () => done(true); $("#confirm-no").onclick = () => done(false);
      dlg.showModal();
    });
  }
  async function runAction(action) {
    try {
      const r = await api("/api/action", { action });
      if (r.job) { $("#info-dialog").close(); openJob(r.job, action); }
      else toast(t({ "restart-kiosk": "toast.restarting", reboot: "toast.rebooting", poweroff: "toast.off" }[action] || "toast.done"));
    } catch (_) { toast(t("toast.error")); }
  }
  $$("[data-action]").forEach(btn => btn.addEventListener("click", async () => {
    if (btn.dataset.confirm && !(await confirmBox(t(btn.dataset.confirm)))) return;
    runAction(btn.dataset.action);
  }));
  $$(".channel").forEach(c => c.addEventListener("click", async () => {
    if (c.classList.contains("active")) return;
    const name = c.dataset.channel === "test" ? t("ch.test") : t("ch.prod");
    if (await confirmBox(t("confirm.channel", { c: name }))) runAction(`channel-${c.dataset.channel}`);
  }));

  // ---------- logs ----------
  async function loadLogs() {
    try { const r = await api("/api/logs?n=400"); const el = $("#log"); el.textContent = r.log || "-"; el.scrollTop = el.scrollHeight; } catch (_) {}
  }
  $("#logs-refresh").addEventListener("click", loadLogs);

  // ---------- info ----------
  $("#info-btn").addEventListener("click", () => { refreshStatus(); $("#info-dialog").showModal(); });
  $("#info-close").addEventListener("click", () => $("#info-dialog").close());

  // ---------- start ----------
  applyLang();
  api("/api/session").then(r => showApp(r.user)).catch(showLogin);
})();
