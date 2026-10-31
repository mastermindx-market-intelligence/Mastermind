# PROPOSAL — authenticated ticker-news adapter for the Mastermind bot

**Status: PROPOSAL. Not implemented, not admitted, not scheduled.** This note
records a design option only. It adds no client, store, cache, scheduler or
credential, and nothing in Mastermind calls the route described here.

## Why

`brain/bot_mcp.py` `get_news` / `get_intelligence` and `portfolio/lenses.py`
`_news_row` read the **vendored Macro snapshot** (`vendor/macro/site/news/by_ticker.json`,
`vendor/macro/site/intelligence/by_ticker.json`). Since the D2 boundary change those
reads carry `freshness` (`asof`, `source_asof`, `retained_from_previous_build`,
`generated_utc`, `basis: "vendored_macro_file"`) and `evidence_grade`
(`vendored_snapshot` or `legacy_fallback`). That is honest, but the ceiling is the
vendored file: it is as old as the last vendor sync and the last nightly build, and it
has no per-row rights receipt.

Macro already serves a fresher, rights-scoped read: the private ticker-news API in
Macro `app/ticker_news.py`, mounted by Macro `app/main.py`.

## The existing Macro route (read, not changed)

| Route | Purpose |
| --- | --- |
| `GET /api/ticker-news/{ticker}` | current snapshot, schema `ticker_news.snapshot.v1` |
| `GET /api/ticker-news/{ticker}/changes` | incremental changes after a `change_sequence` |
| `GET /api/ticker-news/stories/{story_id}` | one story |
| `GET /api/ticker-news/{ticker}/stream` | live stream |

**Auth boundary.** Every route depends on `require_site_full_user`
(`app/ticker_news.py`): it authenticates the bearer through `app.main.require_user`,
then enforces paid site access with `app.paywall.enforce_site_full(..., always=True)`.
A failure is returned through `_private_error` (private, non-cacheable). Read rights
are resolved per user by `_rights_for_user` into `NewsReadRights`. There is no
anonymous or service path, and this proposal does not add one.

**Snapshot schema `ticker_news.snapshot.v1`** (fields this adapter would consume):

| Field | Meaning for the bot |
| --- | --- |
| `rows` | rights-filtered story rows (the bot would quote these, never re-rank them) |
| `change_sequence` | monotone cursor; the adapter's freshness clock and the `/changes` resume point |
| `source_health` | per-source health; drives a `degraded` state instead of silent emptiness |
| `rights_basis` | receipt identity (`receipt_id`, `source`, `provider`, `effective_at`, `expires_at`) or `null` |
| `universe_known_at` | when the ticker's security mapping was known; `null` when no provenance |
| `state` | snapshot state derived from health and row count |

## What it would unlock

A read returned by this adapter would carry
`freshness.basis = "authenticated_ticker_news_api"`,
`freshness.change_sequence`, and **`evidence_grade = "rights_scoped_snapshot"`**, but only
when `rights_basis` is non-null and its `expires_at` is in the future at read time.
A null or expired `rights_basis` keeps `evidence_grade = "vendored_snapshot"` semantics
(the adapter falls back to the vendored file and says so). Evidence grade is a
provenance label only; it never becomes ranking, sizing or trading authority.

## What is blocked

1. **The bot's service auth identity.** The route requires a site-full *user*. The
   Mastermind bot has no Macro user, bearer or entitlement, and minting one (a service
   account, a token, a paywall exemption) is a security/auth decision for the Macro
   auth owner with a proportionate independent review. It is not decided here.
2. **Rights scope for a non-human reader.** `_rights_for_user` resolves rights for a
   person; whether the bot may redistribute rights-scoped rows inside Mastermind needs
   a rights ruling. Commercial-data attestations do not cover unnamed providers.
3. **Placement.** Any client must reuse an existing Mastermind HTTP/auth seam. No new
   cache or store; a stale or failed read falls back to the vendored file with
   `missing_reason` set.

## Not in scope

No raw repository-content URL, no Pages mirror, no anonymous fetch of Macro
(`tests/test_no_anonymous_macro_reads.py` stays binding). No scheduler, no polling of
`/stream`, no write path.
