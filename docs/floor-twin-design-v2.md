> **Repo note (2026-09-27):** in this repo, v0.3 applies to **Live Simulation v2** only (`/live-v2`, `/api/v2`, `config/v2/`). Live Simulation v1 and the other pages keep the v0.2 design. See `decision-log.md`.

# Floor Twin Design v2 (Light Theme)

> Status: v0.3. Supersedes the floor/twin parts of `visualization-spec.md` §2 and §5. Everything else in that doc still applies.
> Visual reference: `design/floor-twin-design.html` (open in a browser; **Play demo** shows the crowd → temperature → automation loop).
> Geometry: `design/floor-plan-v2.json` (metres).

---

## 1. Principles

- **Light by default, dark on toggle.** One token set, two themes (`data-theme="light|dark"` on `<html>`), persisted per user. No hard-coded colours in components.
- **Calm by default, detail on demand.** The occupancy layer shows desks, room fill and only *exceptions* (auto-released, over capacity, oversized, booked, warm and rising). Everything else lives in the selection panel.
- **One layer at a time.** Occupancy · Temperature · Lighting · HVAC. Non-occupancy layers fade desks to 35% so the overlay reads.
- **Real geometry.** The plan is drawn in metres from the layout; the renderer scales it. No grid-generated layouts.

## 2. Tokens

| Token | Light | Dark | Use |
|---|---|---|---|
| `--page` / `--panel` / `--paper` | `#F2F4F7` / `#FFFFFF` / `#FCFDFE` | `#0E1318` / `#161D25` / `#141A21` | app bg, cards, floor slab |
| `--ink` / `--ink-2` / `--ink-3` | `#1E2A36` / `#5A6674` / `#8E98A5` | `#E4E9EF` / `#A7B1BD` / `#768292` | text |
| `--rule` | `#E3E7ED` | `#26303B` | hairlines |
| `--wall` / `--glass` / `--column` | `#3A4655` / `#9CC3E0` / `#B8C0CA` | `#C3CDD8` / `#4E86B3` / `#4B5765` | walls, glazing, structure |
| `--desk-occ` | `#1F9D55` (line `#15703C`) | same | occupied (sensor) |
| `--desk-held` | `#F2A516` (line `#A86B06`) + white centre dot | same | logged in, away |
| `--desk-vacant` | `#FFFFFF` (line `#B4BDC8`) | `#1B232C` | available |
| `--desk-off` | hatched `#E6E9ED` | `#232B34` | out of service |
| `--accent` | `#1D5FD1` | same | room fill (10–40% mix by count/capacity), focus |
| `--released` / `--danger` / `--warn` | `#6D3FD1` / `#C62828` / `#8A5A00` + tinted bgs | lighter | status chips |
| `--warm` / `--cool` | `#D9621C` / `#2F6FDE` | `#F08A45` / `#6FA0F0` | temperature trend arrows |
| `--esg` | `#0E7C6B` on `#E4F4EF` | on `#12302A` | sustainability panel |

- Typeface: IBM Plex Sans (400/500/600), tabular numerals.
- Temperature ramp (fill at 70%): 21 °C `#3B7DD8` → 22.5 `#C9DBF3` → 24.5 `#EEF1F5` (comfort band, neutral) → 26 `#F0903A` → 27.5 `#D23B2A`.
- Department dot palette unchanged from v0.2.
- Status never relies on colour alone: held desks have a centre dot, out-of-service desks are hatched, released/booked rooms use dashed outlines, chips carry text.

## 3. Floor plan v2 (per floor)

64 × 26 m plate, glazing on all facades, columns on an 8 m grid, two lift cores.

| Band | West → East |
|---|---|
| North (daylight) | Open workspace A (40 desks) · Team hub (collaboration, 10) · Open workspace B (40 desks) |
| Middle | Lounge (12) · Lifts · Boardroom (16, door reader) · Workshop (8) · Lifts · Café (30) · Focus booths 1–4 (1 each) |
| South | Open workspace C (24 desks) · Kaveri 4 · Vaigai 4 · Palar 6 · Bhavani 6 · Noyyal 4 · Amaravathi 8 · Open workspace D (32 desks) |

- 136 desks in 2 × 2 pods, 12 bookable rooms, 3 common areas (modelled as `COMMON_AREA` rooms filling their zone, so the v0.2 room-count sensor model still applies).
- Readers: lift-lobby reader at each core, boardroom door reader, secure-zone reader on zone D only on the Finance floor.
- **Floor variants** (overrides on the same geometry): Floor 1 replaces Team hub with *Reception* (building entrance reader) and uses a larger café capacity; Finance (restricted zone D) is on Floor 3; Floor 4 is `ASSIGNED` desks.

## 4. Layers and indicators

| Layer | Areas show | Labels |
|---|---|---|
| Occupancy (default) | desks by state, room fill by count/capacity, exception chips | `count/cap`; warm-spot marker `25.9° ▲` only when ≥ 25.5 °C and occupied |
| Temperature | area fill by the ramp | `24.1° ▲0.6` = current and change over the last 15 min (▲ warm/orange, ▼ cool/blue, → within ±0.2) |
| Lighting | full / daylight-dimmed / dimmed-empty / off | `100%`, `70%`, `30%`, `Off` |
| HVAC | Eco · Pre-cool · High · Vent boost tints (Normal = no tint) | mode name |

Simulation view adds ground-truth dots (department colours) and a striped *True headcount* cell; it never changes operational numbers.

## 5. Panels

- **KPI strip (max 5):** desk utilisation, desks occupied · held, meeting rooms in use, estimated people, warm spots.
- **Selection:**
  - Desk: sensor state, workstation login (identity only from login).
  - Room/area: people, temperature + 15-min trend, CO₂, HVAC mode, lighting, last automation, and a sparkline of the last hour with the setpoint as a dashed line.
- **Sustainability today:** energy saved vs. baseline (hero), kWh used, CO₂e avoided, ₹ saved, comfort compliance.
- **Automation log:** last 4 actions, each with what and why (`environment-and-esg.md` §4).

## 6. Rendering rules

- Same as v0.2 §5.3: cached static layer (walls, glazing, cores, labels), dynamic overlays/desks, dots on their own layer with 900 ms tweening, dirty-flag redraws.
- Temperature trend (`delta_15m`), warm-spot flags and all ESG numbers come from the backend; the browser only draws them.
- Desks, rooms and zones are keyboard-focusable; Enter selects.
