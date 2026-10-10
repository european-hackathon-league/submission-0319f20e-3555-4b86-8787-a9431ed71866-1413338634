# G70 / US i7 asset handoff

A second, independent artist model by Nazh Design, offered under CC BY 4.0. The geometry is titled **2023 BMW I7 G70**; **US MY2023 i7 xDrive60** is the separately sourced reference scope, not a certification of US trim. The simplified interior includes seats, steering wheel, dashboard, console and rear cabin. It is suitable for window views; close interior walkthroughs expose coarse source geometry. See `manifest.json` for exact byte size, triangles, SHA-256, provenance and limitations.

## Files and contract

Mount the complete `assets/vehicles/g70-us/` directory at `/models/g70-us/` (or another static prefix). Load `/models/g70-us/manifest.json`, then resolve each `files.*.path` relative to that manifest URL. The model is `i7-g70.glb`; it is self-contained and uses Draco. Keep `LICENSE.txt` beside it, `poster.webp` for loading, and `schematic.svg` for fallback. `official-facts.json` is cited vehicle context, never customer evidence. `verification.json` records the actual acceptance run.

The additive catalog entry is `g70-us-i7` in `assets/vehicles/index.json`. G60 remains the default and its directory is unchanged. The schema and zone identifiers match G60. No `web/`, API, database, Compose, root dependency or shared planning file is changed. The viewer under `assets/vehicles/tools/` is a standalone acceptance utility; these changes do not implement Troy's platform or vehicle picker.

```js
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { DRACOLoader } from "three/addons/loaders/DRACOLoader.js";

const manifestURL = new URL("/models/g70-us/manifest.json", location.origin);
const manifest = await fetch(manifestURL).then((r) => r.json());
if (manifest.status !== "ready") throw new Error("Asset is not ready");
const loader = new GLTFLoader().setDRACOLoader(
  new DRACOLoader().setDecoderPath("/draco/"),
);
const { scene: vehicle } = await loader.loadAsync(
  new URL(manifest.files.model.path, manifestURL).href,
);
scene.add(vehicle);
vehicle.updateMatrixWorld(true);
const charging = vehicle.getObjectByName("anchor_charging");
// Use charging.getWorldPosition(new THREE.Vector3()) for the hotspot.
```

Serve the Draco decoder from the **same Three.js version** as the loader (copy `three/examples/jsm/libs/draco/gltf/`). No runtime source website or external texture request is required.

Units are metres, right-handed, **+Y up, +Z forward, +X vehicle left**. Ground origin is at the center of the exterior bounding box including mirrors. Uniform reference length is 5.38988 m, converted from BMW's US MY2023 212.2 in specification; artist proportions may differ. Charging is the approximate right rear quarter-panel zone: negative X and Z. The source has no open socket. Do not infer installed equipment from any anchor.

All eleven empty nodes are at the scene root and named `anchor_<zone>`. Exact coordinates and topics are in `manifest.zones`: charging, battery_range, seats_front, rear_cabin, cockpit, infotainment, acoustics, assistance, chassis, cargo and exterior. Use these for interaction identity. A semantic zone is not a mechanical part. Battery, cargo, infotainment and acoustics remain approximations. The simplified seat/cockpit surfaces do not certify US steering layout, trim or option availability.

Eight render meshes use `mesh_<material>` names: `body_paint`, `alloy_satin`, `trim_black`, `rubber_tires`, `glass_tinted`, `interior_shell`, `dashboard` and `lamp_rear`. These are material groups. Override only **body_paint**, cloning the material per instance first; leave glass, chrome and cabin materials alone. The supplied silver is an authored finish, not an official BMW paint code. Three.js `material.color.set('#...')` accepts sRGB; `paintDefaultLinearRGB` is linear. The optional clearcoat extension enhances the finish; neutral studio lighting and ACES tone mapping are recommended. No postprocessing is necessary.

Use all five manifest camera position/target/FOV/clip settings. Cockpit, seats and rear-cabin presets frame the windows and show the simplified cabin. Display each camera's optional `note` and the selected zone's `approximation`. No roof/door cutaway or animation is supplied. Use a minimum 44×44 CSS pixel target and accessible zone selector. Internal topic pins can be hidden until selected. Cap DPR at 2 and render on interaction.

## Evidence binding

On charging click, fetch **`/requirements?vehicle=G70&market=US&limit=1000&offset=0`**, paginate to `total`, and filter `item.topic` against `zones.charging.topics`. Other zones use their manifest topic lists. Keep vehicle/market filtering explicit. If the API returns no G70 rows, show an empty state; **never substitute G60 evidence or official vehicle facts**. Geometry reference year is not an evidence filter.

When G70 data exists, pass `item.id` into the existing requirement/trace flow; display `item.key`. Read `/requirements/{id}/trace` for original source feedback, score, PM decisions and findings, then `/audit?entity_id={id}` for audit history. Paginate trace evidence with `limit`/`offset`. Stop audit pagination on an empty/short page or non-advancing `next_after`; the API may return the old cursor when no rows remain. Route into Troy's existing scoped trace UI when that route is supported. No new frontend route is promised here.

The existing test API returned **zero G70/US requirements** at acceptance. The charging click and empty state were verified; a G70 evidence/decision trace could not be demonstrated without G70 records. The existing G60 synthetic trace was separately rechecked after generalizing the acceptance utility. No customer evidence, scores or synthetic fixtures are shipped.

Official facts remain in a separate context panel, with URL, market and model year on every fact. The current BMW US i7 product page is MY2027 and describes a newer design; its specs are deliberately excluded from this MY2023 reference package. No BMW web imagery or hidden configurator resources were copied.

## Attribution for footer and README

[2023 BMW I7 G70](https://sketchfab.com/3d-models/2023-bmw-i7-g70-07937cca69864dfe9f4b4ed235fc32f7) by [Nazh Design ✔](https://sketchfab.com/NazhDesign), [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Optimized geometry, materials and anchors modified.

Keep this linked credit visible and include `LICENSE.txt` in distributions. The creator's offered CC licence permits the Git/browser handoff with attribution and modification notice. BMW marks remain with their owners; no BMW supply or endorsement is claimed. Raw original and converted downloads stay outside Git. Troy can load the package after pulling; we have not modified his checkout or claimed that he has already loaded it.
