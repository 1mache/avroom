import React, { forwardRef, useEffect, useImperativeHandle, useRef } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";

// Camera tuned for "object on pedestal" framing inside current viewport sizes.
const CAMERA_FOV = 40;
const CAMERA_NEAR = 0.1;
const CAMERA_FAR = 1000;
const CAMERA_POSITION = { x: 0, y: 0, z: 7 };

// Cap device pixel ratio so retina screens do not multiply GPU cost too hard.
const MAX_PIXEL_RATIO = 2;

// Three-light setup gives soft studio look without needing environment maps.
const AMBIENT_LIGHT_COLOR = 0xffffff;
const AMBIENT_LIGHT_INTENSITY = 0.6;

const KEY_LIGHT_COLOR = 0x9ad9db;
const KEY_LIGHT_INTENSITY = 2.0;
const KEY_LIGHT_POSITION = { x: 4, y: 6, z: 5 };

const FILL_LIGHT_COLOR = 0x0c8186;
const FILL_LIGHT_INTENSITY = 0.8;
const FILL_LIGHT_POSITION = { x: -5, y: 2, z: -4 };

const RIM_LIGHT_COLOR = 0xf3d39b;
const RIM_LIGHT_INTENSITY = 0.45;
const RIM_LIGHT_POSITION = { x: 0, y: -3, z: -6 };

const MATERIAL_ROUGHNESS = 0.3;

// The viewer canvas is inflated by this factor around the object's on-stage
// rect (see model3DFrameStyle in MainPage) and the model is fit to fill
// 1/this of the viewport. Net effect: the model reads at the same size as the
// 2D cutout it replaces, while still having empty canvas around it so parts
// that swing outside the original silhouette during an orbit aren't clipped.
export const MODEL_3D_FRAME_PADDING = 1.5;

// Generated GLBs come back lying flat: the side the source photo saw faces the
// mesh's -Y axis, with the photo's "up" along +X. Left uncorrected, the viewer
// opens on an edge-on sliver and the user must orbit ~90 degrees before the
// object even looks like itself. Mapping -Y onto the camera axis (+Z) and +X
// onto screen up (+Y) makes the starting pose reproduce the photo, which is
// also the pose the backend renders at zero rotation
// (_GLB_TO_VIEW_ROTATION in mesh_render_novel_view_strategy.py).
const glbToViewRotation = (): THREE.Matrix4 =>
  new THREE.Matrix4().set(
    0, 0, -1, 0,
    1, 0, 0, 0,
    0, -1, 0, 0,
    0, 0, 0, 1,
  );

interface Props {
  glbData: ArrayBuffer | null;
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
  { glbData, className, style },
  ref,
) {
  const mountRef = useRef<HTMLDivElement>(null);
  const rendererRef = useRef<THREE.WebGLRenderer | null>(null);
  const controlsRef = useRef<OrbitControls | null>(null);
  const initialAzimuthalRef = useRef(0);
  const initialPolarRef = useRef(0);

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
    // Three.js object when GLB data changes or component unmounts.
    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(
      CAMERA_FOV,
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
    controls.enableDamping = true;
    controls.enablePan = false;
    controls.target.set(0, 0, 0);
    controlsRef.current = controls;
    initialAzimuthalRef.current = controls.getAzimuthalAngle();
    initialPolarRef.current = controls.getPolarAngle();

    scene.add(new THREE.AmbientLight(AMBIENT_LIGHT_COLOR, AMBIENT_LIGHT_INTENSITY));

    const key = new THREE.DirectionalLight(KEY_LIGHT_COLOR, KEY_LIGHT_INTENSITY);
    key.position.set(KEY_LIGHT_POSITION.x, KEY_LIGHT_POSITION.y, KEY_LIGHT_POSITION.z);
    scene.add(key);

    const fill = new THREE.DirectionalLight(FILL_LIGHT_COLOR, FILL_LIGHT_INTENSITY);
    fill.position.set(FILL_LIGHT_POSITION.x, FILL_LIGHT_POSITION.y, FILL_LIGHT_POSITION.z);
    scene.add(fill);

    const rim = new THREE.DirectionalLight(RIM_LIGHT_COLOR, RIM_LIGHT_INTENSITY);
    rim.position.set(RIM_LIGHT_POSITION.x, RIM_LIGHT_POSITION.y, RIM_LIGHT_POSITION.z);
    scene.add(rim);

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

    const loader = new GLTFLoader();
    loader.parse(glbData.slice(0), "", (gltf) => {
      const obj = gltf.scene;
      const box = new THREE.Box3().setFromObject(obj);
      const center = box.getCenter(new THREE.Vector3());
      const size = box.getSize(new THREE.Vector3());
      const maxDim = Math.max(size.x, size.y, size.z) || 1;

      // Normalize to roughly unit size first so the fit iteration below starts
      // from extents comparable to the orbit radius, whatever scale the source
      // GLB happens to use.
      const normalizedScale = 1 / maxDim;
      obj.scale.setScalar(normalizedScale);
      obj.position.copy(center).multiplyScalar(-normalizedScale);

      obj.traverse((child) => {
        if (child instanceof THREE.Mesh && child.material instanceof THREE.MeshStandardMaterial) {
          child.material.roughness = MATERIAL_ROUGHNESS;
        }
      });

      // Correction sits between the group and the model so the group's own scale
      // stays the single thing fitGroupToView touches.
      const oriented = new THREE.Group();
      oriented.applyMatrix4(glbToViewRotation());
      oriented.add(obj);

      group.add(oriented);
      fitGroupToView();
    });

    let frameId: number;
    const animate = () => {
      frameId = requestAnimationFrame(animate);
      controls.update();
      renderer.render(scene, camera);
    };
    animate();

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
      controls.dispose();
      renderer.dispose();
      rendererRef.current = null;
      controlsRef.current = null;
      if (mount.contains(renderer.domElement)) {
        mount.removeChild(renderer.domElement);
      }
    };
  }, [glbData]);

  return (
    <div className={`model-3d-frame${className ? ` ${className}` : ""}`} style={style}>
      <div ref={mountRef} className="model-3d-viewport" />
    </div>
  );
});
