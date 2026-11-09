// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { ResearchEvidenceEntry } from "./ResearchEvidenceEntry";
import { evidenceUrl } from "./evidence-contract";
afterEach(cleanup);
it("actual citation entry supplies usable OS-default render controls without storage", async () => {
  const id = `rvitem.v1.${"a".repeat(64)}`;
  const text = "Long literal " + "x".repeat(800);
  const storage = vi.spyOn(Storage.prototype, "setItem");
  const { container } = render(<ResearchEvidenceEntry itemId={id} signOut={async () => {}}
    transport={{ available: () => true, authGeneration: () => 1, subscribe: () => () => {},
      signIn: async () => {}, readEvidenceItem: async () => ({ id, title: "Source title", text,
        url: evidenceUrl(id), metadata: { coverage: "COMPLETE_BOUNDED_ITEM" } }) }} />);
  await screen.findByText("Source title");
  expect(container.querySelector(".shell")?.getAttribute("data-theme")).toBe("dark");
  expect(container.querySelector(".shell")?.getAttribute("lang")).toBe("en");
  await act(async () => fireEvent.click(screen.getByRole("button", { name: "Change language" })));
  expect(screen.getByRole("heading", { name: "来源片段" })).toBeTruthy();
  expect(container.querySelector(".shell")?.getAttribute("lang")).toBe("zh-CN");
  await act(async () => fireEvent.click(screen.getByRole("button", { name: "切换主题" })));
  expect(container.querySelector(".shell")?.getAttribute("data-theme")).toBe("light");
  expect(container.querySelector("pre")?.className).toBe("visible-text");
  expect(container.querySelector("pre")?.textContent).toBe(text);
  expect(storage).not.toHaveBeenCalled(); storage.mockRestore();
});
