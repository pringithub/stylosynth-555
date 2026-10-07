import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { loadSynthModel } from "./model.js";
import { RoomEnvironment } from "three/addons/environments/RoomEnvironment.js";
import { deriveParams, lfoRate, octaveIndex, pitch } from "./synth-model.js";
import {
  KEY_CODES,
  KEY_LABELS,
  LABEL_NAMES,
  controlInfo,
  shortValue,
} from "./play-info.js";
import { SoundViewer } from "./play-scope.js";
import {
  POSES,
  createHand,
  createScrewdriver,
  setPose,
  tipPosition,
} from "./play-hands.js";
import { PEDALS, PEDAL_DEFAULTS, PedalBoard } from "./play-fx.js";
import { SONGS, SongPlayer, compile } from "./play-songs.js";

const bench = window.StyloBench;
const $ = (sel) => document.querySelector(sel);

// board reference -> setting it drives
const KNOBS = { RV1: "volume", RV3: "depth" };
const TRIMMERS = { RV4: "tune", RV5: "span", RV2: "rate" };
const SWITCHES = {
  SW1: "power",
  SW2: "oct_down1",
  SW3: "oct_down2",
  SW4: "tone_soft",
  SW5: "vibrato",
};
const KNOB_SWEEP = (300 * Math.PI) / 180;
const TRIM_TURNS = 25;
const LEVER_TRAVEL = 3.0; // mm
const STYLUS_HOVER = 3.0; // mm above the pads when not touching
// tip -> cap while playing; the brass tip protrudes only 4 mm past the 10 mm barrel, so keep it
// within ~25 deg of vertical or the barrel edge dips into the board
const STYLUS_DIR = new THREE.Vector3(0.42, 1.0, 0.1).normalize();
const OVERLAY_LAYER = 1; // rendered but ignored by picking (stylus, key highlight, plug, hand)
const HAND_SCALE = 0.8;
const HAND_LINGER_MS = 450;

let model, keypad, renderer, scene, camera, controls, root, pcb, pcbTop;
const ownerOf = new Map();
const knobPivots = {},
  trimPivots = {},
  levers = {};
const keyOverlays = new Map();
const keyCenters = new Map();
let ledMaterials = [];
let stylus, stylusRest, stylusAxis, plug, playQuat;
const stylusGoal = {
  pos: new THREE.Vector3(),
  quat: new THREE.Quaternion(),
  snap: true,
};
let keypadBounds;
let playKey = 0;
let drag = null;
let master = 0.5;
const heldKeys = []; // keypad keys held on the computer keyboard, most recent last
const labels = [];
let hoverId = null;
let hand, screwdriver, handRoot;
const handState = {
  kind: null,
  ref: null,
  p: 0,
  until: 0,
  startAngle: 0,
  twist: 0,
  anchor: new THREE.Vector3(),
};
const TRIM_REGRIP = (2 * Math.PI) / 3; // a hand turns a screwdriver ~120 deg, then re-grips
let viewer;
let lastFrame = performance.now();
const audio = { ctx: null, node: null, starting: null, board: null };
const PEDAL_STORE = "stylosynth.pedals";
let pedalState = loadPedalState();
const pedalUi = {};
let player;
const raycaster = new THREE.Raycaster();
const ndc = new THREE.Vector2();

async function getJSON(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${url}: ${r.status}`);
  return r.json();
}

// ---- scene ------------------------------------------------------------------------------------

function setupScene() {
  const host = $("#play-host");
  renderer = new THREE.WebGLRenderer({ antialias: true });
  renderer.setPixelRatio(window.devicePixelRatio || 1);
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.NeutralToneMapping;
  host.append(renderer.domElement);

  scene = new THREE.Scene();
  scene.background = new THREE.Color(0x1b232c);
  const pmrem = new THREE.PMREMGenerator(renderer);
  scene.environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;
  scene.environmentIntensity = 0.55;
  const sun = new THREE.DirectionalLight(0xffffff, 1.4);
  sun.position.set(120, 400, 250);
  scene.add(sun);

  camera = new THREE.PerspectiveCamera(35, 1, 1, 5000);
  camera.layers.enable(OVERLAY_LAYER);
  controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.maxPolarAngle = Math.PI * 0.49;
  controls.minDistance = 60;
  controls.maxDistance = 900;
  new ResizeObserver(resize).observe(host);
}

function resetView() {
  camera.position.set(80, 230, 250);
  controls.target.set(72, 25, 55);
  controls.update();
}

function resize() {
  const host = $("#play-host");
  const w = host.clientWidth,
    h = host.clientHeight;
  if (!w || !h) return;
  renderer.setSize(w, h);
  camera.aspect = w / h;
  camera.updateProjectionMatrix();
}

function boxOf(obj) {
  return new THREE.Box3().setFromObject(obj);
}

function pivotAround(center, objects) {
  const pivot = new THREE.Group();
  pivot.position.copy(center);
  root.add(pivot);
  pivot.updateMatrixWorld(true);
  for (const o of objects) pivot.attach(o);
  return pivot;
}

function register(obj, info) {
  if (obj) ownerOf.set(obj, info);
}

function named(name) {
  const o = root.getObjectByName(name);
  if (!o)
    throw new Error(
      `model is missing ${name} (rebuild with bench/build_assets.py)`,
    );
  return o;
}

function toOverlayLayer(obj) {
  obj.traverse((o) => o.layers.set(OVERLAY_LAYER));
}

async function loadModel() {
  root = (await loadSynthModel()).scene.clone(true);
  scene.add(root);
  root.updateMatrixWorld(true);
  pcb = named("SS_PCB");
  pcbTop = boxOf(pcb).max.y;
  register(pcb, { kind: "pcb" });

  for (const [ref, id] of Object.entries(KNOBS)) {
    const knob = named(`SS_${ref}_knob`),
      mark = named(`SS_${ref}_mark`);
    knobPivots[ref] = {
      pivot: pivotAround(boxOf(knob).getCenter(new THREE.Vector3()), [
        knob,
        mark,
      ]),
      id,
    };
    for (const o of [
      knob,
      mark,
      root.getObjectByName(`SS_${ref}_shaft`),
      root.getObjectByName(`SS_${ref}`),
    ]) {
      register(o, { kind: "knob", id, ref });
    }
  }
  for (const [ref, id] of Object.entries(TRIMMERS)) {
    const screw = named(`SS_${ref}_screw`);
    trimPivots[ref] = {
      pivot: pivotAround(boxOf(screw).getCenter(new THREE.Vector3()), [screw]),
      id,
    };
    register(screw, { kind: "trim", id, ref });
    register(root.getObjectByName(`SS_${ref}`), { kind: "trim", id, ref });
  }
  for (const [ref, id] of Object.entries(SWITCHES)) {
    const lever = named(`SS_${ref}_lever`);
    levers[ref] = { lever, baseX: lever.position.x, id };
    register(lever, { kind: "switch", id, ref });
    register(root.getObjectByName(`SS_${ref}`), { kind: "switch", id, ref });
  }
  for (const n of ["SS_J4", "SS_J4_nose"])
    register(root.getObjectByName(n), {
      kind: "switch",
      id: "phones",
      ref: "J4",
    });

  ledMaterials = [];
  for (const n of ["SS_D2", "SS_D2_dome"]) {
    named(n).traverse((o) => {
      if (!o.isMesh) return;
      o.material = o.material.clone();
      ledMaterials.push(o.material);
    });
  }

  buildStylus();
  buildKeyOverlays();
  buildPlug();
  buildHands();
  buildLabels();
}

function buildStylus() {
  const body = named("SS_Stylus_body"),
    tip = named("SS_Stylus_tip");
  const tb = boxOf(tip);
  // the tip cone points towards the player (+z) in the exported layout
  const tipPoint = new THREE.Vector3(
    (tb.min.x + tb.max.x) / 2,
    (tb.min.y + tb.max.y) / 2,
    tb.max.z,
  );
  stylusAxis = boxOf(body)
    .getCenter(new THREE.Vector3())
    .sub(tipPoint)
    .normalize();
  stylus = pivotAround(tipPoint, [body, tip]);
  toOverlayLayer(stylus);
  stylusRest = {
    pos: stylus.position.clone(),
    quat: stylus.quaternion.clone(),
  };
  playQuat = new THREE.Quaternion().setFromUnitVectors(stylusAxis, STYLUS_DIR);
  aimRest(true);
}

function buildKeyOverlays() {
  const top = pcbTop + 0.05;
  const mat = new THREE.MeshBasicMaterial({
    color: 0xffffff,
    transparent: true,
    opacity: 0.55,
    depthWrite: false,
    side: THREE.DoubleSide,
  });
  let x0 = Infinity,
    y0 = Infinity,
    x1 = -Infinity,
    y1 = -Infinity;
  for (const k of keypad.keys) {
    const shape = new THREE.Shape(
      k.poly.map(([x, y]) => new THREE.Vector2(x, y)),
    );
    const mesh = new THREE.Mesh(new THREE.ShapeGeometry(shape), mat);
    mesh.rotation.x = Math.PI / 2; // shape (x, y) -> board (x, z)
    mesh.position.set(0, top, 0);
    mesh.visible = false;
    toOverlayLayer(mesh);
    root.add(mesh);
    keyOverlays.set(k.key, mesh);
    keyCenters.set(k.key, keyTouchPoint(k));
    for (const [x, y] of k.poly) {
      x0 = Math.min(x0, x);
      y0 = Math.min(y0, y);
      x1 = Math.max(x1, x);
      y1 = Math.max(y1, y);
    }
  }
  keypadBounds = { x0: x0 - 1, y0: y0 - 1, x1: x1 + 1, y1: y1 + 1 };
}

/** Where the stylus lands for a key: sharps in their middle, naturals on the wide part below the sharps. */
function keyTouchPoint(k) {
  const xs = k.poly.map((p) => p[0]),
    ys = k.poly.map((p) => p[1]);
  const yMax = Math.max(...ys);
  const bottomXs = k.poly.filter((p) => p[1] > yMax - 0.01).map((p) => p[0]);
  const x = k.sharp
    ? (Math.min(...xs) + Math.max(...xs)) / 2
    : (Math.min(...bottomXs) + Math.max(...bottomXs)) / 2;
  const y = k.sharp ? (Math.min(...ys) + yMax) / 2 : yMax - 7;
  const p = pcb.localToWorld(new THREE.Vector3(x, 0, y));
  p.y = pcbTop;
  return p;
}

function buildHands() {
  handRoot = new THREE.Group();
  hand = createHand();
  hand.scale.setScalar(HAND_SCALE);
  handRoot.add(hand);
  handRoot.visible = false;
  screwdriver = createScrewdriver();
  screwdriver.visible = false;
  toOverlayLayer(handRoot);
  toOverlayLayer(screwdriver);
  root.add(handRoot, screwdriver);
}

function topCenter(obj, lift = 0) {
  const b = boxOf(obj);
  return new THREE.Vector3(
    (b.min.x + b.max.x) / 2,
    b.max.y + lift,
    (b.min.z + b.max.z) / 2,
  );
}

function buildLabels() {
  const host = $("#labels");
  const add = (anchor, cls, id, key = 0) => {
    const el = document.createElement("div");
    el.className = `lbl ${cls}`;
    host.append(el);
    labels.push({ el, anchor, id, key });
  };
  for (const [ref, id] of Object.entries(KNOBS))
    add(topCenter(named(`SS_${ref}_knob`), 4), "", id);
  for (const [ref, id] of Object.entries(TRIMMERS))
    add(topCenter(named(`SS_${ref}_screw`), 3), "", id);
  for (const [ref, id] of Object.entries(SWITCHES))
    add(topCenter(named(`SS_${ref}`), 6), "", id);
  add(topCenter(named("SS_J4"), 3), "", "phones");
  keypad.keys.forEach((k) => {
    add(
      keyCenters
        .get(k.key)
        .clone()
        .setY(pcbTop + 1),
      "key",
      null,
      k.key,
    );
    labels.at(-1).el.textContent = KEY_LABELS[k.key - 1];
  });
}

function buildPlug() {
  const nose = boxOf(named("SS_J4_nose"));
  const geo = new THREE.CylinderGeometry(1.75, 1.75, 30, 24);
  geo.rotateX(Math.PI / 2);
  plug = new THREE.Mesh(
    geo,
    new THREE.MeshStandardMaterial({
      color: 0x222222,
      metalness: 0.2,
      roughness: 0.5,
    }),
  );
  plug.position.set(
    (nose.min.x + nose.max.x) / 2,
    (nose.min.y + nose.max.y) / 2,
    nose.min.z - 13,
  );
  toOverlayLayer(plug);
  root.add(plug);
}

// ---- keypad -----------------------------------------------------------------------------------

function inPoly(x, y, poly) {
  let inside = false;
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const [xi, yi] = poly[i],
      [xj, yj] = poly[j];
    if (yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi)
      inside = !inside;
  }
  return inside;
}

function keyAt(x, y) {
  const order = [
    ...keypad.keys.filter((k) => k.sharp),
    ...keypad.keys.filter((k) => !k.sharp),
  ];
  return order.find((k) => inPoly(x, y, k.poly))?.key || 0;
}

// ---- picking & interaction ---------------------------------------------------------------------

function infoOf(obj) {
  for (let o = obj; o; o = o.parent) if (ownerOf.has(o)) return ownerOf.get(o);
  return null;
}

function pick(e) {
  const r = renderer.domElement.getBoundingClientRect();
  ndc.set(
    ((e.clientX - r.left) / r.width) * 2 - 1,
    -((e.clientY - r.top) / r.height) * 2 + 1,
  );
  raycaster.setFromCamera(ndc, camera);
  const hit = raycaster.intersectObject(root, true)[0];
  if (!hit) return null;
  const info = infoOf(hit.object);
  if (info?.kind === "pcb") {
    const local = pcb.worldToLocal(hit.point.clone());
    const b = keypadBounds;
    if (
      local.x >= b.x0 &&
      local.x <= b.x1 &&
      local.z >= b.y0 &&
      local.z <= b.y1
    ) {
      return { kind: "keypad", key: keyAt(local.x, local.z), point: hit.point };
    }
  }
  return info && info.kind !== "pcb"
    ? { ...info, point: hit.point }
    : { kind: "none", point: hit.point };
}

function aimStylus(point, touching, snap) {
  stylusGoal.pos.set(
    point.x,
    pcbTop + (touching ? 0.1 : STYLUS_HOVER),
    point.z,
  );
  stylusGoal.quat.copy(playQuat);
  stylusGoal.snap = snap;
}

function aimRest(snap = false) {
  stylusGoal.pos.copy(stylusRest.pos);
  stylusGoal.quat.copy(stylusRest.quat);
  stylusGoal.snap = snap;
}

function stepStylus(dt) {
  if (stylusGoal.snap) {
    stylus.position.copy(stylusGoal.pos);
    stylus.quaternion.copy(stylusGoal.quat);
    return;
  }
  const k = 1 - Math.exp(-dt / 0.045);
  const dx = stylusGoal.pos.x - stylus.position.x,
    dz = stylusGoal.pos.z - stylus.position.z;
  stylus.position.x += dx * k;
  stylus.position.z += dz * k;
  // hop over the pads while travelling, then come down onto the target
  const yGoal = stylusGoal.pos.y + Math.min(Math.hypot(dx, dz) * 0.5, 12);
  stylus.position.y += (yGoal - stylus.position.y) * Math.min(1, 1.5 * k);
  stylus.quaternion.slerp(stylusGoal.quat, k);
}

// ---- hands ------------------------------------------------------------------------------------

function poseHandAt(pose, pitchRad, yawRad, fingers) {
  setPose(hand, POSES[pose]);
  hand.rotation.set(pitchRad, yawRad, 0, "YXZ");
  hand.position.set(0, 0, 0);
  handRoot.position.set(0, 0, 0);
  handRoot.rotation.set(0, 0, 0);
  handRoot.updateMatrixWorld(true);
  // shift the hand so the contact point (fingertip or pinch centre) sits at handRoot's origin
  const contact = new THREE.Vector3();
  for (const f of fingers) contact.add(root.worldToLocal(tipPosition(hand, f)));
  hand.position.copy(contact.divideScalar(fingers.length)).negate();
}

function engageHand(kind, ref) {
  if (!$("#hands-toggle").checked) return;
  if (handState.kind !== kind || handState.ref !== ref) {
    if (handState.kind === "trim") screwdriver.visible = false;
    handState.kind = kind;
    handState.ref = ref;
    if (kind === "knob") {
      poseHandAt("pinch", -0.3, 0.35, ["index", "thumb"]);
      handState.startAngle = knobPivots[ref].pivot.rotation.y;
    } else if (kind === "trim") {
      poseHandAt("pinch", -0.2, 0.35, ["index", "thumb"]);
      const { pivot } = trimPivots[ref];
      const top = boxOf(named(`SS_${ref}_screw`)).max.y;
      pivot.add(screwdriver);
      screwdriver.position.set(
        0,
        top - pivot.getWorldPosition(new THREE.Vector3()).y,
        0,
      );
      screwdriver.userData.baseY = screwdriver.position.y;
      handState.startAngle = pivot.rotation.y;
      handState.twist = 0;
    } else {
      poseHandAt("press", -1.05, 0.25, ["index"]);
    }
  }
  handState.until = Infinity;
}

function releaseHand(linger = HAND_LINGER_MS) {
  if (handState.kind) handState.until = performance.now() + linger;
}

function handAnchor(out) {
  const { kind, ref } = handState;
  if (kind === "knob") return out.copy(topCenter(named(`SS_${ref}_knob`), -3));
  if (kind === "trim") {
    return screwdriver
      .getWorldPosition(out)
      .add(new THREE.Vector3(0, screwdriver.userData.gripY, 0));
  }
  return out.copy(topCenter(levers[ref].lever, 0.3));
}

function stepHand(dt) {
  if (!handState.kind) return;
  const want = performance.now() < handState.until ? 1 : 0;
  handState.p += (want - handState.p) * (1 - Math.exp(-dt / 0.07));
  const p = handState.p;
  if (!want && p < 0.02) {
    handRoot.visible = false;
    screwdriver.visible = false;
    handState.kind = handState.ref = null;
    return;
  }
  const away = (1 - p) ** 2;
  if (handState.kind === "trim") {
    // the anchor sits on the screwdriver grip, so hand and screwdriver arrive and leave together
    screwdriver.visible = true;
    screwdriver.position.y = screwdriver.userData.baseY + away * 60;
    const turned =
      trimPivots[handState.ref].pivot.rotation.y - handState.startAngle;
    const target = turned - TRIM_REGRIP * Math.round(turned / TRIM_REGRIP);
    handState.twist += (target - handState.twist) * (1 - Math.exp(-dt / 0.035));
  }
  handAnchor(handState.anchor);
  handRoot.position.copy(handState.anchor);
  if (handState.kind === "trim") {
    handRoot.rotation.y = handState.twist;
  } else {
    handRoot.position.add(new THREE.Vector3(away * 30, away * 90, away * 70));
    // the hand turns with the knob while gripping it
    handRoot.rotation.y =
      handState.kind === "knob"
        ? knobPivots[handState.ref].pivot.rotation.y - handState.startAngle
        : 0;
  }
  handRoot.visible = true;
}

function stepLevers(dt) {
  const k = 1 - Math.exp(-dt / 0.035);
  for (const l of Object.values(levers)) {
    const target = l.baseX + (bench.settings[l.id] ? LEVER_TRAVEL : 0);
    l.lever.position.x += (target - l.lever.position.x) * k;
  }
}

// ---- keyboard ---------------------------------------------------------------------------------

function stylusBusy() {
  return heldKeys.length > 0 || Boolean(player?.playing);
}

function pressKey(key) {
  aimStylus(keyCenters.get(key), true, false);
  setPlayKey(key);
  showInfo("key");
}

function onKeyDown(e) {
  if (bench.view !== "play" || e.ctrlKey || e.metaKey || e.altKey) return;
  if (
    e.target instanceof Element &&
    e.target.closest("input, select, textarea")
  )
    return;
  const idx = KEY_CODES.indexOf(e.code);
  if (idx < 0) return;
  e.preventDefault();
  if (e.repeat) return;
  startAudio();
  const key = idx + 1;
  const i = heldKeys.indexOf(key);
  if (i >= 0) heldKeys.splice(i, 1);
  heldKeys.push(key);
  pressKey(key);
}

function onKeyUp(e) {
  const idx = KEY_CODES.indexOf(e.code);
  if (idx < 0) return;
  const i = heldKeys.indexOf(idx + 1);
  if (i < 0) return;
  heldKeys.splice(i, 1);
  if (heldKeys.length) {
    pressKey(heldKeys.at(-1));
  } else {
    setPlayKey(0);
    aimStylus(stylusGoal.pos.clone(), false, false); // lift in place
  }
}

function releaseAllKeys() {
  if (!heldKeys.length) return;
  heldKeys.length = 0;
  setPlayKey(0);
  aimStylus(stylusGoal.pos.clone(), false, false);
}

// ---- info card & labels -----------------------------------------------------------------------

function showInfo(id) {
  hoverId = id;
  updateInfo();
}

function updateInfo() {
  const card = $("#info-card");
  const info = hoverId
    ? controlInfo(model, bench.settings, hoverId, playKey)
    : null;
  card.hidden = !info;
  if (!info) return;
  $("#info-title").textContent = info.title;
  $("#info-value").textContent = info.value;
  $("#info-role").textContent = info.role;
}

function updateLabelText() {
  const s = bench.settings;
  for (const l of labels) {
    if (l.key) {
      l.el.classList.toggle("on", l.key === playKey);
      continue;
    }
    const v = shortValue(model, s, l.id);
    l.el.replaceChildren(
      Object.assign(document.createElement("b"), {
        textContent: LABEL_NAMES[l.id],
      }),
    );
    if (v) l.el.append(document.createElement("br"), v);
  }
}

const projected = new THREE.Vector3();

function placeLabels() {
  const host = $("#labels");
  host.hidden = !$("#labels-toggle").checked;
  if (host.hidden) return;
  const w = host.clientWidth,
    h = host.clientHeight;
  for (const l of labels) {
    projected.copy(l.anchor).project(camera);
    const visible =
      projected.z < 1 &&
      Math.abs(projected.x) < 1.05 &&
      Math.abs(projected.y) < 1.05;
    l.el.style.display = visible ? "" : "none";
    if (!visible) continue;
    const x = ((projected.x + 1) / 2) * w,
      y = ((1 - projected.y) / 2) * h;
    l.el.style.transform = `translate(${x.toFixed(1)}px, ${y.toFixed(1)}px) translate(-50%, ${l.key ? "-50%" : "-100%"})`;
  }
}

function setPlayKey(key) {
  if (key === playKey) return;
  playKey = key;
  for (const [k, mesh] of keyOverlays) mesh.visible = k === key;
  if (key) bench.set("key", key); // the Bench tab picks up the last touched key
  pushParams();
  updateHud();
  updateLabelText();
  if (hoverId === "key") updateInfo();
}

function clamp01(v) {
  return Math.min(1, Math.max(0, v));
}

function onPointerDown(e) {
  if (e.button !== 0) return;
  startAudio();
  const hit = pick(e);
  if (!hit || hit.kind === "none") return; // OrbitControls takes it
  controls.enabled = false;
  renderer.domElement.setPointerCapture(e.pointerId);
  if (hit.kind === "keypad") {
    drag = { kind: "stylus" };
    aimStylus(hit.point, Boolean(hit.key), true);
    setPlayKey(hit.key);
    showInfo("key");
  } else if (hit.kind === "knob" || hit.kind === "trim") {
    drag = {
      kind: hit.kind,
      id: hit.id,
      y0: e.clientY,
      v0: bench.settings[hit.id],
    };
    engageHand(hit.kind, hit.ref);
    showInfo(hit.id);
  } else if (hit.kind === "switch") {
    if (hit.ref !== "J4") engageHand("switch", hit.ref);
    bench.set(hit.id, !bench.settings[hit.id]);
    drag = { kind: "click" };
    showInfo(hit.id);
  }
}

function onPointerMove(e) {
  if (drag?.kind === "stylus") {
    const hit = pick(e);
    if (hit?.kind === "keypad") {
      aimStylus(hit.point, Boolean(hit.key), true);
      setPlayKey(hit.key);
    } else {
      setPlayKey(0);
    }
    return;
  }
  if (drag?.kind === "knob" || drag?.kind === "trim") {
    const sens = drag.kind === "knob" ? 200 : 800;
    bench.set(
      drag.id,
      Math.round(clamp01(drag.v0 + (drag.y0 - e.clientY) / sens) * 1000) / 1000,
    );
    return;
  }
  if (drag) return;
  const hit = pick(e);
  const kind = hit?.kind;
  renderer.domElement.style.cursor =
    kind === "keypad"
      ? "none"
      : kind === "knob" || kind === "trim"
        ? "ns-resize"
        : kind === "switch"
          ? "pointer"
          : "grab";
  if (kind === "keypad") {
    if (!stylusBusy()) aimStylus(hit.point, false, true);
    showInfo("key");
  } else {
    if (!stylusBusy()) aimRest();
    showInfo(
      kind === "knob" || kind === "trim" || kind === "switch" ? hit.id : null,
    );
  }
}

function onPointerUp(e) {
  if (!drag) return;
  if (drag.kind === "stylus") {
    setPlayKey(0);
    const hit = pick(e);
    if (hit?.kind === "keypad") aimStylus(hit.point, false, true);
    else aimRest();
  }
  if (drag.kind !== "stylus") releaseHand();
  drag = null;
  controls.enabled = true;
  if (renderer.domElement.hasPointerCapture(e.pointerId))
    renderer.domElement.releasePointerCapture(e.pointerId);
}

function onWheel(e) {
  const hit = pick(e);
  if (hit?.kind !== "knob" && hit?.kind !== "trim") return;
  e.preventDefault();
  e.stopImmediatePropagation(); // keep OrbitControls from zooming
  engageHand(hit.kind, hit.ref);
  releaseHand(700);
  const step = hit.kind === "knob" ? 0.02 : 0.004;
  bench.set(
    hit.id,
    Math.round(
      clamp01(bench.settings[hit.id] - Math.sign(e.deltaY) * step) * 1000,
    ) / 1000,
  );
}

// ---- state -> model / audio / HUD --------------------------------------------------------------

function applySettings() {
  const s = bench.settings;
  for (const { pivot, id } of Object.values(knobPivots))
    pivot.rotation.y = -(s[id] - 0.5) * KNOB_SWEEP;
  for (const { pivot, id } of Object.values(trimPivots))
    pivot.rotation.y = -s[id] * TRIM_TURNS * 2 * Math.PI;
  for (const m of ledMaterials) {
    m.emissive.setHex(s.power ? 0xff2010 : 0x000000);
    m.emissiveIntensity = s.power ? 2.5 : 0;
  }
  plug.visible = s.phones;
  pushParams();
  updateHud();
  updateLabelText();
  updateInfo();
}

function pushParams() {
  if (audio.node)
    audio.node.port.postMessage({
      params: deriveParams(model, bench.settings, playKey),
    });
}

function pct(v) {
  return `${Math.round(v * 100)} %`;
}

function updateHud() {
  const s = bench.settings;
  const p = s.power && playKey ? pitch(model, s, playKey) : null;
  $("#hud-note").textContent = p ? p.note : s.power ? "—" : "OFF";
  $("#hud-freq").textContent = p
    ? `555 ${p.f555.toFixed(1)} Hz · out ${p.fOut.toFixed(2)} Hz · ${p.cents >= 0 ? "+" : ""}${p.cents.toFixed(1)} c`
    : s.power
      ? "stylus up"
      : "power off";
  const vib = s.vibrato
    ? `vibrato ${lfoRate(model, s.rate).toFixed(1)} Hz, depth ${pct(s.depth)}`
    : "vibrato off";
  $("#hud-state").textContent =
    `${model.octaves[octaveIndex(s)]} · ${s.tone_soft ? "soft" : "bright"} · ${vib} · ` +
    `vol ${pct(s.volume)}${s.phones ? " · phones" : ""}`;
}

// ---- audio ------------------------------------------------------------------------------------

function setAudioButton(state) {
  const b = $("#audio-btn");
  b.textContent =
    state === "on"
      ? "Audio on"
      : state === "error"
        ? "Audio failed"
        : "Start audio";
  b.classList.toggle("on", state === "on");
}

function startAudio() {
  if (audio.ctx) {
    if (audio.ctx.state !== "running")
      audio.ctx.resume().then(() => setAudioButton("on"));
    return audio.starting;
  }
  // created synchronously inside the user gesture so the browser allows playback
  const ctx = new AudioContext({ latencyHint: "interactive" });
  audio.ctx = ctx;
  audio.starting = ctx.audioWorklet
    .addModule("synth-worklet.js")
    .then(() => {
      audio.node = new AudioWorkletNode(ctx, "stylosynth", {
        numberOfInputs: 0,
        outputChannelCount: [2],
        processorOptions: {
          params: deriveParams(model, bench.settings, playKey),
          master,
        },
      });
      audio.board = new PedalBoard(
        ctx,
        audio.node,
        pedalState,
        $("#trails-toggle").checked,
      );
      audio.board.output.connect(ctx.destination);
      viewer.attach(ctx, audio.board.output);
      setAudioButton("on");
    })
    .catch((err) => {
      console.error(err);
      setAudioButton("error");
    });
  return audio.starting;
}

function toggleAudio() {
  if (audio.ctx?.state === "running") {
    audio.ctx.suspend().then(() => setAudioButton("off"));
  } else {
    startAudio();
  }
}

let resumeOnReturn = false;

/** Leaving Play stops everything at once (song, held keys, echo and reverb tails); coming back resumes. */
function onViewChange(view) {
  if (view !== "play") {
    if (player?.playing) stopSong();
    releaseAllKeys();
    setPlayKey(0);
    if (audio.ctx?.state === "running") {
      resumeOnReturn = true;
      audio.ctx.suspend().then(() => setAudioButton("off"));
    }
  } else if (resumeOnReturn && audio.ctx) {
    resumeOnReturn = false;
    // fresh, empty delay lines and reverb, so no frozen tail resumes mid-echo
    audio.node.disconnect();
    audio.board.dispose();
    audio.board = new PedalBoard(
      audio.ctx,
      audio.node,
      pedalState,
      $("#trails-toggle").checked,
    );
    audio.board.output.connect(audio.ctx.destination);
    viewer.attach(audio.ctx, audio.board.output);
    pushParams(); // re-send the lifted-stylus state in case it was queued behind the suspend
    audio.ctx.resume().then(() => setAudioButton("on"));
  }
}

// ---- pedals -----------------------------------------------------------------------------------

function loadPedalState() {
  const state = structuredClone(PEDAL_DEFAULTS);
  try {
    const saved = JSON.parse(localStorage.getItem(PEDAL_STORE) || "{}");
    for (const p of Object.keys(state)) {
      for (const k of Object.keys(state[p])) {
        if (typeof saved[p]?.[k] === typeof state[p][k])
          state[p][k] = saved[p][k];
      }
    }
  } catch {
    /* corrupt or unavailable storage: keep defaults */
  }
  return state;
}

function savePedalState() {
  try {
    localStorage.setItem(PEDAL_STORE, JSON.stringify(pedalState));
  } catch {
    /* storage disabled */
  }
}

function buildPedals() {
  const host = $("#pedals");
  for (const p of PEDALS) {
    const box = document.createElement("div");
    box.className = "pedal";
    box.style.setProperty("--pedal", p.color);
    box.title = p.about;
    const head = document.createElement("div");
    head.className = "pedal-head";
    head.append(
      p.name,
      Object.assign(document.createElement("span"), { className: "led" }),
    );
    box.append(head);
    const ui = { box, params: {} };
    for (const prm of p.params) {
      const label = document.createElement("label");
      const input = Object.assign(document.createElement("input"), {
        type: "range",
        min: prm.min,
        max: prm.max,
        step: prm.step,
      });
      const out = Object.assign(document.createElement("span"), {
        className: "pv",
      });
      input.addEventListener("input", () =>
        setPedal(p.id, prm.id, Number(input.value)),
      );
      label.append(prm.label, input, out);
      box.append(label);
      ui.params[prm.id] = { input, out, fmt: prm.fmt };
    }
    const stomp = Object.assign(document.createElement("button"), {
      type: "button",
      className: "stomp",
      title: `${p.name} on/off`,
    });
    stomp.addEventListener("click", () => {
      startAudio();
      setPedal(p.id, "on", !pedalState[p.id].on);
    });
    box.append(stomp);
    host.append(box);
    pedalUi[p.id] = ui;
  }
  refreshPedals();
}

function refreshPedals() {
  for (const [id, ui] of Object.entries(pedalUi)) {
    const s = pedalState[id];
    ui.box.classList.toggle("on", s.on);
    for (const [k, { input, out, fmt }] of Object.entries(ui.params)) {
      input.value = s[k];
      out.textContent = fmt(s[k]);
    }
  }
}

function setPedal(pedal, param, value) {
  pedalState[pedal][param] = value;
  audio.board?.set(pedal, param, value);
  savePedalState();
  refreshPedals();
}

function loadPedals(state) {
  pedalState = state;
  audio.board?.load(state);
  savePedalState();
  refreshPedals();
}

// ---- songs ------------------------------------------------------------------------------------

function buildSongs() {
  const sel = $("#song-select");
  for (const s of SONGS) sel.append(new Option(s.title, s.id));
  sel.addEventListener("change", () => {
    if (player.playing) startSong();
    else showSongCredit();
  });
  $("#song-play").addEventListener("click", () =>
    player.playing ? stopSong() : startSong(),
  );
  $("#song-loop").addEventListener("change", (e) => {
    if (player.playing) player.loop = e.target.checked;
  });
  player = new SongPlayer({
    press: (key) => pressKey(key),
    release: () => {
      setPlayKey(0);
      aimStylus(stylusGoal.pos.clone(), false, false);
    },
    progress: (text) => {
      $("#song-status").textContent = text;
    },
    set: applySongChanges,
    ended: () => setSongButton(false),
  });
  showSongCredit();
}

/** Automation from a song: panel settings (`tone` = soft/bright) and `pedal.param` keys. */
function applySongChanges(changes, pedals) {
  for (const [k, v] of Object.entries(changes)) {
    if (k.includes(".")) {
      const [pedal, param] = k.split(".");
      setPedal(pedal, param, v);
    } else if (k === "tone") {
      bench.set("tone_soft", v === "soft");
    } else {
      bench.set(k, v);
    }
  }
  for (const [pedal, preset] of Object.entries(pedals)) {
    for (const [param, v] of Object.entries(preset)) setPedal(pedal, param, v);
  }
}

function showSongCredit() {
  const s = SONGS.find((x) => x.id === $("#song-select").value);
  $("#song-status").textContent = `${s.credit} · ${s.bpm} bpm`;
}

function setSongButton(playing) {
  $("#song-play").textContent = playing ? "Stop" : "Play song";
  $("#song-play").classList.toggle("on", playing);
  if (!playing) showSongCredit();
}

async function startSong() {
  const song = SONGS.find((x) => x.id === $("#song-select").value);
  let compiled;
  try {
    compiled = compile(song, model);
  } catch (err) {
    $("#song-status").textContent = err.message;
    return;
  }
  player.stop();
  heldKeys.length = 0;
  bench.set("power", true);
  bench.set("phones", false);
  const pedals = structuredClone(PEDAL_DEFAULTS);
  for (const [id, preset] of Object.entries(compiled.pedals))
    Object.assign(pedals[id], preset);
  loadPedals(pedals);
  setSongButton(true);
  await startAudio();
  player.play(compiled, $("#song-loop").checked);
}

function stopSong() {
  player.stop();
  setSongButton(false);
}

// ---- wiring -----------------------------------------------------------------------------------

function bindUI() {
  const canvas = renderer.domElement;
  canvas.addEventListener("pointerdown", onPointerDown, { capture: true });
  canvas.addEventListener("pointermove", onPointerMove);
  canvas.addEventListener("pointerup", onPointerUp);
  canvas.addEventListener("pointercancel", onPointerUp);
  canvas.addEventListener("pointerleave", () => {
    if (drag) return;
    if (!stylusBusy()) aimRest();
    showInfo(null);
  });
  canvas.addEventListener("wheel", onWheel, { capture: true, passive: false });
  window.addEventListener("keydown", onKeyDown);
  window.addEventListener("keyup", onKeyUp);
  window.addEventListener("blur", releaseAllKeys);
  bench.onView(onViewChange);
  $("#hands-toggle").addEventListener("change", () => releaseHand(0));
  $("#audio-btn").addEventListener("click", toggleAudio);
  $("#master").addEventListener("input", (e) => {
    master = Number(e.target.value);
    $("#master-val").textContent = pct(master);
    audio.node?.port.postMessage({ master });
  });
  $("#view-reset").addEventListener("click", resetView);
  $("#probe-btn").addEventListener("click", () => bench.show("bench"));
  bindPrefs();
}

const PREFS_STORE = "stylosynth.prefs";

function bindPrefs() {
  let prefs = {};
  try {
    prefs = JSON.parse(localStorage.getItem(PREFS_STORE) || "{}");
  } catch {
    /* keep defaults */
  }
  const save = () => {
    try {
      localStorage.setItem(PREFS_STORE, JSON.stringify(prefs));
    } catch {
      /* storage disabled */
    }
  };
  const board = $("#pedalboard"),
    minBtn = $("#pedals-min");
  const setMin = (min) => {
    board.classList.toggle("min", min);
    minBtn.textContent = min ? "+" : "–";
    minBtn.title = min ? "Show the pedal knobs" : "Minimise the pedals";
    prefs.pedalsMin = min;
    save();
  };
  setMin(Boolean(prefs.pedalsMin));
  minBtn.addEventListener("click", () =>
    setMin(!board.classList.contains("min")),
  );

  const trails = $("#trails-toggle");
  trails.checked = Boolean(prefs.trails);
  trails.addEventListener("change", () => {
    prefs.trails = trails.checked;
    save();
    audio.board?.setTrails(trails.checked);
  });
}

function animate() {
  requestAnimationFrame(animate);
  const now = performance.now();
  const dt = Math.min((now - lastFrame) / 1000, 0.1);
  lastFrame = now;
  if (bench.view !== "play") return;
  stepStylus(dt);
  stepLevers(dt);
  stepHand(dt);
  controls.update();
  renderer.render(scene, camera);
  placeLabels();
  const s = bench.settings;
  viewer.draw(s.power && playKey ? pitch(model, s, playKey).fOut : 0);
}

async function init() {
  try {
    [model, keypad] = await Promise.all([
      // without the Python server, fall back to the parameters recorded by bench/export_demo.py
      (bench.hosted ? Promise.reject() : getJSON("api/play_model")).catch(() =>
        getJSON("demo/play_model.json"),
      ),
      getJSON("model/keypad.json"),
    ]);
    await bench.ready;
    setupScene();
    await loadModel();
  } catch (err) {
    console.error(err);
    const hint = /WebGL/i.test(err.message)
      ? " (WebGL is disabled in this browser; open the page in Chrome or Firefox)"
      : "";
    $("#play-loading").textContent =
      `Play view failed to load: ${err.message}${hint}`;
    return;
  }
  $("#play-loading").hidden = true;
  viewer = new SoundViewer(
    $("#sound-scope"),
    $("#sound-fft"),
    $("#sound-readout"),
  );
  buildPedals();
  buildSongs();
  resetView();
  resize();
  bindUI();
  bench.onChange(applySettings);
  bench.onView((v) => {
    if (v === "play") resize();
  });
  applySettings();
  animate();
}

init();
