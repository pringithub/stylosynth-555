// One shared download of the module's 3D model for the Welcome and Play views.
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";

let pending = null;

/** Resolves to the parsed glTF; callers that modify the scene graph should clone it. */
export function loadSynthModel() {
  pending ??= new GLTFLoader().loadAsync("model/stylosynth.glb");
  return pending;
}
