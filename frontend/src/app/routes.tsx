import { Navigate, type RouteObject } from "react-router";

import { PlaceholderPanel } from "@/components/PlaceholderPanel";

import { AppShell } from "./AppShell";
import { NAVIGATION } from "./navigation";
import { NotFound } from "./NotFound";
import { SectionLayout } from "./SectionLayout";

function sectionRoutes(): RouteObject[] {
  return NAVIGATION.map((section) => {
    const [firstTab] = section.tabs;
    if (section.slug === "" && firstTab) {
      return { index: true, element: <PlaceholderPanel tab={firstTab} /> };
    }
    return {
      path: section.slug,
      element: <SectionLayout section={section} />,
      children: [
        { index: true, element: <Navigate to={firstTab?.slug ?? ""} replace /> },
        ...section.tabs.map((tab) => ({ path: tab.slug, element: <PlaceholderPanel tab={tab} /> })),
      ],
    };
  });
}

export const routes: RouteObject[] = [
  {
    path: "/",
    element: <AppShell />,
    children: [...sectionRoutes(), { path: "*", element: <NotFound /> }],
  },
];
