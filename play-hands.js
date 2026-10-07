// Procedural right hand (capsule phalanges, posable joints) and a screwdriver, sized in mm.
import * as THREE from "three";

const SKIN = new THREE.MeshStandardMaterial({
  color: 0xd8a07f,
  roughness: 0.6,
  metalness: 0,
});

// palm-down right hand, fingers along -z, thumb on the -x side; [x at knuckle, phalanx lengths, radius]
const FINGERS = {
  index: [-24, [38, 24, 19], 7.6],
  middle: [-7, [43, 27, 21], 7.9],
  ring: [10, [40, 25, 20], 7.4],
  pinky: [25, [31, 19, 17], 6.6],
};
const THUMB = { base: [-36, -6, 4], lengths: [30, 24, 20], radius: 9 };

function capsuleGeo(r, len) {
  const g = new THREE.CapsuleGeometry(r, len, 6, 14);
  g.rotateX(Math.PI / 2); // capsule axis -> z
  return g;
}

function chain(lengths, radius) {
  const root = new THREE.Group();
  const joints = [];
  let parent = root;
  lengths.forEach((len, i) => {
    const joint = new THREE.Group();
    parent.add(joint);
    joints.push(joint);
    const r = radius * (1 - 0.09 * i);
    const seg = new THREE.Mesh(capsuleGeo(r, len), SKIN);
    seg.position.z = -len / 2;
    joint.add(seg);
    const next = new THREE.Group();
    next.position.z = -len;
    joint.add(next);
    parent = next;
  });
  const tip = new THREE.Group();
  tip.position.z = -radius * 0.7; // fingertip pad, just inside the end cap
  parent.add(tip);
  return { root, joints, tip };
}

export function createHand() {
  const hand = new THREE.Group();
  const palm = new THREE.Mesh(new THREE.SphereGeometry(1, 28, 18), SKIN);
  palm.scale.set(40, 11, 44);
  palm.position.z = -4;
  hand.add(palm);
  const wrist = new THREE.Mesh(capsuleGeo(24, 70), SKIN);
  wrist.scale.set(1.15, 0.7, 1);
  wrist.position.z = 70;
  hand.add(wrist);

  const fingers = {};
  for (const [name, [x, lengths, r]] of Object.entries(FINGERS)) {
    const c = chain(lengths, r);
    c.root.position.set(x, 0, -40);
    c.root.rotation.y = -x * 0.004; // slight splay
    hand.add(c.root);
    fingers[name] = c;
  }
  const thumb = chain(THUMB.lengths, THUMB.radius);
  thumb.root.position.set(...THUMB.base);
  hand.add(thumb.root);
  fingers.thumb = thumb;
  hand.userData.fingers = fingers;
  return hand;
}

// curl angles (rad) per phalanx; thumb also has yaw (towards the index side), pitch (down) and roll
export const POSES = {
  // index-thumb gap ~16 mm (found by grid search), fingertips level and pointing down
  pinch: {
    index: [0.8, 0.88, 0.56],
    middle: [1.0, 1.08, 0.56],
    ring: [1.25, 1.45, 0.9],
    pinky: [1.3, 1.45, 0.9],
    thumb: { yaw: 1.0, pitch: -0.4, roll: 0.6, curl: [0.9, 0.3, 0.2] },
  },
  press: {
    index: [0.12, 0.08, 0.05],
    middle: [1.35, 1.5, 1.0],
    ring: [1.4, 1.55, 1.0],
    pinky: [1.4, 1.55, 1.0],
    thumb: { yaw: 0.9, pitch: -0.7, roll: 0.9, curl: [0.5, 0.6, 0.4] },
  },
};

export function setPose(hand, pose) {
  const f = hand.userData.fingers;
  for (const name of ["index", "middle", "ring", "pinky"]) {
    f[name].joints.forEach((j, i) => {
      j.rotation.x = -pose[name][i];
    });
  }
  const t = pose.thumb;
  f.thumb.root.rotation.set(t.pitch, t.yaw, t.roll, "YXZ");
  f.thumb.joints.forEach((j, i) => {
    j.rotation.x = -t.curl[i];
  });
}

export function tipPosition(hand, finger, target = new THREE.Vector3()) {
  hand.updateMatrixWorld(true);
  return hand.userData.fingers[finger].tip.getWorldPosition(target);
}

/** Screwdriver with its blade tip at the origin, pointing down (-y). */
export function createScrewdriver() {
  const g = new THREE.Group();
  const steel = new THREE.MeshStandardMaterial({
    color: 0xc8ccd0,
    metalness: 1,
    roughness: 0.3,
  });
  const grip = new THREE.MeshStandardMaterial({
    color: 0xd32f2f,
    roughness: 0.45,
  });
  const blade = new THREE.Mesh(new THREE.BoxGeometry(2.2, 3, 0.5), steel);
  blade.position.y = 1.5;
  const shaft = new THREE.Mesh(
    new THREE.CylinderGeometry(1.1, 1.1, 32, 16),
    steel,
  );
  shaft.position.y = 3 + 16;
  const handle = new THREE.Mesh(
    new THREE.CylinderGeometry(6.5, 5.5, 42, 6),
    grip,
  );
  handle.position.y = 35 + 21;
  g.add(blade, shaft, handle);
  g.userData.gripY = 35 + 21;
  return g;
}
