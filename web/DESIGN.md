# BMW visual identity

A BMW-inspired adaptation of the saved Frontier workspace. All nine page types remain: Overview, Transactions, Monthly, Subscriptions, Trips, Trip details, Trends, Review and Settings. Page composition, square corners, spacing, query logic and workflows are retained.

## Direction

Automotive precision with a quiet financial cockpit. Graphite navigation, cool white working surfaces, hairline borders and blue emphasis. Design variance 3/10, motion intensity 4/10, density 6/10. The existing Base UI primitives and Recharts remain in place.

- Reference: [BMW USA](https://www.bmwusa.com/) for its light sans-serif headings, blue calls to action, monochrome surfaces and logo treatment.
- Typeface: Barlow, weights 300–600, for titles, interface and values. IBM Plex Mono remains for compact labels and tabular details. Both are self-hosted by Next.js. Barlow is an open-source alternative for this concept; BMW's proprietary BMW Type Next font was not copied.
- Accent: BMW-inspired blue `#1c69d4`, supported by blue-grey secondary chart series. Positive/negative financial semantics retain green/red.
- All cards, buttons, popovers, tables, dialogs and mobile menus inherit the squared design system. The circular BMW roundel retains its original geometry.
- The overview uses an original canvas animation of blue airflow ribbons and moving light traces. It pauses on user request, off screen, when the document is hidden, or when reduced motion is preferred. Device pixel ratio is capped and frame state stays outside React rendering.
- Light and dark mode share the same blue identity. This edition has its own theme preference key.

## Asset sources

The official white and grey BMW roundels are stored under `public/brand/`, sourced from the public BMW USA site:

- [White roundel](https://www.bmwusa.com/content/dam/bmw/marketUS/common/images/logo-icons/BMW/BMW_White_Logo.svg.asset.1695740583851.svg)
- [Grey roundel](https://www.bmwusa.com/content/dam/bmw/marketUS/common/images/logo-icons/BMW/BMW_Grey_Logo.svg.asset.1695740583799.svg)

BMW branding belongs to its respective owner. This local workspace is an independent design concept, identified as BMW concept in the sidebar.

## Isolation

The BMW edition is a complete sibling folder, not a theme toggle inside Frontier. Its local preview uses `BMW_DEMO=1`, the `.bmw-demo/` database, app port 3002 and database port 55440. The Frontier database, theme settings and source files remain separate. Live mode preserves the original Supabase configuration without changing its connection settings.

## Verification

- ESLint and optimized Next.js production build pass, including TypeScript checks.
- All nine page types render with the shared BMW visual system.
- Browser checks covered transaction search, account/date filtering, trip details, light/dark mode, animation pause/resume and mobile navigation.
- Overview has no horizontal overflow at 1280px desktop or 390px mobile. All desktop pages were checked for document overflow.
- Browser console reported no errors.
- A SHA-256 comparison confirmed all 129 saved Frontier files remained unchanged. Original repository changes were also preserved.
- Desktop screenshot: `artifacts/overview.png`.
