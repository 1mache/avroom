import React, { forwardRef, useEffect, useImperativeHandle, useRef } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import { OBJLoader } from "three/examples/jsm/loaders/OBJLoader.js";

// Camera tuned for "object on pedestal" framing inside current viewport sizes.
export const CAMERA_FOV = 40;
const CAMERA_NEAR = 0.1;
const CAMERA_FAR = 1000;
const CAMERA_POSITION = { x: 0, y: 0, z: 7 };

// Cap device pixel ratio so retina screens do not multiply GPU cost too hard.
const MAX_PIXEL_RATIO = 2;

// Neutral white studio rig, brighter than before so the object's real
// texture reads instead of a dark, tinted silhouette. Colors are white on
// every light -- a cyan/warm tint on key/fill/rim was staining the model.
const AMBIENT_LIGHT_COLOR = 0xffffff;
const AMBIENT_LIGHT_INTENSITY = 1.0;

const KEY_LIGHT_COLOR = 0xffffff;
export const KEY_LIGHT_INTENSITY = 2.2;
const KEY_LIGHT_POSITION = { x: 4, y: 6, z: 5 };

const FILL_LIGHT_COLOR = 0xffffff;
const FILL_LIGHT_INTENSITY = 1.0;
const FILL_LIGHT_POSITION = { x: -5, y: 2, z: -4 };

const RIM_LIGHT_COLOR = 0xffffff;
const RIM_LIGHT_INTENSITY = 0.75;
const RIM_LIGHT_POSITION = { x: 0, y: -3, z: -6 };

// Follows the camera so whatever face the user orbits toward is never left
// unlit -- the three fixed world lights above only cover the pose the rig
// was aimed at.
const HEADLIGHT_COLOR = 0xffffff;
const HEADLIGHT_INTENSITY = 0.65;

export const MATERIAL_ROUGHNESS = 0.3;
// glTF defaults to metallicFactor=1; a fully metallic PBR material with no
// environment map renders near-black under direct lights alone. Clamp it
// down so brightening the rig above actually shows.
export const MAX_MATERIAL_METALNESS = 0.1;

// The viewer canvas is inflated by this factor around the object's on-stage
// rect (see model3DFrameStyle in MainPage) and the model is fit to fill
// 1/this of the viewport. Net effect: the model reads at the same size as the
// 2D cutout it replaces, while still having empty canvas around it so parts
// that swing outside the original silhouette during an orbit aren't clipped.
export const MODEL_3D_FRAME_PADDING = 1.5;

// Hunyuan3D-2.1 (the active reconstruction backend) emits glTF-standard Y-up
// geometry with the photographed face toward +Z, so the starting pose already
// reproduces the photo -- no correction needed. Kept as a named identity
// transform (mirrored by _GLB_TO_VIEW_ROTATION in
// mesh_render_novel_view_strategy.py) so a future generator with a different
// axis convention has a single place to fix it.
const glbToViewRotation = (): THREE.Matrix4 => new THREE.Matrix4();

interface Props {
  glbData: ArrayBuffer | null;
  /** "glb" (default) parses via GLTFLoader; "obj" decodes glbData as UTF-8 OBJ text via OBJLoader. */
  format?: "glb" | "obj";
  /**
   * Optional overrides for the debug 3D panel (`DebugScreen`). All default to
   * today's hardcoded constants below when omitted, so `WorkspaceScreen` —
   * which never passes any of these — sees byte-identical behavior to before
   * these props existed.
   */
  roughness?: number;
  metalness?: number;
  keyLightIntensity?: number;
  cameraFov?: number;
  /**
   * When false, OrbitControls drag is disabled and the camera is driven only
   * by ``orbitAzimuthDeg`` / ``orbitElevationDeg`` / ``orbitRollDeg``.
   * Workspace rotate leaves this true so the user can grab the mesh; Debug
   * Dashboard also leaves it unset (true).
   */
  enableOrbitDrag?: boolean;
  /** Azimuth delta in degrees from the viewer's starting pose (Y axis). */
  orbitAzimuthDeg?: number;
  /** Elevation delta in degrees from the viewer's starting pose (up = positive). */
  orbitElevationDeg?: number;
  /** Screen-space roll (Z) in degrees from the viewer's starting pose. */
  orbitRollDeg?: number;
  /** Fired when the user finishes an orbit drag (azimuth / elevation deltas). */
  onOrbitChange?: (azimuthDeg: number, elevationDeg: number) => void;
  className?: string;
  style?: React.CSSProperties;
}

// Angle/snapshot captured relative to the pose the viewer started at, around
// the object center -- orbit distance/pan never factor in. Sign convention
// (which drag direction is "positive") is not guaranteed to match the
// backend's CLOCKWISE/UP conventions on the first try; flip here if a
// real rotation comes back mirrored.
export interface RotationCapture {
  azimuthDeg: number;
  relativeElevationDeg: number;
  snapshotDataUrl: string;
}

export interface Model3DFrameHandle {
  capture(): RotationCapture | null;
}

const radToDeg = (radians: number): number => (radians * 180) / Math.PI;
const degToRad = (degrees: number): number => (degrees * Math.PI) / 180;

/** Place the orbit camera at azimuth/elevation/roll deltas from identity. */
function applyOrbitPose(
  controls: OrbitControls,
  initialAzimuthal: number,
  initialPolar: number,
  azimuthDeg: number,
  elevationDeg: number,
  rollDeg: number,
): void {
  const camera = controls.object as THREE.PerspectiveCamera;
  const offset = new THREE.Vector3().copy(camera.position).sub(controls.target);
  const spherical = new THREE.Spherical().setFromVector3(offset);
  spherical.theta = initialAzimuthal + degToRad(azimuthDeg);
  spherical.phi = initialPolar - degToRad(elevationDeg);
  spherical.makeSafe();
  offset.setFromSpherical(spherical);
  camera.position.copy(controls.target).add(offset);
  camera.up.set(0, 1, 0);
  camera.lookAt(controls.target);
  if (rollDeg !== 0) {
    const forward = new THREE.Vector3()
      .subVectors(controls.target, camera.position)
      .normalize();
    camera.up.applyAxisAngle(forward, degToRad(rollDeg));
    camera.lookAt(controls.target);
  }
  controls.update();
}

// Above this many vertices the fit samples with a stride instead of reading
// every one -- generated GLBs run to hundreds of thousands of vertices, and a
// silhouette's extremes survive sampling far better than the loop cost does.
const MAX_FIT_SAMPLE_POINTS = 60000;

// Flat [x,y,z,...] of the model's vertices in camera space, used to fit the
// model by its real silhouette. Bounding-box corners would be far cheaper but
// project well outside a curved or concave shape (a chair, a sphere), which
// fits the object noticeably smaller than the rect it is meant to fill.
const collectCameraSpacePoints = (
  root: THREE.Object3D,
  camera: THREE.Camera,
): Float64Array => {
  const meshes: THREE.Mesh[] = [];
  let totalVertices = 0;
  root.traverse((child) => {
    if (child instanceof THREE.Mesh && child.geometry?.getAttribute("position")) {
      meshes.push(child);
      totalVertices += child.geometry.getAttribute("position").count;
    }
  });

  if (totalVertices === 0) {
    return new Float64Array(0);
  }

  const stride = Math.max(1, Math.ceil(totalVertices / MAX_FIT_SAMPLE_POINTS));
  const sampled: number[] = [];
  const point = new THREE.Vector3();

  for (const mesh of meshes) {
    const position = mesh.geometry.getAttribute("position");
    for (let i = 0; i < position.count; i += stride) {
      point
        .fromBufferAttribute(position as THREE.BufferAttribute, i)
        .applyMatrix4(mesh.matrixWorld)
        .applyMatrix4(camera.matrixWorldInverse);
      sampled.push(point.x, point.y, point.z);
    }
  }

  return Float64Array.from(sampled);
};

export const Model3DFrame = forwardRef<Model3DFrameHandle, Props>(function Model3DFrame(
  {
    glbData,
    format = "glb",
    roughness = MATERIAL_ROUGHNESS,
    metalness,
    keyLightIntensity = KEY_LIGHT_INTENSITY,
    cameraFov = CAMERA_FOV,
    enableOrbitDrag = true,
    orbitAzimuthDeg = 0,
    orbitElevationDeg = 0,
    orbitRollDeg = 0,
    onOrbitChange,
    className,
    style,
  },
  ref,
) {
  const mountRef = useRef<HTMLDivElement>(null);
  const rendererRef = useRef<THREE.WebGLRenderer | null>(null);
  const controlsRef = useRef<OrbitControls | null>(null);
  const initialAzimuthalRef = useRef(0);
  const initialPolarRef = useRef(0);
  const orbitDraggingRef = useRef(false);
  const orbitAzimuthDegRef = useRef(orbitAzimuthDeg);
  const orbitElevationDegRef = useRef(orbitElevationDeg);
  const orbitRollDegRef = useRef(orbitRollDeg);
  const onOrbitChangeRef = useRef(onOrbitChange);
  orbitAzimuthDegRef.current = orbitAzimuthDeg;
  orbitElevationDegRef.current = orbitElevationDeg;
  orbitRollDegRef.current = orbitRollDeg;
  onOrbitChangeRef.current = onOrbitChange;
  // Populated by the load effect below; read by the secondary slider-driven
  // effects so a knob tweak can mutate the live scene in place instead of
  // re-parsing the model (glbData/format are the only load-effect deps).
  const sceneStateRef = useRef<{
    camera: THREE.PerspectiveCamera;
    keyLight: THREE.DirectionalLight;
    group: THREE.Group;
    fitGroupToView: () => void;
  } | null>(null);

  useImperativeHandle(
    ref,
    () => ({
      capture: () => {
        const renderer = rendererRef.current;
        const controls = controlsRef.current;
        if (!renderer || !controls) {
          return null;
        }

        const azimuthDeg = radToDeg(controls.getAzimuthalAngle() - initialAzimuthalRef.current);
        // Three.js polar angle shrinks as the camera rises above the equator,
        // so an upward orbit must read as a positive elevation delta.
        const relativeElevationDeg = radToDeg(
          initialPolarRef.current - controls.getPolarAngle(),
        );

        return {
          azimuthDeg,
          relativeElevationDeg,
          snapshotDataUrl: renderer.domElement.toDataURL("image/png"),
        };
      },
    }),
    [],
  );

  useEffect(() => {
    const mount = mountRef.current;
    if (!mount || !glbData) {
      return;
    }

    const width = mount.clientWidth;
    const height = mount.clientHeight;

    // Scene lifecycle is fully local to this effect so cleanup can dispose every
    // Three.js object when GLB data changes or component unmounts. roughness/
    // metalness/keyLightIntensity/cameraFov are read once here (initial
    // construction) but deliberately NOT in the deps array below -- the three
    // secondary effects further down mutate this same live scene in place
    // when a slider changes, so a knob tweak never re-parses the model.
    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(
      cameraFov,
      width / height,
      CAMERA_NEAR,
      CAMERA_FAR,
    );
    camera.position.set(
      CAMERA_POSITION.x,
      CAMERA_POSITION.y,
      CAMERA_POSITION.z,
    );
    camera.lookAt(0, 0, 0);

    // preserveDrawingBuffer is required for capture() to read real pixels via
    // toDataURL -- without it the buffer is cleared before readback.
    const renderer = new THREE.WebGLRenderer({
      antialias: true,
      alpha: true,
      preserveDrawingBuffer: true,
    });
    renderer.setSize(width, height);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, MAX_PIXEL_RATIO));
    mount.appendChild(renderer.domElement);
    rendererRef.current = renderer;

    // Damping keeps orbit motion feeling weighted instead of twitchy. Target
    // is pinned to the object center (the GLB is recentered to the origin
    // below) and panning is disabled so that center can never drift --
    // rotation angles are only meaningful around a fixed pivot.
    const controls = new OrbitControls(camera, renderer.domElement);
    // Damping would keep moving after pointer-up and desync the X/Y sliders.
    controls.enableDamping = false;
    controls.enablePan = false;
    controls.enableRotate = enableOrbitDrag;
    controls.target.set(0, 0, 0);
    controlsRef.current = controls;
    initialAzimuthalRef.current = controls.getAzimuthalAngle();
    initialPolarRef.current = controls.getPolarAngle();

    scene.add(new THREE.AmbientLight(AMBIENT_LIGHT_COLOR, AMBIENT_LIGHT_INTENSITY));

    const key = new THREE.DirectionalLight(KEY_LIGHT_COLOR, keyLightIntensity);
    key.position.set(KEY_LIGHT_POSITION.x, KEY_LIGHT_POSITION.y, KEY_LIGHT_POSITION.z);
    scene.add(key);

    const fill = new THREE.DirectionalLight(FILL_LIGHT_COLOR, FILL_LIGHT_INTENSITY);
    fill.position.set(FILL_LIGHT_POSITION.x, FILL_LIGHT_POSITION.y, FILL_LIGHT_POSITION.z);
    scene.add(fill);

    const rim = new THREE.DirectionalLight(RIM_LIGHT_COLOR, RIM_LIGHT_INTENSITY);
    rim.position.set(RIM_LIGHT_POSITION.x, RIM_LIGHT_POSITION.y, RIM_LIGHT_POSITION.z);
    scene.add(rim);

    // Headlight rides on the camera so it always points at whatever the user
    // is currently orbiting toward. Requires the camera itself to be in the
    // scene graph -- otherwise the light's parent transform never updates.
    const headlight = new THREE.DirectionalLight(HEADLIGHT_COLOR, HEADLIGHT_INTENSITY);
    headlight.position.set(0, 0, 0);
    headlight.target.position.set(0, 0, -1);
    camera.add(headlight);
    camera.add(headlight.target);
    scene.add(camera);

    const group = new THREE.Group();
    scene.add(group);

    // Scales the model so its *projected* silhouette fills the viewport (minus
    // MODEL_3D_FRAME_PADDING). Fitting on the bounding box's largest edge
    // instead would shrink deep objects to a fraction of the frame, since the
    // depth axis costs size on screen without ever occupying any.
    const orbitRadius = camera.position.length();
    const fitGroupToView = () => {
      if (group.children.length === 0) {
        return;
      }

      group.scale.setScalar(1);
      camera.updateMatrixWorld();
      group.updateMatrixWorld(true);

      const points = collectCameraSpacePoints(group, camera);
      if (points.length === 0) {
        return;
      }

      // Each vertex's projected size depends on its own depth, which depends on
      // the scale being solved for. Converge by repeatedly measuring the current
      // projection and dividing out how far it overshoots the target -- the
      // model must land at 1/MODEL_3D_FRAME_PADDING of the viewport, which is
      // exactly the object's 2D cutout rect. This mirrors the backend's mesh
      // render (MeshRenderNovelViewStrategy), so the snapshot preview and the
      // synthesized result come back the same size.
      const tanHalfFov = Math.tan((camera.fov * Math.PI) / 360);
      const targetHalfNdc = 1 / MODEL_3D_FRAME_PADDING;
      let scale = 1;
      for (let i = 0; i < 8; i += 1) {
        let overshoot = 0;
        for (let p = 0; p < points.length; p += 3) {
          // Scaling moves a vertex along the view axis, but not the camera, so
          // its depth is the orbit radius minus how far scaling pulled it in.
          const depth = Math.max(
            orbitRadius - scale * (points[p + 2] + orbitRadius),
            orbitRadius * 0.05,
          );
          const ndcX = Math.abs(scale * points[p]) / (depth * tanHalfFov * camera.aspect);
          const ndcY = Math.abs(scale * points[p + 1]) / (depth * tanHalfFov);
          overshoot = Math.max(overshoot, ndcX, ndcY);
        }
        if (overshoot <= 1e-8) {
          break;
        }
        scale *= targetHalfNdc / overshoot;
      }

      group.scale.setScalar(scale);
    };

    // Read by the secondary slider-driven effects below so a knob tweak can
    // reach into this same live scene instead of re-running this effect.
    sceneStateRef.current = { camera, keyLight: key, group, fitGroupToView };

    // Shared by both loader branches: recenter/normalize the loaded object,
    // apply the material sliders, orient it, and fit it to the viewport.
    const settleLoadedObject = (obj: THREE.Object3D, isObjFormat: boolean) => {
      const box = new THREE.Box3().setFromObject(obj);
      const center = box.getCenter(new THREE.Vector3());
      const size = box.getSize(new THREE.Vector3());
      const maxDim = Math.max(size.x, size.y, size.z) || 1;

      // Normalize to roughly unit size first so the fit iteration below starts
      // from extents comparable to the orbit radius, whatever scale the source
      // model happens to use.
      const normalizedScale = 1 / maxDim;
      obj.scale.setScalar(normalizedScale);
      obj.position.copy(center).multiplyScalar(-normalizedScale);

      obj.traverse((child) => {
        if (!(child instanceof THREE.Mesh)) {
          return;
        }
        if (isObjFormat) {
          // OBJ has no usable baked PBR material here (OBJLoader's own
          // default is Phong, and any referenced .mtl may be missing) --
          // always give it a fresh MeshStandardMaterial so the roughness/
          // metalness sliders have something to drive.
          child.material = new THREE.MeshStandardMaterial({
            color: 0xaaaaaa,
            roughness,
            metalness: metalness ?? MAX_MATERIAL_METALNESS,
          });
        } else if (child.material instanceof THREE.MeshStandardMaterial) {
          child.material.roughness = roughness;
          child.material.metalness =
            metalness === undefined
              ? Math.min(child.material.metalness, MAX_MATERIAL_METALNESS)
              : metalness;
        }
      });

      // Correction sits between the group and the model so the group's own scale
      // stays the single thing fitGroupToView touches.
      const oriented = new THREE.Group();
      oriented.applyMatrix4(glbToViewRotation());
      oriented.add(obj);

      group.add(oriented);
      // Fit at identity, then restore last rotation. Fitting while already
      // orbited changes projected silhouette size; a scene remount (Strict
      // Mode) also skips the orbit effect, so this is the one restore site.
      applyOrbitPose(
        controls,
        initialAzimuthalRef.current,
        initialPolarRef.current,
        0,
        0,
        0,
      );
      fitGroupToView();
      applyOrbitPose(
        controls,
        initialAzimuthalRef.current,
        initialPolarRef.current,
        orbitAzimuthDegRef.current,
        orbitElevationDegRef.current,
        orbitRollDegRef.current,
      );
    };

    if (format === "obj") {
      const text = new TextDecoder().decode(glbData);
      const obj = new OBJLoader().parse(text);
      settleLoadedObject(obj, true);
    } else {
      const loader = new GLTFLoader();
      loader.parse(glbData.slice(0), "", (gltf) => {
        settleLoadedObject(gltf.scene, false);
      });
    }

    let frameId: number;
    const applyScreenRoll = () => {
      const roll = orbitRollDegRef.current;
      if (!roll) {
        return;
      }
      const forward = new THREE.Vector3()
        .subVectors(controls.target, camera.position)
        .normalize();
      camera.up.set(0, 1, 0).applyAxisAngle(forward, degToRad(roll));
      camera.lookAt(controls.target);
    };
    const animate = () => {
      frameId = requestAnimationFrame(animate);
      controls.update();
      applyScreenRoll();
      renderer.render(scene, camera);
    };
    animate();

    const reportOrbit = () => {
      const azimuthDeg = radToDeg(controls.getAzimuthalAngle() - initialAzimuthalRef.current);
      const elevationDeg = radToDeg(initialPolarRef.current - controls.getPolarAngle());
      onOrbitChangeRef.current?.(azimuthDeg, elevationDeg);
    };
    const onOrbitStart = () => {
      orbitDraggingRef.current = true;
    };
    const onOrbitEnd = () => {
      orbitDraggingRef.current = false;
      reportOrbit();
    };
    controls.addEventListener("start", onOrbitStart);
    controls.addEventListener("end", onOrbitEnd);

    const observer = new ResizeObserver(() => {
      const nextWidth = mount.clientWidth;
      const nextHeight = mount.clientHeight;
      camera.aspect = nextWidth / nextHeight;
      renderer.setSize(nextWidth, nextHeight);
      camera.updateProjectionMatrix();
      fitGroupToView();
    });
    observer.observe(mount);

    return () => {
      cancelAnimationFrame(frameId);
      observer.disconnect();
      controls.removeEventListener("start", onOrbitStart);
      controls.removeEventListener("end", onOrbitEnd);
      controls.dispose();
      renderer.dispose();
      rendererRef.current = null;
      controlsRef.current = null;
      sceneStateRef.current = null;
      if (mount.contains(renderer.domElement)) {
        mount.removeChild(renderer.domElement);
      }
    };
    // roughness/metalness/keyLightIntensity/cameraFov intentionally omitted --
    // see comment at the top of this effect; the three effects below handle
    // their live updates without re-running this one.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [glbData, format, enableOrbitDrag]);

  // Material sliders: mutate every already-loaded mesh's material in place.
  // A no-op if the model hasn't finished loading yet -- settleLoadedObject
  // above already applies the current roughness/metalness at load time, so
  // there's no gap between "model appears" and "sliders take effect."
  useEffect(() => {
    const state = sceneStateRef.current;
    if (!state) {
      return;
    }
    state.group.traverse((child) => {
      if (child instanceof THREE.Mesh && child.material instanceof THREE.MeshStandardMaterial) {
        child.material.roughness = roughness;
        if (metalness !== undefined) {
          child.material.metalness = metalness;
        }
      }
    });
  }, [roughness, metalness]);

  // Key light slider: mutate the existing light's intensity, no reload.
  useEffect(() => {
    const state = sceneStateRef.current;
    if (!state) {
      return;
    }
    state.keyLight.intensity = keyLightIntensity;
  }, [keyLightIntensity]);

  // Camera FOV slider: mutate the existing camera and re-fit, no reload --
  // fitGroupToView reads camera.fov live off the (mutated) camera object.
  useEffect(() => {
    const state = sceneStateRef.current;
    if (!state) {
      return;
    }
    state.camera.fov = cameraFov;
    state.camera.updateProjectionMatrix();
    state.fitGroupToView();
  }, [cameraFov]);

  // Drive spherical angles from rotateX/Y drafts + roll from rotateZ.
  // Skip while the user is mid-drag so OrbitControls owns the camera.
  useEffect(() => {
    if (orbitDraggingRef.current) {
      return;
    }
    const controls = controlsRef.current;
    const renderer = rendererRef.current;
    if (!controls || !renderer) {
      return;
    }
    applyOrbitPose(
      controls,
      initialAzimuthalRef.current,
      initialPolarRef.current,
      orbitAzimuthDeg,
      orbitElevationDeg,
      orbitRollDeg,
    );
  }, [orbitAzimuthDeg, orbitElevationDeg, orbitRollDeg]);

  return (
    <div className={`model-3d-frame${className ? ` ${className}` : ""}`} style={style}>
      <div ref={mountRef} className="model-3d-viewport" />
    </div>
  );
});
