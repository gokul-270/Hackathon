/**
 * viewer3d.js – Three.js-based 3D URDF viewer & editor (ES module)
 *
 * Loads a URDF XML string, builds a matching Three.js scene graph,
 * supports click-selection with TransformControls for interactive
 * translate / rotate / scale editing, bidirectional highlight events,
 * STL mesh loading, and automatic resize handling.
 *
 * Public API exposed on window.viewer3d:
 *   loadURDF(xmlString)                    – parse & rebuild scene from URDF XML
 *   refresh()                              – rebuild from the last loaded URDF XML
 *   highlightLink(name)                    – highlight a specific link mesh
 *   clearHighlight()                       – remove all highlights
 *   fitToModel()                           – orbit camera to frame the whole model
 *   getCanvas()                            – return the <canvas> element
 *   getSelectedLink()                      – return currently selected link name or null
 *   setTransformMode(mode)                 – 'translate'|'rotate'|'scale'
 *   setSnap(enabled)                       – toggle snapping for transform gizmo
 *   deselectAll()                          – deselect and detach transform gizmo
 *   updateLinkTransform(linkName, xyz, rpy)– update a link's 3D transform without rebuild
 */

import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { TransformControls } from 'three/addons/controls/TransformControls.js';
import { STLLoader } from 'three/addons/loaders/STLLoader.js';
import { OBJLoader } from 'three/addons/loaders/OBJLoader.js';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------
const BG_COLOR        = 0x1a1a2e;
const GRID_SIZE       = 20;
const GRID_DIVISIONS  = 20;
const GRID_COLOR      = 0x888888;
const DEFAULT_COLOR   = 0x5b9bd5;   // steel-blue
const ARM_COLOR       = 0xc08030;   // orange for arm links
const HIGHLIGHT_COLOR = 0x4fc3f7;   // cyan glow
const CAMERA_POS      = new THREE.Vector3(3, 3, 3);

const SNAP_TRANSLATE  = 0.05;       // metres
const SNAP_ROTATE     = THREE.MathUtils.degToRad(5); // 5-degree increments
const SNAP_SCALE      = 0.1;

const GROUND_SIZE     = 30;
const GROUND_COLOR    = 0x3a3a5e;
const GROUND_OPACITY  = 0.35;

// Debounce delay for dispatching transform events (ms)
const TRANSFORM_DISPATCH_DELAY = 80;

// ---------------------------------------------------------------------------
// Module state
// ---------------------------------------------------------------------------
let renderer, scene, camera, orbitControls, transformControls;
let gridHelper, axesHelper, groundPlane;
let robotGroup = null;          // top-level group holding all URDF geometry
let currentUrdfXml = null;      // last loaded XML string
let selectedMesh = null;        // currently highlighted mesh
let selectedLinkName = null;    // name of the currently selected link
let originalMaterials = new Map();  // mesh → original material (for un-highlight)
const stlLoader = new STLLoader();
const objLoader = new OBJLoader();

let snapEnabled = false;
let transformDispatchTimer = null;

// Map of linkName → Three.js Group for efficient partial updates
let linkGroupMap = new Map();

// ---------------------------------------------------------------------------
// Initialization
// ---------------------------------------------------------------------------

/**
 * Boot the 3D viewer.  Called once when the module is first evaluated.
 */
function init() {
  const canvas = document.getElementById('viewer3d-canvas');
  if (!canvas) {
    console.error('[viewer3d] <canvas id="viewer3d-canvas"> not found');
    return;
  }

  // Renderer — guard against zero-size container (hidden tab)
  renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
  renderer.setPixelRatio(window.devicePixelRatio);
  renderer.setClearColor(BG_COLOR);
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;

  // Scene
  scene = new THREE.Scene();

  // Camera
  camera = new THREE.PerspectiveCamera(50, 1, 0.01, 200);
  camera.position.copy(CAMERA_POS);
  camera.lookAt(0, 0, 0);

  // Orbit Controls
  orbitControls = new OrbitControls(camera, renderer.domElement);
  orbitControls.enableDamping = true;
  orbitControls.dampingFactor = 0.12;
  orbitControls.target.set(0, 0, 0);

  // Transform Controls (gizmo)
  transformControls = new TransformControls(camera, renderer.domElement);
  transformControls.setSize(0.8);
  scene.add(transformControls);

  // Disable orbit while user is dragging the gizmo; dispatch transform on release
  transformControls.addEventListener('dragging-changed', (event) => {
    orbitControls.enabled = !event.value;
    if (event.value) {
      // Drag started — notify editor so it can snapshot undo state
      document.dispatchEvent(new CustomEvent('viewer3d-transform-start', {
        detail: { linkName: transformControls.object?.userData?.linkName || transformControls.object?.name || null },
      }));
    } else {
      // Drag ended — dispatch final transform, then notify editor to rebuild
      onTransformEnd();
      document.dispatchEvent(new CustomEvent('viewer3d-transform-end', {
        detail: { linkName: transformControls.object?.userData?.linkName || transformControls.object?.name || null },
      }));
    }
  });

  // Dispatch transform changes (debounced) while gizmo moves
  transformControls.addEventListener('objectChange', onTransformObjectChange);

  // Lighting
  const ambient = new THREE.AmbientLight(0xffffff, 0.6);
  scene.add(ambient);

  const dir = new THREE.DirectionalLight(0xffffff, 0.9);
  dir.position.set(5, 10, 7);
  dir.castShadow = true;
  dir.shadow.mapSize.set(1024, 1024);
  scene.add(dir);

  const fill = new THREE.DirectionalLight(0xffffff, 0.3);
  fill.position.set(-4, 3, -5);
  scene.add(fill);

  // Semi-transparent ground plane
  const groundGeom = new THREE.PlaneGeometry(GROUND_SIZE, GROUND_SIZE);
  const groundMat  = new THREE.MeshStandardMaterial({
    color: GROUND_COLOR,
    transparent: true,
    opacity: GROUND_OPACITY,
    side: THREE.DoubleSide,
    depthWrite: false,
  });
  groundPlane = new THREE.Mesh(groundGeom, groundMat);
  groundPlane.rotation.x = -Math.PI / 2;  // lie flat on XZ
  groundPlane.position.y = -0.001;         // just below grid to avoid z-fighting
  groundPlane.receiveShadow = true;
  groundPlane.name = '__ground__';
  scene.add(groundPlane);

  // Grid + axes
  gridHelper = new THREE.GridHelper(GRID_SIZE, GRID_DIVISIONS, GRID_COLOR, GRID_COLOR);
  scene.add(gridHelper);

  axesHelper = new THREE.AxesHelper(1.5);
  scene.add(axesHelper);

  // Resize handling via ResizeObserver
  const container = canvas.parentElement || document.body;
  const ro = new ResizeObserver(() => handleResize(canvas, container));
  ro.observe(container);
  handleResize(canvas, container);

  // Click → raycasting
  canvas.addEventListener('pointerdown', onCanvasClick);

  // External event listeners ---
  // Cross-panel selection sync (from tree / properties panel)
  document.addEventListener('urdf-select', (e) => {
    const { type, name } = e.detail || {};
    if (type === 'link') highlightLink(name);
  });

  // Transform mode switching via custom event
  document.addEventListener('viewer3d-set-mode', (e) => {
    const mode = e.detail?.mode;
    if (mode) setTransformMode(mode);
  });

  // Snap toggle via custom event
  document.addEventListener('viewer3d-set-snap', (e) => {
    const enabled = !!e.detail?.enabled;
    setSnap(enabled);
  });

  // Render loop
  tick();
}

// ---------------------------------------------------------------------------
// Render loop
// ---------------------------------------------------------------------------
function tick() {
  requestAnimationFrame(tick);
  if (!renderer) return;
  orbitControls.update();
  renderer.render(scene, camera);
}

// ---------------------------------------------------------------------------
// Resize
// ---------------------------------------------------------------------------
function handleResize(canvas, container) {
  const w = container.clientWidth  || window.innerWidth;
  const h = container.clientHeight || window.innerHeight;
  if (w === 0 || h === 0) return;  // container hidden – skip to avoid NaN aspect
  renderer.setSize(w, h, false);
  camera.aspect = w / h;
  camera.updateProjectionMatrix();
}

// ---------------------------------------------------------------------------
// URDF Parsing & Scene Building
// ---------------------------------------------------------------------------

/**
 * Parse a URDF XML string and (re-)build the 3D scene.
 * @param {string} xmlString  - raw URDF XML
 */
async function loadURDF(xmlString) {
  currentUrdfXml = xmlString;

  // Detach gizmo & clear selection before rebuilding
  deselectAll();

  // Remove previous robot group
  if (robotGroup) {
    scene.remove(robotGroup);
    disposeGroup(robotGroup);
  }
  robotGroup = new THREE.Group();
  robotGroup.name = 'robot';
  linkGroupMap = new Map();
  scene.add(robotGroup);

  // Parse XML
  const parser = new DOMParser();
  const doc = parser.parseFromString(xmlString, 'text/xml');
  const robotEl = doc.querySelector('robot');
  if (!robotEl) {
    console.warn('[viewer3d] No <robot> element found in URDF');
    return;
  }

  // Build lookup maps
  const linkEls  = Array.from(robotEl.querySelectorAll(':scope > link'));
  const jointEls = Array.from(robotEl.querySelectorAll(':scope > joint'));

  const linkMap  = new Map();  // name → XML element
  const childOf  = new Map();  // childLink → { jointEl, parentLink }
  const children = new Map();  // parentLink → [ { jointEl, childLink } ]

  for (const el of linkEls) {
    linkMap.set(el.getAttribute('name'), el);
  }

  for (const jel of jointEls) {
    const parentName = jel.querySelector('parent')?.getAttribute('link');
    const childName  = jel.querySelector('child')?.getAttribute('link');
    if (parentName && childName) {
      childOf.set(childName, { jointEl: jel, parentLink: parentName });
      if (!children.has(parentName)) children.set(parentName, []);
      children.get(parentName).push({ jointEl: jel, childLink: childName });
    }
  }

  // Find root link (not a child of any joint)
  let rootName = null;
  for (const name of linkMap.keys()) {
    if (!childOf.has(name)) { rootName = name; break; }
  }
  if (!rootName && linkMap.size > 0) {
    rootName = linkMap.keys().next().value;
  }

  // Recursive build
  if (rootName) {
    const rootObj = await buildLink(rootName, null, linkMap, children);
    robotGroup.add(rootObj);
  }
}

/**
 * Recursively build a Three.js Object3D for a URDF link and its children.
 */
async function buildLink(linkName, jointEl, linkMap, childrenMap) {
  const group = new THREE.Group();
  group.name = linkName;
  group.userData.linkName = linkName;
  group.userData.jointName = jointEl ? jointEl.getAttribute('name') : null;

  // Register in lookup map for partial updates
  linkGroupMap.set(linkName, group);

  // Apply joint origin transform (translation + rotation)
  if (jointEl) {
    const origin = jointEl.querySelector('origin');
    if (origin) {
      applyOrigin(group, origin);
    }
  }

  // Build visual geometry for this link
  const linkEl = linkMap.get(linkName);
  if (linkEl) {
    const visuals = linkEl.querySelectorAll('visual');
    for (const vis of visuals) {
      const mesh = await buildVisual(vis, linkName, jointEl);
      if (mesh) group.add(mesh);
    }
  }

  // Recurse into child links
  const kids = childrenMap.get(linkName) || [];
  const childPromises = kids.map(({ jointEl: jel, childLink }) =>
    buildLink(childLink, jel, linkMap, childrenMap)
  );
  const childObjects = await Promise.all(childPromises);
  for (const obj of childObjects) group.add(obj);

  return group;
}

/**
 * Construct a Three.js mesh from a URDF <visual> element.
 */
async function buildVisual(visualEl, linkName, jointEl) {
  const geomEl = visualEl.querySelector('geometry');
  if (!geomEl) return null;

  let geometry = null;
  let isSTL = false;

  // --- Box ---
  const boxEl = geomEl.querySelector('box');
  if (boxEl) {
    const size = parseVec3(boxEl.getAttribute('size'), [1, 1, 1]);
    geometry = new THREE.BoxGeometry(size[0], size[1], size[2]);
  }

  // --- Cylinder ---
  const cylEl = geomEl.querySelector('cylinder');
  if (!geometry && cylEl) {
    const radius = parseFloat(cylEl.getAttribute('radius')) || 0.05;
    const length = parseFloat(cylEl.getAttribute('length')) || 0.1;
    geometry = new THREE.CylinderGeometry(radius, radius, length, 32);
  }

  // --- Sphere ---
  const sphEl = geomEl.querySelector('sphere');
  if (!geometry && sphEl) {
    const radius = parseFloat(sphEl.getAttribute('radius')) || 0.05;
    geometry = new THREE.SphereGeometry(radius, 32, 16);
  }

  // --- Mesh (STL / OBJ) ---
  const meshEl = geomEl.querySelector('mesh');
  let objGroup = null;  // For OBJ files that return a Group instead of Geometry
  if (!geometry && meshEl) {
    const filename = meshEl.getAttribute('filename') || '';
    const scaleAttr = meshEl.getAttribute('scale');
    const scale = scaleAttr ? parseVec3(scaleAttr, [1, 1, 1]) : [1, 1, 1];
    const lowerFn = filename.toLowerCase();

    if (lowerFn.endsWith('.obj')) {
      // OBJ files return a THREE.Group (may include materials from MTL)
      objGroup = await loadOBJ(filename);
      if (objGroup) {
        objGroup.scale.set(scale[0], scale[1], scale[2]);
      } else {
        geometry = new THREE.BoxGeometry(0.05, 0.05, 0.05);
      }
    } else {
      // STL or other — returns BufferGeometry
      geometry = await loadSTL(filename);
      if (geometry) {
        geometry = geometry.clone();
        geometry.scale(scale[0], scale[1], scale[2]);
        isSTL = true;
      } else {
        geometry = new THREE.BoxGeometry(0.05, 0.05, 0.05);
      }
    }
  }

  if (!geometry && !objGroup) return null;

  let resultMesh;

  if (objGroup) {
    // OBJ Group — assign userData and apply origin
    objGroup.userData = {
      linkName,
      jointName: jointEl ? jointEl.getAttribute('name') : null,
    };
    objGroup.traverse(child => {
      if (child.isMesh) {
        child.castShadow = true;
        child.receiveShadow = true;
        child.userData = { linkName, jointName: jointEl ? jointEl.getAttribute('name') : null };
      }
    });
    const visOrigin = visualEl.querySelector('origin');
    if (visOrigin) applyOrigin(objGroup, visOrigin);
    return objGroup;
  }

  // Material
  const color = parseMaterialColor(visualEl) || pickDefaultColor(linkName);
  const material = new THREE.MeshStandardMaterial({
    color,
    metalness: 0.3,
    roughness: 0.6,
    flatShading: isSTL,
  });

  resultMesh = new THREE.Mesh(geometry, material);
  resultMesh.castShadow = true;
  resultMesh.receiveShadow = true;
  resultMesh.userData = {
    linkName,
    jointName: jointEl ? jointEl.getAttribute('name') : null,
  };

  // Apply visual-level origin if present
  const visOrigin = visualEl.querySelector('origin');
  if (visOrigin) {
    applyOrigin(resultMesh, visOrigin);
  }

  return resultMesh;
}

// ---------------------------------------------------------------------------
// STL Loading
// ---------------------------------------------------------------------------

/**
 * Load an STL geometry from a URDF mesh filename attribute.
 * Strips common package:// prefixes and resolves to /meshes/<file>.
 * @param {string} rawPath  – e.g. "package://vehicle_arm_sim/meshes/base.stl"
 * @returns {Promise<THREE.BufferGeometry|null>}
 */
function loadSTL(rawPath) {
  // Strip package:// prefix variants
  let path = rawPath.replace(/^package:\/\/[^/]+\/meshes\//, '');
  // Also handle file:// or absolute paths – just grab the filename
  const lastSlash = path.lastIndexOf('/');
  if (lastSlash >= 0) path = path.substring(lastSlash + 1);

  const url = '/meshes/' + path;

  return new Promise((resolve) => {
    stlLoader.load(
      url,
      (geometry) => {
        geometry.computeVertexNormals();
        resolve(geometry);
      },
      undefined,
      (err) => {
        console.warn('[viewer3d] Failed to load STL "' + url + '":', err);
        resolve(null);  // caller will use fallback geometry
      }
    );
  });
}

// ---------------------------------------------------------------------------
// OBJ + MTL Loading
// ---------------------------------------------------------------------------

/**
 * Parse an MTL file manually to extract diffuse color (Kd) and texture map (map_Kd).
 * Returns { color: [r,g,b]|null, textureFile: string|null }
 */
function parseMTLText(text) {
  const result = { color: null, textureFile: null };
  for (const raw of text.split('\n')) {
    const line = raw.trim();
    if (line.startsWith('Kd ')) {
      const parts = line.substring(3).trim().split(/\s+/);
      if (parts.length >= 3) {
        result.color = [parseFloat(parts[0]), parseFloat(parts[1]), parseFloat(parts[2])];
      }
    } else if (line.startsWith('map_Kd ')) {
      result.textureFile = line.substring(7).trim();
    }
  }
  return result;
}

/**
 * Load an OBJ mesh with proper materials.
 * Manually fetches MTL to parse texture references, then explicitly loads
 * textures via TextureLoader and creates MeshStandardMaterial (PBR)
 * for consistent rendering with the rest of the scene.
 *
 * @param {string} rawPath  – e.g. "package://vehicle_arm_sim/meshes/plant.obj"
 * @returns {Promise<THREE.Group|null>}
 */
async function loadOBJ(rawPath) {
  // Strip package:// prefix variants
  let path = rawPath.replace(/^package:\/\/[^/]+\/meshes\//, '');
  const lastSlash = path.lastIndexOf('/');
  if (lastSlash >= 0) path = path.substring(lastSlash + 1);

  const objUrl = '/meshes/' + path;
  const mtlName = path.replace(/\.obj$/i, '.mtl');
  const mtlUrl = '/meshes/' + mtlName;

  console.log('[viewer3d] loadOBJ: path=' + path + ' objUrl=' + objUrl + ' mtlUrl=' + mtlUrl);

  // Step 1: Fetch & parse MTL for texture info
  let mtlInfo = { color: null, textureFile: null };
  try {
    const resp = await fetch(mtlUrl);
    if (resp.ok) {
      const mtlText = await resp.text();
      mtlInfo = parseMTLText(mtlText);
      console.log('[viewer3d] MTL parsed:', JSON.stringify(mtlInfo));
    } else {
      console.warn('[viewer3d] MTL not found (HTTP ' + resp.status + '): ' + mtlUrl);
    }
  } catch (e) {
    console.warn('[viewer3d] MTL fetch error:', e);
  }

  // Step 2: Load texture (if referenced in MTL)
  let texture = null;
  if (mtlInfo.textureFile) {
    const texUrl = '/meshes/' + mtlInfo.textureFile;
    console.log('[viewer3d] Loading texture: ' + texUrl);
    try {
      texture = await new Promise((res, rej) => {
        new THREE.TextureLoader().load(
          texUrl,
          (tex) => { console.log('[viewer3d] Texture loaded OK: ' + texUrl); res(tex); },
          undefined,
          (err) => { console.warn('[viewer3d] Texture load failed: ' + texUrl, err); rej(err); }
        );
      });
      texture.colorSpace = THREE.SRGBColorSpace;
    } catch (_) {
      texture = null;
    }
  }

  // Step 3: Create PBR material
  const matOpts = { metalness: 0.1, roughness: 0.8 };
  if (texture) {
    matOpts.map = texture;
  }
  if (mtlInfo.color) {
    matOpts.color = new THREE.Color(mtlInfo.color[0], mtlInfo.color[1], mtlInfo.color[2]);
  }
  const pbrMaterial = new THREE.MeshStandardMaterial(matOpts);

  // Step 4: Load OBJ geometry
  return new Promise((resolve) => {
    new OBJLoader().load(
      objUrl,
      (group) => {
        // Apply our PBR material to all meshes in the group
        group.traverse((child) => {
          if (child.isMesh) {
            child.material = pbrMaterial;
          }
        });
        console.log('[viewer3d] Loaded OBJ with ' + (texture ? 'texture' : 'color-only')
                     + ' material: ' + path);
        resolve(group);
      },
      undefined,
      (err) => {
        console.warn('[viewer3d] Failed to load OBJ "' + objUrl + '":', err);
        resolve(null);
      }
    );
  });
}

// ---------------------------------------------------------------------------
// Origin / Transform Helpers
// ---------------------------------------------------------------------------

/**
 * Apply xyz + rpy from a URDF <origin> element to a Three.js object.
 *
 * URDF RPY convention: rotation = Rz(yaw) * Ry(pitch) * Rx(roll)
 * Three.js Euler 'ZYX': applies X first, then Y, then Z → matches URDF.
 *   new THREE.Euler(roll, pitch, yaw, 'ZYX')
 */
function applyOrigin(obj, originEl) {
  const xyz = originEl.getAttribute('xyz');
  if (xyz) {
    const [x, y, z] = parseVec3(xyz, [0, 0, 0]);
    obj.position.set(x, y, z);
  }

  const rpy = originEl.getAttribute('rpy');
  if (rpy) {
    const [roll, pitch, yaw] = parseVec3(rpy, [0, 0, 0]);
    obj.rotation.set(roll, pitch, yaw, 'ZYX');
  }
}

// ---------------------------------------------------------------------------
// Material / Color Helpers
// ---------------------------------------------------------------------------

/**
 * Extract material colour from a <visual> element.
 * Looks for <material><color rgba="r g b a"/></material>.
 * @returns {THREE.Color|null}
 */
function parseMaterialColor(visualEl) {
  const matEl = visualEl.querySelector('material');
  if (!matEl) return null;

  const colorEl = matEl.querySelector('color');
  if (colorEl) {
    const rgba = colorEl.getAttribute('rgba');
    if (rgba) {
      const parts = rgba.trim().split(/\s+/).map(Number);
      if (parts.length >= 3) {
        return new THREE.Color(parts[0], parts[1], parts[2]);
      }
    }
  }

  // Fallback: check for a name attribute referencing a known colour
  return null;
}

/**
 * Pick a default colour for a link based on naming heuristics.
 */
function pickDefaultColor(linkName) {
  const lower = (linkName || '').toLowerCase();
  if (lower.includes('arm') || lower.includes('link') || lower.includes('shoulder') ||
      lower.includes('elbow') || lower.includes('wrist')) {
    return new THREE.Color(ARM_COLOR);
  }
  return new THREE.Color(DEFAULT_COLOR);
}

// ---------------------------------------------------------------------------
// Selection & Highlighting
// ---------------------------------------------------------------------------
const raycaster = new THREE.Raycaster();
const pointer   = new THREE.Vector2();

/**
 * Handle pointer-down on the canvas: cast a ray and select the hit link.
 * Ignores clicks on the TransformControls gizmo itself.
 */
function onCanvasClick(event) {
  if (!robotGroup) return;

  // If user is interacting with the transform gizmo, don't change selection
  if (transformControls.dragging) return;

  const rect = renderer.domElement.getBoundingClientRect();
  pointer.x =  ((event.clientX - rect.left) / rect.width)  * 2 - 1;
  pointer.y = -((event.clientY - rect.top)  / rect.height) * 2 + 1;

  raycaster.setFromCamera(pointer, camera);
  const hits = raycaster.intersectObjects(robotGroup.children, true);

  if (hits.length > 0) {
    const mesh = hits[0].object;
    const linkName = mesh.userData?.linkName;
    if (linkName) {
      selectLink(linkName);
    }
  } else {
    deselectAll();
  }
}

/**
 * Select a link by name: highlight it, attach transform gizmo, dispatch events.
 */
function selectLink(linkName) {
  if (!linkName || !robotGroup) return;

  console.log('[viewer3d] selectLink called:', linkName);

  // Already selected? Skip highlight rebuild but keep gizmo
  if (selectedLinkName === linkName) return;

  clearHighlight();

  selectedLinkName = linkName;

  // Find the link group to attach the gizmo to
  const linkGroup = linkGroupMap.get(linkName);

  robotGroup.traverse((obj) => {
    if (obj.isMesh && obj.userData?.linkName === linkName) {
      // Store original material so we can restore later
      originalMaterials.set(obj, obj.material);

      obj.material = new THREE.MeshStandardMaterial({
        color: HIGHLIGHT_COLOR,
        emissive: HIGHLIGHT_COLOR,
        emissiveIntensity: 0.4,
        metalness: 0.2,
        roughness: 0.4,
      });
      selectedMesh = obj;  // track last highlighted for simple cases
    }
  });

  // Attach TransformControls to the link group (not individual mesh)
  if (linkGroup) {
    transformControls.attach(linkGroup);
  }

  // Dispatch events for cross-panel sync
  document.dispatchEvent(new CustomEvent('viewer3d-select', {
    detail: { type: 'link', name: linkName },
  }));
  document.dispatchEvent(new CustomEvent('urdf-select', {
    detail: { type: 'link', name: linkName },
  }));
}

/**
 * Highlight every mesh that belongs to the given link name.
 * If the link differs from the current selection, also selects it.
 */
function highlightLink(name) {
  if (!name) {
    deselectAll();
    return;
  }
  selectLink(name);
}

/**
 * Restore all highlighted meshes to their original materials.
 */
function clearHighlight() {
  for (const [mesh, mat] of originalMaterials) {
    if (mesh.material !== mat) {
      mesh.material.dispose();
      mesh.material = mat;
    }
  }
  originalMaterials.clear();
  selectedMesh = null;
}

/**
 * Deselect everything: clear highlight, detach gizmo, reset state.
 */
function deselectAll() {
  clearHighlight();
  selectedLinkName = null;
  if (transformControls) {
    transformControls.detach();
  }
}

// ---------------------------------------------------------------------------
// TransformControls – Mode, Snap, Events
// ---------------------------------------------------------------------------

/**
 * Switch the transform gizmo mode.
 * @param {'translate'|'rotate'|'scale'} mode
 */
function setTransformMode(mode) {
  if (!transformControls) return;
  const valid = ['translate', 'rotate', 'scale'];
  if (!valid.includes(mode)) {
    console.warn('[viewer3d] Invalid transform mode "' + mode + '"');
    return;
  }
  transformControls.setMode(mode);
  applySnap();
}

/**
 * Enable or disable snapping on the transform gizmo.
 * @param {boolean} enabled
 */
function setSnap(enabled) {
  snapEnabled = !!enabled;
  applySnap();
}

/**
 * Internal: apply current snap settings to the transform gizmo.
 */
function applySnap() {
  if (!transformControls) return;

  if (snapEnabled) {
    transformControls.setTranslationSnap(SNAP_TRANSLATE);
    transformControls.setRotationSnap(SNAP_ROTATE);
    transformControls.setScaleSnap(SNAP_SCALE);
  } else {
    transformControls.setTranslationSnap(null);
    transformControls.setRotationSnap(null);
    transformControls.setScaleSnap(null);
  }
}

/**
 * Called continuously while the gizmo is being dragged.
 * We debounce dispatching the transform event to avoid flooding.
 */
function onTransformObjectChange() {
  if (transformDispatchTimer) clearTimeout(transformDispatchTimer);
  transformDispatchTimer = setTimeout(dispatchTransformEvent, TRANSFORM_DISPATCH_DELAY);
}

/**
 * Called when the user releases the gizmo (mouseUp on TransformControls).
 * Dispatch the final transform value immediately.
 */
function onTransformEnd() {
  if (transformDispatchTimer) {
    clearTimeout(transformDispatchTimer);
    transformDispatchTimer = null;
  }
  dispatchTransformEvent();
}

/**
 * Read the attached object's position and rotation,
 * then dispatch a viewer3d-transform event so the main editor
 * can update the URDF XML.
 */
function dispatchTransformEvent() {
  const obj = transformControls.object;
  if (!obj) return;

  const linkName = obj.userData?.linkName || obj.name;
  if (!linkName) return;

  const mode = transformControls.mode; // 'translate' | 'rotate' | 'scale'

  // Position directly from the object (local to its parent = joint origin)
  const pos = obj.position;

  // Euler rotation: URDF expects (roll, pitch, yaw) in 'ZYX' order
  const euler = obj.rotation;
  // euler.order should be 'ZYX'; components are (x=roll, y=pitch, z=yaw)
  const roll  = euler.x;
  const pitch = euler.y;
  const yaw   = euler.z;

  // Scale from object (only meaningful in 'scale' mode)
  const sc = obj.scale;

  document.dispatchEvent(new CustomEvent('viewer3d-transform', {
    detail: {
      linkName,
      mode,
      position: { x: pos.x, y: pos.y, z: pos.z },
      rotation: { r: roll, p: pitch, y: yaw },
      scale: { x: sc.x, y: sc.y, z: sc.z },
    },
  }));
}

// ---------------------------------------------------------------------------
// Partial Update (without full rebuild)
// ---------------------------------------------------------------------------

/**
 * Update a single link's position and rotation in the 3D scene
 * without triggering a full URDF re-parse & rebuild.
 *
 * @param {string} linkName - the URDF link name
 * @param {{x:number, y:number, z:number}} xyz - new position
 * @param {{r:number, p:number, y:number}} rpy - new rotation (roll, pitch, yaw)
 */
function updateLinkTransform(linkName, xyz, rpy) {
  const group = linkGroupMap.get(linkName);
  if (!group) {
    console.warn('[viewer3d] updateLinkTransform: link "' + linkName + '" not found in scene');
    return;
  }

  if (xyz) {
    group.position.set(
      xyz.x ?? group.position.x,
      xyz.y ?? group.position.y,
      xyz.z ?? group.position.z
    );
  }

  if (rpy) {
    group.rotation.set(
      rpy.r ?? group.rotation.x,
      rpy.p ?? group.rotation.y,
      rpy.y ?? group.rotation.z,
      'ZYX'
    );
  }
}

// ---------------------------------------------------------------------------
// Camera Fitting
// ---------------------------------------------------------------------------

/**
 * Adjust the camera so the entire model is visible.
 */
function fitToModel() {
  if (!robotGroup) return;

  const box = new THREE.Box3().setFromObject(robotGroup);
  if (box.isEmpty()) return;

  const center = box.getCenter(new THREE.Vector3());
  const size   = box.getSize(new THREE.Vector3());
  const maxDim = Math.max(size.x, size.y, size.z);
  const dist   = maxDim / (2 * Math.tan((camera.fov * Math.PI) / 360));

  orbitControls.target.copy(center);
  camera.position.copy(center).add(new THREE.Vector3(dist, dist * 0.8, dist));
  camera.lookAt(center);
  orbitControls.update();
}

// ---------------------------------------------------------------------------
// Utility
// ---------------------------------------------------------------------------

/**
 * Parse a space-separated string of numbers into an array.
 * @param {string} str       – e.g. "0.1 0.2 0.3"
 * @param {number[]} fallback – default values if parsing fails
 * @returns {number[]}
 */
function parseVec3(str, fallback) {
  if (!str) return fallback;
  const parts = str.trim().split(/\s+/).map(Number);
  return parts.length >= fallback.length ? parts : fallback;
}

/**
 * Recursively dispose geometry and materials of a group.
 */
function disposeGroup(obj) {
  obj.traverse((child) => {
    if (child.isMesh) {
      child.geometry?.dispose();
      if (Array.isArray(child.material)) {
        child.material.forEach((m) => m.dispose());
      } else {
        child.material?.dispose();
      }
    }
  });
}

/**
 * Force a full rebuild from the last-loaded URDF string.
 */
function refresh() {
  if (currentUrdfXml) loadURDF(currentUrdfXml);
}

/**
 * Update the color of all meshes belonging to a link, live, without
 * rebuilding the scene.  Works even when the link is highlighted
 * (stores the new color so it persists after deselect).
 *
 * @param {string} linkName – URDF link name
 * @param {number} r  – red   0-1
 * @param {number} g  – green 0-1
 * @param {number} b  – blue  0-1
 */
function updateLinkColor(linkName, r, g, b) {
  if (!robotGroup) return;
  const newColor = new THREE.Color(r, g, b);
  robotGroup.traverse((obj) => {
    if (obj.isMesh && obj.userData?.linkName === linkName) {
      // If this mesh is currently highlighted, update both:
      //  1. The stored original material (so un-highlight restores the new colour)
      //  2. The visible highlight material (so the user sees feedback immediately)
      const orig = originalMaterials.get(obj);
      if (orig) {
        orig.color.copy(newColor);
        // Tint the highlight to blend selection glow with new colour
        obj.material.color.copy(newColor);
        obj.material.emissive.copy(newColor);
        obj.material.emissiveIntensity = 0.35;
      } else {
        obj.material.color.copy(newColor);
      }
    }
  });
}

/**
 * Return the currently selected link name, or null if nothing selected.
 * @returns {string|null}
 */
function getSelectedLink() {
  return selectedLinkName;
}

/**
 * Update a single link's mesh scale in the 3D scene.
 * The scale is applied to the Object3D (not baked into geometry), so it's
 * a visual preview only. Call loadURDF() to bake it permanently.
 *
 * @param {string} linkName - the URDF link name
 * @param {number} sx - scale X
 * @param {number} sy - scale Y
 * @param {number} sz - scale Z
 */
function updateLinkScale(linkName, sx, sy, sz) {
  const group = linkGroupMap.get(linkName);
  if (!group) {
    console.warn('[viewer3d] updateLinkScale: link "' + linkName + '" not found in scene');
    return;
  }
  group.scale.set(sx, sy, sz);
}

/**
 * Get a link's current 3D position and rotation (from its Object3D).
 * Returns { position: {x,y,z}, rotation: {r,p,y} } or null if not found.
 *
 * @param {string} linkName - the URDF link name
 * @returns {{position: {x:number, y:number, z:number}, rotation: {r:number, p:number, y:number}}|null}
 */
function getLinkTransform(linkName) {
  const group = linkGroupMap.get(linkName);
  if (!group) return null;
  const pos = group.position;
  const euler = group.rotation;
  return {
    position: { x: pos.x, y: pos.y, z: pos.z },
    rotation: { r: euler.x, p: euler.y, y: euler.z },
  };
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------
window.viewer3d = {
  loadURDF,
  refresh,
  highlightLink,
  clearHighlight,
  fitToModel,
  getCanvas: () => renderer?.domElement ?? null,
  getSelectedLink,
  setTransformMode,
  setSnap,
  deselectAll,
  updateLinkTransform,
  updateLinkColor,
  updateLinkScale,
  getLinkTransform,
};

// ---------------------------------------------------------------------------
// Boot
// ---------------------------------------------------------------------------
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}
