# G60 / US i5 M60 asset handoff

This is Nazh Design's licensed BMW i5 M60 artist model, optimized for browser use. It is an **exterior model**. Cabin, battery and cargo anchors represent approximate topic zones; no interior walkthrough is supported. The creator calls it “2023”; **US MY2024** is our separately sourced reference scope, not a certification of US trim, equipment or geometry. Source panel faceting and simplified light internals remain.

## Files and mounting

Copy this entire `assets/vehicles/g60-us/` directory into the frontend's static `models/g60-us/` directory. The suggested public URLs are `/models/g60-us/i5-m60.glb` and `/models/g60-us/manifest.json`; Troy can mount elsewhere and resolve all manifest file paths against that manifest URL. Keep `LICENSE.txt` beside the GLB and display the linked attribution below. No frontend files have been implemented or changed. `../index.json` is a multi-vehicle catalog; add another manifest later without changing the G60 contract.

- `i5-m60.glb`: self-contained glTF 2.0, Draco compressed; size, SHA-256 and triangle count are in `manifest.json`.
- `manifest.json`: vehicle provenance, licence, material names, 11 anchors, 5 camera presets, API topic mapping and limitations.
- `poster.webp`: locally rendered from this GLB; same model attribution applies.
- `schematic.svg`: original team drawing; accessible 2D fallback, front up. It is not official BMW imagery.
- `official-facts.json`: cited product context with per-fact market and model year; never customer evidence.
- `LICENSE.txt`: licence and modification notice.

## Loading in Three.js

Use the frontend's Three.js version consistently for core, addons and Draco decoder. Copy the decoder files from `three/examples/jsm/libs/draco/gltf/` to a static `/draco/` directory. The acceptance viewer includes a working local example, with no CDN or BMW assets fetched at runtime.

```js
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { DRACOLoader } from "three/addons/loaders/DRACOLoader.js";

const manifestURL = new URL("/models/g60-us/manifest.json", location.origin);
const manifest = await fetch(manifestURL).then((r) => r.json());
if (manifest.status !== "ready") throw new Error("Vehicle asset not ready");
const draco = new DRACOLoader().setDecoderPath("/draco/");
const loader = new GLTFLoader().setDRACOLoader(draco);
const gltf = await loader.loadAsync(
  new URL(manifest.files.model.path, manifestURL).href,
);
scene.add(gltf.scene);
gltf.scene.updateMatrixWorld(true);
const charging = gltf.scene.getObjectByName("anchor_charging");
// charging.getWorldPosition(new THREE.Vector3()) gives the hotspot position.
```

Coordinates are **right-handed, metres, +Y up, +Z forward, +X vehicle left**. Origin is at ground level in the center of the exterior bounding box, including mirrors. BMW's MY2024 US FAQ places the charge flap on the **right rear**: negative X and negative Z. This corrects the old plan's left-rear assumption. Anchors are empty scene-root nodes named `anchor_<zone>`; their translations exactly match `manifest.zones[zone].position`.

Named render meshes are `mesh_body_paint`, `mesh_alloy_satin`, `mesh_trim_black`, `mesh_rubber_tires`, `mesh_glass_opaque`, `mesh_lamp_front`, `mesh_lamp_rear`, `mesh_badge_blue` and `mesh_plate_white`. These are material groups, not selectable mechanical assemblies. Do not infer seats or battery geometry from mesh names. Stable interaction identity is the anchor name.

Override only material `body_paint`. Clone it before changing a vehicle instance's color. Three.js `material.color.set('#...')` accepts sRGB colors; the manifest's default RGB is **linear**. Do not recolor badges, glass, tires or lamps. The supplied finish is authored satin blue, not a named BMW paint option. Use a neutral studio environment map and soft lighting; the diagnostic viewer's generated studio setup is a reference. Cap DPR at 2 and render on interaction. Postprocessing is not required.

Use camera positions/targets/FOV/near/far from the manifest. Cockpit, seats and rear-cabin presets deliberately frame the corresponding **window/exterior region**. Keep the approximation label visible; never move the camera inside this shell or advertise an interior cutaway. Render hotspots at least 44×44 CSS pixels, with an accessible zone selector. Hide approximate internal pins by default; selection can reveal them. Use poster then schematic on WebGL/load failure.

## Live requirements and trace

The GLB and manifest contain **no customer evidence, scores or decisions**. On charging click, fetch `/requirements?vehicle=G60&market=US&limit=1000&offset=0`, paginate to `total`, and filter `item.topic === 'charging'`. The current API has no topic query parameter. Every other zone uses its existing topic(s) from the manifest. Do not filter requirements by the geometry reference model year unless the data contract supplies a year.

Use `item.id` in API calls and `item.key` as the display identifier. Route selection into Troy's existing requirement detail and trace view. `/requirements/{id}/trace` supplies the requirement/version, score, source metadata and located original evidence, PM decisions and findings. Paginate `evidence` with `limit`/`offset`; `/audit?entity_id={id}` supplies audit history using `next_after`. Stop at an empty/short page or a cursor that does not advance: this API returns the previous cursor even when no rows remain. Do not invent `/history` or replace unavailable evidence with vehicle specifications. Display errors/empty states honestly. The acceptance tool exercises this flow read-only; the API's normal access-audit logging still occurs.

Keep `official-facts.json` in a separate “Official vehicle context” panel with source URL, market and model year on every fact. The current BMW US product page is MY2027; do not reuse its specifications for MY2024. The acceptance run used an existing **synthetic** G60/US API fixture and displayed that label. No synthetic record is shipped in this package, and this is not verification of real customer feedback ingestion.

## Attribution for footer and README

[2023 BMW I5 M60](https://sketchfab.com/3d-models/2023-bmw-i5-m60-207fd872d28b4cafa7fefe061ae98e26) by [Nazh Design ✔](https://sketchfab.com/NazhDesign), [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Optimized geometry, materials and anchors modified.

Keep these links and a visible modification notice in the app footer. Include `LICENSE.txt` in any distribution. BMW trademarks remain with their owners. This is an independent artist model; no BMW endorsement is claimed. No BMW website imagery, configurator GLB or hidden textures were copied. Git/browser handoff relies on the creator's offered CC BY licence; no organizer asset permission has been received.

## Acceptance

See `../verification.json` for measured browser load/performance, anchor and trace checks. The model was loaded locally on this laptop; this is not a claim that Troy has loaded it in his frontend. He can verify after pulling with the standalone acceptance tool in `../tools/`. Raw 28 MB / 43 MB downloads stay outside Git.
