import React, { useEffect, useRef } from "react";
import * as THREE from "three";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";

interface Props {
  glbData: ArrayBuffer | null;
}

export const Model3DFrame: React.FC<Props> = ({ glbData }) => {
  const mountRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const mount = mountRef.current;
    if (!mount || !glbData) return;

    const width = mount.clientWidth;
    const height = mount.clientHeight;

    const scene = new THREE.Scene();

    // fov=40 is a narrow lens — less perspective distortion than the typical 75, looks more "product photo"
    const camera = new THREE.PerspectiveCamera(40, width / height, 0.1, 1000);
    camera.position.set(0, 1.5, 7);
    camera.lookAt(0, 0, 0);

    // alpha: true = transparent canvas background so the CSS background shows through
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setSize(width, height);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2)); // cap at 2x — 3x+ screens get diminishing returns and burn GPU
    mount.appendChild(renderer.domElement);

    scene.add(new THREE.AmbientLight(0xffffff, 0.6));

    // Three-point lighting rig in Tailwind blue palette for a stylized look
    const key = new THREE.DirectionalLight(0x93c5fd, 2.0); // key: main light, upper-right-front
    key.position.set(4, 6, 5);
    scene.add(key);

    const fill = new THREE.DirectionalLight(0x60a5fa, 0.6); // fill: softens shadows on the left-back side
    fill.position.set(-5, 2, -4);
    scene.add(fill);

    const rim = new THREE.DirectionalLight(0xbfdbfe, 0.4); // rim: below-back edge highlight to separate model from background
    rim.position.set(0, -3, -6);
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
      group.scale.setScalar(3 / maxDim);  // scale so the longest axis = 3 units, which fits the camera at z=7

      // Override every mesh's material — ignores whatever the GLB shipped with, enforces uniform blue style
      obj.traverse((child) => {
        if (child instanceof THREE.Mesh) {
          child.material = new THREE.MeshPhongMaterial({
            color: 0xdbeafe,    // Tailwind blue-100
            specular: 0x93c5fd, // Tailwind blue-300 highlight
            shininess: 120,     // 0–1000; 120 = moderately glossy
          });
        }
      });

      group.add(obj);
    });

    let frameId: number;
    const animate = () => {
      frameId = requestAnimationFrame(animate);
      group.rotation.y += 0.007; // slow Y-axis spin so all sides of the model are visible
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
      <div ref={mountRef} className="model-3d-viewport" />
    </div>
  );
};
