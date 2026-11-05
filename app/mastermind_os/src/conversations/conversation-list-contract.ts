/** UI projection over qualified existing reads. These locators grant nothing. */
export type ConversationListSourceState =
  | "CURRENT" | "PENDING" | "STALE" | "UNAVAILABLE"
  | "WITHHELD" | "UNASSOCIATED" | "UNKNOWN";

export interface CurrentConversationLocator {
  readonly kind: "current";
  readonly workRef: string;
  readonly rootJobId: string;
  readonly jobId: string;
  readonly attemptId: string;
  readonly selectionRef: string;
  readonly sourceRef: string;
  readonly sourceRevision: string;
  readonly epoch: string;
  readonly authGeneration: number;
}

export interface ConversationProjectLocator {
  readonly kind: "project";
  readonly workRef: string;
  readonly sourceRef: string;
  readonly sourceRevision: string;
  readonly authGeneration: number;
}

export interface ConversationListRecentRow {
  readonly key: string;
  readonly locator: CurrentConversationLocator;
  /** Actual associated Mission title, never generated from reply prose. */
  readonly title: string | null;
  readonly projectTitle: string | null;
  /** Current-window owner observation clock, not a saved/last-message clock. */
  readonly observedAt: string;
  /** Genuine ephemeral current draft only; never a saved-draft receipt. */
  readonly unsentDraft: boolean;
}

export interface ConversationListProjectRow {
  readonly key: string;
  readonly locator: ConversationProjectLocator;
  readonly title: string | null;
  /** Existing authored project next action; optional local search metadata. */
  readonly nextAction: string | null;
}

export interface ConversationListSource {
  readonly owner: "CURRENT_WINDOW" | "PROJECT_CATALOGUE";
  readonly state: ConversationListSourceState;
  readonly observedAt: string | null;
  readonly revision: string | null;
}

export interface ConversationListModel {
  readonly schema: "mastermind.conversations_list_projection.v1";
  /** Presentation epoch only. Actual host identity is fenced by the App owner. */
  readonly authGeneration: number;
  readonly recentState: ConversationListSourceState;
  readonly projectsState: ConversationListSourceState;
  readonly recent: readonly ConversationListRecentRow[];
  readonly projects: readonly ConversationListProjectRow[];
  readonly sources: readonly ConversationListSource[];
  /** No global history read or cross-project session enumeration is performed. */
  readonly historyCoverage: "NOT_ENUMERATED";
}

export interface ConversationListProps {
  readonly model: ConversationListModel;
  readonly locale?: "en" | "zh-CN";
  readonly theme?: "dark" | "light";
  readonly query: string;
  readonly onQueryChange: (query: string) => void;
  readonly showAllProjects: boolean;
  readonly onShowAllProjects: () => void;
  /** Changes only on explicit Back, never on mount or source refresh. */
  readonly restoreFocus?: { readonly key: string | null; readonly request: number };
  /** Each actual App callback rechecks current host/auth/source before routing. */
  readonly onOpenCurrent: (locator: CurrentConversationLocator) => boolean;
  readonly onOpenProject: (locator: ConversationProjectLocator) => boolean;
  readonly onOpenMetaCeo: () => void;
  readonly onSourcesAndAccess: () => void;
  readonly onRefresh?: () => void;
  /** Supplied only by a real new-conversation owner; absence is not a grant. */
  readonly onNewConversation?: () => void;
  /** Independent authenticated Session source, never a current-window grant. */
  readonly onOpenSessionRequests?: () => boolean;
}
