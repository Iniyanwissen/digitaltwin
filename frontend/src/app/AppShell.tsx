import { Outlet, useLocation } from "react-router";

import { Header } from "./Header";
import { NAVIGATION } from "./navigation";
import { Sidebar } from "./Sidebar";

export function AppShell() {
  const { pathname } = useLocation();
  const firstSegment = pathname.split("/")[1] ?? "";
  const section = NAVIGATION.find((s) => s.slug === firstSegment);

  return (
    <div className="flex h-full">
      <Sidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        <Header section={section} />
        <main className="flex-1 overflow-auto p-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
