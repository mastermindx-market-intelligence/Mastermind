# Sovereign auction context: source-only Mastermind consumer candidate

This candidate is based on Mastermind `c7e47c859eb2925c5626931fd511800773ba09ac`.
It is not deployed, published, merged, or a claim that the producer path is live.
Root is the sole canonical external writer. All candidate files are beneath this
patch directory; full existing target files were copied from their verified Git
blob preimages before narrow edits.

## Boundary and behavior

`brain/sovereign_auction_context.py` is a pure clock-injectable validator plus a
fresh local reader of `vendor/macro/site/feeds/event_calendar.json`. It consumes
only the exact nested `sovereign_auction_context` W1 schema. It does not fetch,
produce observations, cache, import risk/decision modules, or infer a score,
probability, drain, settlement, or freshness policy.

The reader requires the exact context-only/research-only/null-probability/not-
scored authority on both context and rows. It rejects future evidence against
both producer cutoff and the injected current clock; scheduled future clocks
remain allowed. Exact aware ISO clocks, finite non-boolean decimal values,
nonnegative USD amounts, official HTTPS source URLs, lifecycle states, bounded
30-day coverage and result evidence are validated. Offering/result decimal
strings keep their original values and units. Unknown fields, including hostile
`band`/`stressed` and dangerous auction aliases, do not leave the allowlist.
Source-health observations, successful receipt clocks, attempts/failures, ages
and null freshness thresholds remain separate; freshness is always unassessed.
Source-health clocks must be ordered, the recorded age must equal the producer-
cutoff age, and first-observed cannot follow the selected vintage. Lifecycle and
issue-calendar labels must agree with the producer cutoff in ET. Original
Treasury security type and class flags must agree with the normalized class;
missing flags remain unknown rather than being coerced false.

`app/web.py` adds one helper/call after existing rotation enrichment. Only the
served dictionary gets the sibling. It never writes stored Market View, fills
the stored `event_calendar` plane, changes availability/coverage/tilt authority,
or enters a prompt/decision/risk path. Missing/corrupt stored Market View retains
its existing 404/500 status. Any display-only helper failure leaves the existing
response fields intact and supplies an explicit unavailable sibling.

`app/static/market_view.html` adds a sibling section using the current theme,
layout, `data-lang` preference, and bilingual EN/ZH copy. Scheduled auctions,
awaiting results and tentative observations appear before past observed results;
producer chronological order stays intact within each group. Five rows per group
are immediately visible, with group counts and native expand controls for the
remaining bounded producer rows. Actual classes, episode identifiers, USD amounts,
auction/issue dates, scheduled deadline clocks, evidence clocks, unknown/result
states, source-health failures and official links are escaped before HTML output.
The section states that it is outside decision-plane coverage, Research only,
Not scored, and Freshness unassessed. New styles are scoped to that section.

`config/contracts.yml` only lists the new reader under existing
`feeds-plane.consumer_modules`; its display-only/ADVISORY effect stays intact.
No controller/forecast/config enable flag is added. Production display remains
OFF through the existing producer publication boundary: absent nested data gives
explicit unavailable context. No producer publication has been performed here.

## Exact fixtures

`tests/fixtures/sovereign_auction_context/event_calendar.json` is byte-identical
to the shared authoritative fixture supplied by root. SHA256:
`b3e7eb3b5ca32e0ebe3d23011d9fa917841f38e9fb436c73c8ca62b53b01d0cb`.
It uses the exact original upcoming response and observed upper bound
`2026-10-08T22:12:22.414829+00:00`, at producer cutoff 22:15Z. Three genuine future
Bill auctions pass. It is fixture evidence, not live availability evidence.

`bill_observation.json` is a W1 `make_observation` receipt generated from the
real `bill_future_nonstandard_deadline.json` row encoded as a one-row JSON list
(the producer's current JSON adapter requires a list), using its official
announcement URL and the original observed upper bound. Its `build_context`
wrapper `bill_event_calendar.json` is generated at `2026-10-08T23:00:00+00:00`.
The Bill's offering is exactly `95000000000` USD; competitive deadline is
`2026-10-13T17:00:00+00:00`; result and probabilities remain null. The immutable
receipt includes its exact list-body hash. No historical forecast is claimed.

## Verification and remaining acceptance

Run from the candidate/repository root:

```sh
python -m unittest discover -s tests -p 'test_sovereign_auction*.py' -v
node tests/test_sovereign_auction_renderer.cjs
```

Local result after scoped review: **19 pure validator/reader tests passed**. The native API test class
is **blocked/skipped because this scratch environment has no FastAPI** and does
not contain the complete application repository. No replacement FastAPI or
portfolio modules were used to create an apparent pass.

The renderer unit test executes the actual HTML script's rendering functions and
passes: genuine fixture amounts/clocks, EN/ZH, future priority with 43 past result
rows plus 3 future auctions, count/expand, awaiting-result/null states, escaped
malicious upstream text/attribute values, unsafe-link suppression and explicit
unavailable. This is renderer-function evidence; it does not establish browser
layout, full HTTP route operation, accessibility or live publication.

The independently inspected, actual four-source capture also passed through the
final W1 producer and this consumer at a fixed 2026-10-08T23:00:00Z cutoff:
74 observed episodes, four source-health records, and Bill/Note/Bond/TIPS/FRN
classes. No CMB was present in that current capture; a separate synthetic class-
consistency control covers CMB. Exact input and module hashes, executed commands,
stdout/stderr and proof limits are retained in `REVIEW_VERIFICATION.json`; the
bounded review findings are in `REVIEW_sovereign_auction_context.md`.

The four native API tests are prepared for root's official workspace. They call
the actual API function and actual local reader with a frozen injected clock,
check original no-cache headers and stored bytes/authority fields, fresh rereads,
existing absent/corrupt Market View status, fail-soft display composition,
unchanged `decision_context.assemble`/`prompt_summary`, unchanged PM enrichment,
and unchanged actual crash-auction helper even with hostile band/stressed fields
under the new sibling. Root must run them with the full real dependencies and
complete the actual route, browser and publication-path verification. Those
checks are not accepted locally by mocking missing application modules.

Forbidden source paths (`brain/market_view.py`, `brain/decision_context.py`,
`brain/anticipation.py`, `brain/treasury_context.py`, PM/strategist, portfolio,
flags, risk/exit engines) are not changed. No source publication, provider use,
external messages, deployment or merge was performed.
