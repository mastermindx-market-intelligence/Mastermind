// @vitest-environment jsdom
import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";
import { useConversationListNavigation } from "./useConversationListNavigation";
afterEach(cleanup);
it("preserves filter/continuation/selection across actual detail and project return intents without redirecting an original draft to the list", () => {
  const scope = { host: {}, authGeneration: 3, hostGeneration: 7 };
  const { result } = renderHook(() => useConversationListNavigation(scope));
  act(() => { result.current.changeQuery("Original project"); result.current.showAll(); result.current.showCurrentDetail("current:original"); });
  expect(result.current.view).toBe("detail");
  act(() => result.current.backToList());
  expect(result.current.query).toBe("Original project"); expect(result.current.showAllProjects).toBe(true);
  expect(result.current.restoreFocus).toEqual({ key: "current:original", request: 1 });
  act(() => result.current.rememberProject("WS:ONE", "project:WS:ONE"));
  expect(result.current.projectReturn).toBe("WS:ONE");
  act(() => result.current.backToList());
  expect(result.current.projectReturn).toBeNull();
  expect(result.current.restoreFocus).toEqual({ key: "project:WS:ONE", request: 2 });
  act(() => result.current.showCurrentDetail()); // Existing Memory/Edit draft intent, not a guessed list row.
  expect(result.current.view).toBe("detail"); expect(result.current.query).toBe("Original project");
  act(() => result.current.showList());
  expect(result.current.view).toBe("list"); expect(result.current.restoreFocus).toBeUndefined();
});
it("clears private query/return state on real host or auth epochs while preserving source-refresh query within one owner", () => {
  const host = {}, initial = { host, authGeneration: 3, hostGeneration: 7 };
  const { result, rerender } = renderHook(({ scope }) => useConversationListNavigation(scope), { initialProps: { scope: initial } });
  act(() => { result.current.changeQuery("Private topic"); result.current.rememberProject("WS:ONE", "project:WS:ONE"); });
  rerender({ scope: { ...initial } }); expect(result.current.query).toBe("Private topic");
  rerender({ scope: { ...initial, host: {} } });
  expect(result.current.query).toBe(""); expect(result.current.projectReturn).toBeNull();
  act(() => result.current.changeQuery("New private topic"));
  rerender({ scope: { ...initial, authGeneration: 4 } });
  expect(result.current.query).toBe(""); expect(result.current.view).toBe("list");
});
