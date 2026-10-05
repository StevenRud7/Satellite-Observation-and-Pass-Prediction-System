import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";

import type { PassEvent } from "../types/api";
import { interpolatePassProfile, passKeyPoints } from "../utils/passGeometry";
import { latLonToVector3, SCENE_EARTH_RADIUS, topocentricToScenePosition } from "./globeMath";

export interface GlobeSceneHandle {
  setPassData: (observerLatDeg: number, observerLonDeg: number, pass: PassEvent) => void;
  resize: () => void;
  dispose: () => void;
}

const GRID_COLOR = 0x2a3a52;
const OBSERVER_COLOR = 0xe8b04b;
const PASS_COLOR = 0x5fd0a8;

function buildGraticule(): THREE.Group {
  const group = new THREE.Group();
  const material = new THREE.LineBasicMaterial({
    color: GRID_COLOR,
    transparent: true,
    opacity: 0.6,
  });

  // Latitude circles
  for (let lat = -60; lat <= 60; lat += 30) {
    const points: THREE.Vector3[] = [];
    for (let lon = 0; lon <= 360; lon += 5) {
      points.push(latLonToVector3(lat, lon));
    }
    group.add(new THREE.LineLoop(new THREE.BufferGeometry().setFromPoints(points), material));
  }

  // Longitude meridians
  for (let lon = 0; lon < 360; lon += 30) {
    const points: THREE.Vector3[] = [];
    for (let lat = -90; lat <= 90; lat += 5) {
      points.push(latLonToVector3(lat, lon));
    }
    group.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(points), material));
  }

  return group;
}

export function createGlobeScene(container: HTMLElement): GlobeSceneHandle {
  const scene = new THREE.Scene();

  const camera = new THREE.PerspectiveCamera(
    45,
    container.clientWidth / container.clientHeight,
    0.1,
    100,
  );
  camera.position.set(3.2, 2.2, 3.2);

  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.setSize(container.clientWidth, container.clientHeight);
  container.appendChild(renderer.domElement);

  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.minDistance = 2.6;
  controls.maxDistance = 8;

  scene.add(new THREE.AmbientLight(0xffffff, 0.55));
  const sunLight = new THREE.DirectionalLight(0xffffff, 1.0);
  sunLight.position.set(5, 3, 2);
  scene.add(sunLight);

  const earth = new THREE.Mesh(
    new THREE.SphereGeometry(SCENE_EARTH_RADIUS, 48, 48),
    new THREE.MeshPhongMaterial({
      color: 0x0d3b5c,
      shininess: 8,
      transparent: true,
      opacity: 0.92,
    }),
  );
  scene.add(earth);
  scene.add(buildGraticule());

  // Subtle atmosphere glow: a slightly larger sphere, back-face only.
  const atmosphere = new THREE.Mesh(
    new THREE.SphereGeometry(SCENE_EARTH_RADIUS * 1.03, 48, 48),
    new THREE.MeshBasicMaterial({
      color: 0x5fa8d0,
      transparent: true,
      opacity: 0.12,
      side: THREE.BackSide,
    }),
  );
  scene.add(atmosphere);

  const observerMarker = new THREE.Mesh(
    new THREE.SphereGeometry(0.035, 16, 16),
    new THREE.MeshBasicMaterial({ color: OBSERVER_COLOR }),
  );
  observerMarker.visible = false;
  scene.add(observerMarker);

  const passLine = new THREE.Line(
    new THREE.BufferGeometry(),
    new THREE.LineBasicMaterial({ color: PASS_COLOR, linewidth: 2 }),
  );
  scene.add(passLine);

  const peakMarker = new THREE.Mesh(
    new THREE.SphereGeometry(0.045, 16, 16),
    new THREE.MeshBasicMaterial({ color: PASS_COLOR }),
  );
  peakMarker.visible = false;
  scene.add(peakMarker);

  let animationFrameId: number;
  function animate(): void {
    animationFrameId = requestAnimationFrame(animate);
    controls.update();
    renderer.render(scene, camera);
  }
  animate();

  function setPassData(observerLatDeg: number, observerLonDeg: number, pass: PassEvent): void {
    const observerPosition = latLonToVector3(observerLatDeg, observerLonDeg);
    observerMarker.position.copy(observerPosition);
    observerMarker.visible = true;

    const profile = interpolatePassProfile(pass);
    const points = profile.map((p) =>
      topocentricToScenePosition(observerPosition, p.azimuthDeg, p.elevationDeg, p.rangeKm),
    );
    passLine.geometry.dispose();
    passLine.geometry = new THREE.BufferGeometry().setFromPoints(points);

    const [, peak] = passKeyPoints(pass);
    peakMarker.position.copy(
      topocentricToScenePosition(
        observerPosition,
        peak.azimuthDeg,
        peak.elevationDeg,
        peak.rangeKm,
      ),
    );
    peakMarker.visible = true;

    // Aim the camera roughly toward the observer for a helpful default view.
    controls.target.copy(observerPosition.clone().multiplyScalar(0.3));
  }

  function resize(): void {
    camera.aspect = container.clientWidth / container.clientHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(container.clientWidth, container.clientHeight);
  }

  function dispose(): void {
    cancelAnimationFrame(animationFrameId);
    controls.dispose();
    renderer.dispose();
    scene.traverse((object) => {
      if (object instanceof THREE.Mesh || object instanceof THREE.Line) {
        object.geometry.dispose();
        const material = object.material;
        if (Array.isArray(material)) {
          material.forEach((m) => m.dispose());
        } else {
          material.dispose();
        }
      }
    });
    if (renderer.domElement.parentElement === container) {
      container.removeChild(renderer.domElement);
    }
  }

  return { setPassData, resize, dispose };
}
