import { useEffect, useState } from "react";

export interface ConversationListNavigationScope {
  readonly host: object | undefined;
  readonly authGeneration: number;
  readonly hostGeneration: number | null;
}
interface Navigation {
  scope: ConversationListNavigationScope;
  view: "list" | "detail";
  query: string;
  showAllProjects: boolean;
  selectedKey: string | null;
  projectReturn: string | null;
  focusRequest: number;
  restore: boolean;
}
const sameScope = (a: ConversationListNavigationScope, b: ConversationListNavigationScope) =>
  a.host === b.host && a.authGeneration === b.authGeneration && a.hostGeneration === b.hostGeneration;
const empty = (scope: ConversationListNavigationScope): Navigation => ({
  scope: Object.freeze({ ...scope }), view: "list", query: "", showAllProjects: false,
  selectedKey: null, projectReturn: null, focusRequest: 0, restore: false,
});

/** Ephemeral list/return intent only. No reads, history registry, pending
 * operation, selection mutation or persistent query storage is introduced. */
export function useConversationListNavigation(scope: ConversationListNavigationScope) {
  const [stored, setStored] = useState(() => empty(scope));
  // Mask immediately during the first render of a new principal/host epoch.
  const current = sameScope(stored.scope, scope) ? stored : empty(scope);
  useEffect(() => {
    setStored(old => sameScope(old.scope, scope) ? old : empty(scope));
  }, [scope.host, scope.authGeneration, scope.hostGeneration]);
  const update = (change: (value: Navigation) => Navigation) =>
    setStored(old => change(sameScope(old.scope, scope) ? old : empty(scope)));
  return {
    view: current.view,
    query: current.query,
    showAllProjects: current.showAllProjects,
    projectReturn: current.projectReturn,
    restoreFocus: current.restore
      ? { key: current.selectedKey, request: current.focusRequest } : undefined,
    changeQuery: (query: string) => update(value => ({ ...value,
      query: query.slice(0, 128), showAllProjects: false, restore: false })),
    showAll: () => update(value => ({ ...value, showAllProjects: true })),
    /** Explicit global navigation, separate from every original-draft intent. */
    showList: () => update(value => ({ ...value, view: "list", projectReturn: null, restore: false })),
    /** Existing Edit draft/current-window callbacks use this intent; it grants
     * no content access and never substitutes the new list for the draft. */
    showCurrentDetail: (selectedKey: string | null = null) => update(value => ({ ...value,
      view: "detail", selectedKey, projectReturn: null, restore: false })),
    rememberProject: (workRef: string, selectedKey: string) => update(value => ({ ...value,
      projectReturn: workRef, selectedKey, restore: false })),
    backToList: () => update(value => ({ ...value, view: "list", projectReturn: null,
      focusRequest: value.focusRequest + 1, restore: true })),
    backFromNewConversation: () => update(value => ({ ...value, view: 'list', projectReturn: null,
      selectedKey: 'new-conversation', focusRequest: value.focusRequest + 1, restore: true })),
  };
}
