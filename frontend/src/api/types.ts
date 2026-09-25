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
