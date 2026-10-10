# G70 / US i7 asset handoff

A second, independent artist model by Nazh Design, offered under CC BY 4.0. The geometry is titled **2023 BMW I7 G70**; **US MY2024 i7 M70 xDrive** is the separately sourced reference scope, not a certification of US trim. The simplified interior includes seats, steering wheel, dashboard, console and rear cabin. It is suitable for window views; close interior walkthroughs expose coarse source geometry. See `manifest.json` for exact byte size, triangles, SHA-256, provenance and limitations.

## Files and contract

Mount the complete `assets/vehicles/g70-us/` directory at `/models/g70-us/` (or another static prefix). Load `/models/g70-us/manifest.json`, then resolve each `files.*.path` relative to that manifest URL. The model is `i7-g70.glb`; it is self-contained and uses Draco. Keep `LICENSE.txt` beside it, `poster.webp` for loading, and `schematic.svg` for fallback. `official-facts.json` is cited vehicle context, never customer evidence. `verification.json` records the actual acceptance run.

The additive catalog entry is `g70-us-i7` in `assets/vehicles/index.json`. G60 remains the default and its GLB is unchanged. The schema and zone identifiers match G60. No `web/`, API, database, Compose, root dependency or shared planning file is changed. The viewer under `assets/vehicles/tools/` is a standalone acceptance utility; these changes do not implement Troy's platform or vehicle picker.

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

Units are metres, right-handed, **+Y up, +Z forward, +X vehicle left**. Ground origin is at the center of the exterior bounding box including mirrors. Uniform reference length is 5.38988 m, converted from BMW's US MY2024 M70 212.2 in specification; artist proportions may differ. Charging is the approximate right rear quarter-panel zone: negative X and Z. The source has no open socket. Do not infer installed equipment from any anchor.

All eleven empty nodes are at the scene root and named `anchor_<zone>`. Exact coordinates and topics are in `manifest.zones`: charging, battery_range, seats_front, rear_cabin, cockpit, infotainment, acoustics, assistance, chassis, cargo and exterior. Use these for interaction identity. A semantic zone is not a mechanical part. Battery, cargo, infotainment and acoustics remain approximations. The simplified seat/cockpit surfaces do not certify US steering layout, trim or option availability.

The render meshes use `mesh_<material>` names including `body_paint`, `wheel_m70_dark`, `alloy_satin`, `trim_black`, `rubber_tires`, `glass_tinted`, `interior_shell`, `dashboard` and `lamp_rear`. Author-built rear letters are `badge_rear_i7` and `badge_rear_m70_xdrive`. These are visual groups, not a certified parts list. Override **body_paint** for user-selected paint, cloning the material per instance first; leave badges, chrome and cabin materials alone. The supplied silver is an authored finish, not an official BMW paint code. Three.js `material.color.set('#...')` accepts sRGB; `paintDefaultLinearRGB` is linear. The optional clearcoat extension enhances the finish; neutral studio lighting and ACES tone mapping are recommended. No postprocessing is necessary.

Use all six manifest camera position/target/FOV/clip settings, including `rear_badges`. Cockpit, seats and rear-cabin presets frame the windows and show the simplified cabin. Display each camera's optional `note` and the selected zone's `approximation`. The i7 and M70 xDrive rear text is fitted to the artist trunk surface, with darkened wheel faces for M70 visual distinction. The source fascia, mirrors, side skirts and rear diffuser remain approximations; no roof/door cutaway or animation is supplied. Use a minimum 44×44 CSS pixel target and accessible zone selector. Internal topic pins can be hidden until selected. Cap DPR at 2 and render on interaction.

## Evidence binding

On charging click, fetch **`/requirements?vehicle=G70&market=US&limit=1000&offset=0`**, paginate to `total`, and filter `item.topic` against `zones.charging.topics`. Other zones use their manifest topic lists. Keep vehicle/market filtering explicit. If the API returns no G70 rows, show an empty state; **never substitute G60 evidence or official vehicle facts**. Geometry reference year is not an evidence filter.

When G70 data exists, pass `item.id` into the existing requirement/trace flow; display `item.key`. Read `/requirements/{id}/trace` for original source feedback, score, PM decisions and findings, then `/audit?entity_id={id}` for audit history. Paginate trace evidence with `limit`/`offset`. Stop audit pagination on an empty/short page or non-advancing `next_after`; the API may return the old cursor when no rows remain. Route into Troy's existing scoped trace UI when that route is supported. No new frontend route is promised here.

For window appearance, read `manifest.rendering.windowFinishes`: set `glass_tinted` material color from the selected `baseColorLinearRGB` (linear space), opacity, metalness and roughness; set `transparent` when opacity is below 1 and disable depth writing for transparent glass. The default is tinted; the untinted setting reveals the simplified artist cabin. Tint is a visual state, not a claim about BMW equipment or legal tint. The standalone viewer demonstrates the switch for both vehicles.

The existing test API returned **zero G70/US requirements** at acceptance. The charging click and empty state were verified; a G70 evidence/decision trace could not be demonstrated without G70 records. The existing G60 synthetic trace was separately rechecked after generalizing the acceptance utility. No customer evidence, scores or synthetic fixtures are shipped.

Official facts remain in a separate context panel, with URL, market and model year on every fact. US MY2024 M70 facts and design cues come from [BMW PressClub USA](https://www.press.bmwgroup.com/usa/article/detail/T0413219EN_US/the-bmw-i7-m70-xdrive?language=en_US). The current BMW US i7 product page describes a newer design and is excluded from this MY2024 reference package. No BMW web imagery or hidden configurator resources were copied.

## Attribution for footer and README

[2023 BMW I7 G70](https://sketchfab.com/3d-models/2023-bmw-i7-g70-07937cca69864dfe9f4b4ed235fc32f7) by [Nazh Design ✔](https://sketchfab.com/NazhDesign), [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Optimized and visually adapted toward US MY2024 i7 M70 xDrive; details are illustrative.

Keep this linked credit visible and include `LICENSE.txt` in distributions. The creator's offered CC licence permits the Git/browser handoff with attribution and modification notice. BMW marks remain with their owners; no BMW supply or endorsement is claimed. Raw original and converted downloads stay outside Git. Troy can load the package after pulling; we have not modified his checkout or claimed that he has already loaded it.
