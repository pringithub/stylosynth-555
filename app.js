"use strict";

const $ = (sel) => document.querySelector(sel);
const COLORS = [
  "#ffd54f",
  "#4fc3f7",
  "#81c784",
  "#f06292",
  "#ba68c8",
  "#ff8a65",
  "#4db6ac",
  "#e0e0e0",
  "#9575cd",
  "#aed581",
  "#ffb74d",
  "#64b5f6",
  "#f48fb1",
  "#dce775",
  "#90a4ae",
  "#80cbc4",
];
const MAX_CHANNELS = 16;
const PAD = { l: 96, r: 12, t: 8, b: 26 };

const CONTROL_SPEC = [
  {
    title: "Power",
    items: [
      { id: "power", type: "toggle", label: "POWER (SW1)" },
      {
        id: "adapter",
        type: "select",
        label: "Source",
        options: [
          [false, "9 V battery (J2)"],
          [true, "DC adapter (J1)"],
        ],
      },
      {
        id: "supply_v",
        type: "range",
        label: "Supply voltage",
        min: 5,
        max: 12,
        step: 0.1,
        fmt: (v) => `${v.toFixed(1)} V`,
      },
      { id: "phones", type: "toggle", label: "Headphones plugged (J4)" },
    ],
  },
  { title: "Stylus", keys: true },
  {
    title: "Panel",
    items: [
      { id: "oct_down1", type: "toggle", label: "OCT -1 (SW2)" },
      { id: "oct_down2", type: "toggle", label: "OCT -2 (SW3)" },
      { id: "tone_soft", type: "toggle", label: "TONE soft (SW4)" },
      { id: "vibrato", type: "toggle", label: "VIBRATO (SW5)" },
      {
        id: "volume",
        type: "range",
        label: "VOLUME (RV1, log)",
        min: 0,
        max: 1,
        step: 0.01,
        fmt: pct,
      },
      {
        id: "depth",
        type: "range",
        label: "DEPTH (RV3)",
        min: 0,
        max: 1,
        step: 0.01,
        fmt: pct,
      },
    ],
  },
  {
    title: "Trimmers",
    items: [
      {
        id: "tune",
        type: "range",
        label: "TUNE (RV4)",
        min: 0,
        max: 1,
        step: 0.01,
        fmt: pct,
      },
      {
        id: "span",
        type: "range",
        label: "SPAN (RV5)",
        min: 0,
        max: 1,
        step: 0.01,
        fmt: pct,
      },
      {
        id: "rate",
        type: "range",
        label: "LFO RATE (RV2, higher = slower)",
        min: 0,
        max: 1,
        step: 0.01,
        fmt: pct,
      },
    ],
  },
  {
    title: "Capture",
    items: [
      {
        id: "duration_ms",
        type: "select",
        label: "Capture length",
        options: [
          [20, "20 ms"],
          [50, "50 ms"],
          [100, "100 ms"],
          [250, "250 ms (~5 s to run)"],
          [600, "600 ms (~12 s to run)"],
          [1000, "1 s (~20 s to run)"],
        ],
      },
      {
        id: "settle_ms",
        type: "range",
        label: "Discard start-up",
        min: 0,
        max: 200,
        step: 5,
        fmt: (v) => `${v} ms`,
      },
    ],
  },
];

let META = null;
let settings = null;
let lastResult = null;
let channels = ["OSC_OUT", "TH", "CV", "OCT_SEL", "AMP_OUT"];
let view = null;
let traceData = null;
let running = false;
let pending = false;
let debounceTimer = null;
let hoverX = null;
let drag = null;
let audioNet = "";
let currentView = "welcome";
const VIEWS = ["welcome", "play", "bench", "report"];
const VIEW_TITLES = {
  welcome: "Welcome",
  play: "Play",
  bench: "Bench",
  report: "Report",
};

/** Each page is its own history entry (#play, #bench, ...), so Back/Forward move between them. */
function navigate(name) {
  if (!VIEWS.includes(name)) name = "welcome";
  if (location.hash === `#${name}`) showView(name);
  else location.hash = name; // fires hashchange -> showView
}
let benchStale = true;
let online = false;
let demoMode = false;
let demoData = null;
const HEALTH_POLL_MS = 5000;
// bench/server.py only listens on loopback, so a copy served from anywhere else (GitHub Pages) is demo-only
const HOSTED = !["localhost", "127.0.0.1", "[::1]"].includes(location.hostname);
const changeListeners = [];
const viewListeners = [];
let resolveReady;

// Shared panel state for the Play view (play.js) and this Bench view.
window.StyloBench = {
  ready: new Promise((r) => {
    resolveReady = r;
  }),
  hosted: HOSTED,
  get settings() {
    return settings;
  },
  get view() {
    return currentView;
  },
  set(key, value) {
    if (settings[key] === value) return;
    settings[key] = value;
    changed();
  },
  onChange(fn) {
    changeListeners.push(fn);
  },
  onView(fn) {
    viewListeners.push(fn);
  },
  show: (name) => navigate(name),
  run: () => run(),
};

function pct(v) {
  return `${Math.round(v * 100)} %`;
}

function el(tag, opts = {}, ...children) {
  const e = document.createElement(tag);
  if (opts.cls) e.className = opts.cls;
  if (opts.text !== undefined) e.textContent = opts.text;
  if (opts.title) e.title = opts.title;
  for (const [k, v] of Object.entries(opts.attrs || {})) e.setAttribute(k, v);
  e.append(...children);
  return e;
}

async function api(path, opts) {
  const r = await fetch(path, opts);
  const body = await r.json().catch(() => ({ error: r.statusText }));
  if (!r.ok) throw new Error(body.error || r.statusText);
  return body;
}

function setStatus(text, cls = "") {
  const s = $("#status");
  s.textContent = text;
  s.className = `status ${cls}`;
}

// ---- formatting ---------------------------------------------------------------------------------

function fmtV(v) {
  if (v === null || v === undefined) return "—";
  return Math.abs(v) < 1 ? `${(v * 1e3).toFixed(1)} mV` : `${v.toFixed(3)} V`;
}
function fmtHz(f) {
  if (!f) return "—";
  if (f < 10) return `${f.toFixed(3)} Hz`;
  if (f < 1000) return `${f.toFixed(2)} Hz`;
  return `${(f / 1000).toFixed(4)} kHz`;
}
function fmtCents(c) {
  return c === null || c === undefined
    ? "—"
    : `${c >= 0 ? "+" : ""}${c.toFixed(1)} c`;
}
function fmtTime(t) {
  const a = Math.abs(t);
  if (a < 1e-12) return "0";
  if (a < 1e-3) return `${(t * 1e6).toFixed(a < 1e-5 ? 1 : 0)} µs`;
  if (a < 1) return `${(t * 1e3).toFixed(a < 1e-2 ? 2 : 1)} ms`;
  return `${t.toFixed(3)} s`;
}
function fmtTick(t, step) {
  const [scale, unit] =
    step < 1e-3 ? [1e6, "µs"] : step < 1 ? [1e3, "ms"] : [1, "s"];
  const decimals = Math.max(0, -Math.floor(Math.log10(step * scale) + 1e-9));
  return Math.abs(t) < step / 1e6
    ? "0"
    : `${(t * scale).toFixed(decimals)} ${unit}`;
}
function fmtNum(v, unit) {
  if (v === null || v === undefined) return "—";
  if (unit === "V") return fmtV(v);
  if (unit === "Hz") return fmtHz(v);
  if (unit === "cents") return fmtCents(v);
  return `${Number(v.toPrecision(4))} ${unit}`;
}

// ---- controls -----------------------------------------------------------------------------------

function octaveName() {
  return META.octaves[
    (settings.oct_down1 ? 1 : 0) + (settings.oct_down2 ? 2 : 0)
  ];
}

function buildControls() {
  const root = $("#controls");
  for (const sec of CONTROL_SPEC) {
    const s = el("section", {}, el("h2", { text: sec.title }));
    if (sec.keys) s.append(el("div", { cls: "keys", attrs: { id: "keys" } }));
    for (const c of sec.items || []) s.append(buildControl(c));
    root.append(s);
  }
  refreshKeys();
}

function buildControl(c) {
  if (c.type === "toggle") {
    const input = el("input", { attrs: { type: "checkbox" } });
    input.checked = Boolean(settings[c.id]);
    input.addEventListener("change", () => {
      settings[c.id] = input.checked;
      changed();
    });
    return el(
      "label",
      { cls: "toggle" },
      el("span", { text: c.label }),
      input,
      el("span", { cls: "knob" }),
    );
  }
  if (c.type === "range") {
    const out = el("b", { text: c.fmt(settings[c.id]) });
    const input = el("input", {
      attrs: { type: "range", min: c.min, max: c.max, step: c.step },
    });
    input.value = settings[c.id];
    input.addEventListener("input", () => {
      out.textContent = c.fmt(Number(input.value));
    });
    input.addEventListener("change", () => {
      settings[c.id] = Number(input.value);
      changed();
    });
    return el(
      "div",
      { cls: "ctl" },
      el("div", { cls: "row" }, el("span", { text: c.label }), out),
      input,
    );
  }
  const sel = el("select");
  c.options.forEach(([value, label], i) => {
    const o = el("option", { text: label, attrs: { value: i } });
    if (value === settings[c.id]) o.selected = true;
    sel.append(o);
  });
  sel.addEventListener("change", () => {
    settings[c.id] = c.options[Number(sel.value)][0];
    changed();
  });
  return el(
    "div",
    { cls: "ctl" },
    el("div", { cls: "row" }, el("span", { text: c.label })),
    sel,
  );
}

function refreshKeys() {
  const box = $("#keys");
  box.replaceChildren();
  const oct = octaveName();
  for (const k of META.keys) {
    const b = el(
      "button",
      {
        cls: settings.key === k.key ? "on" : "",
        attrs: { type: "button" },
        title: `key ${k.key}: 555 at ${k.f555_hz} Hz`,
      },
      el("span", { text: k.notes[oct] }),
      el("small", { text: String(k.key) }),
    );
    b.addEventListener("click", () => {
      settings.key = k.key;
      changed();
    });
    box.append(b);
  }
  const lift = el("button", {
    cls: `lift ${settings.key === 0 ? "on" : ""}`,
    text: "Lift stylus",
    attrs: { type: "button" },
  });
  lift.addEventListener("click", () => {
    settings.key = 0;
    changed();
  });
  box.append(lift);
}

function changed() {
  refreshKeys();
  for (const fn of changeListeners) fn(settings);
  if (currentView !== "bench") {
    benchStale = true;
    return;
  }
  if (!$("#auto").checked) return;
  clearTimeout(debounceTimer);
  debounceTimer = setTimeout(run, 250);
}

function showView(name) {
  if (!VIEWS.includes(name)) name = "welcome";
  currentView = name;
  for (const t of document.querySelectorAll(".tab"))
    t.classList.toggle("on", t.dataset.view === name);
  for (const v of VIEWS) $(`#${v}-view`).hidden = v !== name;
  for (const e of document.querySelectorAll(".bench-only"))
    e.hidden = name !== "bench";
  if (name !== "bench") $("#audio").pause();
  document.title =
    name === "welcome"
      ? "StyloSynth-555"
      : `${VIEW_TITLES[name]} · StyloSynth-555`;
  if (name === "report" && !$("#report-frame").src)
    $("#report-frame").src = "report.pdf";
  if (name === "bench") {
    $("#controls").replaceChildren();
    buildControls();
    sizeScope();
    drawScope();
    if (!demoMode && benchStale && $("#auto").checked) run();
  }
  for (const fn of viewListeners) fn(name);
}

// ---- server connection and demo mode ------------------------------------------------------------

async function getJSON(url, timeoutMs = 4000) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const r = await fetch(url, { cache: "no-store", signal: ctrl.signal });
    if (!r.ok) throw new Error(`${url}: ${r.status}`);
    return await r.json();
  } finally {
    clearTimeout(timer);
  }
}

async function checkServer() {
  if (HOSTED) online = false;
  else
    try {
      online = (await getJSON("api/health", 2500)).ok === true;
    } catch {
      online = false;
    }
  updateServerIcon();
  return online;
}

function updateServerIcon() {
  const s = $("#server-status");
  s.className = `srv ${online ? "on" : "off"}`;
  s.lastElementChild.textContent = online
    ? "server connected"
    : HOSTED
      ? "demo"
      : demoMode
        ? "server offline · demo"
        : "server offline";
  s.title = online
    ? "Every change is simulated live with ngspice"
    : HOSTED
      ? "This hosted copy has no simulation server; run bench/server.py locally to simulate live."
      : "Start bench/server.py to simulate live; this page reconnects automatically.";
}

async function pollServer() {
  if (currentView !== "bench" || document.hidden) return;
  const was = online;
  await checkServer();
  if (online && !was && demoMode) {
    exitDemo();
  } else if (online && !was) {
    setStatus("server reconnected", "ok");
  } else if (!online && was && !demoMode) {
    // a local server that stopped also took the demo files with it; keep the last live run then
    enterDemo().catch(() =>
      setStatus(
        "simulation server stopped: showing the last live run. Restart " +
          "bench/server.py and this page reconnects automatically.",
        "err",
      ),
    );
  }
}

function fillDemoList(sim) {
  const s = sim.settings,
    sum = sim.summary;
  const rows = [
    ["Key", `${s.key} (${sum.note})`],
    ["Octave", sum.octave],
    ["Tone", s.tone_soft ? "soft" : "bright"],
    [
      "Vibrato",
      s.vibrato ? `on, depth ${pct(s.depth)}, rate ${pct(s.rate)}` : "off",
    ],
    ["Volume", pct(s.volume)],
    [
      "Supply",
      `${s.supply_v.toFixed(1)} V ${s.adapter ? "adapter" : "battery"}`,
    ],
    ["Output", s.phones ? "headphones" : "speaker"],
    ["Capture", `${s.duration_ms} ms after ${s.settle_ms} ms settle`],
    [
      "Simulated",
      `${sim.points.toLocaleString()} points in ${sim.wall_s.toFixed(1)} s`,
    ],
  ];
  $("#demo-list").replaceChildren(
    ...rows.flatMap(([k, v]) => [el("dt", { text: k }), el("dd", { text: v })]),
  );
}

async function enterDemo() {
  demoData ??= {
    sim: await getJSON("demo/sim.json"),
    traces: await getJSON("demo/traces.json", 20000),
  };
  demoMode = true;
  updateServerIcon();
  $("#demo-banner").hidden = false;
  $("#controls").hidden = true;
  $("#demo-settings").hidden = false;
  $("#run").disabled = true;
  document.body.classList.add("demo");
  fillDemoList(demoData.sim);
  lastResult = demoData.sim;
  const [detail] = demoData.traces.views;
  view = { t0: detail.t0, t1: detail.t1 }; // open on the detailed window; double-click shows it all
  renderCards(lastResult);
  renderChecks(lastResult);
  renderNets(lastResult);
  await loadTraces();
  updateAudio();
  setStatus("recorded run", "");
}

function exitDemo() {
  demoMode = false;
  updateServerIcon();
  $("#demo-banner").hidden = true;
  $("#controls").hidden = false;
  $("#demo-settings").hidden = true;
  $("#run").disabled = false;
  document.body.classList.remove("demo");
  benchStale = true;
  if (currentView === "bench") run();
}

/** Slice the recorded scope data: the detailed first window if it covers the view, else the overview. */
function demoTraces(t0, t1) {
  const [detail, overview] = demoData.traces.views;
  const v = t0 >= detail.t0 && t1 <= detail.t1 ? detail : overview;
  let i0 = v.t.findIndex((t) => t >= t0);
  if (i0 < 0) i0 = v.t.length - 1;
  let i1 = v.t.findIndex((t) => t > t1);
  if (i1 < 0) i1 = v.t.length;
  i0 = Math.max(0, i0 - 1);
  i1 = Math.min(v.t.length, i1 + 1);
  const t = v.t.slice(i0, i1);
  const out = {};
  for (const name of channels) {
    const c = v.ch[name];
    if (c)
      out[name] = { t, min: c.min.slice(i0, i1), max: c.max.slice(i0, i1) };
  }
  return { channels: out };
}

// ---- simulation ---------------------------------------------------------------------------------

async function run() {
  if (demoMode) return;
  if (running) {
    pending = true;
    return;
  }
  running = true;
  benchStale = false;
  $("#run").disabled = true;
  setStatus("simulating…", "busy");
  try {
    const res = await api("api/sim", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(settings),
    });
    lastResult = res;
    view = null;
    renderCards(res);
    renderChecks(res);
    renderNets(res);
    await loadTraces();
    updateAudio();
    setStatus(
      `${res.points.toLocaleString()} points · ${res.wall_s.toFixed(2)} s`,
      "ok",
    );
  } catch (e) {
    setStatus(e.message, "err");
  } finally {
    running = false;
    $("#run").disabled = false;
    if (pending) {
      pending = false;
      run();
    }
  }
}

function renderCards(res) {
  const s = res.summary;
  const v = res.measurements;
  const hours = s.supply_ma > 0.1 ? 500 / s.supply_ma : null;
  const cards = [
    [
      "Note",
      s.note || (res.settings.key ? "—" : "stylus up"),
      s.key ? `key ${s.key} · ${s.octave}` : s.octave,
    ],
    [
      "555 pitch (OSC_OUT)",
      fmtHz(s.f_osc),
      `target ${fmtHz(s.f_osc_target)} · ${fmtCents(s.cents_osc)}`,
    ],
    [
      "Output pitch (OCT_SEL)",
      fmtHz(s.f_out),
      `target ${fmtHz(s.f_out_target)} · ${fmtCents(s.cents_out)}`,
    ],
    [
      "Supply current",
      `${s.supply_ma.toFixed(1)} mA`,
      `peak ${s.supply_peak_ma.toFixed(0)} mA${hours ? ` · ~${hours.toFixed(0)} h on 500 mAh` : ""}`,
    ],
    ["Rails", `${fmtV(v["+9V"].mean)}`, `+5V ${fmtV(v["+5V"].mean)}`],
  ];
  $("#cards").replaceChildren(
    ...cards.map(([label, value, sub]) =>
      el(
        "div",
        { cls: "card" },
        el("div", { cls: "label", text: label }),
        el("div", { cls: "value", text: value }),
        el("div", { cls: "sub", text: sub }),
      ),
    ),
  );
}

function renderChecks(res) {
  const t = $("#checks");
  const head = el(
    "tr",
    {},
    ...["Check", "Measured", "Expected", "Result", "Notes"].map((h, i) =>
      el("th", { cls: i === 0 || i === 4 ? "l" : "", text: h }),
    ),
  );
  const rows = res.checks.map((c) => {
    const exp =
      c.lo === null
        ? "—"
        : c.lo === c.hi
          ? fmtNum(c.lo, c.unit)
          : `${fmtNum(c.lo, c.unit)} … ${fmtNum(c.hi, c.unit)}`;
    const result =
      c.pass === null
        ? ["n/a", "na"]
        : c.pass
          ? ["PASS", "pass"]
          : ["FAIL", "fail"];
    return el(
      "tr",
      {},
      el("td", { cls: "l", text: c.name }),
      el("td", { text: fmtNum(c.value, c.unit) }),
      el("td", { text: exp }),
      el("td", { cls: result[1], text: result[0] }),
      el("td", { cls: "note", text: c.note }),
    );
  });
  t.replaceChildren(head, ...rows);
}

function renderNets(res) {
  const t = $("#nets");
  const head = el(
    "tr",
    {},
    ...["Scope", "Net", "Mean", "Min", "Max", "Vpp", "Freq", "Duty", ""].map(
      (h, i) => el("th", { cls: i < 2 ? "l" : "", text: h }),
    ),
  );
  const rows = [];
  let block = null;
  // nets arrive sorted with the Power block first, so the supply channel joins that group
  const entries = [
    { net: META.supply_channel, block: "Power", pins: ["supply current, mA"] },
    ...META.nets,
  ];
  for (const n of entries) {
    if (n.block !== block) {
      block = n.block;
      rows.push(
        el(
          "tr",
          { cls: "block" },
          el("td", { text: block, attrs: { colspan: 9 } }),
        ),
      );
    }
    const m = res.measurements[n.net];
    const box = el("input", { attrs: { type: "checkbox" } });
    box.checked = channels.includes(n.net);
    box.addEventListener("change", () => toggleChannel(n.net, box));
    const idx = channels.indexOf(n.net);
    const swatch = el("span", { cls: "swatch" });
    swatch.style.background =
      idx >= 0 ? COLORS[idx % COLORS.length] : "transparent";
    const listen = el("button", { text: "listen", attrs: { type: "button" } });
    if (demoMode && n.net !== "SPK_P") {
      listen.disabled = true;
      listen.title = "Only the speaker output was recorded for the demo";
    }
    listen.addEventListener("click", () => {
      audioNet = n.net;
      $("#audio-net").value = n.net;
      updateAudio(true);
    });
    const cells = !m
      ? [`${res.summary.supply_ma.toFixed(1)} mA`, "", "", "", "", ""]
      : m.floating
        ? ["floating", "", "", "", "", ""]
        : [
            fmtV(m.mean),
            fmtV(m.min),
            fmtV(m.max),
            fmtV(m.vpp),
            fmtHz(m.freq),
            m.duty === null ? "—" : pct(m.duty),
          ];
    rows.push(
      el(
        "tr",
        {},
        el("td", { cls: "l" }, swatch, box),
        el("td", { cls: "l", text: n.net, title: n.pins.join(", ") }),
        ...cells.map((c) => el("td", { text: c })),
        el("td", {}, m ? listen : ""),
      ),
    );
  }
  t.replaceChildren(head, ...rows);
}

function toggleChannel(net, box) {
  if (box.checked) {
    if (channels.length >= MAX_CHANNELS) {
      box.checked = false;
      setStatus(`max ${MAX_CHANNELS} channels`, "err");
      return;
    }
    channels.push(net);
  } else {
    channels = channels.filter((c) => c !== net);
  }
  sizeScope();
  if (lastResult) renderNets(lastResult);
  loadTraces().catch((e) => setStatus(e.message, "err"));
}

// ---- audio --------------------------------------------------------------------------------------

function buildAudioSelect() {
  const sel = $("#audio-net");
  sel.append(
    el("option", { text: "auto: speaker / headphones", attrs: { value: "" } }),
  );
  for (const n of META.nets)
    sel.append(el("option", { text: n.net, attrs: { value: n.net } }));
  sel.addEventListener("change", () => {
    audioNet = sel.value;
    updateAudio(true);
  });
  $("#normalise").addEventListener("change", () => updateAudio(true));
}

function updateAudio(play = false) {
  if (!lastResult) return;
  const net = audioNet || (lastResult.settings.phones ? "HP" : "SPK_P");
  const audio = $("#audio");
  const wasPlaying = !audio.paused;
  if (demoMode) {
    if (net !== "SPK_P") {
      audio.removeAttribute("src");
      audio.load();
      setStatus(
        "demo: only the speaker output was recorded; connect the server to listen to other nets",
        "err",
      );
      return;
    }
    audio.src = "demo/speaker.wav";
  } else {
    const q = new URLSearchParams({
      net,
      normalise: $("#normalise").checked ? "1" : "0",
      v: Date.now(),
    });
    audio.src = `api/audio?${q}`;
  }
  if (play || wasPlaying) audio.play().catch(() => {});
}

// ---- scope --------------------------------------------------------------------------------------

function sizeScope() {
  $("#scope").style.height =
    `${Math.max(260, channels.length * 72 + PAD.t + PAD.b)}px`;
}

async function loadTraces() {
  if (!lastResult || !channels.length) {
    traceData = null;
    drawScope();
    return;
  }
  const t0 = view ? view.t0 : 0;
  const t1 = view ? view.t1 : lastResult.t_end;
  if (demoMode) {
    traceData = { ...demoTraces(t0, t1), view: { t0, t1 } };
    drawScope();
    return;
  }
  const points = Math.max(
    200,
    Math.round($("#scope").clientWidth - PAD.l - PAD.r),
  );
  const q = new URLSearchParams({ nets: channels.join(","), t0, t1, points });
  const data = await api(`api/trace?${q}`);
  data.view = { t0, t1 };
  traceData = data;
  drawScope();
}

function niceStep(range, target) {
  const raw = range / target;
  const mag = 10 ** Math.floor(Math.log10(raw));
  const norm = raw / mag;
  return (norm < 1.5 ? 1 : norm < 3.5 ? 2 : norm < 7.5 ? 5 : 10) * mag;
}

function lowerBound(arr, x) {
  let lo = 0,
    hi = arr.length;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (arr[mid] < x) lo = mid + 1;
    else hi = mid;
  }
  return Math.min(lo, arr.length - 1);
}

function drawScope() {
  const cv = $("#scope");
  const dpr = window.devicePixelRatio || 1;
  const W = cv.clientWidth,
    H = cv.clientHeight;
  cv.width = Math.round(W * dpr);
  cv.height = Math.round(H * dpr);
  const g = cv.getContext("2d");
  g.setTransform(dpr, 0, 0, dpr, 0, 0);
  g.fillStyle = "#0b0f14";
  g.fillRect(0, 0, W, H);
  g.font = "12px system-ui, sans-serif";
  if (!traceData) {
    g.fillStyle = "#8796a5";
    g.fillText(
      lastResult ? "no channels selected" : "run a simulation",
      PAD.l,
      H / 2,
    );
    return;
  }
  const { t0, t1 } = traceData.view;
  const pw = W - PAD.l - PAD.r;
  const n = channels.length;
  const lh = (H - PAD.t - PAD.b) / n;
  const x = (t) => PAD.l + ((t - t0) / (t1 - t0)) * pw;

  const step = niceStep(t1 - t0, Math.max(3, Math.floor(pw / 90)));
  g.strokeStyle = "#1e2833";
  g.fillStyle = "#8796a5";
  g.textAlign = "center";
  for (let t = Math.ceil(t0 / step) * step; t <= t1 + 1e-15; t += step) {
    const xx = x(t);
    g.beginPath();
    g.moveTo(xx, PAD.t);
    g.lineTo(xx, H - PAD.b);
    g.stroke();
    g.fillText(fmtTick(t, step), xx, H - 8);
  }

  channels.forEach((name, i) => {
    const ch = traceData.channels[name];
    const color = COLORS[i % COLORS.length];
    const top = PAD.t + i * lh,
      bot = top + lh;
    g.strokeStyle = "#2a3542";
    g.beginPath();
    g.moveTo(PAD.l, bot);
    g.lineTo(W - PAD.r, bot);
    g.stroke();
    if (!ch || !ch.t.length) return;
    let lo = Infinity,
      hi = -Infinity;
    for (let k = 0; k < ch.t.length; k++) {
      if (ch.min[k] < lo) lo = ch.min[k];
      if (ch.max[k] > hi) hi = ch.max[k];
    }
    const dataLo = lo,
      dataHi = hi;
    if (hi - lo < 0.05) {
      const m = (hi + lo) / 2;
      lo = m - 0.05;
      hi = m + 0.05;
    }
    const padv = (hi - lo) * 0.08;
    lo -= padv;
    hi += padv;
    const y = (v) => bot - 4 - ((v - lo) / (hi - lo)) * (lh - 8);
    ch.scale = { lo, hi, top, bot };

    const unit = name === META.supply_channel ? " mA" : " V";
    g.textAlign = "left";
    g.fillStyle = color;
    g.fillText(name, 6, top + 14);
    g.fillStyle = "#8796a5";
    g.fillText(`max ${dataHi.toPrecision(3)}${unit}`, 6, top + 28);
    g.fillText(`min ${dataLo.toPrecision(3)}${unit}`, 6, bot - 6);

    g.save();
    g.beginPath();
    g.rect(PAD.l, top, pw, lh);
    g.clip();
    g.strokeStyle = color;
    g.lineWidth = 1.25;
    g.beginPath();
    for (let k = 0; k < ch.t.length; k++) {
      const xx = x(ch.t[k]);
      if (k === 0) g.moveTo(xx, y(ch.min[k]));
      else g.lineTo(xx, y(ch.min[k]));
      if (ch.max[k] !== ch.min[k]) g.lineTo(xx, y(ch.max[k]));
    }
    g.stroke();
    g.restore();
  });

  if (drag && Math.abs(drag.x1 - drag.x0) > 2) {
    g.fillStyle = "rgba(255, 213, 79, 0.12)";
    g.fillRect(
      Math.min(drag.x0, drag.x1),
      PAD.t,
      Math.abs(drag.x1 - drag.x0),
      H - PAD.t - PAD.b,
    );
  }

  if (hoverX !== null && hoverX >= PAD.l && hoverX <= W - PAD.r) {
    const t = t0 + ((hoverX - PAD.l) / pw) * (t1 - t0);
    g.strokeStyle = "rgba(255,255,255,0.35)";
    g.beginPath();
    g.moveTo(hoverX, PAD.t);
    g.lineTo(hoverX, H - PAD.b);
    g.stroke();
    g.textAlign = hoverX > W - 160 ? "right" : "left";
    const tx = hoverX + (hoverX > W - 160 ? -6 : 6);
    channels.forEach((name, i) => {
      const ch = traceData.channels[name];
      if (!ch || !ch.scale) return;
      const k = lowerBound(ch.t, t);
      const v = (ch.min[k] + ch.max[k]) / 2;
      const unit = name === META.supply_channel ? " mA" : " V";
      g.fillStyle = COLORS[i % COLORS.length];
      g.fillText(`${v.toPrecision(4)}${unit}`, tx, ch.scale.top + 14);
    });
    g.fillStyle = "#dbe4ec";
    g.fillText(fmtTime(t), tx, H - PAD.b - 4);
  }
}

function canvasX(ev) {
  return ev.clientX - $("#scope").getBoundingClientRect().left;
}

function bindScope() {
  const cv = $("#scope");
  cv.addEventListener("mousedown", (ev) => {
    drag = { x0: canvasX(ev), x1: canvasX(ev) };
  });
  cv.addEventListener("mousemove", (ev) => {
    hoverX = canvasX(ev);
    if (drag) drag.x1 = hoverX;
    drawScope();
  });
  cv.addEventListener("mouseleave", () => {
    hoverX = null;
    drag = null;
    drawScope();
  });
  window.addEventListener("mouseup", () => {
    if (!drag || !traceData) {
      drag = null;
      return;
    }
    const { x0, x1 } = drag;
    drag = null;
    if (Math.abs(x1 - x0) < 6) {
      drawScope();
      return;
    }
    const pw = cv.clientWidth - PAD.l - PAD.r;
    const { t0, t1 } = traceData.view;
    const toT = (px) =>
      t0 + (Math.min(Math.max(px - PAD.l, 0), pw) / pw) * (t1 - t0);
    const a = toT(Math.min(x0, x1)),
      b = toT(Math.max(x0, x1));
    if (b - a < 2e-6) {
      drawScope();
      return;
    }
    view = { t0: a, t1: b };
    loadTraces().catch((e) => setStatus(e.message, "err"));
  });
  const reset = () => {
    view = null;
    loadTraces().catch((e) => setStatus(e.message, "err"));
  };
  cv.addEventListener("dblclick", reset);
  $("#zoom-reset").addEventListener("click", reset);
  let resizeTimer = null;
  window.addEventListener("resize", () => {
    drawScope();
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => loadTraces().catch(() => {}), 300);
  });
}

// ---- start --------------------------------------------------------------------------------------

async function init() {
  const live = await checkServer();
  try {
    META = live ? await api("api/meta") : await getJSON("demo/meta.json");
  } catch (e) {
    setStatus(`no simulation server and no demo data: ${e.message}`, "err");
    return;
  }
  demoMode = !live;
  settings = { ...META.defaults };
  buildControls();
  buildAudioSelect();
  sizeScope();
  bindScope();
  drawScope();
  $("#run").addEventListener("click", run);
  for (const t of document.querySelectorAll(".tab"))
    t.addEventListener("click", () => navigate(t.dataset.view));
  window.addEventListener("hashchange", () => showView(location.hash.slice(1)));
  resolveReady();
  const first = VIEWS.includes(location.hash.slice(1))
    ? location.hash.slice(1)
    : "welcome";
  history.replaceState(null, "", `#${first}`); // normalise the landing URL without adding an entry
  showView(first);
  if (demoMode) await enterDemo().catch((e) => setStatus(e.message, "err"));
  if (HOSTED)
    $("#demo-reconnect").textContent =
      "This page can't reach a local server from here, so open the local copy instead.";
  else setInterval(pollServer, HEALTH_POLL_MS);
}

init();
