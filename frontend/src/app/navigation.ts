import {
  Boxes,
  ChartColumn,
  Database,
  LayoutDashboard,
  type LucideIcon,
  Play,
  Users,
  CalendarRange,
} from "lucide-react";

export interface NavTab {
  slug: string;
  label: string;
  /** Implementation phase that delivers this tab (docs/implementation-plan.md). */
  phase: number | string;
  features: string[];
}

export interface NavSection {
  slug: string; // "" = root route
  label: string;
  icon: LucideIcon;
  description: string;
  tabs: NavTab[];
}

export const NAVIGATION: NavSection[] = [
  {
    slug: "",
    label: "Overview",
    icon: LayoutDashboard,
    description: "Live headline numbers for the whole workplace.",
    tabs: [
      {
        slug: "",
        label: "Overview",
        phase: 6,
        features: [
          "Employees inside, occupied and available desks, peak today",
          "Desk, room and building utilization %",
          "Occupancy over time (today)",
          "Live floor cards with current counts",
          "Team distribution today",
        ],
      },
    ],
  },
  {
    slug: "twin",
    label: "Digital Twin",
    icon: Boxes,
    description: "The building and its floors, live.",
    tabs: [
      {
        slug: "building",
        label: "Building",
        phase: 6,
        features: ["Floor utilization bars", "Capacity vs occupancy per floor", "Click through to a floor"],
      },
      {
        slug: "floor",
        label: "Floor Plan",
        phase: 7,
        features: [
          "SVG floor plan with live desk and room states",
          "Desk states: vacant, occupied, held (logged in but vacant), unavailable",
          "Desk and room detail panels",
          "Heat maps: current, 7-day, 30-day (Phase 8B)",
          "HVAC mode overlay (Phase 13)",
        ],
      },
    ],
  },
  {
    slug: "analytics",
    label: "Analytics",
    icon: ChartColumn,
    description: "History from the warehouse.",
    tabs: [
      {
        slug: "occupancy",
        label: "Occupancy",
        phase: "8B",
        features: ["Attendance trends", "Peak occupancy trend", "Hourly patterns"],
      },
      {
        slug: "real-estate",
        label: "Real Estate",
        phase: "8B",
        features: [
          "Capacity, average and P90 peak occupancy",
          "Unused capacity and desk-to-employee ratio",
          "Rule-based recommendations with supporting metrics",
        ],
      },
      {
        slug: "teams",
        label: "Teams",
        phase: "8B",
        features: ["Team attendance rates", "Team distribution by floor"],
      },
      {
        slug: "rooms",
        label: "Rooms",
        phase: "8B",
        features: ["Room utilization", "Right-sizing", "Booking effectiveness and ghost bookings"],
      },
      {
        slug: "environment",
        label: "Environment",
        phase: 13,
        features: ["Zone temperature, CO2, humidity", "Occupancy vs temperature", "Automation log"],
      },
    ],
  },
  {
    slug: "planning",
    label: "Planning",
    icon: CalendarRange,
    description: "What-if capacity planning.",
    tabs: [
      {
        slug: "scenarios",
        label: "Scenarios",
        phase: 12,
        features: [
          "Projected building and floor occupancy",
          "Desk shortage/surplus and room sufficiency",
          "Saved scenarios and comparison",
        ],
      },
      {
        slug: "events",
        label: "Events & Visitors",
        phase: 12,
        features: ["Create special events", "Register visitors"],
      },
    ],
  },
  {
    slug: "directory",
    label: "Directory",
    icon: Users,
    description: "Master data: people and spaces.",
    tabs: [
      {
        slug: "employees",
        label: "Employees",
        phase: 2,
        features: ["Searchable employee list", "Filters: team, floor, work mode, profile"],
      },
      {
        slug: "teams",
        label: "Teams",
        phase: 2,
        features: ["Teams and departments", "Home floors and zone allocations"],
      },
      {
        slug: "spaces",
        label: "Spaces",
        phase: 2,
        features: ["Floors, zones, desks, rooms and common areas", "Sensors per space"],
      },
    ],
  },
  {
    slug: "data",
    label: "Data",
    icon: Database,
    description: "Events, pipeline and source health.",
    tabs: [
      {
        slug: "events",
        label: "Live Events",
        phase: 6,
        features: ["Streaming event table", "Filters by type, employee, floor, desk, sensor", "Event rate"],
      },
      {
        slug: "pipeline",
        label: "Pipeline",
        phase: "8B",
        features: ["Lineage RAW → STAGING → CORE → MART", "Record counts per layer", "Pipeline runs"],
      },
      {
        slug: "sources",
        label: "Sources & Quality",
        phase: "8B / 9",
        features: [
          "Source status, events received, latency",
          "Duplicates, late events, sensor downtime (Phase 9)",
        ],
      },
    ],
  },
  {
    slug: "simulation",
    label: "Simulation",
    icon: Play,
    description: "Run and inspect the simulated world.",
    tabs: [
      {
        slug: "control",
        label: "Control",
        phase: 3,
        features: ["Start, pause, resume, stop, reset", "Speed selector", "Simulation truth counters"],
      },
      {
        slug: "debug",
        label: "Debug",
        phase: 9,
        features: ["Ground truth vs observed for a desk or room (clearly labelled)"],
      },
    ],
  },
];

export function sectionPath(section: NavSection): string {
  return `/${section.slug}`;
}

export function tabPath(section: NavSection, tab: NavTab): string {
  return tab.slug ? `/${section.slug}/${tab.slug}` : sectionPath(section);
}
