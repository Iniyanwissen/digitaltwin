// Live Simulation v2 contracts (server: twin_server/v2, docs/environment-and-esg.md §5.3).

import type { FrameMessage, SnapshotMessage } from "@/features/live/types";

export interface V2Zone {
  zone_id: string;
  code: string;
  name: string;
  zone_type: string;
  x: number;
  y: number;
  w: number;
  h: number;
  facade: string | null;
  is_restricted: boolean;
  capacity: number | null;
}

export interface V2Desk {
  workspace_id: string;
  zone_id: string;
  x: number;
  y: number;
  w: number;
  h: number;
  facing: string;
}

export interface V2Room {
  room_id: string;
  name: string;
  room_type: string;
  area_subtype: string | null;
  x: number;
  y: number;
  w: number;
  h: number;
  capacity: number;
  zone_id: string;
  has_badge_reader: boolean;
  has_panel: boolean;
  is_bookable: boolean;
}

export interface V2Floor {
  floor_id: string;
  floor_number: number;
  name: string;
  desk_policy: string;
  width: number;
  height: number;
  glazing: string[];
  cores: { x: number; y: number; w: number; h: number; label: string }[];
  zones: V2Zone[];
  desks: V2Desk[];
  rooms: V2Room[];
  readers: { access_point_id: string; reader_type: string; x: number; y: number; target_id: string }[];
}

export interface V2Layout {
  building: { building_id: string; name: string };
  floors: V2Floor[];
  departments: string[];
}

/** [temperature, delta_15m, co2, hvac_mode, light_level_pct, setpoint_c, ventilation_boost] */
export type AreaValue = [number | null, number, number | null, string, number, number, boolean];

export interface EsgSummary {
  kwh: number;
  baseline_kwh: number;
  saved_kwh: number;
  saved_pct: number;
  co2e_kg: number;
  cost_inr: number;
  comfort_pct: number;
}

export interface FloorKpiV2 {
  desk_util_pct: number;
  occupied_desks: number;
  held_desks: number;
  rooms_in_use: number;
  rooms: number;
  est_people: number;
  warm_spots: number;
}

export interface ActionItem {
  t: string;
  area: string;
  area_name: string;
  floor: string | null;
  rule: string;
  action: string;
  tag: "HVAC" | "Lighting" | "Rooms" | string;
  reason: string;
}

export type Chip = "released" | "over" | "too_big";

interface V2Extras {
  areas: Record<string, AreaValue>;
  esg: EsgSummary;
  esg_floors: Record<string, EsgSummary>;
  floor_kpis: Record<string, FloorKpiV2>;
  chips: Record<string, Chip>;
  booked: Record<string, string>;
  warm_areas: string[];
  actions: ActionItem[];
}

export type SnapshotV2 = SnapshotMessage & V2Extras;
export type FrameV2 = FrameMessage & V2Extras;
export type LiveMessageV2 = SnapshotV2 | FrameV2;

export interface BookingInfo {
  booking_id: string;
  start: string;
  end: string;
  attendees: number;
  released: boolean;
  checked_in: boolean;
}

export interface AreaDetail {
  area_id: string;
  area_type: "ZONE" | "ROOM";
  floor_id: string;
  name: string;
  area_m2: number;
  facade: string | null;
  capacity: number | null;
  people: number | null;
  temperature: number | null;
  delta_15m: number | null;
  co2: number | null;
  hvac_mode: string | null;
  light_level_pct: number | null;
  setpoint_c: number | null;
  ventilation_boost: boolean | null;
  last_action: ActionItem | null;
  history: { t: string; temp: number | null; co2: number | null }[];
  current_booking?: BookingInfo | null;
  next_booking?: BookingInfo | null;
}

export type Layer = "occupancy" | "temperature" | "lighting" | "hvac";
export type Selection = { kind: "desk"; id: string } | { kind: "area"; id: string } | null;
