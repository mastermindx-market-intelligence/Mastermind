import { screen, within } from "@testing-library/react";

/** Exercise the contextual user path; operational routes are not global links. */
export async function navigateCompanyOperation(
  user: { click(element: HTMLElement): Promise<void> },
  route: "Work" | "Programs" | "Fleet & Capacity",
) {
  // Full labeled sidebar exposes these same incumbent route owners directly.
  const label = route === "Work" ? "Work queue" : `${route} workspace`;
  const direct = screen.queryByRole("button", { name: label });
  if (direct) { await user.click(direct); return; }
  let context = screen.queryByRole("navigation", { name: "Company operations" })
    ?? screen.queryByRole("navigation", { name: "Project operations" });
  if (!context) {
    await user.click(screen.getByRole("button", { name: "Today" }));
    context = screen.getByRole("navigation", { name: "Company operations" });
  }
  await user.click(within(context).getByRole("button", {
    name: route === "Programs" ? "Open Programs" : route,
  }));
}


/** Explicit drilldown to retained legacy reader tabs from the Paper workspace. */
export async function openLegacyProjectTabs(user: {click(element: HTMLElement): Promise<void>}) {
  if (screen.queryByRole("tablist", {name:"Project workspace"})) return;
  await user.click(await screen.findByRole("button", {name:"Project details"}));
  await user.click(screen.getByText("More work details", {selector:"summary"}));
}
