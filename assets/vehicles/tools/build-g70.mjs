// Build only from the licensed artist download recorded in the G70 manifest.
import fs from "node:fs/promises";
import path from "node:path";
import crypto from "node:crypto";
import { NodeIO } from "@gltf-transform/core";
import {
  ALL_EXTENSIONS,
  KHRMaterialsClearcoat,
} from "@gltf-transform/extensions";
import {
  getBounds,
  dedup,
  weld,
  prune,
  draco as compressDraco,
} from "@gltf-transform/functions";
import draco from "draco3dgltf";
import {
  Matrix4,
  Matrix3,
  Vector3,
  BufferGeometry,
  BufferAttribute,
} from "three";
import { FontLoader } from "three/addons/loaders/FontLoader.js";
import { TextGeometry } from "three/addons/geometries/TextGeometry.js";
import { MeshBVH } from "three-mesh-bvh";
const [input, output] = process.argv.slice(2);
if (!input || !output)
  throw Error("Usage: node build-g70.mjs private-converted.glb output.glb");
const manifestPath = path.join(path.dirname(output), "manifest.json");
const manifest = JSON.parse(await fs.readFile(manifestPath, "utf8"));
const sha = (b) => crypto.createHash("sha256").update(b).digest("hex");
if (sha(await fs.readFile(input)) !== manifest.source.buildInputSha256)
  throw Error("Unrecognized source input");
const io = new NodeIO()
  .registerExtensions(ALL_EXTENSIONS)
  .registerDependencies({
    "draco3d.decoder": await draco.createDecoderModule(),
    "draco3d.encoder": await draco.createEncoderModule(),
  });
const doc = await io.read(input),
  root = doc.getRoot(),
  scene = root.listScenes()[0],
  bounds = getBounds(scene);
const scale = 5.38988 / (bounds.max[2] - bounds.min[2]),
  cx = (bounds.max[0] + bounds.min[0]) / 2,
  cz = (bounds.max[2] + bounds.min[2]) / 2;
const oldNodes = root.listNodes(),
  oldMeshes = root.listMeshes(),
  buffer = root.listBuffers()[0],
  groups = new Map(),
  triangles = new Map();
let duplicateTriangles = 0;
for (const node of oldNodes) {
  const mesh = node.getMesh();
  if (!mesh) continue;
  const matrix = new Matrix4().fromArray(node.getWorldMatrix()),
    nm = new Matrix3().getNormalMatrix(matrix);
  for (const p of mesh.listPrimitives()) {
    const pos = p.getAttribute("POSITION"),
      norm = p.getAttribute("NORMAL"),
      col = p.getAttribute("COLOR_0"),
      idx = p.getIndices();
    for (let t = 0; t < (idx?.getCount() ?? pos.getCount()); t += 3) {
      const vs = [];
      for (let j = 0; j < 3; j++) {
        const i = idx ? idx.getScalar(t + j) : t + j,
          v = new Vector3()
            .fromArray(pos.getElement(i, []))
            .applyMatrix4(matrix),
          n = new Vector3()
            .fromArray(norm.getElement(i, []))
            .applyMatrix3(nm)
            .normalize();
        vs.push({
          p: [
            (v.x - cx) * scale,
            (v.y - bounds.min[1]) * scale,
            (v.z - cz) * scale,
          ],
          n: n.toArray(),
          c: col.getElement(i, []),
        });
      }
      const key = vs
        .map((v) => v.p.map((x) => Math.round(x * 1e6)).join(","))
        .sort()
        .join("|");
      if (triangles.has(key)) {
        duplicateTriangles++;
        // Prefer the painted face over the source's light-grey reverse face.
        if (Math.abs(vs[0].c[0] - 0.3294) < 0.005) triangles.set(key, vs);
      } else triangles.set(key, vs);
    }
  }
}
const paintedPositions = [];
for (const vs of triangles.values())
  if (Math.abs(vs[0].c[0] - 0.3294) < 0.005)
    for (const v of vs) paintedPositions.push(...v.p);
const paintedGeometry = new BufferGeometry().setAttribute(
  "position",
  new BufferAttribute(new Float32Array(paintedPositions), 3),
);
const bvh = new MeshBVH(paintedGeometry);
let coveredBackingTriangles = 0;
for (const vs of triangles.values()) {
  if (Math.abs(vs[0].c[0] - 0.7373) < 0.005) {
    const center = new Vector3();
    for (const v of vs) center.add(new Vector3().fromArray(v.p));
    center.multiplyScalar(1 / 3);
    if (bvh.closestPointToPoint(center, {}, 0, 0.00004)) {
      coveredBackingTriangles++;
      continue;
    }
  }
  const c = vs[0].c,
    center = vs.reduce((a, v) => a.map((x, i) => x + v.p[i] / 3), [0, 0, 0]);
  const [x, y, z] = center;
  const nearWheel =
    Math.abs(x) > 0.72 &&
    Math.min(Math.hypot(z - 1.58, y - 0.37), Math.hypot(z + 1.63, y - 0.37)) <
      0.43;
  let name;
  if (c[1] < 0.15 && c[0] > 0.5) name = "lamp_rear";
  else if (Math.abs(c[0] - 0.3294) < 0.005) name = "body_paint";
  else if (Math.abs(c[0] - 0.502) < 0.005)
    name = nearWheel ? "wheel_m70_dark" : "alloy_satin";
  else if (c[0] < 0.15) {
    if (y > 1.03 && Math.abs(x) < 0.91 && z < 1.02 && z > -1.92)
      name = "glass_tinted";
    else name = nearWheel ? "rubber_tires" : "trim_black";
  } else if (y > 1.37 || (y > 1.3 && Math.abs(x) > 0.69)) name = "body_paint";
  else if (y > 0.48 && y < 1.43 && Math.abs(x) < 0.9 && z > -1.82 && z < 0.98) {
    name = z > 0.65 && y > 0.77 ? "dashboard" : "interior_shell";
  } else name = "alloy_satin";

  if (!groups.has(name))
    groups.set(name, { positions: [], normals: [], color: c });
  const g = groups.get(name);
  for (const v of vs) {
    g.positions.push(...v.p);
    g.normals.push(...v.n);
  }
}
paintedGeometry.dispose();
for (const n of oldNodes) n.dispose();
for (const m of oldMeshes) m.dispose();
const clearcoat = doc.createExtension(KHRMaterialsClearcoat);
const finishes = {
  body_paint: { color: [0.19, 0.215, 0.24, 1], metal: 0.36, rough: 0.5 },
  alloy_satin: { color: [0.48, 0.51, 0.54, 1], metal: 0.9, rough: 0.23 },
  wheel_m70_dark: { color: [0.027, 0.029, 0.034, 1], metal: 0.78, rough: 0.25 },
  trim_black: { color: [0.008, 0.01, 0.013, 1], metal: 0.25, rough: 0.28 },
  rubber_tires: { color: [0.008, 0.01, 0.012, 1], metal: 0, rough: 0.86 },
  glass_tinted: { color: [0.012, 0.022, 0.029, 0.58], metal: 0.1, rough: 0.12 },
  interior_shell: { color: [0.38, 0.3, 0.22, 1], metal: 0, rough: 0.82 },
  dashboard: { color: [0.021, 0.019, 0.018, 1], metal: 0.05, rough: 0.6 },
  lamp_rear: {
    color: [0.48, 0.003, 0.015, 1],
    metal: 0.1,
    rough: 0.2,
    emissive: [0.2, 0.001, 0.004],
  },
};
for (const [name, g] of groups) {
  const f = finishes[name];
  const material = doc
    .createMaterial(name)
    .setBaseColorFactor(f.color)
    .setMetallicFactor(f.metal)
    .setRoughnessFactor(f.rough)
    .setDoubleSided(true);
  if (f.emissive) material.setEmissiveFactor(f.emissive);
  if (name === "glass_tinted")
    material.setAlphaMode("BLEND").setDoubleSided(false);
  if (name === "body_paint")
    material.setExtension(
      "KHR_materials_clearcoat",
      clearcoat
        .createClearcoat()
        .setClearcoatFactor(0.28)
        .setClearcoatRoughnessFactor(0.4),
    );
  // Smooth source face normals only across a gentle crease, preserving sharp body seams.
  if (name === "body_paint") {
    const buckets = new Map();
    const keyAt = (i) =>
      g.positions
        .slice(i, i + 3)
        .map((v) => Math.round(v * 1000))
        .join(",");
    for (let i = 0; i < g.normals.length; i += 3) {
      const key = keyAt(i);
      if (!buckets.has(key)) buckets.set(key, []);
      buckets.get(key).push(g.normals.slice(i, i + 3));
    }
    const smooth = [];
    for (let i = 0; i < g.normals.length; i += 3) {
      const base = new Vector3().fromArray(g.normals, i),
        sum = new Vector3();
      for (const a of buckets.get(keyAt(i))) {
        const n = new Vector3().fromArray(a);
        if (n.dot(base) > 0.64) sum.add(n);
      }
      sum.normalize().toArray(smooth, i);
    }
    g.normals = smooth;
  }
  const p = doc.createPrimitive().setMaterial(material);
  for (const [semantic, data] of [
    ["POSITION", g.positions],
    ["NORMAL", g.normals],
  ])
    p.setAttribute(
      semantic,
      doc
        .createAccessor()
        .setType("VEC3")
        .setArray(new Float32Array(data))
        .setBuffer(buffer),
    );
  scene.addChild(
    doc
      .createNode("mesh_" + name)
      .setMesh(doc.createMesh("mesh_" + name).addPrimitive(p)),
  );
}
// Small, separately named author-built details. The source artist mesh is retained,
// while the lettering suggests the MY2024 M70 reference; neither is CAD.
const badgeMaterial = doc.createMaterial("badge_satin_metal")
  .setBaseColorFactor([0.09, 0.105, 0.12, 1])
  .setMetallicFactor(0.52).setRoughnessFactor(0.24).setDoubleSided(true);
function addDetail(name, geometry, material) {
  const g = geometry.index ? geometry.toNonIndexed() : geometry;
  const p = doc.createPrimitive().setMaterial(material);
  for (const semantic of ["POSITION", "NORMAL"]) {
    const a = g.getAttribute(semantic.toLowerCase());
    p.setAttribute(semantic, doc.createAccessor().setType("VEC3")
      .setArray(new Float32Array(a.array)).setBuffer(buffer));
  }
  scene.addChild(doc.createNode(name).setMesh(doc.createMesh(name).addPrimitive(p)));
  g.dispose();
  if (geometry !== g) geometry.dispose();
}
const font = new FontLoader().parse(JSON.parse(await fs.readFile(
  new URL("./node_modules/three/examples/fonts/helvetiker_bold.typeface.json", import.meta.url), "utf8")));
for (const [name, label, x, y, z, size] of [
  ["badge_rear_i7", "i7", 0.60, 0.855, -2.52, 0.09],
  ["badge_rear_m70_xdrive", "M70 xDrive", -0.56, 0.855, -2.525, 0.058],
]) {
  const g = new TextGeometry(label, { font, size, depth: 0.004, curveSegments: 3,
    bevelEnabled: true, bevelThickness: 0.0006, bevelSize: 0.0006, bevelSegments: 1 });
  g.computeBoundingBox();
  // Centre each label locally; a half turn makes its face readable from behind.
  const width = g.boundingBox.max.x - g.boundingBox.min.x;
  g.translate(-width / 2, -size / 2, 0);
  g.rotateY(Math.PI);
  g.translate(x, y, z);
  // The G70 source trunk curves rearward towards its centre. Bend the tiny
  // lettering onto that local contour so neither end disappears into paint.
  const position = g.getAttribute("position");
  for (let i = 0; i < position.count; i++)
    position.setZ(i, -2.68 + 0.17 * Math.abs(position.getX(i)) + position.getZ(i) - z);
  position.needsUpdate = true;
  g.computeVertexNormals();
  addDetail(name, g, badgeMaterial);
}
await doc.transform(
  dedup(),
  weld(),
  prune({ keepLeaves: true }),
  compressDraco({
    method: "edgebreaker",
    quantizePosition: 16,
    quantizeNormal: 12,
  }),
);
for (const [id, z] of Object.entries(manifest.zones))
  scene.addChild(
    doc
      .createNode(z.anchor)
      .setTranslation(z.position)
      .setExtras({ topicZone: id, approximation: z.approximation }),
  );
root.getAsset().copyright =
  "2023 BMW I7 G70 by Nazh Design ✔ (Sketchfab), CC BY 4.0. Modified: optimized, PBR finishes, M70-inspired details, metre coordinates and anchors. Independent artist model; MY2024 US M70 design reference.";
await io.write(output, doc);
const bytes = await fs.readFile(output);
manifest.files.model = {
  path: path.basename(output),
  bytes: bytes.length,
  triangles: root
    .listMeshes()
    .flatMap((m) => m.listPrimitives())
    .reduce((s, p) => s + p.getIndices().getCount() / 3, 0),
  sha256: sha(bytes),
};
manifest.rendering.boundsMetres = getBounds(scene);
await fs.writeFile(manifestPath, JSON.stringify(manifest, null, 2) + "\n");
console.log(
  JSON.stringify(
    {
      duplicateTriangles,
      coveredBackingTriangles,
      ...manifest.files.model,
      bounds: manifest.rendering.boundsMetres,
    },
    null,
    2,
  ),
);
