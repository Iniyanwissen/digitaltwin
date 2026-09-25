import { NavLink, Outlet } from "react-router";

import { cn } from "@/lib/utils";

import { type NavSection, tabPath } from "./navigation";

export function SectionLayout({ section }: { section: NavSection }) {
  return (
    <div className="space-y-6">
      {section.tabs.length > 1 && (
        <nav className="flex gap-1 border-b border-slate-200">
          {section.tabs.map((tab) => (
            <NavLink
              key={tab.slug}
              to={tabPath(section, tab)}
              className={({ isActive }) =>
                cn(
                  "-mb-px border-b-2 px-4 py-2 text-sm font-medium",
                  isActive
                    ? "border-brand-500 text-brand-600"
                    : "border-transparent text-slate-500 hover:text-slate-800",
                )
              }
            >
              {tab.label}
            </NavLink>
          ))}
        </nav>
      )}
      <Outlet />
    </div>
  );
}
