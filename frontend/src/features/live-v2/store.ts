import { LiveStore } from "@/features/live/store";
import type { LiveMessage } from "@/features/live/types";

import type { ActionItem, AreaValue, Chip, EsgSummary, FloorKpiV2, LiveMessageV2 } from "./types";

const ACTION_CAP = 60;

/** v1 LiveStore plus the v2 extras: areas, ESG, KPI strip, chips, bookings, warm areas, actions. */
export class LiveStoreV2 extends LiveStore {
  areas: Record<string, AreaValue> = {};
  esg: EsgSummary | null = null;
  floorKpis: Record<string, FloorKpiV2> = {};
  chips: Record<string, Chip> = {};
  booked: Record<string, string> = {};
  warmAreas = new Set<string>();
  actions: ActionItem[] = [];

  override apply(message: LiveMessage): void {
    const msg = message as LiveMessageV2;
    if (msg.type === "snapshot") {
      this.areas = { ...(msg.areas ?? {}) };
      this.actions = [...(msg.actions ?? [])].reverse().slice(0, ACTION_CAP);
    } else {
      if (msg.areas) Object.assign(this.areas, msg.areas);
      if (msg.actions?.length) this.actions = [...[...msg.actions].reverse(), ...this.actions].slice(0, ACTION_CAP);
    }
    this.esg = msg.esg ?? this.esg;
    this.floorKpis = msg.floor_kpis ?? this.floorKpis;
    this.chips = msg.chips ?? {};
    this.booked = msg.booked ?? {};
    this.warmAreas = new Set(msg.warm_areas ?? []);
    super.apply(message); // notifies subscribers after everything above is merged
  }
}
