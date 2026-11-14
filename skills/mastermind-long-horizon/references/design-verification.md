# Design and real-interface verification

## Establish the consumer before drawing

Name the user, the primary journey, the existing design system and the actual
runtime/data owner. Preserve the approved source and product acceptance. Reuse
maintained components and native capabilities before inventing a commodity widget,
control service or navigation system. Use original or properly licensed assets.

For an actual Paper or Figma task load that product's governing workflow before
its tools. A retrieved design is a reference, not permission to overwrite another
designer's board. Preserve stable file/artboard/node identity and active writers.
For a code-only task use the existing component library and tokens; do not force a
new design tool or create mockups that postpone the needed implementation.

## Design states, not only the happy screenshot

Make the main next action obvious without hiding the full goal. For long-horizon
agents expose objective, current task, pending child returns, evidence, precise
blocker and supported native controls. Keep deep diagnostic details expandable.
Use plain labels distinguishing queued, running, waiting for input, cancelled,
unknown effect, result available, verified and accepted.

Cover loading, empty, partial, stale, denied, offline, retryable technical failure,
uncertain action, and successful return. Missing evidence is not a zero value or a
green badge. A clean mock conversation must not imply the real runtime is wired.
Preserve unsent drafts and the user's selected project during reconnect and errors.

Keep queue-next, steer-current, pause-goal and stop-run separate. Explain the scope
of a child cancellation. Disable unsupported actions with an exact reason rather
than pretending a queued message executed a native control. Never show a restart
as a harmless refresh when it could abandon active work or replay effects.

## Responsive and accessible execution

Use the existing project's responsive breakpoints; where no standard exists,
exercise representative narrow/mobile, tablet and desktop layouts (approximately
390, 768 and 1440 CSS pixels), plus the real target window. Test intermediate widths
rather than optimizing only three screenshots. Preserve the primary task/action
and source context when a desktop rail becomes a narrow drawer.

Check semantic labels, keyboard traversal, visible focus, modal focus containment
and return, Escape behavior, readable contrast and zoom, reduced motion, loading
announcements, overflow, long labels, localization and screen-reader names. Do not
encode state solely by color. Keep touch targets comfortable and tab order logical.
Do not change global browser/OS accessibility settings just to obtain a screenshot.

## Verify through the existing browser/desktop owners

Run affected component and integration tests, then exercise the actual consumer
path. Select the correct Chrome profile/tab via the Mastermind plugin or the exact
native app/window via Peekaboo. Never switch a live personal tab for convenience.
Record the tested source build, viewport, locale/theme, state and original action.

Use DOM/accessibility inspection to confirm control semantics and actual enabled
states. Use screenshots to inspect alignment, clipping, density, hierarchy and
responsive behavior. Neither screenshot similarity nor a passing component test
alone proves a working authenticated workflow. A visual model's opinion must be
corroborated by observed controls and real behavior.

Review every changed meaningful state, not just the first rendered frame. Verify
keyboard-only operation, interrupted return, duplicate-action prevention, selected
identity isolation and stale-data handling. Redact or avoid unrelated private data
before sharing artifacts; do not persist credentials in screenshots.

## Preserve truthful evidence

Separate editable design, source implementation, fixture/browser test, installed
native tool, live provider use and final product acceptance. Keep exact references
and explicit limitations. A natural-language statement that an element looks good
is not a browser test. A generated image is not a screenshot of the implemented UI.

At each useful milestone fix visible/functional defects, rerun affected checks,
save and read back the source/evidence, then continue the next unmet parent
criterion. Do not keep polishing a peripheral panel while the primary user journey
cannot complete. Do not declare harness parity from one attractive demo.
