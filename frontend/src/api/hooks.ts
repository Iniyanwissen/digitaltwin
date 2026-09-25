import { keepPreviousData, useQuery } from "@tanstack/react-query";

import { api } from "./client";
import type { EmployeeQuery } from "./types";

const HEALTH_POLL_MS = 5_000;
// Master data only changes when config is regenerated.
const MASTER_STALE_MS = 5 * 60_000;

export function useHealth() {
  return useQuery({
    queryKey: ["health"],
    queryFn: api.health,
    refetchInterval: HEALTH_POLL_MS,
    retry: false,
  });
}

export function useMeta() {
  return useQuery({ queryKey: ["meta"], queryFn: api.meta, staleTime: Infinity });
}

export function useBuildings() {
  return useQuery({ queryKey: ["buildings"], queryFn: api.buildings, staleTime: MASTER_STALE_MS });
}

export function useFloors() {
  return useQuery({ queryKey: ["floors"], queryFn: api.floors, staleTime: MASTER_STALE_MS });
}

export function useZones(floorId: string | undefined) {
  return useQuery({
    queryKey: ["zones", floorId],
    queryFn: () => api.zones(floorId),
    enabled: Boolean(floorId),
    staleTime: MASTER_STALE_MS,
  });
}

export function useAccessPoints(floorId: string | undefined) {
  return useQuery({
    queryKey: ["access-points", floorId],
    queryFn: () => api.accessPoints(floorId),
    enabled: Boolean(floorId),
    staleTime: MASTER_STALE_MS,
  });
}

export function useRooms(floorId: string | undefined) {
  return useQuery({
    queryKey: ["rooms", floorId],
    queryFn: () => api.rooms(floorId),
    enabled: Boolean(floorId),
    staleTime: MASTER_STALE_MS,
  });
}

export function useDepartments() {
  return useQuery({ queryKey: ["departments"], queryFn: api.departments, staleTime: MASTER_STALE_MS });
}

export function useTeams() {
  return useQuery({ queryKey: ["teams"], queryFn: api.teams, staleTime: MASTER_STALE_MS });
}

export function useEmployees(query: EmployeeQuery) {
  return useQuery({
    queryKey: ["employees", query],
    queryFn: () => api.employees(query),
    placeholderData: keepPreviousData,
    staleTime: MASTER_STALE_MS,
  });
}

export function useEmployeeFacets() {
  return useQuery({
    queryKey: ["employee-facets"],
    queryFn: api.employeeFacets,
    staleTime: MASTER_STALE_MS,
  });
}
