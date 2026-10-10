# BMW Requirement Twin vehicle assets

**Status: sourcing — no approved 3D model delivered yet.**

The selected target is an accurate licensed BMW i5 M60 xDrive (G60), US reference scope, initially MY2024. The user rejected the stylised sedan; it and its raw authoring files are outside Git and are not part of this package.

The [candidate review](research/README.md) records current download/licence findings and official references. The [tools](tools/README.md) are ready for the authorized download. Sketchfab requires user authentication; neither inspected browser session was signed in when the normal download action was attempted.

Planned first ready package: `g60-us/manifest.json`, optimized GLB, poster, 2D schematic, licence, attribution and integration notes. Each vehicle will have its own directory and a versioned manifest; another vehicle can be added without blocking G60. Do not import a directory as a ready asset until its manifest has `status: "ready"` and validation passes.

Acceptance still required after acquisition: inspect exterior/interior and source year/market, optimize without losing visible detail, calibrate metres/orientation, add 11 anchors and 5 cameras, record hashes and attribution, open the actual GLB in a browser, check charging hit area and performance. Customer requirements must come from the G60/US API; official vehicle facts remain separately cited context.

Preparation checks on 2026-10-10: local-source inspection and optimization smoke test passed; a compressed test GLB decoded successfully and had zero Khronos validator errors/warnings. The validator reports that Draco internals are unsupported, so browser decoding remains a required final check. No BMW model performance result is claimed. The existing BMW Compose services were inspected and left running; no API, database or frontend was changed.
