import { Navigate, type RouteObject } from "react-router";

import { PlaceholderPanel } from "@/components/PlaceholderPanel";

import { AppShell } from "./AppShell";
import { type NavSection, type NavTab, NAVIGATION } from "./navigation";
import { NotFound } from "./NotFound";
import { PAGES } from "./pages";
import { SectionLayout } from "./SectionLayout";

function pageFor(section: NavSection, tab: NavTab) {
  const Page = PAGES[`${section.slug}/${tab.slug}`];
  return Page ? <Page /> : <PlaceholderPanel tab={tab} />;
}

function sectionRoutes(): RouteObject[] {
  return NAVIGATION.map((section) => {
    const [firstTab] = section.tabs;
    if (section.slug === "" && firstTab) {
      return { index: true, element: pageFor(section, firstTab) };
    }
    return {
      path: section.slug,
      element: <SectionLayout section={section} />,
      children: [
        { index: true, element: <Navigate to={firstTab?.slug ?? ""} replace /> },
        ...section.tabs.map((tab) => ({ path: tab.slug, element: pageFor(section, tab) })),
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
