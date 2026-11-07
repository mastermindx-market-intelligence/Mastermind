# Portfolio consumption of the selected Sector generation

The existing `get_sector_rotation` MCP tool reads the same selected-generation owner as Macro. Its public selectors remain `legacy`, `sector_dossiers`, and `sector_windows`; the last selector requires one explicit sector ETF. No new tool, publisher, generation selector, scheduler, authentication path or trading authority is introduced.

## Source binding

The deployed Mastermind process must have its normally installed, pinned Macro library at `vendor/macro` and the existing `MACRO_SECTOR_GENERATIONS_ROOT` configuration pointing to Macro's private native generation store. The root must be absolute, non-root, without parent traversal or surrounding whitespace. The incumbent native facade still checks filesystem and snapshot integrity. The consumer never creates that directory, publishes a snapshot, changes the selected pointer, or retries through the static Central artifact.

The Macro dependency must include the native generation contract, wire encoder, Sector view engine and their existing publisher/freshness modules. A sparse checkout containing only `engine` and `lib` is insufficient. Advance or provision this dependency through the existing deployment owner with an accepted source revision. Qualification against a separate source worktree is not a production dependency update.

The two existing ordinary CI checkouts use immutable Macro candidate `91add9613ad29dcfb82ff75036dd6519cfc6c06f` with `engine`, `lib`, and `scripts` for this integration qualification. The existing strict shard validator records that same source contract, and the existing RWE checkout guidance includes the same script dependency. This is an explicit CI-only dependency admission, supported by the real-owner tests, while Macro PR 10780's own delivery gates remain binding. The separate paired Brain production fixture is unchanged. No moving branch, mixed source overlay, test skip, credential expansion, runtime data or second CI owner is introduced.

Mastermind's `scripts` initializer appends only its own installed `vendor/macro/scripts` path. This makes the two existing Macro owner modules importable even when Mastermind's scripts package was imported before `bot`. Mastermind's own scripts remain first. There is no ambient package discovery, module replacement, copied publisher or change to Macro's initializer.

If configuration or the native dependency is absent, the tool reports a bounded unavailable state. It does not retain static PSL measurements under a native source label.

## Capture and projection

Each accepted read invokes the incumbent selected-generation facade once for the fixed five-member Sector bundle. The facade verifies the selected manifest and captures its bytes. The existing Macro semantic projector and 4 MiB preview-wire encoder then qualify that same capture. Portfolio passes the captured original Central document to its existing parsers; it does not substitute the narrower public preview core, which omits legacy market and basket fields.

All three MCP projections disclose the same bounded public `native_receipt` in source health. Its `content_sha256` identifies the owner's authorized representation. It is not a hash of the MCP response, raw Central, or transport bytes. Its generation ID, input version, source session, publication clock and qualification come from that one capture.

A pointer change after capture cannot mix the original Central with a successor's receipt. A later tool call or navigation may read the newly selected generation and reports its new identity; URLs do not freeze an old generation forever.

The existing dossier stays 21/63 sessions. The exact companion stays 5/20/63 sessions, with its original absolute and SPY-relative values, clocks, qualifications and all-eleven status coverage. These parsers and selectors retain their existing ownership.

## Honest qualification and bounded output

Owner `accepted` maps to source health `fresh` and `stale: false`; owner `stale` maps to `stale` and `stale: true`. Owner `degraded` remains explicit in the native receipt and maps to `unknown` with `stale: null`, because degradation alone does not establish temporal staleness. None of these mappings establishes original historical availability or changes dossier/PIT limitations.

The native receipt is included before the existing dossier and exact-window 7,200-character/byte checks. The native legacy path also checks the complete packet before the generic serializer: if it cannot fit, it withdraws the whole measurement packet with `native_legacy_transport_budget_exceeded`. It never silently drops a sector, window or reason. Existing non-native parser fixture behavior is preserved.

Storage, contract, import and size failures expose closed reason codes without private exception details or local source paths. Every packet remains contextual. Existing ranking, sizing, trading, gating and escalation restrictions remain in force.

## Qualification and release evidence

Run the focused suites in the normal dependency-complete test environment with the pinned Macro installation available:

```bash
PYTHONDONTWRITEBYTECODE=1 python -m pytest -q \
  tests/test_portfolio_sector_native_generation.py \
  tests/test_portfolio_sector_dossiers.py \
  tests/test_portfolio_intelligence.py \
  tests/test_portfolio_intelligence_mcp.py
```

The native suite publishes only to pytest temporary directories through the real existing publisher. It covers both package import orders, ambient-package exclusion, all three real MCP serializers, all eleven exact-window selections, pointer replacement after capture, corrupted retained members, missing configuration/selection/dependency, bounded failures and qualification aging without read-side writes. Its fixture provenance records which raw documents are synthetic reconstructions of a captured preview.

Source-linked implementation and current release evidence live in [Mastermind #1202's native-consumer leaf](https://github.com/mastermindx-market-intelligence/Mastermind/issues/1202#issuecomment-6710917714). Source tests and controlled browser fixtures do not prove deployed native-root binding or authenticated production navigation. Those remain required before the original project is accepted.
