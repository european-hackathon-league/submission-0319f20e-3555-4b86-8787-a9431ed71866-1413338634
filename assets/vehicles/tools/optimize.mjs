// Use only on an authorized local download. Writes an intermediate outside Git.
// Orientation, anchors, final materials and manifest follow visual inspection.
import { NodeIO } from "@gltf-transform/core";
import { ALL_EXTENSIONS } from "@gltf-transform/extensions";
import {
  dedup,
  prune,
  weld,
  simplify,
  textureCompress,
  draco as compressDraco,
} from "@gltf-transform/functions";
import { MeshoptDecoder, MeshoptSimplifier } from "meshoptimizer";
import draco from "draco3dgltf";
import sharp from "sharp";
import path from "node:path";
import fs from "node:fs/promises";
const [source, target] = process.argv.slice(2);
if (!source || !target)
  throw Error(
    "Usage: node optimize.mjs /private/source.gltf /private/intermediate.glb",
  );
const input = path.resolve(source),
  output = path.resolve(target);
if (input === output) throw Error("Never overwrite the raw source.");
if (!output.endsWith(".glb")) throw Error("Output must be GLB.");
try {
  await fs.access(output);
  throw Error("Output already exists; choose a new intermediate name.");
} catch (e) {
  if (e.code !== "ENOENT") throw e;
}
const ratio = Number(process.env.ASSET_KEEP_RATIO || ".25");
if (!Number.isFinite(ratio) || ratio <= 0 || ratio > 1)
  throw Error("ASSET_KEEP_RATIO must be (0, 1].");
await MeshoptSimplifier.ready;
await MeshoptDecoder.ready;
const io = new NodeIO()
  .registerExtensions(ALL_EXTENSIONS)
  .registerDependencies({
    "draco3d.decoder": await draco.createDecoderModule(),
    "draco3d.encoder": await draco.createEncoderModule(),
    "meshopt.decoder": MeshoptDecoder,
  });
const document = await io.read(input);
const count = () =>
  document
    .getRoot()
    .listMeshes()
    .flatMap((m) => m.listPrimitives())
    .reduce(
      (n, p) =>
        n +
        (p.getMode() === 4
          ? (p.getIndices()?.getCount() ||
              p.getAttribute("POSITION").getCount()) / 3
          : 0),
      0,
    );
const before = count();
await document.transform(
  dedup(),
  weld(),
  simplify({
    simplifier: MeshoptSimplifier,
    ratio,
    error: 0.0005,
    lockBorder: true,
  }),
  prune({ keepLeaves: true }),
  textureCompress({
    encoder: sharp,
    targetFormat: "webp",
    resize: [2048, 2048],
    quality: 90,
    slots: /^(?!normalTexture).*$/,
  }),
  textureCompress({
    encoder: sharp,
    targetFormat: "webp",
    resize: [2048, 2048],
    lossless: true,
    slots: /normalTexture/,
  }),
  compressDraco({ method: "edgebreaker" }),
);
await io.write(output, document);
console.log(
  JSON.stringify(
    {
      source: path.basename(input),
      output,
      trianglesBefore: before,
      trianglesAfter: count(),
      bytes: (await fs.stat(output)).size,
      note: "Intermediate only; requires visual comparison, anchors, licence and manifest before delivery.",
    },
    null,
    2,
  ),
);
