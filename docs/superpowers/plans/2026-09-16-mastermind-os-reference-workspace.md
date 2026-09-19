# Mastermind OS Reference Workspace Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans for the admitted slice. This operation executes its bounded reference directly; it starts no external worker.

**Goal:** Produce a usable, testable offline reference of the first integrated OS journey without suggesting that the runtime or command plane is connected.

**Architecture:** A single self-contained HTML document renders a bounded recorded-evidence checkpoint and four explicit presentation scenarios. It performs no network requests, storage writes, provider actions or canonical mutations. This is product-contract verification, not installation or production acceptance.

**Tech Stack:** HTML, CSS, ordinary browser JavaScript; Python pytest + Playwright in an already-equipped validation environment. No runtime/library/dependency manifest changes.

**Spec:** `docs/superpowers/specs/2026-09-16-mastermind-os-integrated-rollout-design.md`

## Global constraints

- Existing CCR and Fabric responsibilities remain; no new canonical workstream or runtime owner.
- Only the six paths enumerated in the specification may change.
- The Chairman has approved the integrated OS direction and delegated end-to-end ownership. The reference is one intermediate proof, never the parent completion.
- No existing Figma file, app/runtime/auth/provider/shared test/CI source is touched.
- Every screen says recorded reference or synthetic scenario; no current running count, live conversation, completed release, entitlement quantity or autonomous-supervision claim.
- Every effect control remains unavailable; navigation is functional and read-only.
- User/source strings use text rendering, not HTML interpolation.
- Default is decision-first Today; Programs opens a workspace; machinery is explicit Advanced.
- Tests must run in a real local browser, observe an intended missing-artifact RED, then verify real document behavior and negative states.
- No third-party requests, analytics, remote assets, service worker, persistent state or automatic updates.

## Files and interfaces

The HTML document is the complete reference artifact. It has no external runtime API and must not be imported as an application backend. Hash routes are closed to `today`, `program`, `workspace`, `connections`, `evidence`, `ask`, and `advanced`; unknown routes safely return to Today. Scenario values are closed to `recorded`, `source_missing`, `effect_unknown`, and `corrected`.

The browser suite serves only the exact authored HTML from an ephemeral loopback test origin. It leaves browser policy unchanged; the file can also be opened directly where file navigation is allowed. It must not mock the rendering, replace HTTP responses or create test hooks inside the reference. The acceptance JSON records only exact artifact hashes and this test campaign, not live company state.

### Task 1: Freeze the human/machine outcome and source boundary

Files: the specification, this plan, `research/mastermind_os/README.md`.

- [ ] Verify current procedure pin and independent source custody.
- [ ] Record the full program scope, retained owners, seven release increments and real-path acceptance campaign.
- [ ] Mark #595 and the prior recorded workspace as retained evidence, not absent/rejected/shipped by inference.
- [ ] Publish exact limits: no runtime, no command connection, no Figma edits, no external workers.

Deliverable: an unambiguous design contract that a new principal can recover and a reviewer can reject independently of styling.

### Task 2: Test-first connected reference journey

Files: `research/mastermind_os/test_reference_workspace.py`, `reference_workspace.html`.

Discriminating examples:

```python
def test_reference_exists():
    assert HTML.is_file(), 'The integrated reference workspace has not been built'


def test_program_to_workspace(page):
    page.get_by_role('button', name='Open Mastermind OS', exact=True).click()
    expect(page.get_by_role('heading', name='Mastermind OS', exact=True)).to_be_visible()
    page.get_by_role('button', name='Open execution workspace', exact=True).click()
    expect(page.get_by_role('heading', name='Execution Fabric', exact=True)).to_be_visible()
    expect(page.get_by_text('Conversation is not connected', exact=True)).to_be_visible()
```

- [ ] Run the missing-artifact test and retain its intended failure.
- [ ] Implement the shell, Today, Program, Workspace, Connections, Evidence, Ask Sol and Advanced views.
- [ ] Use one shared bounded reference-data collection; do not create separate inconsistent graph/list sources.
- [ ] Verify every navigation control changes the intended view and every enabled details control opens usable information.

Deliverable: a complete navigable product journey rather than disconnected screens.

### Task 3: Truth, correction and intervention negatives

Same HTML and test file.

```python
def test_unknown_effect_never_enables_send(page):
    page.get_by_label('Reference scenario').select_option('effect_unknown')
    expect(page.get_by_text('Synthetic scenario · outcome unknown', exact=True)).to_be_visible()
    page.get_by_role('button', name='Open Mastermind OS', exact=True).click()
    page.get_by_role('button', name='Open execution workspace', exact=True).click()
    expect(page.get_by_role('button', name='Send instruction', exact=True)).to_be_disabled()
    expect(page.locator('.callout.bad').get_by_text('Reconcile the original operation. Do not resend.', exact=True)).to_be_visible()
```

- [ ] Missing-source scenario withholds all-clear and runtime totals while keeping known references readable.
- [ ] Unknown-effect scenario preserves original-operation reconciliation and disables send.
- [ ] Corrected-evidence scenario explicitly withdraws the prior support; it never silently rewrites the checkpoint.
- [ ] All non-recorded scenarios are persistently labeled synthetic on every route.
- [ ] Ask Sol has no dead message input and no implied paid/API substitute.

Deliverable: error states that preserve meaning and authority, not decorative red badges.

### Task 4: Accessibility, safety and responsive proof

Same HTML and test file; local screenshots are evidence attachments, not production captures.

```python
def test_keyboard_known_navigation(page):
    button = page.get_by_role('button', name='Programs', exact=True)
    button.focus()
    button.press('Enter')
    expect(page.get_by_role('heading', name='Mastermind OS', exact=True)).to_be_visible()


def test_no_horizontal_overflow(page):
    for width, height in [(1440, 1000), (1024, 768), (390, 844)]:
        page.set_viewport_size({'width': width, 'height': height})
        assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
```

- [ ] Known-target keyboard activation works; dialog Escape closes and restores focus.
- [ ] Connections has a usable equivalent list with the same items as its graph.
- [ ] Search reflects hostile text as text; unsupported hash routes fail safely.
- [ ] A restrictive hash-based Content Security Policy disables all network connections and form submission.
- [ ] The suite sees no external requests, JavaScript errors, local/session storage writes or runtime mutation API.
- [ ] Inspect desktop, narrow and failure screenshots; fix layout defects before claiming the reference passed.

Deliverable: real browser-tested reference with explicitly limited accessibility coverage, not a WCAG certification.

### Task 5: Immutable publication and existing-owner integration

Files: README and `reference_acceptance.json`; all source paths remain the same six-file envelope.

- [ ] Run the entire reference suite, syntax/diff checks and source scan.
- [ ] Record HTML/spec/plan/test hashes, browser/environment, actual test results and production-effect=false.
- [ ] Publish on the SAME managed operation branch. The first four contract/test records use sequential authenticated GitHub contents writes; the HTML and validation record use the reconciled owned workspace and one ordinary commit/push. Reconcile each effect before the next write.
- [ ] Fast-forward only the clean owned workspace to the four-record remote checkpoint, transfer the remaining source with exact hash readback, compare all six byte hashes, inspect the six-path diff, and open one Draft/HOLD PR. No reset, force or foreign workspace edit. Reconcile any uncertain write before repeating it.
- [ ] Cross-reference the exact published revision to existing #595, #600 and Macro #7120 through bounded evidence/intake comments.
- [ ] Send one compact same-root OS integration intake to incumbent Claude8 without overriding its current child rulings or pretending delivery is consumption.

Stop boundary for this reference: browser-verified artifact published, exact owner integration requested, and the missing authenticated producer contract named. The Mastermind OS parent remains nonterminal. Do not merge/install or mark a real R1/R2 capability complete from this reference.

## Next real implementation, not performed by this reference

The next source wave must pair the current owner-issued mission observation and visible-content/history resource with the actual CCR consumer. Admission requires exact producer version, grant/coverage/ordering contract, current source custody, a real usable input, and a browser acceptance target. Reuse the existing source instead of promoting this fixed checkpoint into a backend or creating a second transcript/graph store.

The current DF1 stream, #677/#653 admission work, Provider Capacity #688, AD-RET2, CCTX-1 and native PF1 work remain independently owned. Fable may stage economical child implementation under its existing authority only after it proves a supervision/return path; this plan itself launches no subagent.

## Execution checkpoint — 2026-09-16

The intended missing-artifact RED was observed before writing the HTML. Two source-only checks now pass; JavaScript syntax is validated separately. Playwright browser execution has not reached the document: default browser payload is absent, and the installed Chromium returns `ERR_BLOCKED_BY_ADMINISTRATOR` on direct-file and temporary loopback-preview navigation. No policy changes or cross-host browser retry were performed. Browser task checkboxes remain open.

The reference is safe to publish only as Draft/HOLD with those limitations and exact hashes. It is not eligible for source-release, product acceptance or deployment based on the current evidence.

Publication continuity: the first four records reached `498b0bfe23109e7feddcce73f73f54e0583048da` and the clean managed workspace was fast-forwarded to that exact head. Studio went offline during the first HTML write. After reconnection, a stat and exact-workspace check proved that HTML was absent, so that effect was reconciled as NONE before repeating the write on the same host/path. The complete native HTML then read back at SHA-256 `160426f6d9105fa946520d6c51d967453ebb00746b78973d45bb27d410892353`, identical to the sandbox candidate. Browser restrictions remain unchanged and browser acceptance is still unproven.

## Continuation repair: connected design graph and recoverable focus

The same six-path carrier now supplies a pure inline presentation module, consumed by both real SVG connection paths and the equivalent relationship list. No framework, package manifest, company graph store or runtime protocol is added. Seven relationships connect the existing six design nodes, with exact endpoint validation and no execution authority. Source tests execute that same module directly with Node; this is not simulated browser acceptance.

The same source repair changes the skip-link event to retain the active hash route, captures the search input before the transient result button is removed, and uses the tested connected/non-disabled focus-target selector on dialog close. Graph/list re-render returns focus to its replacement control. Four additional real-browser regressions cover edge/list equality, skip-link route preservation, search-dialog focus, and the narrow-screen equivalent list. They are required and unrun while the historical browser-policy blocker remains.

Verified sequence: eleven intended missing-model RED cases; fifteen source checks GREEN after independent-review repair; both inline scripts syntax-valid; three targeted mutations killed. The complete collection is fifty-four cases, including thirty-nine still-unverified browser cases. No browser, provider, installed Runtime, OAuth, live user session, or external worker was exercised by these tests. The pure helper result is not authority to check off Task 4's real-browser requirements.

Program integration advanced separately: #704 exact-head review 5228415542 resolves only the new route's strict two-key query question and requests seven bounded contract repairs. Same writer, same one-file records PR; R2A local tree remains partial, the authorized hot window remains in R2, and company acceptance comes only from its existing exact-artifact decision owner. Claude8 consumed and relayed this to the incumbent writer (1789593485.305139). Preserve the live-reader and DF1 writers and do not manufacture another implementation while awaiting their exact interfaces.
