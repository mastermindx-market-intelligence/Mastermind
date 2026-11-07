# Product public projections: canonical integration of PR #1308

## Source decision

[#1301](https://github.com/mastermindx-market-intelligence/Mastermind/pull/1301)
is the canonical Product MCP service, merged at
`8d820abd80a190c96912c953a2abc286795d2093`.
The [current integration decision](https://github.com/mastermindx-market-intelligence/Mastermind/pull/1308#issuecomment-6675015454)
resolves the collision recorded in
[6104851707](https://github.com/mastermindx-market-intelligence/Mastermind/pull/1308#issuecomment-6104851707).
This slice extends that service through its existing owners.

Catalog 1.3.0 retains the observation envelope
`mastermind.product_observation.v1` and the exact existing
`product_diagnostics` and `product_market_pulse` tool schemas.
It adds two tools with empty, closed inputs:

| Tool | Fixed source | Response byte ceiling |
| --- | --- | --- |
| `product_macro_overlay` | `https://www.mastermind-x.com/api/overlay` | 512 KiB |
| `product_market_risk` | `https://app.mastermind-x.com/data/market_risk.json` | 64 KiB |

The existing three endpoint ceilings stay 256 KiB. Streaming and strict JSON
decoding use the same endpoint-specific limit. There is no caller-selected
URL, credential, cookie, account, retry, provider or cap. The existing transport
continues to disable redirects, ambient proxies/TLS settings, cookies across
calls, compression and automatic retries.

The complete catalog remains bounded below 32 KiB. Catalog version and digest
are pinned together in the existing authenticated catalog test; old two-tool
schemas are compared exactly during qualification.

## Evidence and authority semantics

Overlay reports counts, source clocks, delay/realtime claims and bounded
SPY/QQQ/VIX and US/CN/HK/CA context. It omits prices, raw ticker/vendor tape and
undeclared strings. Unknown context vocabulary becomes explicit unknown,
invalid or other; absent calendar qualification is not converted to true.
Overlay is always partial and unqualified for current regime or trade use.
The producer's exact `YYYY-MM-DD HH:MM:SS UTC` build spelling is
normalized to RFC3339; no other timestamp parser is relaxed.

Terminal risk retains the owner's displayed verdict and optional score,
source session, literal display-only flag, basis, source clocks, stale flag and
separate owner freshness verdict. A missing score stays null. No market or
execution signal is derived from the score.

The [Terminal owner contract](https://github.com/mastermindx-market-intelligence/mastermind-terminal/blob/1148477475dbff4ab49397e2ecfc10f7e98ab70a/ingest/pull_macro_risk.py)
defines settled, legacy_display and live_display bases. An event timestamp is
optional for settled/legacy observations and required for live observations.
Live sessions are checked against the event's America/New_York date.
The live_score_pending_band cause preserves the displayed verdict; it does
not recompute that verdict from numeric evidence.

Only the producer's finite top-level freshness reason vocabulary is exposed.
Unknown, malformed or oversized reason lists retain an explicit invalid
qualification and bounded counts; private/free-form strings are not forwarded.
Nested risk-envelope freshness is a different producer contract and is not
mixed into this headline.

Owner qualification alone cannot supply missing observation clocks.
Unavailable build/expiry or score remains partial; future build/event,
elapsed expiry and literal owner stale remain distinguishable.
A clean reason list cannot override explicit refusal/staleness.
The reader does not impose a new maximum-session-age policy or invent an expiry.

The two new observation schemas distinguish a complete retained body from
an unobserved/discarded representation. An empty successful response is invalid
with zero bytes and the true empty-body SHA-256. An oversized discarded body
has no full-body or fabricated-prefix digest. Existing tools keep their
historical non-observed null-digest contract.

The existing final authenticated return validates both the closed schemas and
the new semantic invariants after the existing JWT/identity/audit recheck.
A faulty reader cannot relabel a missing-score, stale or unqualified result as
qualified, or append undeclared overlay prices/private context.

## Existing owners remain canonical

The service keeps `product.observe`, existing Business OAuth policy,
JWT verification, durable audit, top-level tool securitySchemes and
credential-specific authentication challenges. Its existing
`product_http_app` / PreAuthMcpBodyApp and host launcher own the
HTTP byte boundary and lifecycle.

This public slice requires no synthetic product-user grant. Private account
operations remain absent and require an accepted application-owner binding.
The original alternative app/contracts/deployment/mount/runtime and root test
files from #1308 are not copied over the canonical service. Their source
history remains reachable at
`18b484cd2748c94f66ea78b40026ed3371f89c7e`.

## Remaining obligations preserved from the original mission

This source integration does not complete
[mission #1303](https://github.com/mastermindx-market-intelligence/Mastermind/issues/1303)
or prove an installed Product plugin.

| Original obligation | Disposition |
| --- | --- |
| Public Macro status | Already provided by canonical product_diagnostics; its schema/behavior is preserved. |
| Public Macro overlay and Terminal risk | Integrated into the canonical public service in this slice. |
| Real resource/audience/scope and client allowlist | Existing identity owner and approved policy remain required. No OAuth allowlist edit or alternate auth plane. |
| Private product-user grant and late revocation | Future application-owner integration. The historical helper clipped owner expiry before identity comparison; raw owner expiry must remain separately bound before that helper can be adopted. |
| Host readiness and SDK mount | Future qualified host composition must preserve the existing PreAuthMcpBodyApp/lifecycle and accept only literal owner readiness. The historical direct SDK mount is not adopted. |
| Signed live Product canary | Earlier explicit denial remains. No retry, alternate carrier or success claim. |
| Browser #1259, screenshots and controlled account journeys | Original Chrome/attached-tab policy, consent, session and Browser resource admission remain required. |
| Terminal #894 | Existing source/SSH/index.lock refusal remains; no alternate workspace or publication retry. |
| Preview, approved release, production/rollback and one controlled action | Unproven original journey, retained for the incumbent product/release owners. |

Offline fixtures use synthetic source data and loopback transport only.
Authenticated SDK tests use synthetic keys and an in-process ASGI app; their
execution is evidence for source behavior, not real consent or a production
account. Source qualification, protected merge, deployment and real product
acceptance are distinct.
