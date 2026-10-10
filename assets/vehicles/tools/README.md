# Asset authoring and acceptance tools

This is a standalone developer viewer, not Troy's frontend. It reads only the shipped asset and a loopback BMW API, and has no bundled customer records. Node 22+ and Python 3 are required; install pinned dependencies with `pnpm install --frozen-lockfile` in this directory.

From the repository root:

```sh
python3 assets/vehicles/tools/serve.py --api http://127.0.0.1:18000
# Open http://127.0.0.1:18460/tools/viewer.html
node assets/vehicles/tools/validate.mjs assets/vehicles/g60-us
```

The viewer includes all five camera presets, material isolation, paint override, a 44 px charging target, approximate zone toggle, API topic filtering, source/score/decision/audit trace, attribution, 2D fallback and poster export. The local server only binds loopback and proxies GET requests for requirement and audit routes. Existing access logging may write API audit events. Never start or stop another worker's API stack for this tool. Override `--api` to the intended stack.

Rebuild only from the authorized **Sketchfab converted GLB download** stored outside Git. The source hash must match the manifest; the script rejects other input. The original downloaded GLB is also retained privately for provenance. The build removes coincident/covered back faces, normalizes coordinates, rebuilds normals and materials, simplifies protected mesh borders, compresses with Draco, embeds anchors and updates the size/hash/triangle metadata. It does not extract any website viewer resource.

```sh
node --max-old-space-size=6144 assets/vehicles/tools/build.mjs \
  /private/path/sketchfab-converted.glb assets/vehicles/g60-us/i5-m60.glb
node assets/vehicles/tools/inspect.mjs assets/vehicles/g60-us/i5-m60.glb
```

Re-render the poster and repeat browser acceptance after changing geometry, lighting or materials. Set manifest status to `review` while making changes, and only set it to `ready` after acceptance. `optimize.mjs` is an intermediate source-inspection utility; it is not the final G60 build (the original needs backing-face cleanup before simplification). Keep intermediates and all original downloads outside Git. The Khronos validator cannot inspect compressed Draco internals, so independently decoding the GLB and opening it in the browser are required alongside `validate.mjs`.

The poster is generated with the viewer's **Save poster** control from the actual GLB, then encoded as WebP. No screenshot of BMW's site is used. Browser performance numbers are local warm HTTP/decode measurements, not a mobile/network SLA.
