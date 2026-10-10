// Read an authorized source download; never extracts geometry from a web viewer.
import { NodeIO } from "@gltf-transform/core";
import { ALL_EXTENSIONS } from "@gltf-transform/extensions";
import draco from "draco3dgltf";
import { MeshoptDecoder } from "meshoptimizer";
import { getBounds } from "@gltf-transform/functions";
import path from "node:path";
const source = process.argv[2];
if (!source)
  throw Error("Usage: node inspect.mjs /absolute/private/source.gltf");
const io = new NodeIO()
  .registerExtensions(ALL_EXTENSIONS)
  .registerDependencies({
    "draco3d.decoder": await draco.createDecoderModule(),
    "meshopt.decoder": MeshoptDecoder,
  });
const document = await io.read(path.resolve(source)),
  root = document.getRoot();
const summary = {
  source: path.basename(source),
  asset: document.getRoot().getAsset(),
  scenes: root
    .listScenes()
    .map((s) => ({ name: s.getName(), bounds: getBounds(s) })),
  triangles: root
    .listMeshes()
    .flatMap((m) => m.listPrimitives())
    .reduce(
      (sum, p) =>
        sum +
        (p.getMode() === 4
          ? (p.getIndices()?.getCount() ||
              p.getAttribute("POSITION").getCount()) / 3
          : 0),
      0,
    ),
  materials: root
    .listMaterials()
    .map((m) => ({
      name: m.getName(),
      color: m.getBaseColorFactor(),
      metal: m.getMetallicFactor(),
      roughness: m.getRoughnessFactor(),
      alpha: m.getAlphaMode(),
    })),
  textures: root
    .listTextures()
    .map((t) => ({
      name: t.getName(),
      mime: t.getMimeType(),
      bytes: t.getImage()?.byteLength,
      size: t.getSize(),
    })),
  nodes: root
    .listNodes()
    .filter((n) => n.getMesh())
    .map((n) => ({
      name: n.getName(),
      mesh: n.getMesh().getName(),
      position: n.getWorldTranslation(),
      bounds: getBounds(n),
      materials: n
        .getMesh()
        .listPrimitives()
        .map((p) => p.getMaterial()?.getName()),
    })),
};
console.log(JSON.stringify(summary, null, 2));
