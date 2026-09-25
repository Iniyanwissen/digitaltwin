import type { Health, Meta } from "./types";

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, acceptStatuses: number[] = []): Promise<T> {
  const response = await fetch(path, { headers: { Accept: "application/json" } });
  if (!response.ok && !acceptStatuses.includes(response.status)) {
    throw new ApiError(response.status, `${path} failed with ${response.status}`);
  }
  return (await response.json()) as T;
}

export const api = {
  // /health answers 503 with a full body when a component is down.
  health: () => request<Health>("/health", [503]),
  meta: () => request<Meta>("/api/v1/meta"),
};
