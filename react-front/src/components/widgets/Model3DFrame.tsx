import React, { useEffect, useRef } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";

// Camera tuned for "object on pedestal" framing inside current viewport sizes.
const CAMERA_FOV = 40;
const CAMERA_NEAR = 0.1;
const CAMERA_FAR = 1000;
const CAMERA_POSITION = { x: 0, y: 1.5, z: 7 };

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

const MODEL_TARGET_SIZE = 3;
const MATERIAL_ROUGHNESS = 0.3;

interface NormalizedPos {
  x: number;
  y: number;
}

interface Props {
  glbData: ArrayBuffer | null;
  // Reserved hook for putting a guide image behind the WebGL canvas.
  backgroundImage?: string | null;
  clickNormalizedPos?: NormalizedPos | null;
  className?: string;
  style?: React.CSSProperties;
}

// Re-center camera framing toward original click target so 3D preview feels tied
// to same object the user selected in the source image.
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
  className,
  style,
}) => {
  const mountRef = useRef<HTMLDivElement>(null);

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

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setSize(width, height);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, MAX_PIXEL_RATIO));
    mount.appendChild(renderer.domElement);

    // Damping keeps orbit motion feeling weighted instead of twitchy.
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;

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

    applyClickViewOffset(camera, clickNormalizedPos, width, height);

    const loader = new GLTFLoader();
    loader.parse(glbData.slice(0), "", (gltf) => {
      const obj = gltf.scene;
      const box = new THREE.Box3().setFromObject(obj);
      const center = box.getCenter(new THREE.Vector3());
      const size = box.getSize(new THREE.Vector3());
      const maxDim = Math.max(size.x, size.y, size.z);

      // Normalize imported model so wildly different GLB source scales still fit
      // same viewer framing.
      obj.position.copy(center).negate();
      group.scale.setScalar(MODEL_TARGET_SIZE / maxDim);

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
      const nextWidth = mount.clientWidth;
      const nextHeight = mount.clientHeight;
      camera.aspect = nextWidth / nextHeight;
      // View offset depends on viewport dimensions, not only camera target.
      applyClickViewOffset(camera, clickNormalizedPos, nextWidth, nextHeight);
      renderer.setSize(nextWidth, nextHeight);
      camera.updateProjectionMatrix();
    });
    observer.observe(mount);

    return () => {
      cancelAnimationFrame(frameId);
      observer.disconnect();
      controls.dispose();
      renderer.dispose();
      if (mount.contains(renderer.domElement)) {
        mount.removeChild(renderer.domElement);
      }
    };
  }, [glbData, clickNormalizedPos]);

  return (
    <div className={`model-3d-frame${className ? ` ${className}` : ""}`} style={style}>
      <div
        ref={mountRef}
        className="model-3d-viewport"
        style={
          backgroundImage
            ? {
                backgroundImage: `url(${backgroundImage})`,
                backgroundSize: "contain",
                backgroundPosition: "center",
                backgroundRepeat: "no-repeat",
              }
            : undefined
        }
      />
    </div>
  );
};
