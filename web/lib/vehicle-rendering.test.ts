import { describe, expect, test } from "bun:test";
import * as THREE from "three";
import { fittedCameraPosition, studioMaterial, disposeVehicle } from "./vehicle-rendering";

// G70 bounds are larger than G60; test projection, not a specific camera distance.
const bounds = new THREE.Box3(new THREE.Vector3(-1.11, 0, -2.7), new THREE.Vector3(1.11, 1.54, 2.7));
describe("vehicle camera framing", () => {
  for (const aspect of [0.55, 0.8, 1, 1.7, 2.4]) {
    test(`keeps all vehicle corners in frame at aspect ${aspect}`, () => {
      const target = bounds.getCenter(new THREE.Vector3());
      const camera = new THREE.PerspectiveCamera(32, aspect, 0.03, 100);
      camera.position.copy(fittedCameraPosition(bounds, target, new THREE.Vector3(-4.6, 1.47, 5.4), camera.fov, aspect));
      camera.lookAt(target);
      camera.updateMatrixWorld();
      for (const x of [bounds.min.x, bounds.max.x]) {
        for (const y of [bounds.min.y, bounds.max.y]) {
          for (const z of [bounds.min.z, bounds.max.z]) {
            const point = new THREE.Vector3(x, y, z).project(camera);
            expect(Math.abs(point.x)).toBeLessThan(0.87);
            expect(Math.abs(point.y)).toBeLessThan(0.87);
            expect(point.z).toBeLessThan(1);
            expect(point.z).toBeGreaterThan(-1);
          }
        }
      }
    });
  }
});

test("refined paint retains source maps, uses physical shading and never mutates the GLB material", () => {
  const source = new THREE.MeshStandardMaterial({ color: "#123456", map: new THREE.Texture(), roughness: 0.8 });
  source.name = "body_paint";
  const material = studioMaterial(source, "#bdc7cf", true);
  expect(material.map).toBe(source.map);
  expect(material.defines).toHaveProperty("PHYSICAL");
  expect(material.clearcoat).toBeGreaterThan(0);
  expect(material.color.getHexString()).toBe("bdc7cf");
  expect(source.color.getHexString()).toBe("123456");
  expect(source.roughness).toBe(0.8);
});

test("transparent cabin windows retain transparency and avoid blocking surfaces behind them", () => {
  const source = new THREE.MeshStandardMaterial({ transparent: true, opacity: 0.58 });
  source.name = "glass_tinted";
  const material = studioMaterial(source, "#ffffff", false);
  expect(material.transparent).toBe(true);
  expect(material.depthWrite).toBe(false);
  expect(material.opacity).toBeLessThan(1);
});

test("shared resources and textures are disposed once on model change", () => {
  const scene = new THREE.Scene();
  const geometry = new THREE.BoxGeometry();
  const texture = new THREE.Texture();
  const source = new THREE.MeshStandardMaterial({ map: texture });
  const replacement = studioMaterial(source, "#244a70", true);
  scene.add(new THREE.Mesh(geometry, replacement), new THREE.Mesh(geometry, replacement));
  const disposals = { geometry: 0, source: 0, replacement: 0, texture: 0 };
  geometry.addEventListener("dispose", () => disposals.geometry++);
  source.addEventListener("dispose", () => disposals.source++);
  replacement.addEventListener("dispose", () => disposals.replacement++);
  texture.addEventListener("dispose", () => disposals.texture++);
  disposeVehicle(scene, [source]);
  expect(disposals).toEqual({ geometry: 1, source: 1, replacement: 1, texture: 1 });
});
