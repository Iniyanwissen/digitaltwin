// Mirrors services/twin-server/twin_server/api/schemas.py

export type ComponentStatus = "ok" | "degraded" | "down";

export interface ComponentHealth {
  status: ComponentStatus;
  detail: string;
  info: Record<string, unknown>;
}

export interface Health {
  status: ComponentStatus;
  checked_at: string;
  components: Record<string, ComponentHealth>;
}

export interface ConfigSummary {
  content_hash: string;
  seed: number;
  timezone: string;
  scale_preset: string;
  organization: string;
  employee_count: number;
  layout_files: string[];
  default_speed: number;
  allowed_speeds: number[];
  core_hours: string;
}

export interface Meta {
  name: string;
  version: string;
  environment: string;
  server_time: string;
  config: ConfigSummary;
}

export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

// ---------------------------------------------------------------- spaces

export interface AccessPoint {
  access_point_id: string;
  building_id: string;
  floor_id: string;
  name: string;
  direction: string;
  x: number;
  y: number;
  reader_type: string;
  target_id: string;
}

export interface FloorSummary {
  floor_id: string;
  building_id: string;
  floor_number: number;
  name: string;
  desk_policy: string;
  max_occupancy: number;
  plan_width: number;
  plan_height: number;
  is_available: boolean;
  desks: number;
  cabins: number;
  workspaces: number;
  rooms: number;
  room_seats: number;
  common_areas: number;
  common_area_capacity: number;
  zones: number;
  sensors: number;
  home_employees: number;
  home_teams: number;
  readers: number;
  employees_per_workspace: number;
}

export interface Building {
  building_id: string;
  org_id: string;
  name: string;
  timezone: string;
  max_occupancy: number;
  gross_area_sqm: number;
  floors: FloorSummary[];
  access_points: AccessPoint[];
}

export interface Zone {
  zone_id: string;
  floor_id: string;
  name: string;
  zone_type: string;
  x: number;
  y: number;
  width: number;
  height: number;
  max_occupancy: number;
  area_sqm: number;
  is_restricted: boolean;
  workspaces: number;
}

export interface Room {
  room_id: string;
  floor_id: string;
  zone_id: string;
  zone_name: string | null;
  name: string;
  room_type: string;
  area_subtype: string | null;
  capacity: number;
  x: number;
  y: number;
  width: number;
  height: number;
  is_bookable: boolean;
  status: string;
  has_badge_reader: boolean;
  has_panel: boolean;
}

// ---------------------------------------------------------------- people

export interface Department {
  department_id: string;
  name: string;
  employees: number;
  teams: number;
}

export interface Team {
  team_id: string;
  name: string;
  department_id: string;
  department_name: string;
  home_floor_id: string;
  home_floor_name: string;
  office_days: number[];
  size_target: number;
  members: number;
  zone_allocations: { zone_id: string; zone_name: string; share: number }[];
  secure_zones: { zone_id: string; zone_name: string }[];
}

export interface Employee {
  employee_id: string;
  code: string;
  employee_name: string;
  email: string;
  job_role: string;
  team_id: string;
  team_name: string;
  department_id: string;
  department_name: string;
  home_floor_id: string;
  home_floor_name: string;
  preferred_zone_id: string;
  manager_id: string | null;
  employment_type: string;
  work_mode: string;
  behavior_profile: string;
  hire_date: string;
  assigned_workspace_id: string | null;
}

export interface FacetValue {
  value: string;
  count: number;
}

export interface EmployeeFacets {
  work_mode: FacetValue[];
  behavior_profile: FacetValue[];
  employment_type: FacetValue[];
}

export interface EmployeeQuery {
  search?: string;
  department_id?: string;
  team_id?: string;
  floor_id?: string;
  work_mode?: string;
  behavior_profile?: string;
  page: number;
  page_size: number;
}
