import * as THREE from "three";

/** Fit every corner, including the nearest bumper, at any viewport aspect ratio. */
export function fittedCameraPosition(
  bounds: THREE.Box3,
  target: THREE.Vector3,
  direction: THREE.Vector3,
  fov: number,
  aspect: number,
  padding = 1.16,
) {
  const back = direction.clone().normalize();
  const right = new THREE.Vector3().crossVectors(new THREE.Vector3(0, 1, 0), back).normalize();
  const up = new THREE.Vector3().crossVectors(back, right).normalize();
  const vertical = Math.tan(THREE.MathUtils.degToRad(fov / 2));
  const horizontal = vertical * Math.max(aspect, 0.1);
  let distance = 0;
  for (const x of [bounds.min.x, bounds.max.x]) {
    for (const y of [bounds.min.y, bounds.max.y]) {
      for (const z of [bounds.min.z, bounds.max.z]) {
        const corner = new THREE.Vector3(x, y, z).sub(target);
        const depth = corner.dot(back);
        distance = Math.max(distance,
          depth + Math.abs(corner.dot(right)) * padding / horizontal,
          depth + Math.abs(corner.dot(up)) * padding / vertical);
      }
    }
  }
  return target.clone().addScaledVector(back, Math.max(distance, 2.5));
}

/** Refine the supplied artist materials while retaining their maps and geometry. */
export function studioMaterial(source: THREE.MeshStandardMaterial, paint: string, isPaint: boolean) {
  // MeshPhysicalMaterial.copy expects another physical material. Copy the common
  // standard properties explicitly so the GLB's textures and vertex colors survive.
  const physical = new THREE.MeshPhysicalMaterial();
  THREE.MeshStandardMaterial.prototype.copy.call(physical, source);
  const material = Object.assign(physical, { defines: { STANDARD: "", PHYSICAL: "" } });
  material.name = source.name;
  material.envMapIntensity = 1;
  if (isPaint) {
    material.color.set(paint);
    material.metalness = 0.4;
    material.roughness = 0.34;
    material.clearcoat = 0.7;
    material.clearcoatRoughness = 0.26;
    material.envMapIntensity = 0.9;
  } else if (source.name.startsWith("glass")) {
    material.color.set("#182631");
    material.metalness = 0.12;
    material.roughness = 0.18;
    material.clearcoat = 1;
    material.clearcoatRoughness = 0.18;
    material.envMapIntensity = 0.85;
    if (source.transparent) {
      material.opacity = 0.78;
      material.depthWrite = false;
    }
  } else if (source.name.includes("alloy") || source.name.includes("badge_satin")) {
    material.color.set("#bac0c8");
    material.metalness = 0.9;
    material.roughness = 0.22;
  } else if (source.name.includes("trim") || source.name.includes("wheel_m70")) {
    material.color.set("#22262b");
    material.metalness = 0.46;
    material.roughness = 0.27;
    material.clearcoat = 0.45;
  } else if (source.name.includes("rubber")) {
    material.color.set("#292b2e");
    material.metalness = 0;
    material.roughness = 0.88;
  } else if (source.name.startsWith("lamp")) {
    material.clearcoat = 1;
    material.clearcoatRoughness = 0.1;
    material.emissiveIntensity = 0.65;
  }
  return material;
}

/** Local softboxes provide paint reflections without fetching an external HDRI. */
export function studioEnvironment(renderer: THREE.WebGLRenderer) {
  const studio = new THREE.Scene();
  studio.background = new THREE.Color("#a0a6ae");
  const softboxes: THREE.Mesh<THREE.PlaneGeometry, THREE.MeshBasicMaterial>[] = [];
  const addSoftbox = (width: number, height: number, position: [number, number, number], strength: number) => {
    const panel = new THREE.Mesh(new THREE.PlaneGeometry(width, height), new THREE.MeshBasicMaterial({
      color: new THREE.Color().setRGB(strength, strength, strength), side: THREE.DoubleSide,
    }));
    panel.position.set(...position);
    panel.lookAt(0, 0, 0);
    studio.add(panel);
    softboxes.push(panel);
  };
  addSoftbox(12, 15, [0, 8, 0], 1.65);
  addSoftbox(14, 5, [-7, 4, 0], 1.75);
  addSoftbox(12, 4, [7, 3, -2], 1.35);
  addSoftbox(8, 6, [1, 4, 8], 1.1);
  const generator = new THREE.PMREMGenerator(renderer);
  const environment = generator.fromScene(studio, 0.14);
  generator.dispose();
  softboxes.forEach((panel) => { panel.geometry.dispose(); panel.material.dispose(); });
  return environment;
}

/** Dispose shared geometry, materials and textures once, including late GLB loads. */
export function disposeVehicle(object: THREE.Object3D, additionalMaterials: Iterable<THREE.Material> = []) {
  const geometries = new Set<THREE.BufferGeometry>();
  const materials = new Set<THREE.Material>(additionalMaterials);
  const textures = new Set<THREE.Texture>();
  object.traverse((child) => {
    if (!(child instanceof THREE.Mesh)) return;
    geometries.add(child.geometry);
    (Array.isArray(child.material) ? child.material : [child.material]).forEach((material) => materials.add(material));
  });
  materials.forEach((material) => {
    Object.values(material).forEach((value) => { if (value instanceof THREE.Texture) textures.add(value); });
    material.dispose();
  });
  geometries.forEach((geometry) => geometry.dispose());
  textures.forEach((texture) => texture.dispose());
}
