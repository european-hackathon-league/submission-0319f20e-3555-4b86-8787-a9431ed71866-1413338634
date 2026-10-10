# 3D Requirement Twin: implementation plan

Status: **proposed**, 10 October 2026. Implements the twin described in the [PM workspace plan](pm-workspace-and-3d-twin.md#3d-requirement-twin-north-star). The goal is one demo moment: **click the charging port on an i5 M60 and land on the original public-charging feedback rows, the score, the PM decision and the audit event.**

## Model

| | Choice |
| --- | --- |
| Primary | [2023 BMW i5 M60 by Nazh Design](https://sketchfab.com/3d-models/2023-bmw-i5-m60-207fd872d28b4cafa7fefe061ae98e26), Sketchfab, free download, **CC Attribution**. 1.5 M triangles, about 795 k vertices. Matches the demo derivative (G60 i5 M60). |
| Backup | [RenderHub BMW i5 M60 G60 2024](https://www.renderhub.com/gallery/44139/bmw-i5-m60-g60-2024), paid, FBX recommended, 4K textures, interior lighting in the C4D version. |
| Last resort | A generic licensed sedan. The plan works with any car because hotspots are anchors, not meshes. |

Not verified yet: whether the Sketchfab model has a usable interior. Seats and cockpit need one. If it is exterior-only, use a semi-transparent body with pins inside, or switch to the backup.

Licence obligations (CC-BY): show "Model: 2023 BMW i5 M60 by Nazh Design, CC BY 4.0" in the twin footer and the README; note any changes made ("decimated and segmented"). Keep the raw download out of Git (`web/assets-src/` ignored); commit only the optimised GLB if its size allows, otherwise share it like the BMW inputs. Do not show the BMW logo in the UI unless BMW confirms; the badge on the car itself is fine.

## Asset pipeline

One-time, about 1 hour. Someone with a Sketchfab login downloads the glTF or FBX.

1. **Blender import** (glTF 2.0 or FBX). Apply transforms, scale to metres, car centred at the origin, front facing +Z, wheels on y = 0.
2. **Decimate** to 150–300 k triangles. Keep detail on the body silhouette, wheels, lights and dashboard; decimate hidden parts (underbody, engine bay) hard or delete them.
3. **Name the zone parts** so they can glow. Rename or join mesh objects to `zone_<id>` (for example `zone_seats_front`, `zone_charging`, `zone_cockpit`) where a clear part exists. Everything else stays as is.
4. **Place anchors.** Add an empty per zone named `anchor_<id>` at the pin position. Anchors are what the UI relies on; named meshes are a bonus.
5. **Materials.** Keep PBR materials and limit textures to 2K. Car paint can be overridden in code.
6. **Export GLB**, then optimise:

```bash
npx @gltf-transform/cli optimize i5.glb web/public/models/i5-m60.glb --compress draco --texture-compress webp --texture-size 2048
```

Target: **under 10 MB**, loads in under 3 seconds on the demo laptop.

## Zones and topic mapping

The analysis engine emits a fixed topic taxonomy (`TOPICS` in `server/analysis_engine.py`). The twin maps those topics to zones in one static file, `web/src/twin/zones.ts`, so no backend change is needed for the first version.

| Zone | Topics | Anchor / mesh | Camera preset |
| --- | --- | --- | --- |
| `charging` | `charging` | Charge-port flap (left rear wing) | Rear three-quarter, left |
| `battery_range` | `range` | Underfloor, centre (body semi-transparent) | Low side view |
| `seats_front` | `comfort` | Driver seat | Through the windscreen |
| `rear_cabin` | `comfort` | Rear bench | Through the rear side window |
| `acoustics` | `quietness` | Whole cabin (glow on the glasshouse) | Side view |
| `cockpit` | `controls` | Steering wheel, iDrive controller | Interior, driver's eye |
| `infotainment` | `connectivity` | Curved display | Interior, centre console |
| `assistance` | `driver-assistance` | Windscreen camera, front sensors | Front three-quarter |
| `chassis` | `driving-experience` | Wheels and suspension | Low front three-quarter |
| `cargo` | `access-storage` | Trunk and doors | Rear, lid open optional |
| `exterior` | `design` | Body | Default orbit |
| *(whole car)* | `overall-experience` | HUD badge, not a pin | — |

`comfort` maps to two zones; a requirement shows on both. When the mapping stabilises, move it into a `topic_zones` reference table in the database (database stream) so it is reviewable and auditable; the UI then reads it from the API.

## Data

All data comes from endpoints that already exist; the twin adds no write path.

| Need | Endpoint | Fields used |
| --- | --- | --- |
| Zone roll-ups | `GET /requirements?vehicle=G60&market=US` (`v_requirement_list`) | `key`, `topic`, `status`, `score_total`, `rank`, `evidence_grade`, `open_review_count`, `last_decision_*` |
| Market delta layer | `v_topic_markets` (through the API) | Topic score and status per market |
| Change layer | `GET /reviews`, `GET /updates` | Requirements touched by the latest batch |
| Click-through | `GET /requirements/{id}`, `/trace`, `GET /audit` | Detail drawer, trace, history (writes the access event) |

Roll-ups per zone are computed client-side: requirement count, top score, worst evidence grade, status mix, open reviews. Pure functions in `web/src/twin/rollup.ts`, unit-tested.

## Interactive stack

| Concern | Package | Use |
| --- | --- | --- |
| Renderer | `three`, `@react-three/fiber` | Three.js scene as React components |
| Helpers | `@react-three/drei` | `useGLTF` (+ Draco), `Environment` (studio HDRI), `ContactShadows`, `Html` pins, `CameraControls`, `Bounds`, `useProgress` loader |
| Effects | `@react-three/postprocessing` | `Selection` + `Outline` on the active zone, subtle `Bloom` on glowing parts |
| State | `zustand` | `selectedZone`, `activeLayer`, `hoveredZone`, `market`; shared by canvas, HUD and the register drawer |
| Data | TanStack Query | Same queries and cache as the rest of the workspace |
| UI over canvas | shadcn/ui | Glass HUD: layer switcher, legend, zone card, attribution |
| Dev only | `leva` | Tune anchor positions, camera presets and colours live |
| Asset tooling | Blender, `@gltf-transform/cli` | Decimate, name zones, compress |

Load the twin route with `next/dynamic` and `ssr: false`, so three.js never ships with the register.

## Components

```text
web/src/twin/
  TwinPage.tsx         route: canvas + HUD + drawer, reads scope from the URL
  TwinCanvas.tsx       <Canvas>, lights, environment, shadows, postprocessing
  CarModel.tsx         useGLTF, paint override, zone meshes → Selection, layer colours
  ZonePins.tsx         <Html> pin per anchor: count + colour, click/hover
  CameraRig.tsx        CameraControls, presets per zone, smooth fly-to, orbit limits
  Hud.tsx              layer switcher, legend, market toggle, attribution
  ZoneCard.tsx         selected zone: top requirements with score + grade, "open in register"
  zones.ts             zone ids, topics, anchor names, camera presets
  rollup.ts            requirements → per-zone aggregates and layer colours
  store.ts             zustand store
  Schematic2D.tsx      top-down SVG with the same zones: fallback and dashboard thumbnail
```

## Interaction

- **Hover** a pin or zone part: outline, tooltip with zone name, requirement count and top score.
- **Click**: camera flies to the zone preset; the zone card opens with its requirements; the URL becomes `/g60/us/twin?zone=charging`.
- **Requirement in the zone card**: opens the standard requirement drawer (trace, score, history, decision panel). The twin never has its own decision UI.
- **Layer switcher** (one at a time): Priority, Evidence strength, Status, Loves vs pains, Market delta, Change. Colours come from the workspace tokens; weak evidence pulses or shows hatched pins, matching the register.
- **Esc / reset**: back to the default orbit. Keyboard: `1–9` jump to zones, `L` cycles layers.
- **Reduced motion**: camera cuts instead of flights.

## Performance and fallback

- `dpr={[1, 2]}`, shadows baked via `ContactShadows`, no real-time shadow maps, `frameloop="demand"` when idle.
- Preload the GLB on the overview page so the twin opens instantly in the demo.
- If WebGL is unavailable or the frame rate stays low, show `Schematic2D` automatically. It uses the same zones, layers and clicks.
- Test on the actual demo laptop and projector resolution before the pitch.

## Milestones

| # | Milestone | Done when | Effort |
| --- | --- | --- | --- |
| 1 | Download, decimate, name zones, anchors, optimise | GLB under 10 MB loads in a bare R3F scene at 60 fps on the demo laptop | 1 h |
| 2 | `zones.ts`, `rollup.ts` + tests, `Schematic2D` on real `/requirements` data | 2D map shows G60/US counts per zone; click opens the drawer | 1 h |
| 3 | Canvas, model, environment, pins, camera presets | Click charging pin → camera flies → zone card lists the charging requirement | 1.5 h |
| 4 | Layers, outline/glow, URL state, HUD, attribution | All six layers switch correctly; deep link reopens the same view | 1 h |
| 5 | Demo polish: preload, loader, fallback, reduced motion | Demo script step 7 runs three times without a glitch | 30 min |
| — | Stretch: G60 vs G70 ghost compare, intent prompt, pin-to-propose | Only after 1–5 | cut first |

Total for the demo version: about 5 hours, which fits P2 in the [workspace plan](pm-workspace-and-3d-twin.md#phasing). If time runs out, ship milestones 1–3 plus the 2D fallback.

## Checks

- `rollup.ts` unit tests: topic → zone, comfort on two zones, worst grade, empty zones.
- Playwright smoke test: open the twin, click the charging pin, the drawer shows a `REQ-G60-US-…` key and a trace row.
- Manual: the twin and register show the same score and grade for the same requirement.
- `docker compose up --build -d`, `docker compose ps`, and `docker compose logs web` clean before committing a milestone.

## Ownership

Part of the `codex/web` stream, files under `web/src/twin/` and `web/public/models/` only. Moving the topic mapping into a database table is a later database-stream change. Open items: download the model (needs a Sketchfab login), confirm it has an interior, and confirm with BMW whether the logo may appear in the UI.
