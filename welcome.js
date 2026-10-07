// Welcome page motion graphics: living-circuit hero, 3D model, signal-chain scopes, counters and reveals.
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { RoomEnvironment } from "three/addons/environments/RoomEnvironment.js";
import { loadSynthModel } from "./model.js";

const bench = window.StyloBench;
const $ = (sel, root = document) => root.querySelector(sel);
const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
const TAU = Math.PI * 2;

// Ode to Joy, first phrase: [keypad key (1 = A), beats]; HIGH octave range, 555 freq = 440 * 2^((key+11)/12)
const MELODY = [
  [10, 1],
  [10, 1],
  [11, 1],
  [13, 1],
  [13, 1],
  [11, 1],
  [10, 1],
  [8, 1],
  [6, 1],
  [6, 1],
  [8, 1],
  [10, 1],
  [10, 1.5],
  [8, 0.5],
  [8, 2],
];
const NOTE_NAMES = [
  "A",
  "A#",
  "B",
  "C",
  "C#",
  "D",
  "D#",
  "E",
  "F",
  "F#",
  "G",
  "G#",
];
const BEAT_S = 0.5;
const SHARP_KEYS = new Set([2, 5, 7, 10, 12, 14, 17, 19]);

function keyName(k) {
  const semis = k - 1 + 9; // key 1 = A4 in the HIGH range
  return `${NOTE_NAMES[(k - 1) % 12]}${4 + Math.floor(semis / 12)}`;
}
function keyHz(k) {
  return 440 * 2 ** ((k - 1) / 12);
} // output pitch in the HIGH octave

function fitCanvas(c) {
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  const w = c.clientWidth,
    h = c.clientHeight;
  if (c.width !== Math.round(w * dpr) || c.height !== Math.round(h * dpr)) {
    c.width = Math.round(w * dpr);
    c.height = Math.round(h * dpr);
  }
  const g = c.getContext("2d");
  g.setTransform(dpr, 0, 0, dpr, 0, 0);
  return { g, w, h };
}

// ---- hero: PCB traces with travelling pulses, a live scope trace and a mini keypad ---------------

class Hero {
  constructor(canvas) {
    this.c = canvas;
    this.traces = [];
    this.size = [0, 0];
  }

  layout(w, h) {
    this.size = [w, h];
    const grid = 26,
      rnd = mulberry(7);
    this.traces = [];
    const count = Math.round((w * h) / 26000);
    for (let i = 0; i < count; i++) {
      let x = Math.round((rnd() * w) / grid) * grid,
        y = Math.round((rnd() * h) / grid) * grid;
      const pts = [[x, y]];
      let dir = Math.floor(rnd() * 4);
      for (let s = 0; s < 3 + Math.floor(rnd() * 4); s++) {
        const len = grid * (2 + Math.floor(rnd() * 6));
        const d = [
          [1, 0],
          [0, 1],
          [-1, 0],
          [0, -1],
          [1, 1],
          [1, -1],
          [-1, 1],
          [-1, -1],
        ][dir];
        const k = d[0] && d[1] ? 0.7071 : 1;
        x += d[0] * len * k;
        y += d[1] * len * k;
        pts.push([x, y]);
        dir = (dir + (rnd() < 0.5 ? 4 : 1) + Math.floor(rnd() * 2)) % 8; // 45/90 deg turns, PCB style
      }
      const lens = [0];
      for (let j = 1; j < pts.length; j++)
        lens.push(
          lens[j - 1] +
            Math.hypot(pts[j][0] - pts[j - 1][0], pts[j][1] - pts[j - 1][1]),
        );
      this.traces.push({
        pts,
        lens,
        total: lens.at(-1),
        speed: 60 + rnd() * 120,
        offset: rnd() * 1000,
        hue: rnd() < 0.7 ? "255,213,79" : "79,195,247",
      });
    }
  }

  pointAt(t, d) {
    const { pts, lens } = t;
    let j = 1;
    while (j < lens.length - 1 && lens[j] < d) j++;
    const f = (d - lens[j - 1]) / (lens[j] - lens[j - 1] || 1);
    return [
      pts[j - 1][0] + (pts[j][0] - pts[j - 1][0]) * f,
      pts[j - 1][1] + (pts[j][1] - pts[j - 1][1]) * f,
    ];
  }

  note(time) {
    const total = MELODY.reduce((a, [, b]) => a + b, 0) * BEAT_S;
    let t = time % total;
    for (const [key, beats] of MELODY) {
      const dur = beats * BEAT_S;
      if (t < dur) return { key, gate: t < dur * 0.85 };
      t -= dur;
    }
    return { key: MELODY[0][0], gate: false };
  }

  draw(time) {
    const { g, w, h } = fitCanvas(this.c);
    if (w !== this.size[0] || h !== this.size[1]) this.layout(w, h);
    const bg = g.createRadialGradient(
      w / 2,
      h * 0.38,
      0,
      w / 2,
      h * 0.4,
      Math.max(w, h) * 0.75,
    );
    bg.addColorStop(0, "#1c2732");
    bg.addColorStop(1, "#0b0f14");
    g.fillStyle = bg;
    g.fillRect(0, 0, w, h);

    // traces and pads
    g.lineWidth = 2;
    for (const t of this.traces) {
      g.strokeStyle = `rgba(${t.hue},0.07)`;
      g.beginPath();
      t.pts.forEach(([x, y], i) => (i ? g.lineTo(x, y) : g.moveTo(x, y)));
      g.stroke();
      g.fillStyle = `rgba(${t.hue},0.12)`;
      for (const [x, y] of [t.pts[0], t.pts.at(-1)]) {
        g.beginPath();
        g.arc(x, y, 4, 0, TAU);
        g.fill();
      }
    }
    // pulses with fading tails
    for (const t of this.traces) {
      const head = ((time * t.speed + t.offset) % (t.total + 200)) - 100;
      for (let k = 0; k < 14; k++) {
        const d = head - k * 5;
        if (d < 0 || d > t.total) continue;
        const [x, y] = this.pointAt(t, d);
        g.fillStyle = `rgba(${t.hue},${(0.55 * (1 - k / 14)).toFixed(3)})`;
        g.beginPath();
        g.arc(x, y, k === 0 ? 2.6 : 2, 0, TAU);
        g.fill();
      }
    }

    // scope trace of the current note (filtered square wave with vibrato)
    const { key, gate } = this.note(time);
    const hz = keyHz(key);
    const yMid = h * 0.79,
      amp = Math.min(30, h * 0.035);
    const cycles = hz / 45;
    const vib = 1 + 0.012 * Math.sin(time * TAU * 5.5);
    g.save();
    g.beginPath();
    for (let x = 0; x <= w; x += 2) {
      const ph = (x / w) * cycles * TAU * vib - time * 9;
      const y = gate ? Math.tanh(5 * Math.sin(ph)) : 0.04 * Math.sin(ph * 0.3);
      if (x === 0) g.moveTo(x, yMid - y * amp);
      else g.lineTo(x, yMid - y * amp);
    }
    g.strokeStyle = "rgba(79,195,247,0.18)";
    g.lineWidth = 10;
    g.stroke();
    g.strokeStyle = "#7fd8ff";
    g.lineWidth = 2;
    g.shadowColor = "#4fc3f7";
    g.shadowBlur = 14;
    g.stroke();
    g.restore();

    // mini keypad lighting the touched key
    const kw = Math.min(22, (w * 0.4) / 12),
      kh = kw * 1.8;
    const x0 = w / 2 - (kw * 12) / 2,
      y0 = h * 0.86;
    let nat = 0;
    for (let k = 1; k <= 20; k++) {
      const sharp = SHARP_KEYS.has(k);
      const on = gate && k === key;
      if (!sharp) {
        g.fillStyle = on ? "#ffd54f" : "rgba(201,168,90,0.35)";
        g.fillRect(x0 + nat * kw + 1, y0, kw - 2, kh);
        nat++;
      }
    }
    nat = 0;
    for (let k = 1; k <= 20; k++) {
      if (!SHARP_KEYS.has(k)) {
        nat++;
        continue;
      }
      const on = gate && k === key;
      g.fillStyle = on ? "#ffd54f" : "rgba(120,100,55,0.9)";
      g.fillRect(x0 + nat * kw - kw * 0.3, y0, kw * 0.6, kh * 0.6);
    }
    g.font = "12px system-ui, sans-serif";
    g.textAlign = "center";
    g.fillStyle = "#8796a5";
    if (gate)
      g.fillText(
        `${keyName(key)}  ·  ${hz.toFixed(1)} Hz  ·  555 at ${(2 * hz).toFixed(0)} Hz, ÷2`,
        w / 2,
        y0 + kh + 20,
      );
  }
}

function mulberry(seed) {
  return () => {
    seed |= 0;
    seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

// ---- hero 3D model: auto-rotates, drag to spin (zoom off so the page still scrolls) ------------------

const RESUME_SPIN_MS = 2500;

class HeroModel {
  constructor(host) {
    this.host = host;
    this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    this.renderer.toneMapping = THREE.NeutralToneMapping;
    this.renderer.setClearColor(0x000000, 0);
    host.prepend(this.renderer.domElement);

    this.scene = new THREE.Scene();
    const pmrem = new THREE.PMREMGenerator(this.renderer);
    this.scene.environment = pmrem.fromScene(
      new RoomEnvironment(),
      0.04,
    ).texture;
    this.scene.environmentIntensity = 0.6;
    const key = new THREE.DirectionalLight(0xffffff, 1.5);
    key.position.set(150, 300, 200);
    const rim = new THREE.DirectionalLight(0xffd54f, 1.2);
    rim.position.set(-250, 120, -200);
    this.scene.add(key, rim);

    this.camera = new THREE.PerspectiveCamera(30, 1, 1, 5000);
    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    Object.assign(this.controls, {
      enableZoom: false,
      enablePan: false,
      enableDamping: true,
      dampingFactor: 0.08,
      autoRotate: !reduced,
      autoRotateSpeed: 1.6,
      minPolarAngle: 0.12 * Math.PI,
      maxPolarAngle: 0.56 * Math.PI,
    });
    this.resumeAt = 0;
    this.controls.addEventListener("start", () => {
      this.controls.autoRotate = false;
      this.resumeAt = Infinity;
    });
    this.controls.addEventListener("end", () => {
      this.resumeAt = performance.now() + RESUME_SPIN_MS;
    });
    this.renderer.domElement.addEventListener("dblclick", () =>
      this.resetView(),
    );
    new ResizeObserver(() => this.resize()).observe(host);
  }

  async load() {
    const model = (await loadSynthModel()).scene.clone(true);
    const box = new THREE.Box3().setFromObject(model);
    const center = box.getCenter(new THREE.Vector3());
    this.radius = box.getSize(new THREE.Vector3()).length() / 2;
    model.position.sub(center);
    this.pivot = new THREE.Group();
    this.pivot.add(model);
    this.scene.add(this.pivot);
    // soft glow on the "floor" under the model
    const c = document.createElement("canvas");
    c.width = c.height = 256;
    const g = c.getContext("2d");
    const grad = g.createRadialGradient(128, 128, 0, 128, 128, 128);
    grad.addColorStop(0, "rgba(255,213,79,0.35)");
    grad.addColorStop(1, "rgba(255,213,79,0)");
    g.fillStyle = grad;
    g.fillRect(0, 0, 256, 256);
    const glow = new THREE.Mesh(
      new THREE.PlaneGeometry(this.radius * 2.6, this.radius * 2.6),
      new THREE.MeshBasicMaterial({
        map: new THREE.CanvasTexture(c),
        transparent: true,
        depthWrite: false,
      }),
    );
    glow.rotation.x = -Math.PI / 2;
    glow.position.y = box.min.y - center.y - 6;
    this.scene.add(glow);
    this.resetView();
    this.resize();
  }

  resetView() {
    const d =
      (this.radius / Math.sin((this.camera.fov * Math.PI) / 360)) * 0.86;
    this.camera.position.set(d * 0.35, d * 0.55, d * 0.76);
    this.controls.target.set(0, 0, 0);
    this.controls.update();
  }

  resize() {
    const w = this.host.clientWidth,
      h = this.host.clientHeight;
    if (!w || !h) return;
    this.renderer.setSize(w, h);
    this.camera.aspect = w / h;
    this.camera.updateProjectionMatrix();
  }

  render(t) {
    if (!this.pivot) return;
    if (!reduced && performance.now() > this.resumeAt)
      this.controls.autoRotate = true;
    if (!reduced) {
      this.pivot.position.y = Math.sin(t * 1.1) * 3;
      this.pivot.rotation.z = Math.sin(t * 0.7) * 0.025;
    }
    this.controls.update();
    this.renderer.render(this.scene, this.camera);
  }
}

function heroFallback(host) {
  const img = Object.assign(document.createElement("img"), {
    src: "media/printed_closeup.jpg",
    alt: "StyloSynth-555 in its printed tray",
    className: "hero-model-img",
  });
  host.replaceChildren(img);
}

// ---- signal-chain mini scopes ------------------------------------------------------------------

const WAVES = {
  keys: (x, t) => (((Math.floor(x * 6 + t * 1.5) * 7919) % 9) / 8) * 1.6 - 0.8, // stylus hopping between taps
  osc: (x, t) => (Math.sin((x * 8 - t * 3) * TAU) >= 0 ? 0.8 : -0.8),
  div: (x, t) => (Math.sin((x * 4 - t * 1.5) * TAU) >= 0 ? 0.8 : -0.8),
  tone: (x, t) => 0.8 * Math.tanh(2.2 * Math.sin((x * 4 - t * 1.5) * TAU)),
  amp: (x, t) =>
    Math.max(
      -0.92,
      Math.min(0.92, 1.25 * Math.tanh(2.2 * Math.sin((x * 4 - t * 1.5) * TAU))),
    ),
  lfo: (x, t) =>
    0.8 * (2 / Math.PI) * Math.asin(Math.sin((x * 1.2 - t * 0.6) * TAU)),
  pwr: (x, t) => 0.35 + 0.03 * Math.sin((x * 30 - t * 6) * TAU),
};
const WAVE_COLORS = {
  keys: "#ffb74d",
  osc: "#4fc3f7",
  div: "#81c784",
  tone: "#ba68c8",
  amp: "#f06292",
  lfo: "#f06292",
  pwr: "#66bb6a",
};

function drawMini(canvas, kind, t) {
  const { g, w, h } = fitCanvas(canvas);
  g.fillStyle = "#0b0f14";
  g.fillRect(0, 0, w, h);
  g.strokeStyle = "#1e2833";
  g.beginPath();
  g.moveTo(0, h / 2);
  g.lineTo(w, h / 2);
  g.stroke();
  g.strokeStyle = WAVE_COLORS[kind];
  g.lineWidth = 2;
  g.shadowColor = WAVE_COLORS[kind];
  g.shadowBlur = 8;
  g.beginPath();
  for (let px = 0; px <= w; px += 1.5) {
    const y = h / 2 - WAVES[kind](px / w, t) * (h / 2 - 6);
    if (px === 0) g.moveTo(px, y);
    else g.lineTo(px, y);
  }
  g.stroke();
  g.shadowBlur = 0;
}

// ---- reveals, counters, pipeline progress, lightbox ---------------------------------------------

function animateCount(el) {
  const target = Number(el.dataset.count),
    dec = Number(el.dataset.dec || 0);
  const pre = el.dataset.prefix || "",
    suf = el.dataset.suffix || "";
  const fmt = (v) =>
    `${pre}${v.toLocaleString(undefined, { minimumFractionDigits: dec, maximumFractionDigits: dec })}${suf}`;
  if (reduced) {
    el.textContent = fmt(target);
    return;
  }
  const t0 = performance.now(),
    dur = 1400;
  const step = (now) => {
    const p = Math.min((now - t0) / dur, 1);
    el.textContent = fmt(target * (1 - (1 - p) ** 3));
    if (p < 1) requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
}

function setupReveals(scroller) {
  const io = new IntersectionObserver(
    (entries) => {
      for (const e of entries) {
        if (!e.isIntersecting) continue;
        e.target.classList.add("in");
        const n = e.target.querySelector("[data-count]");
        if (n) animateCount(n);
        io.unobserve(e.target);
      }
    },
    { root: scroller, threshold: 0.15 },
  );
  for (const el of scroller.querySelectorAll(".reveal")) io.observe(el);
}

function setupPipeline(scroller) {
  const list = $("#pipeline");
  const update = () => {
    const r = list.getBoundingClientRect(),
      view = scroller.getBoundingClientRect();
    const p = (view.bottom - 120 - r.top) / r.height;
    list.style.setProperty(
      "--progress",
      `${Math.max(0, Math.min(1, p)) * 100}%`,
    );
  };
  scroller.addEventListener("scroll", update, { passive: true });
  update();
}

function setupLightbox() {
  const box = $("#lightbox"),
    img = $("img", box),
    cap = $("p", box);
  for (const fig of document.querySelectorAll(".gallery figure")) {
    fig.addEventListener("click", () => {
      img.src = $("img", fig).src;
      img.alt = $("img", fig).alt;
      cap.textContent = $("figcaption", fig).textContent;
      box.hidden = false;
    });
  }
  box.addEventListener("click", () => {
    box.hidden = true;
  });
  window.addEventListener("keydown", (e) => {
    if (e.key === "Escape") box.hidden = true;
  });
}

async function init() {
  await bench.ready;
  for (const b of document.querySelectorAll("[data-go]"))
    b.addEventListener("click", () => bench.show(b.dataset.go));
  const scroller = $("#welcome-view");
  setupReveals(scroller);
  setupPipeline(scroller);
  setupLightbox();

  const hero = new Hero($("#hero-canvas"));
  let model = null;
  try {
    model = new HeroModel($("#hero-model"));
    model.load().catch((err) => {
      console.error(err);
      heroFallback($("#hero-model"));
      model = null;
    });
  } catch (err) {
    console.warn("hero 3D model unavailable:", err.message); // e.g. WebGL disabled
    heroFallback($("#hero-model"));
  }
  const minis = [...document.querySelectorAll("#chain .blk")].map((b) => ({
    c: $("canvas", b),
    kind: b.dataset.wave,
  }));
  let chainVisible = false;
  new IntersectionObserver(
    ([e]) => {
      chainVisible = e.isIntersecting;
    },
    { root: scroller },
  ).observe($("#chain"));

  const t0 = performance.now();
  const frame = (now) => {
    requestAnimationFrame(frame);
    if (bench.view !== "welcome") return;
    const t = reduced ? 1.2 : (now - t0) / 1000;
    if (scroller.scrollTop < scroller.clientHeight) {
      hero.draw(t);
      model?.render(t);
    }
    if (chainVisible) for (const m of minis) drawMini(m.c, m.kind, t);
  };
  requestAnimationFrame(frame);
}

init();
