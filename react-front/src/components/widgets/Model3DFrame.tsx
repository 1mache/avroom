import React, { useEffect, useRef } from "react";
import * as THREE from "three";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";

const CAMERA_FOV = 40;
const CAMERA_NEAR = 0.1;
const CAMERA_FAR = 1000;
const CAMERA_POSITION = { x: 0, y: 1.5, z: 7 };

const MAX_PIXEL_RATIO = 2;

const AMBIENT_LIGHT_COLOR = 0xffffff;
const AMBIENT_LIGHT_INTENSITY = 0.6;

const KEY_LIGHT_COLOR = 0x93c5fd; // Tailwind blue-300
const KEY_LIGHT_INTENSITY = 2.0;
const KEY_LIGHT_POSITION = { x: 4, y: 6, z: 5 };

const FILL_LIGHT_COLOR = 0x60a5fa; // Tailwind blue-400
const FILL_LIGHT_INTENSITY = 0.6;
const FILL_LIGHT_POSITION = { x: -5, y: 2, z: -4 };

const RIM_LIGHT_COLOR = 0xbfdbfe; // Tailwind blue-200
const RIM_LIGHT_INTENSITY = 0.4;
const RIM_LIGHT_POSITION = { x: 0, y: -3, z: -6 };

const MODEL_TARGET_SIZE = 3; // longest axis in world units, fits CAMERA_POSITION.z=7

const MATERIAL_ROUGHNESS = 0.3; // lower = shinier (PBR equivalent of Phong shininess)

interface NormalizedPos {
  x: number;
  y: number;
}

interface Props {
  glbData: ArrayBuffer | null;
  backgroundImage?: string | null;
  clickNormalizedPos?: NormalizedPos | null;
}

/**
 * Shift the camera's projection so a centered scene appears at normalized screen position (cx, cy).
 * Uses setViewOffset to move the principal point — equivalent to a tilt-shift / lens-shift.
 * Pass null to clear the offset (model renders centered).
 */
function applyClickViewOffset(
  camera: THREE.PerspectiveCamera,
  pos: NormalizedPos | null | undefined,
  width: number,
  height: number,
): void {
  if (pos) {
    camera.setViewOffset(
      width,
      height,
      width * (0.5 - pos.x),
      height * (0.5 - pos.y),
      width,
      height,
    );
  } else {
    camera.clearViewOffset();
  }
}

export const Model3DFrame: React.FC<Props> = ({
  glbData,
  backgroundImage,
  clickNormalizedPos,
}) => {
  const mountRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const mount = mountRef.current;
    if (!mount || !glbData) return;

    const width = mount.clientWidth;
    const height = mount.clientHeight;

    const scene = new THREE.Scene();

    // fov=40 is a narrow lens — less perspective distortion than the typical 75, looks more "product photo"
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

    // alpha: true = transparent canvas background so the CSS background shows through
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setSize(width, height);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, MAX_PIXEL_RATIO)); // cap — 3x+ screens get diminishing returns and burn GPU
    mount.appendChild(renderer.domElement);

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;

    scene.add(
      new THREE.AmbientLight(AMBIENT_LIGHT_COLOR, AMBIENT_LIGHT_INTENSITY),
    );

    // Three-point lighting rig in Tailwind blue palette for a stylized look
    const key = new THREE.DirectionalLight(
      KEY_LIGHT_COLOR,
      KEY_LIGHT_INTENSITY,
    ); // key: main light, upper-right-front
    key.position.set(
      KEY_LIGHT_POSITION.x,
      KEY_LIGHT_POSITION.y,
      KEY_LIGHT_POSITION.z,
    );
    scene.add(key);

    const fill = new THREE.DirectionalLight(
      FILL_LIGHT_COLOR,
      FILL_LIGHT_INTENSITY,
    ); // fill: softens shadows on the left-back side
    fill.position.set(
      FILL_LIGHT_POSITION.x,
      FILL_LIGHT_POSITION.y,
      FILL_LIGHT_POSITION.z,
    );
    scene.add(fill);

    const rim = new THREE.DirectionalLight(
      RIM_LIGHT_COLOR,
      RIM_LIGHT_INTENSITY,
    ); // rim: below-back edge highlight to separate model from background
    rim.position.set(
      RIM_LIGHT_POSITION.x,
      RIM_LIGHT_POSITION.y,
      RIM_LIGHT_POSITION.z,
    );
    scene.add(rim);

    // Group wraps the model so rotation/scale apply without touching the model's own transform.
    // Position stays at origin so OrbitControls (target=origin) orbits around model center.
    // Click placement is handled by camera.setViewOffset, not by translating the model.
    const group = new THREE.Group();
    scene.add(group);

    applyClickViewOffset(camera, clickNormalizedPos, width, height);

    const loader = new GLTFLoader();
    // slice(0) copies the buffer — GLTFLoader transfers (detaches) the original ArrayBuffer, which would break React state
    loader.parse(glbData.slice(0), "", (gltf) => {
      const obj = gltf.scene;

      // Normalize the model to fit the view regardless of its original scale/position in the GLB
      const box = new THREE.Box3().setFromObject(obj);
      const center = box.getCenter(new THREE.Vector3());
      const size = box.getSize(new THREE.Vector3());
      const maxDim = Math.max(size.x, size.y, size.z);

      obj.position.copy(center).negate(); // shift model so its geometric center sits at the group origin
      group.scale.setScalar(MODEL_TARGET_SIZE / maxDim);

      // Mutate existing PBR material to boost shininess while preserving GLB textures (map, normalMap, etc).
      obj.traverse((child) => {
        if (child instanceof THREE.Mesh && child.material instanceof THREE.MeshStandardMaterial) {
          child.material.roughness = MATERIAL_ROUGHNESS;
        }
      });

      group.add(obj);
    });

    let frameId: number;
    const animate = () => {
      frameId = requestAnimationFrame(animate);
      controls.update();
      renderer.render(scene, camera);
    };
    animate();

    const observer = new ResizeObserver(() => {
      const w = mount.clientWidth;
      const h = mount.clientHeight;
      camera.aspect = w / h;
      // setViewOffset internally calls updateProjectionMatrix using the new aspect.
      // When no click pos, clearViewOffset still triggers the matrix update.
      applyClickViewOffset(camera, clickNormalizedPos, w, h);
      renderer.setSize(w, h);
    });
    observer.observe(mount);

    return () => {
      cancelAnimationFrame(frameId);
      observer.disconnect();
      controls.dispose();
      renderer.dispose(); // frees GPU resources: textures, buffers, shaders
      if (mount.contains(renderer.domElement)) {
        mount.removeChild(renderer.domElement);
      }
    };
  }, [glbData, clickNormalizedPos]);

  return (
    <div className="frame model-3d-frame">
      <div className="frame-title">
        3D Model
        <span className="coming-soon-badge">Coming Soon</span>
      </div>
      <div
        ref={mountRef}
        className="model-3d-viewport"
        style={
          backgroundImage
            ? {
                backgroundImage: `url(${backgroundImage})`,
                backgroundSize: "cover",
                backgroundPosition: "center",
              }
            : undefined
        }
      />
    </div>
  );
};
