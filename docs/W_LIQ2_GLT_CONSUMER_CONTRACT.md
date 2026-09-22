# W-LIQ.2 — GLT consumer contract (for W-LIQ.3 / W-LIQ.4)

**Status:** shipped in Mastermind PR #914, issue #119. Producer: Macro W-LIQ.1,
merge `38fd57a676de07c361040eea7d5e5127034063e1`, schema
`global_liquidity_transmission.v1`.

This note is the handoff #119 asks for. It says what a later wave may rely on, what it
must not redo, and what is deliberately absent.

---

## 1. The one seam

```
vendor/macro/site/liquiditydata/global_liquidity_transmission.json
        │  (the ONLY raw read in Mastermind)
        ▼
brain/liquidity_transmission.py          ← the sole reader
        │
        ├── context()            full artifact, or {} unless present AND valid AND fresh
        ├── market_plane()       compact plane payload; truthful even when absent/stale
        ├── audit_row()          perception/runlog row; both clocks, separately
        ├── decision_signals(s)  typed chokepoint — inert in every mode this wave
        ├── target(symbol)       {}  (see §4)
        └── opportunities(limit) []  (see §4)
                │
                ▼
brain/market_view.py::_adapt_liquidity_transmission
        │   plane "liquidity_transmission" — advisory, never in _VALIDATED_PLANES
        ▼
bot/phase2.py  → runlog "perception" row + data/brain/glt_audit.jsonl
```

**Do not add a second raw read.** A test (`TestSoleReader`) greps `brain/ bot/ bridge/
scripts/ app/ admin/` and fails on any other module that constructs the artifact path,
opens it, or `json.load`s it. A later wave that needs a new field adds it to the reader,
not to a new call site.

## 2. Clock law — inherit this, do not re-derive it

The producer names its own adapter seam and the reader honours exactly that naming:

| producer field | meaning | use |
|---|---|---|
| `freshness.clocks.evidence_available_at` | conservative all-evidence availability boundary | **the only freshness/age input** |
| `freshness.clocks.release_at` | documented alias of the above | same value; do not treat as separate |
| `freshness.clocks.first_known_at` | when the producer first published | the **known** clock (PIT/audit) — never freshness |
| `meta.generated_at` | when the wrapper was written | **never** evidence availability |
| `freshness.clocks.monetary_release_at` | monetary-only release | **never** the evidence boundary |
| `freshness.clocks.latest_component_observed_at` | newest component *reference* date | never availability |
| `freshness.clocks.state_asof` | economic/state grid date | never availability |
| file mtime | filesystem noise | never an input |

Three rules that are easy to lose and expensive to rediscover:

1. **`freshness.status` condemns but never certifies.** It was computed at write time and
   goes stale on the shelf. A producer declaring itself degraded makes the read stale; a
   producer declaring itself fresh cannot rescue an evidence clock beyond the horizon.
2. **A renamed adapter clock field is a contract change, not a redirect.** If
   `adapter_observed_at_field` stops saying `evidence_available_at`, the read goes
   `invalid`. Fix the reader deliberately; never follow a redirected clock.
3. **Staleness is a union, never an intersection.** `market_view._freshness()` counts
   trading days and `regime_frame._trading_days_since` **clamps a future date to 0
   sessions** — so the view cannot detect a future-dated clock at all. The reader's
   verdict is what catches it, and the adapter ORs the two. Neither side may release what
   the other condemned.

Horizon: `_STALE_DAYS = 10` calendar days from `evidence_available_at` (the producer is
weekly `W-FRI`; one cycle plus a weekend and a release-lag day).

## 3. Two vocabularies, two magnitudes, one null rule

**Vocabularies are closed and disjoint except for `unknown`.** No sentence anywhere may
describe one with the other's words.

- direction (`state.label`, `event_reference.direction_label`): `expanding | flat |
  contracting | unknown`
- quality (`event_reference.quality`): `easing | tightening | mixed | unknown`

A value outside its own set degrades to `unknown` — it is never repaired by borrowing from
the other set. And neither is ever translated into the market_view risk vocabulary
(`risk_off`/`neutral`/`risk_on`): a liquidity direction is not a risk tilt.

**Magnitudes never collapse.** `magnitude` is the raw `state.monetary_impulse` in
`weekly_change_in_expanding_z_score` units and is **not standardized**. `magnitude_z` is
its prior-only causal expanding-z standardization. **Only `magnitude_z` may be gated by a
downstream threshold expressed in z units.** Both travel with their own unit strings;
neither is surfaced as a bare number.

**Missing is not zero.** `state.credit_impulse_global = null` means insufficient comparable
PIT coverage (US C&I and China TSF are different constructs; BIS is quarterly). It stays
`None`. Same for `quality.us_liquidity_quality`.

## 4. What is deliberately absent

`target()` returns `{}` and `opportunities()` returns `[]` **in every mode**, because the
producer publishes `meta.contract_scope = 'state_quality_freshness_only'` and
`meta.forbidden_authority = [trade, allocation, alert, dispatch, transmission_curve,
repricing_gap]`. These are later-wave fields that do not exist in v1.

A later wave populates them **only** when the producer publishes them. Deriving a target or
a ranking from current `state` fabricates authority the producer explicitly withholds — the
reader refuses the artifact outright if `contract_scope` or `authority` widens without the
reader being updated to match.

## 5. Authority ladder — where a later wave plugs in

`off → shadow → display → candidacy → context → vote`, monotone, selected by
`MASTERMIND_GLT_MODE`. Absent → `shadow` (this wave's default). Present but
empty/unrecognized → `off`: a garbled value never escalates and never inherits the default.

**Every rung is inert in W-LIQ.2.** `decision_signals()` returns the same record for `vote`
as for `off`, because the contract scope carries no decision-bearing field. The ladder
exists so a later wave widens authority at one typed chokepoint instead of through ad-hoc
raw reads. `decision_signals()` already has a stable shape (`candidacy`, `tilt`,
`size_multiplier`, `vote`, `inert`, `mode`, `reason`) — extend it there.

Promoting the plane into `_VALIDATED_PLANES` is a separate, gated decision: it requires
on-disk forward grading, exactly as `risk_radar` / `mtf_signals` / `cycles` have.

## 6. What must not be redone

- **Do not add another GLT state producer** in Mastermind, or another raw feed in Macro,
  before refuting the W-LIQ.1 census (`research/GLOBAL_LIQUIDITY_DATA_CENSUS_2026-08-22.md`
  in Macro).
- **Do not recompute or fall back.** Both consumers copy producer values and hashes
  unchanged. There is no local state derivation.
- **Do not re-derive the clock law** (§2) — inherit it from the reader.
- **Do not map the liquidity direction into the risk vocabulary** to "make the plane
  useful". That is the vocabulary crime the producer's `vocabulary_law` forbids, and it
  would silently enrol a shadow plane in the disagreement and coherence math.
- **Do not repin `PLANE_ORDER[-1]`.** The order is append-only; pinning a specific plane as
  permanently last makes it append-hostile (see the restated assertion in
  `tests/test_neural_web_context.py`).

## 7. Known constraints inherited from W-LIQ.1

Visible, not repaired here: ECB/BoJ carry medium revision risk and no full vintage history;
China M2 has no repository release timestamp and is excluded from the causal state; NFCI/
ANFCI revise their full histories and are excluded; BoE/SNB/PBoC total assets lack adequate
canonical feeds and are omitted; no exact historical first-known episode chronology exists
(`meta.historical_first_known_status = 'not_reconstructable_before_this_producer_existed'`).

**Operational note:** the producer is weekly. The sample in
`tests/fixtures/global_liquidity_transmission.json` has `evidence_available_at =
2026-08-28`, so it reads `stale` against a 10-day horizon whenever it is not refreshed.
That is the correct behaviour, not a defect — but it means a live deployment needs the
vendored artifact to keep advancing, and until it does the plane is honestly inert.

## 8. Next gate

W-LIQ.3 (#124) — golden adapter, episode/holdout freeze. It copies
`state.event_reference` **without calculation**; its observed clock is
`evidence_available_at`, its known clock is `first_known_at`. That work is **not** part of
this wave and #124 was not modified here.

Stop before W-LIQ.4 / 5 / 7. No Repricing Map UI, Opportunity Feed, ChinaGate, gap engine,
response curves, predictive promotion, Neural Web voting, or portfolio action.
