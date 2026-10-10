// Build only from the creator-authorized Sketchfab GLB download kept outside Git.
import fs from "node:fs/promises";
import path from "node:path";
import crypto from "node:crypto";
import { NodeIO } from "@gltf-transform/core";
import {
  ALL_EXTENSIONS,
  KHRMaterialsClearcoat,
} from "@gltf-transform/extensions";
import {
  dedup,
  weld,
  simplify,
  prune,
  draco as compressDraco,
  getBounds,
} from "@gltf-transform/functions";
import { MeshoptSimplifier } from "meshoptimizer";
import draco from "draco3dgltf";
import { MeshBVH } from "three-mesh-bvh";
import {
  Matrix4,
  Matrix3,
  Vector3,
  BufferGeometry,
  BufferAttribute,
} from "three";
const [input, output] = process.argv.slice(2);
if (!input || !output)
  throw Error("Usage: node build.mjs private-converted.glb output.glb");
const manifestPath = path.join(path.dirname(output), "manifest.json"),
  manifest = JSON.parse(await fs.readFile(manifestPath, "utf8"));
if (
  crypto
    .createHash("sha256")
    .update(await fs.readFile(input))
    .digest("hex") !== manifest.source.buildInputSha256
)
  throw Error("Input differs from licensed source recorded in manifest.");
const io = new NodeIO()
  .registerExtensions(ALL_EXTENSIONS)
  .registerDependencies({
    "draco3d.decoder": await draco.createDecoderModule(),
    "draco3d.encoder": await draco.createEncoderModule(),
  });
const doc = await io.read(input),
  root = doc.getRoot(),
  scene = root.listScenes()[0],
  bounds = getBounds(scene),
  scale = 5.05968 / (bounds.max[0] - bounds.min[0]),
  cx = (bounds.min[0] + bounds.max[0]) / 2,
  cz = (bounds.min[2] + bounds.max[2]) / 2;
const oldMeshes = root.listMeshes(),
  oldNodes = root.listNodes(),
  buffer = root.listBuffers()[0],
  triangles = new Map();
let sourceTriangles = 0,
  duplicateTriangles = 0;
// The download contains coincident front/back faces with different materials.
// Resolve those BEFORE simplification; separate reduction caused surface flicker.
for (const node of oldNodes) {
  const mesh = node.getMesh();
  if (!mesh) continue;
  const mi = oldMeshes.indexOf(mesh),
    matrix = new Matrix4().fromArray(node.getWorldMatrix()),
    normalMatrix = new Matrix3().getNormalMatrix(matrix);
  for (const p of mesh.listPrimitives()) {
    const pos = p.getAttribute("POSITION"),
      normal = p.getAttribute("NORMAL"),
      color = p.getAttribute("COLOR_0"),
      indices = p.getIndices();
    for (let t = 0; t < (indices?.getCount() ?? pos.getCount()); t += 3) {
      sourceTriangles++;
      let vertices = [],
        keys = [];
      for (let k = 0; k < 3; k++) {
        let ix = indices ? indices.getScalar(t + k) : t + k,
          v = new Vector3()
            .fromArray(pos.getElement(ix, []))
            .applyMatrix4(matrix),
          n = new Vector3()
            .fromArray(normal.getElement(ix, []))
            .applyMatrix3(normalMatrix)
            .normalize();
        vertices.push({
          p: [
            (v.z - cz) * scale,
            (v.y - bounds.min[1]) * scale,
            (cx - v.x) * scale,
          ],
          n: [n.z, n.y, -n.x],
          c: color ? color.getElement(ix, []) : null,
        });
        keys.push([v.x, v.y, v.z].map((x) => Math.round(x * 1e5)).join(","));
      }
      const key = keys.sort().join("|"),
        prev = triangles.get(key);
      if (prev) duplicateTriangles++;
      if (!prev || (!prev.colored && color))
        triangles.set(key, { vertices, part: mi, colored: !!color });
    }
  }
}
const coloredPositions = [];
for (const tri of triangles.values())
  if (tri.colored) for (const v of tri.vertices) coloredPositions.push(...v.p);
const coloredGeometry = new BufferGeometry().setAttribute(
    "position",
    new BufferAttribute(new Float32Array(coloredPositions), 3),
  ),
  bvh = new MeshBVH(coloredGeometry);
let coveredBackfaces = 0;
for (const [key, tri] of triangles) {
  if (tri.colored) continue;
  const center = new Vector3();
  for (const v of tri.vertices) center.add(new Vector3().fromArray(v.p));
  center.multiplyScalar(1 / 3);
  const hit = bvh.closestPointToPoint(center, {}, 0, 0.000025);
  if (hit) {
    triangles.delete(key);
    coveredBackfaces++;
  }
}
coloredGeometry.dispose();
const clearcoat = doc.createExtension(KHRMaterialsClearcoat),
  materials = new Map();
function mat(name, color, metal, rough, emissive) {
  let m = doc
    .createMaterial(name)
    .setBaseColorFactor([...color, 1])
    .setMetallicFactor(metal)
    .setRoughnessFactor(rough)
    .setDoubleSided(true);
  if (emissive) m.setEmissiveFactor(emissive);
  materials.set(name, m);
  return m;
}
mat("body_paint", [0.024, 0.052, 0.083], 0.16, 0.67).setExtension(
  "KHR_materials_clearcoat",
  clearcoat
    .createClearcoat()
    .setClearcoatFactor(0.18)
    .setClearcoatRoughnessFactor(0.5),
);
mat("alloy_satin", [0.5, 0.53, 0.56], 0.86, 0.26).setDoubleSided(false);
mat("trim_black", [0.009, 0.011, 0.014], 0.35, 0.25);
mat("rubber_tires", [0.012, 0.014, 0.016], 0.05, 0.88);
mat("glass_opaque", [0.009, 0.014, 0.022], 0.32, 0.13);
mat("lamp_front", [0.63, 0.78, 0.9], 0.12, 0.18, [0.24, 0.36, 0.48]);
mat("lamp_rear", [0.42, 0.002, 0.012], 0.1, 0.2, [0.25, 0.002, 0.007]);
mat("badge_blue", [0.07, 0.18, 0.6], 0.25, 0.3);
mat("plate_white", [0.8, 0.82, 0.85], 0, 0.6);
const groups = new Map();
for (const tri of triangles.values()) {
  const center = tri.vertices.reduce(
    (a, v) => a.map((n, i) => n + v.p[i] / 3),
    [0, 0, 0],
  );
  const c = tri.vertices[0].c;
  let name = "alloy_satin";
  if (c) {
    if (c[0] > 0.26 && c[0] < 0.29 && Math.abs(c[0] - c[1]) < 0.01)
      name = "body_paint";
    else if (c[0] > 0.45 && c[1] < 0.02)
      name = center[2] > 0 ? "lamp_front" : "lamp_rear";
    else if (c[2] > 0.7 && c[0] < 0.3) name = "badge_blue";
    else if (c[0] > 0.95) name = "plate_white";
    else if ([5, 7, 35].includes(tri.part)) name = "rubber_tires";
    else if (center[1] > 1.02 && Math.abs(center[0]) < 0.85 && center[2] < 0.9)
      name = "glass_opaque";
    else name = "trim_black";
  }
  if (
    !c &&
    center[1] > 1.12 &&
    Math.abs(center[0]) < 0.76 &&
    center[2] < -0.85 &&
    center[2] > -1.95
  )
    name = "glass_opaque";
  if (
    !c &&
    center[2] > 1.75 &&
    center[1] > 0.64 &&
    center[1] < 0.88 &&
    Math.abs(center[0]) > 0.51
  )
    name = "lamp_front";
  let group = groups.get(name);
  if (!group) {
    group = { positions: [], normals: [] };
    groups.set(name, group);
  }
  for (const v of tri.vertices) {
    group.positions.push(...v.p);
    group.normals.push(...v.n);
  }
}
for (const n of oldNodes) n.dispose();
for (const m of oldMeshes) m.dispose();
for (const [name, g] of groups) {
  // Recompute geometric normals, then smooth at matching positions within a 45-degree crease.
  for (let i = 0; i < g.positions.length; i += 9) {
    const a = new Vector3().fromArray(g.positions, i),
      b = new Vector3().fromArray(g.positions, i + 3),
      c = new Vector3().fromArray(g.positions, i + 6),
      n = b.sub(a).cross(c.sub(a)).normalize();
    for (let k = 0; k < 3; k++) n.toArray(g.normals, i + k * 3);
  }

  const normalMap = new Map(),
    keyAt = (i) =>
      g.positions
        .slice(i, i + 3)
        .map((n) => Math.round(n * (name === "body_paint" ? 100 : 100000)))
        .join(",");
  for (let i = 0; i < g.positions.length; i += 3) {
    const key = keyAt(i);
    if (!normalMap.has(key)) normalMap.set(key, []);
    normalMap.get(key).push(g.normals.slice(i, i + 3));
  }
  const smooth = new Float32Array(g.normals.length);
  for (let i = 0; i < g.positions.length; i += 3) {
    const base = new Vector3().fromArray(g.normals, i),
      sum = new Vector3();
    for (const a of normalMap.get(keyAt(i))) {
      const n = new Vector3().fromArray(a);
      if (n.dot(base) > (name === "body_paint" ? 0.5 : 0.7071)) sum.add(n);
    }
    sum.normalize().toArray(smooth, i);
  }
  const p = doc
    .createPrimitive()
    .setAttribute(
      "POSITION",
      doc
        .createAccessor()
        .setType("VEC3")
        .setArray(new Float32Array(g.positions))
        .setBuffer(buffer),
    )
    .setAttribute(
      "NORMAL",
      doc.createAccessor().setType("VEC3").setArray(smooth).setBuffer(buffer),
    )
    .setMaterial(materials.get(name));
  scene.addChild(
    doc
      .createNode("mesh_" + name)
      .setMesh(doc.createMesh("mesh_" + name).addPrimitive(p)),
  );
}
const original = {
  sourceTriangles,
  duplicateTriangles,
  coveredBackfaces,
  uniqueTriangles: triangles.size,
};
triangles.clear();
await MeshoptSimplifier.ready;
await doc.transform(
  dedup(),
  weld(),
  simplify({
    simplifier: MeshoptSimplifier,
    ratio: 0.85,
    error: 0.00001,
    lockBorder: true,
  }),
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
  "2023 BMW I5 M60 by Nazh Design ✔ (Sketchfab), CC BY 4.0. Modified: optimized topology, PBR finishes, metre coordinates and anchors. Independent artist model.";
await io.write(output, doc);
const bytes = await fs.readFile(output);
manifest.files.model = {
  path: path.basename(output),
  bytes: bytes.length,
  triangles: root
    .listMeshes()
    .flatMap((m) => m.listPrimitives())
    .reduce((s, p) => s + p.getIndices().getCount() / 3, 0),
  sha256: crypto.createHash("sha256").update(bytes).digest("hex"),
};
await fs.writeFile(manifestPath, JSON.stringify(manifest, null, 2) + "\n");
console.log(
  JSON.stringify(
    {
      ...original,
      bytes: (await fs.stat(output)).size,
      triangles: root
        .listMeshes()
        .flatMap((m) => m.listPrimitives())
        .reduce((s, p) => s + p.getIndices().getCount() / 3, 0),
    },
    null,
    2,
  ),
);
