import { type ComponentType, lazy } from "react";

import { EmployeesPage } from "@/features/directory/EmployeesPage";
import { SpacesPage } from "@/features/directory/SpacesPage";
import { TeamsPage } from "@/features/directory/TeamsPage";
import { BuildingPage } from "@/features/twin/BuildingPage";

// The live screen (canvas + charts) loads on demand so other pages stay light.
const LiveSimulationPage = lazy(() =>
  import("@/features/live/LiveSimulationPage").then((m) => ({ default: m.LiveSimulationPage })),
);

/** Implemented pages keyed by "<section>/<tab>". Everything else shows its placeholder. */
export const PAGES: Record<string, ComponentType> = {
  "live/": LiveSimulationPage,
  "twin/building": BuildingPage,
  "directory/employees": EmployeesPage,
  "directory/teams": TeamsPage,
  "directory/spaces": SpacesPage,
};
