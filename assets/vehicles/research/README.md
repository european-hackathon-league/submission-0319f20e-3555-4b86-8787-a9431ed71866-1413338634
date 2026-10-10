# G60 / US 3D asset sourcing

Research checked 10 October 2026. The selected model is now downloaded and packaged; see `../g60-us/INTEGRATION.md`.

## Accepted visual target

An accurate, detailed **BMW i5 M60 xDrive (G60)** model, with a usable interior if available. A properly licensed independent artist's model is acceptable; BMW authorship is not required. The generic procedural sedan was rejected and moved entirely outside the repository. No frontend implementation is in scope. Do not contact Troy further; the user will coordinate platform work.

## Sketchfab candidate

- [2023 BMW I5 M60](https://sketchfab.com/3d-models/2023-bmw-i5-m60-207fd872d28b4cafa7fefe061ae98e26), [Nazh Design](https://sketchfab.com/NazhDesign).
- Listing and [public model metadata](https://api.sketchfab.com/v3/models/207fd872d28b4cafa7fefe061ae98e26) checked on 2026-10-10: `isDownloadable: true`, CC Attribution linking to **CC BY 4.0**, 1,477,883 triangles / 795,020 vertices, published 2024-01-20.
- The normal Download 3D Model action opens a login dialog. [Sketchfab's download documentation](https://sketchfab.com/developers/download-api/downloading-models) confirms authenticated download is required. No viewer extraction or authentication bypass is allowed.
- Download inspected: **exterior only**, with opaque windows and no usable seat/dashboard/rear-cabin geometry. Cabin, battery and cargo anchors are explicitly approximate.
- Source naming is “2023”; that does not establish a US model year. Use US MY2024 as separately sourced reference scope, recording any actual geometry/trim mismatch.
- [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) permits sharing and adaptation, including commercial use, subject to attribution, a licence link and indication of changes. An optimized GLB may be redistributed in Git under those terms for rights controlled by the licensor. Preserve provenance and licence notices with the GLB.
- The licence does not confer BMW sponsorship or trademark rights; see [legal code §2(b)](https://creativecommons.org/licenses/by/4.0/legalcode.en). The artist's licence declaration is not a claim of BMW authorization. Do not use BMW brand marks as the application logo or imply endorsement.
- Proposed attribution, only after selection: **“2023 BMW I5 M60 by Nazh Design, CC BY 4.0. Optimized for the Requirement Twin; see asset manifest for changes.”** Link the model title to the original source, the creator to their profile, and CC BY 4.0 to its licence. Replace the modifications with the exact performed operations.

## BMW-provided asset request

An authorized request was posted in the [BMW hackathon channel](https://discord.com/channels/1553151744047976549/1553306479019429939) at **22:45 Europe/Berlin on 2026-10-10**. It asks for a G60/i5 M60 US pack with an interior, and explicit terms for conversion, simplification, public demos/screenshots, private team handoff, repository redistribution, deployed browser delivery, attribution and logos. At 22:55 Maxi (BMW) replied that BMW has no 3D assets, and pointed to the configurator's image-based 360° exterior and interior views as material teams can get creative with for visualizations. That reply answers none of the conversion, redistribution, attribution or logo questions, so the CC BY 4.0 Sketchfab model remains the 3D source. Organizer permission to publish the feedback datasets (22:07) is not permission for configurator assets.

## Official reference separation

The separately recorded official facts are product context, never customer feedback or generated requirements. Every fact records source URL, market and model year. The current US product page identifies MY2027, so its specifications must not silently populate the MY2024 reference vehicle. The PressClub US launch release explicitly concerns MY2024.

The old twin plan incorrectly says the charging port is left rear. BMW's MY2024 US FAQ specifies **right rear side panel**. With right-handed coordinates, +Y up and +Z forward, define +X as vehicle left and put the port on **negative X**.

## Integration boundaries

Own package: `assets/vehicles/`. Proposed frontend static path: `/models/g60-us/`. No files under `web/`, shared plans, API, database, Compose or Troy's checkout are edited. The path is a proposal, not an agreement from Troy. One initial coordination email was already sent before the user instructed that no further contact be made.

The public manifest must distinguish `status: ready` from any pending asset. Do not expose invented sizes, hashes, interior availability or validated anchor coordinates. Actual anchors and camera framing must be calibrated after loading the selected geometry.

## Anonymous-download follow-up

The user attempted signup and reported being redirected to Epic Games without access to their password. No credentials were requested or read. Sketchfab's documented download API requires authentication; its public metadata and thumbnail are not the model archive.

The creator's Sketchfab profile links to [their 3D Warehouse profile](https://3dwarehouse.sketchup.com/user/5f9b35a6-417b-4d92-806a-2fb769488079/Nazh-Design-%E2%88%9A). On inspection that catalog contains one Lexus model, and its description says new uploads moved to Sketchfab and CGTrader. No i5 download was present. No verified anonymous artist-authorized mirror was found in the focused search.

Other located listings are not substitutes for permission: [Freecreat](https://www.freecreat.com/detail/16469.html) requires paid access and does not establish redistribution rights; [Zifir3D on Superhive](https://superhivemarket.com/products/bmw-i5-m60/docs) is a paid royalty-free asset whose exact browser-delivery/team-sharing terms still require review. No purchase or third-party account creation was performed.

The user subsequently signed in through Epic Games. The authenticated Download dialog explicitly displayed “CC Attribution”, creator credit and commercial use allowed. Both the original (28,426,496 bytes) and converted (42,990,308 bytes) GLBs were downloaded through the normal UI. No authentication bypass was used. Exact source hashes are recorded in the final manifest; source archives remain outside Git. The converted GLB is the build input because it includes normals. No textures were present. The derivative adds named PBR materials, topology cleanup, anchors and compression.

A final remote check is recorded in `../verification.json`; no contact with Troy was made during the download/build work.
