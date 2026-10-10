// Artifact-contract verification, independently reading the exported GLB.
import fs from "node:fs/promises";
import path from "node:path";
import crypto from "node:crypto";
import assert from "node:assert/strict";
import validator from "gltf-validator";
import { NodeIO } from "@gltf-transform/core";
import { ALL_EXTENSIONS } from "@gltf-transform/extensions";
import draco from "draco3dgltf";
const folder = path.resolve(process.argv[2] || "../g60-us");
const m = JSON.parse(
  await fs.readFile(path.join(folder, "manifest.json"), "utf8"),
);
assert.equal(
  m.status,
  "ready",
  "Only a fully checked asset may be marked ready",
);
const bytes = await fs.readFile(path.join(folder, m.files.model.path));
assert.equal(
  crypto.createHash("sha256").update(bytes).digest("hex"),
  m.files.model.sha256,
);
assert.equal(bytes.byteLength, m.files.model.bytes);
assert(
  bytes.byteLength < 10_000_000,
  "Asset exceeds preferred 10 MB handoff target",
);
assert.equal(bytes.toString("ascii", 0, 4), "glTF");
assert.equal(bytes.readUInt32LE(4), 2);
assert.equal(bytes.readUInt32LE(8), bytes.byteLength);
const data = JSON.parse(
  bytes.toString("utf8", 20, 20 + bytes.readUInt32LE(12)).trim(),
);
assert(!data.buffers.some((b) => b.uri), "GLB must be self-contained");
assert(
  !(data.images || []).some((i) => i.uri),
  "No external texture dependency",
);
const triangleCount = (data.meshes || [])
  .flatMap((mesh) => mesh.primitives)
  .reduce(
    (sum, p) =>
      sum +
      ((p.mode ?? 4) === 4
        ? data.accessors[p.indices ?? p.attributes.POSITION].count / 3
        : 0),
    0,
  );
assert.equal(
  triangleCount,
  m.files.model.triangles,
  "Manifest triangle count differs from GLB",
);
const zones = [
  "charging",
  "battery_range",
  "seats_front",
  "rear_cabin",
  "cockpit",
  "infotainment",
  "acoustics",
  "assistance",
  "chassis",
  "cargo",
  "exterior",
];
const expectedTopics = [
  "charging",
  "range",
  "comfort",
  "comfort",
  "controls",
  "connectivity",
  "quietness",
  "driver-assistance",
  "driving-experience",
  "access-storage",
  "design",
];
const nodeNames = (data.nodes || []).map((n) => n.name);
for (let i = 0; i < zones.length; i++) {
  let id = zones[i],
    z = m.zones[id];
  assert(z, `Missing ${id}`);
  assert.equal(nodeNames.filter((n) => n === z.anchor).length, 1);
  let node = data.nodes.find((n) => n.name === z.anchor);
  assert.deepEqual(
    node.translation,
    z.position,
    `Manifest differs from GLB: ${id}`,
  );
  assert(z.position.every(Number.isFinite));
  assert(z.topics.includes(expectedTopics[i]));
  assert(m.cameras[z.camera]);
}
assert(
  m.zones.charging.position[0] < 0,
  "Right rear port should be negative X",
);
assert(
  m.zones.charging.position[2] < 0,
  "Right rear port should be negative Z",
);
for (let preset of [
  "default_orbit",
  "charging_port",
  "cockpit",
  "seats",
  "rear_cabin",
]) {
  let c = m.cameras[preset];
  assert(c && c.position.length === 3 && c.target.length === 3);
  assert([...c.position, ...c.target, c.fov].every(Number.isFinite));
}
assert.equal(m.vehicle.code, "G60");
assert.equal(m.vehicle.market, "US");
assert(m.licence.attribution && m.source.url && m.source.creator);
for (let file of [m.licence.file, m.files.poster.path, m.files.fallback.path])
  assert((await fs.stat(path.join(folder, file))).size > 0);
const result = await validator.validateBytes(bytes, { maxIssues: 100 });
console.log(
  JSON.stringify(
    {
      bytes: bytes.byteLength,
      sha256: m.files.model.sha256,
      anchors: zones.length,
      validator: result.issues,
    },
    null,
    2,
  ),
);
assert.equal(
  result.issues.numErrors,
  0,
  "Khronos glTF validator reported errors",
);

// The validator cannot inspect compressed Draco internals. Decode independently
// and validate the expanded geometry as well as the original artifact.
const io = new NodeIO()
  .registerExtensions(ALL_EXTENSIONS)
  .registerDependencies({
    "draco3d.decoder": await draco.createDecoderModule(),
  });
const decoded = await io.readBinary(bytes);
for (const extension of decoded.getRoot().listExtensionsUsed()) {
  if (extension.extensionName === "KHR_draco_mesh_compression")
    extension.dispose();
}
const expanded = await validator.validateBytes(await io.writeBinary(decoded), {
  maxIssues: 100,
});
console.log(JSON.stringify({ decodedValidator: expanded.issues }, null, 2));
assert.equal(
  expanded.issues.numErrors,
  0,
  "Decoded geometry failed validation",
);
