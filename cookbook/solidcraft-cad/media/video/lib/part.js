// Shared Three.js rig for the solidcraft-cad video shots.
//
// The 3D shown here is the demo's own deliverable: the .glb next to each shot
// is written by media/video/export_glb.py from the STEP file SolidCraft
// produced, so every vertex is graded geometry, not a redrawn stand-in.
//
// Every shot builds the same rig and then animates it from its own timeline.
// A shot's `seek(t)` is called once per rendered frame by HyperFrames, so all
// motion below is a pure function of time: the same t always paints the same
// frame, which is what makes the render deterministic.

import * as THREE from './three.module.js';
import { GLTFLoader } from './GLTFLoader.js';
import { mergeVertices } from './BufferGeometryUtils.js';

export const MM_PER_UNIT = 20; // the part is 60x50x9 mm -> ~3 units across

const STEEL = { color: 0xd9d6d0, metalness: 0.86, roughness: 0.34 };
const STEEL_DARK = { color: 0x8f949c, metalness: 0.9, roughness: 0.42 };

export function partMaterial(overrides = {}) {
  return new THREE.MeshStandardMaterial({ ...STEEL, ...overrides });
}

// Build a rig: renderer, scene, camera, lights, and a holder for the model.
// `stageEl` is the DOM node the canvas is appended to.
export function makeRig(stageEl, { fov = 32, exposure = 1.05, background = 0x0d1015 } = {}) {
  const renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true });
  renderer.setSize(1920, 1080, false);
  renderer.setPixelRatio(1);
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = exposure;
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  stageEl.appendChild(renderer.domElement);

  const scene = new THREE.Scene();
  scene.background = new THREE.Color(background);
  const camera = new THREE.PerspectiveCamera(fov, 1920 / 1080, 0.02, 400);

  // Three-point rig, fixed to camera space so the part never goes flat.
  const key = new THREE.DirectionalLight(0xffffff, 3.0);
  const fill = new THREE.DirectionalLight(0x9db4dc, 1.25);
  const rim = new THREE.DirectionalLight(0xffd9a8, 1.5);
  const amb = new THREE.AmbientLight(0x66768f, 1.15);
  scene.add(key, fill, rim, amb);
  key.position.set(4, 6, 5);
  fill.position.set(-5, 2, -4);
  rim.position.set(-2, 3, 6);

  const holder = new THREE.Group(); // rotates/spins the model
  const model = new THREE.Group();  // holds the loaded faces
  holder.add(model);
  scene.add(holder);

  return { renderer, scene, camera, holder, model, lights: { key, fill, rim } };
}

// Load a .glb and split it into one mesh per OpenCascade face, so shots can
// pull faces apart (explode) and slide half the solid away (section).
// Returns null while loading; the shot keeps rendering until it resolves, so
// the first captured frame is never a blank canvas.
export function loadFaces(rig, url, opts = {}) {
  const done = { ready: false, faces: [], error: null, box: null };
  const material = opts.material || (() => partMaterial());
  new GLTFLoader().load(
    url,
    (gltf) => {
      const faceGeoms = [];
      gltf.scene.updateWorldMatrix(true, true);
      gltf.scene.traverse((node) => {
        if (!node.isMesh || !node.geometry) return;
        const g = mergeVertices(node.geometry.clone(), 1e-4);
        g.computeVertexNormals();
        g.applyMatrix4(node.matrixWorld);
        // Faces from the B-spline exports arrive as several patches per
        // surface; keep them in their file order and group by proximity later.
        faceGeoms.push(g);
      });
      const total = new THREE.Box3();
      for (const g of faceGeoms) {
        g.computeBoundingBox();
        total.union(g.boundingBox);
      }
      const centre = total.getCenter(new THREE.Vector3());
      for (const g of faceGeoms) {
        g.translate(-centre.x, -centre.y, -centre.z);
        const mesh = new THREE.Mesh(g, material());
        mesh.userData.centroid = g.boundingBox.getCenter(new THREE.Vector3());
        done.faces.push(mesh);
        rig.model.add(mesh);
      }
      rig.model.scale.setScalar(1 / MM_PER_UNIT);
      done.box = new THREE.Box3().setFromObject(rig.model);
      done.ready = true;
    },
    undefined,
    (err) => { done.error = String(err); }
  );
  return done;
}

// Convenience: aim the camera at the origin from a spherical position.
export function placeCamera(camera, { dist = 9.5, azim = 0, elev = 0, fov }) {
  const a = (azim * Math.PI) / 180;
  const e = (elev * Math.PI) / 180;
  camera.position.set(
    dist * Math.cos(e) * Math.sin(a),
    dist * Math.sin(e),
    dist * Math.cos(e) * Math.cos(a)
  );
  camera.lookAt(0, 0, 0);
  if (fov) { camera.fov = fov; camera.updateProjectionMatrix(); }
}

export function easeInOut(t) { return t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2; }
export function easeOut(t) { return 1 - Math.pow(1 - t, 3); }
export function clamp01(x) { return Math.max(0, Math.min(1, x)); }
// Normalised progress of t inside [a, b], clamped to 0..1.
export function span(t, a, b) { return clamp01((t - a) / Math.max(1e-6, b - a)); }
export { THREE };
