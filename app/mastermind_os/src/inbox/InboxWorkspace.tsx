import { useRef } from "react";
import type { TerminalSharingSource } from "../terminal/terminal-sharing-host";
import { Inbox, type InboxProps } from "./Inbox";
import { TerminalSharingInbox } from "./TerminalSharingInbox";

export interface InboxWorkspaceProps extends Omit<InboxProps, "sharingRequests"> {
  locale: "en" | "zh-CN";
  /** Caller-owned native Terminal capability; never borrowed from workspace auth. */
  terminalHost?: TerminalSharingSource;
}

/** The accepted Paper slot stays outside the Mission-keyed owner context.
 * Only replacement of the actual Terminal capability resets its subtree;
 * the accepted host/hook owns its session, reads and handoff attempts.
 */
export function InboxWorkspace({ locale, terminalHost, ...office }: InboxWorkspaceProps) {
  const owner = useRef({ host: terminalHost, key: 0 });
  if (owner.current.host !== terminalHost) {
    owner.current = { host: terminalHost, key: owner.current.key + 1 };
  }
  return <Inbox {...office} locale={locale} sharingRequests={
    <TerminalSharingInbox key={owner.current.key} host={terminalHost} locale={locale} />
  } />;
}
