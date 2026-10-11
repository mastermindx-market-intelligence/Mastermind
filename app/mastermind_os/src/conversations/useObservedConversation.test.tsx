// @vitest-environment jsdom
import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { useObservedConversation } from "./useObservedConversation";

afterEach(cleanup);
const source = { identity: "exact-result-v1", excerpt: "Keep the source exact.", label: "Test result · freshness unverified" };
const initial = { auth: 3, selection: { workRef: "WS:PROJECT", rootJobId: "JOB-1" }, content: true };
function setup() {
  return renderHook(props => useObservedConversation(props.auth, props.selection, props.content), { initialProps: initial });
}
describe("draft source owner integration", () => {
  it("confirms insertion synchronously once and clears only through guarded Undo", () => {
    const { result } = setup();
    act(() => result.current.changeDraft("Original"));
    const append = result.current.appendSource;
    let first = false, second = true;
    act(() => { first = append(source, 1); second = append(source, 1); });
    expect(first).toBe(true); expect(second).toBe(false);
    expect(result.current.draft).toBe(`Original\n\n“${source.excerpt}”\nSource: ${source.label}`);
    expect(result.current.draftRevision).toBe(2);
    act(() => { expect(result.current.undoSource(source.identity, 2)).toBe(true); });
    expect(result.current.draft).toBe("Original");
  });
  it.each(["auth", "target", "permission"])("rejects an old append closure after %s changes", boundary => {
    const { result, rerender } = setup(); const append = result.current.appendSource, change = result.current.changeDraft;
    const next = { ...initial };
    if (boundary === "auth") next.auth++;
    if (boundary === "target") next.selection = { workRef: "WS:OTHER", rootJobId: "JOB-2" };
    if (boundary === "permission") next.content = false;
    rerender(next);
    act(() => { expect(append(source, 0)).toBe(false); change("Old scope typing"); });
    expect(result.current.draft).toBe(""); expect(result.current.draftInsertion).toBeNull();
  });
  it("invalidates draft bytes before a late old-auth callback can restore them", () => {
    const { result } = setup(); const append = result.current.appendSource;
    act(() => result.current.changeDraft("Private original"));
    act(() => { result.current.invalidateAuth(); expect(append(source, 1)).toBe(false); });
    expect(result.current.draft).toBe(""); expect(result.current.draftInsertion).toBeNull();
  });
  it("preserves separate drafts through project detours and does not retarget source callbacks", () => {
    const { result, rerender } = setup();
    act(() => result.current.changeDraft("Project A")); const appendA = result.current.appendSource;
    rerender({ ...initial, selection: { workRef: "WS:OTHER", rootJobId: "JOB-2" } });
    act(() => { result.current.changeDraft("Project B"); expect(appendA(source, 1)).toBe(false); });
    rerender(initial); expect(result.current.draft).toBe("Project A");
  });
});
