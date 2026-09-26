// Live simulation contracts (docs/live-streaming.md §4; server: twin_server/live, processor/live_state).

export interface LiveLayout {
  building: { building_id: string; name: string; max_occupancy: number };
  floors: {
    floor_id: string;
    floor_number: number;
    name: string;
    desk_policy: string;
    width: number;
    height: number;
    desks: number;
  }[];
  zones: {
    zone_id: string;
    floor_id: string;
    name: string;
    zone_type: string;
    x: number;
    y: number;
    width: number;
    height: number;
    is_restricted: boolean;
  }[];
  workspaces: {
    workspace_id: string;
    floor_id: string;
    zone_id: string;
    workspace_type: string;
    x: number;
    y: number;
    has_sensor: boolean;
  }[];
  rooms: {
    room_id: string;
    floor_id: string;
    zone_id: string;
    name: string;
    room_type: string;
    area_subtype: string | null;
    capacity: number;
    x: number;
    y: number;
    width: number;
    height: number;
    has_badge_reader: boolean;
    has_panel: boolean;
  }[];
  access_points: { access_point_id: string; floor_id: string; name: string; reader_type: string; x: number; y: number }[];
  departments: string[];
}

export type DeskValue = [sensor: number, loggedIn: number];
export type ZoneValue = [temperature: number | null, co2: number | null, hvac: string];
/** [x, y, floor_id, department, state]; null = left the building */
export type TruthPosition = [number, number, string, string, string];

export interface FloorKpi {
  floor_id: string;
  name: string;
  occupied_desks: number;
  held_desks: number;
  room_occupants: number;
  est_headcount: number;
  desks: number;
  desk_util_pct: number;
}

export interface Kpis {
  employees_inside: number;
  occupied_desks: number;
  held_desks: number;
  available_desks: number;
  total_desks: number;
  desk_util_pct: number;
  rooms_in_use: number;
  meeting_rooms: number;
  room_util_pct: number;
  room_occupants: number;
  building_util_pct: number;
  peak_today: number;
  peak_time: string;
  floors: FloorKpi[];
  hvac_eco_zones: number;
}

export interface SeriesPoint {
  m: string;
  inside: number;
  desks: number;
  held: number;
  rooms: number;
}

export interface FeedLine {
  t: string;
  type: string;
  entity: string;
  floor: string | null;
  detail: string;
  identity: "IDENTIFIED" | "ANONYMOUS" | "SYSTEM" | string;
}

/** One readable people-activity line (observed: identified events only; truth: simulation). */
export interface ActivityItem {
  t: string;
  person: string;
  code: string;
  name: string;
  dept: string;
  text: string;
  kind: string;
}

export interface PersonStatus {
  code: string;
  name: string;
  dept: string;
  t: string;
  text: string;
  inside?: boolean;
}

export interface AutomationLine {
  t: string;
  zone: string;
  rule: string;
  action: string;
  params: Record<string, unknown>;
}

export interface TruthSummary {
  inside?: number;
  at_desk?: number;
  in_meeting?: number;
  occupied_desks_truth?: number;
  claimed_desks?: number;
}

export type RunState = "STOPPED" | "RUNNING" | "PAUSED";

export interface StatusInfo {
  run_id: string;
  status: RunState;
  speed: number;
  allowed_speeds: number[];
  sim_time: string;
  events_generated: number;
}

interface StreamBase extends StatusInfo {
  version: number;
  desks: Record<string, DeskValue>;
  rooms: Record<string, number>;
  zones: Record<string, ZoneValue>;
  kpis: Kpis;
  events_total: number;
  automation: AutomationLine[];
}

export interface SnapshotMessage extends StreamBase {
  type: "snapshot";
  series: SeriesPoint[];
  people: Record<string, PersonStatus>;
  activity: ActivityItem[];
  truth?: {
    version: number;
    positions: Record<string, TruthPosition>;
    people: Record<string, PersonStatus>;
    activity: ActivityItem[];
    summary: TruthSummary;
  };
}

export interface FrameMessage extends StreamBase {
  type: "frame";
  feed: FeedLine[];
  point: SeriesPoint | null;
  people: Record<string, PersonStatus | null>;
  activity: ActivityItem[];
  truth?: {
    version: number;
    positions: Record<string, TruthPosition | null>;
    people: Record<string, PersonStatus | null>;
    activity: ActivityItem[];
    summary: TruthSummary;
  };
}

export type LiveMessage = SnapshotMessage | FrameMessage;

export interface DeskDetail {
  workspace_id: string;
  zone_id: string;
  floor_id: string;
  device_type: string;
  has_sensor: boolean;
  sensor_status: string;
  last_sensor_change: string | null;
  logged_in_employee: string | null;
}

export interface RoomDetail {
  room_id: string;
  name: string;
  room_type: string;
  area_subtype: string | null;
  capacity: number;
  sensor_count: number;
  has_panel: boolean;
  has_badge_reader: boolean;
  bookable: boolean;
  current_booking: {
    booking_id: string;
    start: string;
    end: string;
    expected_attendees: number;
    checked_in: boolean;
  } | null;
}

export type SimCommand = "START" | "PAUSE" | "RESUME" | "STOP" | "RESET" | "SET_SPEED";
