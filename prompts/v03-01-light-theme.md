# v0.3 · Step 2 — Light theme (default) with dark toggle

_(Run `/clear` before pasting. Use plan mode.)_

Read `CLAUDE.md`, `docs/floor-twin-design-v2.md` §1–2 and `docs/visualization-spec.md` §2. Open `design/floor-twin-design.html` to see the target look.

**Do**
- Define all colours as CSS variables on `:root` (light) and `:root[data-theme="dark"]`; map them into Tailwind (`theme.extend.colors` referencing the vars). Remove hard-coded hex values from components (grep and fix).
- Light is the default. Header toggle switches theme, persists in `localStorage` (try/catch), and applies before first paint (inline script in `index.html`) to avoid a flash.
- Canvas renderers read colours from the CSS variables at draw time and redraw on theme change (static layer cache invalidated).
- Charts (Recharts/d3) take colours from the same tokens.
- Typeface IBM Plex Sans with system fallback; tabular numerals for KPIs.
- Status must not rely on colour only (held dot, hatched off desks, dashed released/booked outlines, text chips).

**Acceptance**
- Every page renders correctly in light and dark; no hard-coded colours remain (`rg -n "#[0-9a-fA-F]{6}" frontend/src` only hits the token file).
- Toggle works without reload; choice persists; no flash of the wrong theme.
- Contrast: text ≥ 4.5:1, desk state fills distinguishable in both themes (add a small visual test or storybook story per state).

Report against the acceptance list, then stop.
