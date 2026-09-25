import type { ComponentType } from "react";

import { EmployeesPage } from "@/features/directory/EmployeesPage";
import { SpacesPage } from "@/features/directory/SpacesPage";
import { TeamsPage } from "@/features/directory/TeamsPage";
import { BuildingPage } from "@/features/twin/BuildingPage";

/** Implemented pages keyed by "<section>/<tab>". Everything else shows its placeholder. */
export const PAGES: Record<string, ComponentType> = {
  "twin/building": BuildingPage,
  "directory/employees": EmployeesPage,
  "directory/teams": TeamsPage,
  "directory/spaces": SpacesPage,
};
