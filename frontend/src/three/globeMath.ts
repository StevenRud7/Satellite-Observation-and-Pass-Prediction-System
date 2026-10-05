import * as THREE from "three";

/**
 * Coordinate math for the 3D globe view.
 *
 * The globe itself (grid lines, observer marker) is built directly from
 * latitude/longitude using `latLonToVector3` - exact, no approximation.
 *
 * The satellite's pass arc is a different story: the backend gives us
 * topocentric azimuth/elevation/range *relative to the observer*, not
 * the satellite's own latitude/longitude. To place it in the scene, we
 * treat the observer's local tangent plane as flat (a standard East-
 * North-Up frame) and offset from the observer's position along that
 * frame. This is a good approximation at the ranges involved (hundreds
 * to a couple thousand km against Earth's ~6378 km radius) for a display
 * aid, but it is an approximation - not a re-derivation of orbital
 * mechanics on the frontend. The real geometry was already computed
 * exactly by the backend (Phase 2/3); this only decides where to draw it.
 */

export const EARTH_RADIUS_KM = 6378.137;
export const SCENE_EARTH_RADIUS = 2;
const KM_TO_SCENE = SCENE_EARTH_RADIUS / EARTH_RADIUS_KM;

export function latLonToVector3(
  latDeg: number,
  lonDeg: number,
  radius: number = SCENE_EARTH_RADIUS,
): THREE.Vector3 {
  const lat = (latDeg * Math.PI) / 180;
  const lon = (lonDeg * Math.PI) / 180;
  return new THREE.Vector3(
    radius * Math.cos(lat) * Math.cos(lon),
    radius * Math.sin(lat),
    radius * Math.cos(lat) * Math.sin(lon),
  );
}

interface EastNorthUp {
  east: THREE.Vector3;
  north: THREE.Vector3;
  up: THREE.Vector3;
}

export function eastNorthUpAt(position: THREE.Vector3): EastNorthUp {
  const up = position.clone().normalize();
  const worldUp = new THREE.Vector3(0, 1, 0);
  const east = new THREE.Vector3().crossVectors(worldUp, up).normalize();
  const north = new THREE.Vector3().crossVectors(up, east).normalize();
  return { east, north, up };
}

/** Convert one observer-relative az/el/range reading into a scene position. */
export function topocentricToScenePosition(
  observerPosition: THREE.Vector3,
  azimuthDeg: number,
  elevationDeg: number,
  rangeKm: number,
): THREE.Vector3 {
  const { east, north, up } = eastNorthUpAt(observerPosition);
  const az = (azimuthDeg * Math.PI) / 180;
  const el = (elevationDeg * Math.PI) / 180;
  const rangeScene = rangeKm * KM_TO_SCENE;

  const horizontal = rangeScene * Math.cos(el);
  const eastComponent = horizontal * Math.sin(az);
  const northComponent = horizontal * Math.cos(az);
  const upComponent = rangeScene * Math.sin(el);

  return observerPosition
    .clone()
    .add(east.clone().multiplyScalar(eastComponent))
    .add(north.clone().multiplyScalar(northComponent))
    .add(up.clone().multiplyScalar(upComponent));
}
