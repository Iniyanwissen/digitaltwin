import { describe, expect, it } from "vitest";

import { NAVIGATION, tabPath } from "./navigation";

describe("navigation", () => {
  it("has unique section slugs", () => {
    const slugs = NAVIGATION.map((s) => s.slug);
    expect(new Set(slugs).size).toBe(slugs.length);
  });

  it("has unique tab paths and at least one tab per section", () => {
    const paths = NAVIGATION.flatMap((s) => s.tabs.map((t) => tabPath(s, t)));
    expect(new Set(paths).size).toBe(paths.length);
    for (const section of NAVIGATION) expect(section.tabs.length).toBeGreaterThan(0);
  });

  it("keeps the sidebar small", () => {
    expect(NAVIGATION.length).toBeLessThanOrEqual(8);
  });
});
