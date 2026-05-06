import React, { useEffect, useRef } from "react";
import * as THREE from "three";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";

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

const MATERIAL_COLOR = 0xdbeafe;    // Tailwind blue-100
const MATERIAL_SPECULAR = 0x93c5fd; // Tailwind blue-300
const MATERIAL_SHININESS = 120;

const MODEL_TARGET_SIZE = 3; // longest axis in world units, fits CAMERA_POSITION.z=7
const ROTATION_SPEED_Y = 0.007;

interface Props {
  glbData: ArrayBuffer | null;
  backgroundImage?: string | null;
}

export const Model3DFrame: React.FC<Props> = ({ glbData, backgroundImage }) => {
  const mountRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const mount = mountRef.current;
    if (!mount || !glbData) return;

    const width = mount.clientWidth;
    const height = mount.clientHeight;

    const scene = new THREE.Scene();

    // fov=40 is a narrow lens — less perspective distortion than the typical 75, looks more "product photo"
    const camera = new THREE.PerspectiveCamera(CAMERA_FOV, width / height, CAMERA_NEAR, CAMERA_FAR);
    camera.position.set(CAMERA_POSITION.x, CAMERA_POSITION.y, CAMERA_POSITION.z);
    camera.lookAt(0, 0, 0);

    // alpha: true = transparent canvas background so the CSS background shows through
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setSize(width, height);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, MAX_PIXEL_RATIO)); // cap — 3x+ screens get diminishing returns and burn GPU
    mount.appendChild(renderer.domElement);

    scene.add(new THREE.AmbientLight(AMBIENT_LIGHT_COLOR, AMBIENT_LIGHT_INTENSITY));

    // Three-point lighting rig in Tailwind blue palette for a stylized look
    const key = new THREE.DirectionalLight(KEY_LIGHT_COLOR, KEY_LIGHT_INTENSITY); // key: main light, upper-right-front
    key.position.set(KEY_LIGHT_POSITION.x, KEY_LIGHT_POSITION.y, KEY_LIGHT_POSITION.z);
    scene.add(key);

    const fill = new THREE.DirectionalLight(FILL_LIGHT_COLOR, FILL_LIGHT_INTENSITY); // fill: softens shadows on the left-back side
    fill.position.set(FILL_LIGHT_POSITION.x, FILL_LIGHT_POSITION.y, FILL_LIGHT_POSITION.z);
    scene.add(fill);

    const rim = new THREE.DirectionalLight(RIM_LIGHT_COLOR, RIM_LIGHT_INTENSITY); // rim: below-back edge highlight to separate model from background
    rim.position.set(RIM_LIGHT_POSITION.x, RIM_LIGHT_POSITION.y, RIM_LIGHT_POSITION.z);
    scene.add(rim);

    // Group wraps the model so rotation/scale apply without touching the model's own transform
    const group = new THREE.Group();
    scene.add(group);

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

      // Override every mesh's material — ignores whatever the GLB shipped with, enforces uniform blue style
      obj.traverse((child) => {
        if (child instanceof THREE.Mesh) {
          child.material = new THREE.MeshPhongMaterial({
            color: MATERIAL_COLOR,
            specular: MATERIAL_SPECULAR,
            shininess: MATERIAL_SHININESS,
          });
        }
      });

      group.add(obj);
    });

    let frameId: number;
    const animate = () => {
      frameId = requestAnimationFrame(animate);
      group.rotation.y += ROTATION_SPEED_Y;
      renderer.render(scene, camera);
    };
    animate();

    const observer = new ResizeObserver(() => {
      const w = mount.clientWidth;
      const h = mount.clientHeight;
      camera.aspect = w / h;
      camera.updateProjectionMatrix(); // must call after changing any camera property or the old matrix stays in effect
      renderer.setSize(w, h);
    });
    observer.observe(mount);

    return () => {
      cancelAnimationFrame(frameId);
      observer.disconnect();
      renderer.dispose(); // frees GPU resources: textures, buffers, shaders
      if (mount.contains(renderer.domElement)) {
        mount.removeChild(renderer.domElement);
      }
    };
  }, [glbData]);

  return (
    <div className="frame model-3d-frame">
      <div className="frame-title">
        3D Model
        <span className="coming-soon-badge">Coming Soon</span>
      </div>
      <div
        ref={mountRef}
        className="model-3d-viewport"
        style={backgroundImage ? { backgroundImage: `url(${backgroundImage})`, backgroundSize: "cover", backgroundPosition: "center" } : undefined}
      />
    </div>
  );
};
