# Vehicle asset tools

These utilities prepare an **authorized local download**. They do not fetch hidden viewer files. Install with Node.js 22+ and `pnpm install --frozen-lockfile` from this directory. Sharp's prebuilt platform package was verified on the local Apple Silicon laptop. Newer pnpm may require explicit approval of Sharp's installation script if the prebuilt binary is unavailable.

```sh
node inspect.mjs /absolute/private/download/scene.gltf > /absolute/private/inspection.json
node optimize.mjs /absolute/private/download/scene.gltf /absolute/private/intermediate.glb
node validate.mjs ../g60-us
```

Keep both raw downloads and intermediate exports outside Git. The optimizer refuses to overwrite the source or an existing output. It retains named leaves, caps textures at 2048 pixels, uses WebP (lossless for normal maps), conservatively simplifies within a 0.05% geometric error bound, and writes Draco geometry. It preserves source scene structure; it does not pretend to know orientation, paint materials, interior availability or anchor positions before inspecting the model.

Set `ASSET_KEEP_RATIO=0.5` to preserve more geometry if visible details degrade. Size alone is not acceptance. Inspect lights, grille, rims, window edges and interior before approving the output. A heavily partitioned source may remain above the target size; adjust only after reviewing the relevant meshes.

A compressed final GLB needs Three.js `DRACOLoader` with its matching decoder files served from the app, or the equivalent `useGLTF` decoder configuration. WebP textures require modern browser support. Do not claim the model is delivered until the final model is present, the manifest is marked ready, validation passes and a browser opens the actual GLB.

`validate.mjs` checks the GLB container, Khronos validation, SHA-256, size, self-contained resources, all eleven named anchors, topic mappings, camera presets, vehicle scope and companion files. `inspect.mjs` reports mesh/material names, world bounds and texture sizes to support manual calibration. These tools do not implement Troy's frontend.
