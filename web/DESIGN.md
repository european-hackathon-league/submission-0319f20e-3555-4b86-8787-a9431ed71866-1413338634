# BMW visual identity

A product-planning adaptation of the user-supplied BMW financial dashboard, with an exact pre-adaptation checkpoint. The original shell, square components, spacing and visual assets establish the design language.

## Direction

Automotive precision with a quiet product-planning cockpit. Graphite navigation, cool white working surfaces, hairline borders and blue emphasis. Design variance 3/10, motion intensity 4/10, density 6/10. The existing Base UI primitives and Recharts remain in place.

- Reference: [BMW USA](https://www.bmwusa.com/) for its light sans-serif headings, blue calls to action, monochrome surfaces and logo treatment.
- Typeface: Barlow, weights 300–600, for titles, interface and values. IBM Plex Mono remains for compact labels and tabular details. Both are self-hosted by Next.js. Barlow is an open-source alternative for this concept; BMW's proprietary BMW Type Next font was not copied.
- Accent: BMW-inspired blue `#1c69d4`, supported by blue-grey secondary chart series. Status and evidence semantics use restrained green, amber and red.
- All cards, buttons, popovers, tables, dialogs and mobile menus inherit the squared design system. The circular BMW roundel retains its original geometry.
- The overview uses an original canvas animation of blue airflow ribbons and moving light traces. It pauses on user request, off screen, when the document is hidden, or when reduced motion is preferred. Device pixel ratio is capped and frame state stays outside React rendering.
- Light and dark mode share the same blue identity. This edition has its own theme preference key.

## Asset sources

The official white and grey BMW roundels are stored under `public/brand/`, sourced from the public BMW USA site:

- [White roundel](https://www.bmwusa.com/content/dam/bmw/marketUS/common/images/logo-icons/BMW/BMW_White_Logo.svg.asset.1695740583851.svg)
- [Grey roundel](https://www.bmwusa.com/content/dam/bmw/marketUS/common/images/logo-icons/BMW/BMW_Grey_Logo.svg.asset.1695740583799.svg)

BMW branding belongs to its respective owner. This local workspace is an independent design concept, identified as BMW concept in the sidebar.

## Product-planning adaptation

The exact financial dashboard is preserved in commit `33bc645`. The current implementation retains its shell geometry, fonts, motion field, colors, borders and primitives. The content is now the shared product-planning API: requirements, sources, evidence, pipeline, reviews, markets and audit.

New surfaces use the same square geometry and muted typography. Supporting and conflicting evidence stay visible; priority scores always carry an evidence grade. Decision forms preserve the selected version and score. Mobile uses the existing accessible sheet navigation and a full-width detail drawer. See [README.md](README.md) for runtime, verification and remaining API boundaries.
