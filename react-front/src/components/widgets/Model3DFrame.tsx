import React, { useEffect, useRef } from "react";
import * as THREE from "three";
import { OBJLoader } from "three/examples/jsm/loaders/OBJLoader.js";
import toiletModelUrl from "../../assets/toilet.obj?url";

export const Model3DFrame: React.FC = () => {
  const mountRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const mount = mountRef.current;
    if (!mount) return;

    const width = mount.clientWidth;
    const height = mount.clientHeight;

    // Scene
    const scene = new THREE.Scene();

    // Camera
    const camera = new THREE.PerspectiveCamera(40, width / height, 0.1, 1000);
    camera.position.set(0, 1.5, 7);
    camera.lookAt(0, 0, 0);

    // Renderer (transparent bg so CSS handles the dark panel)
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setSize(width, height);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    mount.appendChild(renderer.domElement);

    // Lighting
    scene.add(new THREE.AmbientLight(0xffffff, 0.6));

    const key = new THREE.DirectionalLight(0x93c5fd, 2.0);
    key.position.set(4, 6, 5);
    scene.add(key);

    const fill = new THREE.DirectionalLight(0x60a5fa, 0.6);
    fill.position.set(-5, 2, -4);
    scene.add(fill);

    const rim = new THREE.DirectionalLight(0xbfdbfe, 0.4);
    rim.position.set(0, -3, -6);
    scene.add(rim);

    // Load OBJ
    const group = new THREE.Group();
    scene.add(group);

    const loader = new OBJLoader();
    loader.load(toiletModelUrl, (obj: THREE.Group) => {
      // Center model at origin
      const box = new THREE.Box3().setFromObject(obj);
      const center = box.getCenter(new THREE.Vector3());
      const size = box.getSize(new THREE.Vector3());
      const maxDim = Math.max(size.x, size.y, size.z);

      obj.position.copy(center).negate();
      group.scale.setScalar(3 / maxDim);

      // Blue-tinted ceramic material matching the viewport palette
      obj.traverse((child) => {
        if (child instanceof THREE.Mesh) {
          child.material = new THREE.MeshPhongMaterial({
            color: 0xdbeafe,
            specular: 0x93c5fd,
            shininess: 120,
          });
        }
      });

      group.add(obj);
    });

    // Animate
    let frameId: number;
    const animate = () => {
      frameId = requestAnimationFrame(animate);
      group.rotation.y += 0.007;
      renderer.render(scene, camera);
    };
    animate();

    // Keep canvas sized to container
    const observer = new ResizeObserver(() => {
      const w = mount.clientWidth;
      const h = mount.clientHeight;
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      renderer.setSize(w, h);
    });
    observer.observe(mount);

    return () => {
      cancelAnimationFrame(frameId);
      observer.disconnect();
      renderer.dispose();
      if (mount.contains(renderer.domElement)) {
        mount.removeChild(renderer.domElement);
      }
    };
  }, []);

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
