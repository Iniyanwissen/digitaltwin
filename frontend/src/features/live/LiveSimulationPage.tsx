import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { useSearchParams } from "react-router";

import { liveApi } from "./api";
import { BuildingPanel } from "./BuildingPanel";
import { ControlBar } from "./ControlBar";
import { FloorPanel } from "./FloorPanel";
import { PeoplePanel } from "./PeoplePanel";
import type { Overlay, View } from "./floorRenderer";
import { SidePanel } from "./SidePanel";
import { DEPARTMENT_PALETTE } from "./theme";
import { useLiveConnection } from "./useLive";

/**
 * Live Simulation: the kit reference viewer rebuilt in React (docs/visualization-spec.md §4-5).
 * Operational View shows only what building systems report; Simulation View adds ground-truth
 * dots and truth KPIs from a separate, explicitly requested truth channel.
 */
export function LiveSimulationPage() {
  // Initial view/overlay can come from the URL (?view=simulation&overlay=temperature) for sharing.
  const [params] = useSearchParams();
  const [view, setView] = useState<View>(params.get("view") === "simulation" ? "simulation" : "operational");
  const [overlay, setOverlay] = useState<Overlay>(
    (["occupancy", "temperature", "hvac"] as const).find((o) => o === params.get("overlay")) ?? "occupancy",
  );
  const [floorChoice, setFloorChoice] = useState<string | null>(null);
  const { store, connection } = useLiveConnection(view === "simulation");
  const layout = useQuery({ queryKey: ["live-layout"], queryFn: liveApi.layout, staleTime: Infinity });

  const deptColor = useMemo(
    () =>
      Object.fromEntries(
        (layout.data?.departments ?? []).map((d, i) => [d, DEPARTMENT_PALETTE[i % DEPARTMENT_PALETTE.length]!]),
      ),
    [layout.data],
  );

  const floorId = floorChoice ?? layout.data?.floors[0]?.floor_id;

  return (
    <div className="-m-6 flex h-[calc(100%+3rem)] min-h-[640px] flex-col bg-twin-bg text-twin-text">
      <ControlBar
        store={store}
        connection={connection}
        view={view}
        onView={setView}
        overlay={overlay}
        onOverlay={setOverlay}
      />
      {layout.isError && <div className="p-6 text-sm text-red-300">Live simulation is not available: {String(layout.error)}</div>}
      {layout.data && floorId ? (
        <div className="grid min-h-0 flex-1 grid-cols-[290px_minmax(0,1fr)_340px] gap-3 p-3">
          <div className="flex min-h-0 flex-col gap-3">
            <BuildingPanel store={store} layout={layout.data} floorId={floorId} onSelect={setFloorChoice} />
            <PeoplePanel store={store} view={view} deptColor={deptColor} />
          </div>
          <FloorPanel
            store={store}
            layout={layout.data}
            floorId={floorId}
            view={view}
            overlay={overlay}
            deptColor={deptColor}
          />
          <SidePanel store={store} view={view} />
        </div>
      ) : (
        !layout.isError && <div className="p-6 text-sm text-twin-muted">Loading layout…</div>
      )}
    </div>
  );
}
