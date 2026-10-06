# Atelier observed conversation window

`ConversationWindow` composes the existing `mastermind.product_projection.v1` and
decoded Window/Mission contracts. The current reader proves a bounded managed turn
window and, when the canonical predicate passes, an observed Job/Attempt association.
It supplies no provider conversation ID, session identity or binding generation.
Neither a projection-context session key nor a Mission runtime card fills that gap.
The component rechecks the association and never promotes the window to an exact
managed conversation or full transcript.

Paper: Mastermind OS `01M3NRCX55B452A12819WNE1RH`, page `p-C-0`, CH1 `IZB-0`,
CH6 `K5X-0`, CH91 `KDN-0`; read on 2026-10-04 with token hash `fd2ed32e`.
The implementation retains the 760–880px reading measure, Inter 18/29 desktop and
16/25 mobile response text, 24px mobile gutters, 44px controls, restrained result
panel and composer. Illustrative Paper identities, user messages, model controls,
reviews and result counts are not substituted for missing owner data. Without a
structured answer heading, the complete owner-visible text remains unmodified.

Evidence and context are read-only companion regions. Their controls move focus into
the panel; Close/Escape returns focus. They do not unmount the transcript or replace
the shell-controlled draft. Auth, target, binding and source revision/state changes
unmount inspection state synchronously. WITHHELD hides content, references and draft.
An adverse window does not suppress independently qualified Mission effect truth.
Seven receipt dimensions remain separate; unknown effect offers no resend action.
Even a result qualified for the same Project is withheld from this window's evidence
unless its exact Job/Attempt matches the window association. A sibling result is
UNASSOCIATED here and contributes neither its summary nor its source reference.

`drafts.ts` stores only ephemeral unsent text as immutable React state. The shell
must retain that state above route components and call `alignDrafts` on each increasing
host auth epoch, including sign-out, to discard all previous drafts. `readDraft` also
refuses any epoch mismatch before a cleanup effect can run. Project/root/session/binding
keys isolate text; source revision changes preserve the draft. These keys do not prove
a window/session association or transfer a draft to a successor. A stale-auth write is
rejected. No browser storage, transcript cache, session registry or message queue exists.

The composer is explicitly an unaddressed draft and Send is always unavailable here.
The canonical exact-session/command owner remains the existing orchestrator binding
and operation controller. This passive view does not replace their capability checks,
receipt reconciliation or original-operation recovery. No command callback is accepted.

Source tests cover 22 cases across draft isolation, navigation detours, six source
states, privacy invalidation, evidence focus and unknown-effect behavior. App routing,
live owner acquisition, actual browser/native visual comparison, installed session
binding, mobile keyboard behavior and production acceptance remain separate gates.
The companion currently follows the reading region on narrow screens; the final
installed full-height mobile sheet still requires actual browser qualification.
