# Mastermind T3 cost-aware compaction recommendations

## Current release boundary

This candidate is held in Draft. Report mode calculates bounded per-model
recommendations from local usage metadata. **Automatic application and the
LaunchAgent installer refuse with exit code 2.** The shared provider settings
writer has been removed: checking bytes before `os.replace` is not a
compare-and-swap operation, and a daemon-only lock cannot protect concurrent
Claude, T3 or manual edits.

This source repair does not modify or stop any previously installed copy or
LaunchAgent. Its installed state must be reconciled separately with the actual
settings and execution owners. The original automatic-compaction objective
remains incomplete until owner-qualified application and actual consumer proof.

## Report mode

```sh
python3 integrations/t3_cost_aware_compaction/compaction.py --json
python3 -m unittest discover -s integrations/t3_cost_aware_compaction -p 'test_*.py' -v
```

Report mode reads provider enablement and existing model settings, bounded tails
of recent Claude JSONL records, and the optional local T3 rate catalog. The input
records may contain conversation text; only usage counters, model identity and
deduplication IDs are used for the policy. Output contains aggregate usage,
price provenance and numeric recommendations. It does not retain transcripts,
credentials or the full provider settings.

The report always says `mode: dry_run`, `applied: false`, and
`application_status: held-settings-owner-unqualified`. `would_change` compares
a recommendation with the current settings; `set_to` is the recommended value,
not an observed effective setting. Disabled providers are left alone, including
missing or malformed model settings. Report mode creates no locks, backups,
state directories or settings files.

T3 and Claude Code remain the owners of sessions, compaction, token accounting,
cache and lifecycle. This component sends no model requests, invokes no
`/compact`, restarts no sessions and changes no provider admission or routing.

## Policy

| Model family | Baseline | Allowed recommendation |
| --- | ---: | ---: |
| Fable 5.x | 200K | 175K–350K |
| Opus 5.5/5/4.8/4.7 | 250K | 225K–400K |
| Opus 4.6 | 180K | 180K |
| GLM 5.3/Flash, DeepSeek/MiniMax/Qwen Flash, Fable free | 900K | 900K |

Premium models can receive up to +100K when observed cache reuse is high and
local API-equivalent input cost is low. Low cache reuse and high cost can lower
the target by 25K. Fewer than six qualified samples, unknown or malformed rates,
and non-finite price-cost arithmetic select the baseline policy target. Gradual movement
toward that target retains the ordinary 50K step inside the legal interval.
If an existing value is outside the family interval, normalization to the legal
bounds takes priority over that step. The first upward pass still establishes
the 200K/250K baseline before a larger recommendation.

These numbers do not admit a larger model context. The actual provider and
gateway limit must be verified independently. Local catalog prices are
API-equivalent proxies, not a claim about negotiated or subscription billing.
Fable 5.2 may use the explicitly labelled Fable 5.1 proxy. No savings or live
effective threshold is claimed from a recommendation.

## Existing owner path to qualify next

Mastermind's [pinned native-overlay manifest](https://github.com/mastermindx-market-intelligence/Mastermind/blob/d8dc1873077867f8ddd281c9f98a63bb0b3258df/integrations/t3_agent_bus/manifest.json)
identifies `pingdotgg/t3code@0770446869d247a8b28c27d7ed93f47f8ff0c1e4`.
That [native adapter](https://github.com/pingdotgg/t3code/blob/0770446869d247a8b28c27d7ed93f47f8ff0c1e4/apps/server/src/orchestration-v2/Adapters/ClaudeAdapterV2.ts)
already reads a `--settings` launch argument and resolves
`modelSettings[compiled API model].autoCompactWindow`. An explicit instance
window wins over launch-argument settings, which win over ordinary settings
files. Source support does not prove which installed bundle is running.

A possible restoration is a compaction-owned overlay consumed by that existing
adapter. Before enabling it, qualify the installed adapter and exact model
bindings; have the incumbent settings owner enroll the path without replacing
an existing `--settings` argument or clearing an explicit override; and prove
actual consumption on an authorized subsequent launch. A stale whole-instance
or whole-map upsert is not a safe nested-field patch. Reuse the existing
scheduling owner after its custody is reconciled; do not add another watcher
or a parallel settings authority.

Until that integration is qualified, `--apply` and `install.sh` remain closed.
Do not restore whole historical settings backups over newer owner edits.

## Regression coverage

The local unittest suite covers policy bounds, step behavior, disabled
profiles, malformed catalogs, non-finite rates and arithmetic, source
preservation, and refusal before any application or installer effect.
`tests/test_compaction.py` exposes the same suite to canonical pytest discovery
and the existing same-stem smoke selector.
