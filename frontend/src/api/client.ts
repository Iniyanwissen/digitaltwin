import type {
  AccessPoint,
  Building,
  Department,
  Employee,
  EmployeeFacets,
  EmployeeQuery,
  FloorSummary,
  Health,
  Meta,
  Page,
  Room,
  Team,
  Zone,
} from "./types";

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

type Params = Record<string, string | number | undefined>;

function withParams(path: string, params?: Params): string {
  if (!params) return path;
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") search.set(key, String(value));
  }
  const qs = search.toString();
  return qs ? `${path}?${qs}` : path;
}

async function request<T>(path: string, params?: Params, acceptStatuses: number[] = []): Promise<T> {
  const url = withParams(path, params);
  const response = await fetch(url, { headers: { Accept: "application/json" } });
  if (!response.ok && !acceptStatuses.includes(response.status)) {
    throw new ApiError(response.status, `${url} failed with ${response.status}`);
  }
  return (await response.json()) as T;
}

export const api = {
  // /health answers 503 with a full body when a component is down.
  health: () => request<Health>("/health", undefined, [503]),
  meta: () => request<Meta>("/api/v1/meta"),
  buildings: () => request<Building[]>("/api/v1/buildings"),
  floors: () => request<FloorSummary[]>("/api/v1/floors"),
  zones: (floorId?: string) => request<Zone[]>("/api/v1/zones", { floor_id: floorId }),
  accessPoints: (floorId?: string) =>
    request<AccessPoint[]>("/api/v1/access-points", { floor_id: floorId }),
  rooms: (floorId?: string) => request<Room[]>("/api/v1/rooms", { floor_id: floorId }),
  departments: () => request<Department[]>("/api/v1/departments"),
  teams: () => request<Team[]>("/api/v1/teams"),
  employees: (query: EmployeeQuery) =>
    request<Page<Employee>>("/api/v1/employees", { ...query }),
  employeeFacets: () => request<EmployeeFacets>("/api/v1/employees/facets"),
};
