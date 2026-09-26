import type { DeskDetail, LiveLayout, RoomDetail, SimCommand, StatusInfo } from "./types";

async function json<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, { headers: { Accept: "application/json", "Content-Type": "application/json" }, ...init });
  if (!response.ok) throw new Error(`${path} failed with ${response.status}`);
  return (await response.json()) as T;
}

export const liveApi = {
  layout: () => json<LiveLayout>("/api/v1/live/layout"),
  command: (command: SimCommand, speed?: number) =>
    json<StatusInfo>("/api/v1/simulation/commands", { method: "POST", body: JSON.stringify({ command, speed }) }),
  desk: (id: string) => json<DeskDetail>(`/api/v1/live/desks/${encodeURIComponent(id)}`),
  room: (id: string) => json<RoomDetail>(`/api/v1/live/rooms/${encodeURIComponent(id)}`),
};

export function liveSocketUrl(truth: boolean): string {
  const proto = window.location.protocol === "https:" ? "wss" : "ws";
  return `${proto}://${window.location.host}/ws/live?truth=${truth ? "true" : "false"}`;
}
