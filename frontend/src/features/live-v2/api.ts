import type { DeskDetail, SimCommand, StatusInfo } from "@/features/live/types";

import type { AreaDetail, V2Layout } from "./types";

async function json<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    headers: { Accept: "application/json", "Content-Type": "application/json" },
    ...init,
  });
  if (!response.ok) throw new Error(`${path} failed with ${response.status}`);
  return (await response.json()) as T;
}

export const liveV2Api = {
  layout: () => json<V2Layout>("/api/v2/layout"),
  command: (command: SimCommand, speed?: number) =>
    json<StatusInfo>("/api/v2/simulation/commands", { method: "POST", body: JSON.stringify({ command, speed }) }),
  desk: (id: string) => json<DeskDetail>(`/api/v2/live/desks/${encodeURIComponent(id)}`),
  area: (id: string) => json<AreaDetail>(`/api/v2/live/areas/${encodeURIComponent(id)}`),
};

export const V2_SOCKET_PATH = "/ws/live-v2";
