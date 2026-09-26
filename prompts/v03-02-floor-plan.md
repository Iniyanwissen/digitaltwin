# v0.3 · Step 3 — Real floor plan and decluttered twin

_(Run `/clear` before pasting. Use plan mode.)_

Read `CLAUDE.md`, `docs/floor-twin-design-v2.md`, `design/floor-plan-v2.json`, and the relevant parts of `docs/data-model.md` (layout tables). Use `design/floor-twin-design.html` as the visual and interaction reference (not as code to copy wholesale).

**Backend / data**
- Layout generator reads `layout.floor_plan_file` and `floor_overrides` instead of generating grids. Units are metres. Keep ID patterns from `data-model.md` §1 (map the JSON codes to them; keep the JSON's IDs for Floor 2 as they are).
- Apply per-floor overrides (Floor 1 reception + entrance reader, Floor 3 Finance restricted zone D, Floor 4 assigned desks).
- Alembic migration for the new layout fields (metres, facade, area_m2, w/h/facing, FOCUS_BOOTH, floor_core, env sensors per room).
- Update master-data seed, regenerate `mock-data/master`, and update the determinism test's expected files.
- Team placement: rebalance to the new desk count (136 per floor); keep the attendance calibration test green (adjust `presets.medium.employees` if needed and record it in the decision log).

**Frontend**
- Twin renderer draws from layout JSON in metres: slab, glazing, columns, cores, zones, rooms, desks (2×2 pods), readers, labels.
- Layers: Occupancy (default), Temperature, Lighting, HVAC — one at a time; desks fade to 35% on non-occupancy layers.
- Occupancy layer shows only exception chips (released, over capacity, oversized, booked) and the warm-spot marker.
- Selection panel for desk / room / area; KPI strip max 5 cells.
- Keyboard focus and Enter-to-select on desks, rooms, zones.

**Acceptance**
- All four floors render from the file with their overrides; desk and room counts match the JSON.
- The Floor 2 plan matches the reference design's layout and legend; no chairs/furniture clutter; labels don't overlap at 1280 px width.
- ≥ 50 fps at 60× with Simulation view dots.
- Existing identity/privacy tests still pass.

Report against the acceptance list, then stop.
