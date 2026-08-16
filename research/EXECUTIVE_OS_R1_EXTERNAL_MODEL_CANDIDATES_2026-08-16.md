# Executive OS R1 external model candidates — 2026-08-16

Status: **research-only candidate registry; no provider or worker is armed**.

This document records models that are worth evaluating for future Executive OS
worker capacity because they are available through subscription surfaces already
held by the operator: Claude Pro, Z.AI GLM Coding Plan/Max, Alibaba Cloud Model
Studio Token Plan (Team Edition), Cursor, and Grok Build. It does **not** change
the accepted deterministic R1 fixture, enable an external provider, activate a
live worker slot, grant MCP write authority, or start Phase 1F-C.

The existing logical aliases remain the contract. Model/provider names below are
candidate implementations behind those aliases, not new lifecycle authorities.
Executive OS remains the only job lifecycle and aggregation authority.

## Admission rules

1. `candidate_only=true` for every entry in this registry.
2. `production_armed=false`; no entry is eligible for unattended production use
   merely because a subscription exposes it.
3. Exact model availability must be captured at trial time from the account's
   model selector/API response as `served_model_observed`; provider marketing
   names are not sufficient evidence.
4. Subscription transport eligibility and model quality are separate gates.
5. Do not use provider-side `Auto`/opaque routing as an Executive OS model alias.
   A provider may execute a bounded child job, but Executive OS chooses the job,
   lifecycle, parent/child relationship, review requirement, and aggregation.
6. Builder/reviewer independence should cross provider or model family when
   practical; a provider's internal self-review is not independent review.
7. Keep the accepted fixture harness deterministic. Real-provider measurements
   belong in a follow-on R1 provider-shadow evidence stream, not in the fixture
   inputs in `scripts/executive_os_r1_shadow.py`.

## Subscription-surface constraints

### Claude Pro

Claude Pro includes Claude Code usage under the subscription, with the exact
models exposed by `/model` serving as the account-specific source of truth.
Sonnet 5 is the current default on Pro and is the primary subscription-backed
candidate. Opus 4.8 is a higher-reasoning candidate for difficult planning and
review. Fable 5 is available to Pro but runs on pay-as-you-go usage credits, not
within Pro's included usage limits, so it is a lead/comparator candidate rather
than a subscription-savings worker. API/Console billing is separate from Pro.

### Z.AI GLM Coding Plan / Max

The current Coding Plan documentation lists GLM-5.1, GLM-5-Turbo, GLM-4.7 and
GLM-4.5-Air. The subscription is explicitly restricted to officially supported
tools/products, so a future custom Executive OS adapter must not assume that the
Coding Plan quota is valid outside those supported transports. R1 trials should
record the supported tool actually used.

### Alibaba Cloud Model Studio Token Plan (Team Edition)

The Team Edition uses an exact-string model allowlist. As of 2026-08-16, the
text/reasoning allowlist includes Qwen 3.7/3.6 variants, DeepSeek V4/V3.2,
Kimi K2.7/K2.6/K2.5, GLM 5.2/5.1/5 and MiniMax M2.5.

**Hard subscription constraint:** Alibaba states that Token Plan (Team Edition)
is for interactive use with compatible AI programming and agent tools only and
must not be used for automated scripts or application backends. Therefore every
Alibaba Team entry below is `interactive_shadow_only=true` and
`autonomous_subscription_eligible=false`. If a model later qualifies for
unattended Executive OS work through ordinary PAYG API billing or explicit
contractual permission, that is a separate R4 transport/terms decision.

### Cursor and Grok Build

Cursor released Grok 4.6 on 2026-08-12. Cursor lists Grok 4.6, Grok 4.5 and
Composer 2.5 in its Cursor Models pool and exposes Grok 4.6 through desktop,
web, iOS, CLI and SDK. Grok Build is a separate SpaceXAI coding-agent surface;
Grok 4.5 is its confirmed default as of the latest public model announcement,
with `grok-build-0.1` and Composer 2.5 also confirmed in the product/model menu.
Do not infer that a newer Cursor model is exposed in Grok Build unless the
Grok Build `/model` selector confirms it at trial time.

## Candidate registry

| Candidate | Subscription surface | Initial logical aliases | Priority | Evidence-based reason | Subscription automation disposition |
|---|---|---|---|---|---|
| `claude-sonnet-5` | Claude Pro / Claude Code | `standard.engineering`, `standard.research`, `standard.review`; selected `fast.*` trials | A1 | Anthropic positions it as its most agentic Sonnet; strong coding/tool/research execution and near Opus 4.8 capability at lower cost | controlled subscription shadow; R4 transport review before unattended use |
| `claude-opus-4-8` | Claude Pro / Claude Code | `standard.review`, elevated engineering/research comparator | A-review | deeper reasoning for hard refactors, debugging, architecture and review | reserve for difficult work/review; account `/model` is source of truth |
| `claude-haiku-4-5` | Claude Pro when exposed | `fast.research`, bounded tests/simple edits | B-fast | fast/economical Claude lane for high-volume simple work | probe account availability before trial |
| `claude-fable-5` | Claude Pro + usage credits | frontier lead/review comparator, not Luna/Terra default | special | frontier comparator/lead candidate | **not** subscription-savings capacity; usage-credit billed on Pro |
| `glm-5.1` | Z.AI GLM Max | `standard.engineering`, `standard.research`, `standard.review` | A1 | long-horizon agentic engineering, tool use and structured output | supported-tool shadow only until R4 transport acceptance |
| `glm-5-turbo` | Z.AI GLM Max | `fast.engineering`, `standard.engineering`, tests | A2 | optimized for long-chain execution, tool calling and instruction decomposition | supported-tool shadow only until R4 transport acceptance |
| `glm-4.7` | Z.AI GLM Max | `fast.engineering`, `fast.research`, tests | B | plan-recommended general coding model with strong coding/tool-use results | supported-tool shadow only until R4 transport acceptance |
| `glm-4.5-air` | Z.AI GLM Max | simple `fast.research`, mechanical tests/edits | C | lowest-complexity/quota-preserving GLM lane | supported-tool shadow only |
| `grok-4.6` | Cursor | `standard.engineering`, `standard.research`, `standard.review`; selected fast trials | **A1** | current Cursor frontier model; strong long-horizon coding/knowledge work and competitive with Sol on several current benchmarks | high-priority R1 challenger; R4 SDK/CLI transport review before production |
| `grok-4.5` | Cursor or Grok Build | `standard.engineering`, `standard.research`, `standard.review` | A2 | proven coding/agentic model; useful fallback/control against 4.6 | shadow candidate; record which surface served it |
| `grok-build-0.1` | Grok Build | `fast.engineering`, tests | B-fast | purpose-trained fast agentic coding model; debugging/MCP/tool-calling oriented | Grok Build transport only until R4 review |
| `composer-2.5` | Cursor or Grok Build | `fast.engineering`, tests | B-fast | fast coding model for sustained tasks and complex instructions | shadow candidate; record transport separately |
| `qwen3.7-max` | Alibaba Team | `standard.research`, `standard.review`, selected engineering | A1-shadow | Alibaba's highest-capability Qwen 3.7 model; agent-centric programming/productivity/long-run execution | **interactive shadow only; no automated Executive OS backend under Team plan** |
| `deepseek-v4-pro` | Alibaba Team | `standard.engineering`, `standard.research`, `standard.review` | **A1-shadow** | V4-Pro GA 2026-08-13; major agent upgrades, adjustable effort, 1M context | **interactive shadow only** |
| `kimi-k2.7-code` | Alibaba Team | `fast.engineering`, `standard.engineering`, tests | **A1-shadow** | purpose-built long-horizon coding model; vendor reports materially better coding/agent results and ~30% fewer thinking tokens than K2.6 | **interactive shadow only** |
| `MiniMax-M2.5` | Alibaba Team | `fast.engineering`, `fast.research`, tests | **A1-shadow** | strong coding/tool/search profile with vendor-reported speed/token-efficiency gains | **interactive shadow only** |
| `glm-5.2` | Alibaba Team | `standard.engineering`, `standard.review`, `standard.research` | A2-shadow | highest GLM version on the Team allowlist and a useful cross-surface GLM comparator | **interactive shadow only** |
| `deepseek-v4-flash` | Alibaba Team | `fast.engineering`, `fast.research`, tests | B-shadow | near-Pro reasoning on simpler agent tasks with faster/economical profile | **interactive shadow only** |
| `qwen3.7-plus` | Alibaba Team | `fast.research`, `standard.research`, bounded engineering | B-shadow | balanced model with vision/function-calling and large context; useful for research/document-heavy children | **interactive shadow only** |
| `kimi-k2.6` | Alibaba Team | `standard.research`, general bounded jobs | B-shadow | more general-purpose than K2.7 Code; useful as a research/general control | **interactive shadow only** |
| `qwen3.6-plus` | Alibaba Team | fallback research/general | C-shadow | older balanced Qwen lane | **interactive shadow only** |
| `qwen3.6-flash` | Alibaba Team | mechanical `fast.research`, extraction/tests | C-shadow | lightweight Qwen lane | **interactive shadow only** |
| `deepseek-v3.2` | Alibaba Team | fallback | C-shadow | retained as compatibility/control only; V4 family preferred | **interactive shadow only** |
| `kimi-k2.5` | Alibaba Team | fallback | C-shadow | retained as older control; K2.6/K2.7 preferred | **interactive shadow only** |
| `glm-5.1` / `glm-5` | Alibaba Team | fallback/cross-surface control | C-shadow | useful for same-model/surface comparisons, but Z.AI Max gives a cleaner current GLM path | **interactive shadow only** |

Image-generation-only entries (`qwen-image-2.0`, `qwen-image-2.0-pro`,
`wan2.7-image`, `wan2.7-image-pro`) are intentionally not assigned to the
current worker aliases because R1's representative jobs are implementation,
research, tests and review. They may be catalogued later under a separate media
capability alias if Executive OS gains a governed visual-production job type.

## First matched-job cohort

The first provider-backed R1 comparison should spend measurement effort on the
models most likely to change routing decisions:

| Cohort | Models | Purpose |
|---|---|---|
| A1 autonomous-capability challengers | `grok-4.6`, `claude-sonnet-5`, `glm-5.1` | test whether a cheaper/non-Sol lane can meet standard engineering/research/review quality |
| A1 Alibaba interactive challengers | `deepseek-v4-pro`, `kimi-k2.7-code`, `MiniMax-M2.5`, `qwen3.7-max`, `glm-5.2` | quality/repair/token-efficiency evidence only; do not convert Team-plan access into autonomous capacity |
| fast-lane challengers | `glm-4.7`, `glm-5-turbo`, `grok-build-0.1`, `composer-2.5`, `deepseek-v4-flash`, `qwen3.7-plus`, `claude-haiku-4-5` | identify Luna-like routine labor capacity |
| independent-review comparators | `claude-opus-4-8`, `grok-4.6`, `claude-sonnet-5`, `glm-5.1`, `deepseek-v4-pro` | determine which cross-provider reviewer catches defects with acceptable latency/quota use |
| frontier lead comparator | `claude-fable-5` | compare lead/review quality only; usage-credit billed, so exclude from subscription-savings claims |

## Current online signals worth testing, not accepting as truth

- Cursor's 2026-08-12 Grok 4.6 page reports Grok 4.6 High at 61 on the
  Artificial Analysis Intelligence Index, equal to GPT-5.6 Sol Max in the same
  table. It reports Grok 4.6 ahead of Sol on GDPVal-AA v2, CursorBench v3.2,
  FrontierCode v1.1 Extended, APEX-Agents and AA-Briefcase, while Sol remains
  ahead on DeepSWE v1.1 and Terminal-Bench v3.0. This mixed profile is a strong
  reason to run matched Mastermind jobs rather than infer a universal winner.
- Anthropic reports Sonnet 5 as close to Opus 4.8 while materially improving
  agentic reasoning, tool use, coding and knowledge work. Sonnet 5 also uses a
  newer tokenizer: the same input can map to roughly 1.0–1.35x as many tokens,
  so raw cross-model worker-token counts are not an apples-to-apples efficiency
  metric.
- Z.AI reports GLM-5.1 at 58.4 on SWE-Bench Pro and emphasizes sustained
  long-horizon engineering; GLM-5-Turbo is explicitly optimized for tool use,
  persistent/long-chain execution and instruction decomposition. These are
  vendor results and require R1 replication on Mastermind jobs.
- Moonshot reports Kimi K2.7 Code improves its coding/agent benchmarks over K2.6
  while reducing thinking-token usage by approximately 30%. This makes it a
  particularly relevant Luna/Terra engineering challenger if the Team-plan
  transport constraint is respected.
- MiniMax reports M2.5 at 80.2% SWE-Bench Verified and 37% faster completion of
  that evaluation than M2.1, plus fewer search/agent rounds. These are vendor
  measurements and should be treated as candidate-selection evidence only.
- DeepSeek V4 Pro reached GA on 2026-08-13 with explicit agent upgrades and
  adjustable reasoning effort. V4-Flash remains a deliberate simpler-job
  challenger rather than a default replacement for V4-Pro.
- Alibaba labels `qwen3.7-max` its strongest-reasoning coding-tool choice. Its
  current model-specific page and structured-output documentation are not fully
  consistent about structured-output support, so R4 must probe JSON/schema
  behavior directly instead of assuming it.

## Provider-backed R1 measurement extension

For every real shadow attempt, capture at least:

- `candidate_id`
- `plan_surface` and `account_label`
- `transport` and client version
- `requested_model` and `served_model_observed`
- `effort` / thinking mode
- `logical_alias`, `task_kind`, job/attempt IDs
- completion-quality score and rubric version
- validation pass/fail and validation evidence
- repair count / repair rounds
- wall-clock latency and provider-reported latency if available
- `frontier_lead_tokens`, `frontier_review_tokens`, `frontier_repair_tokens`
- worker input/output/reasoning tokens when exposed
- plan Credits / pool consumption when exposed
- tool-call validity, structured-output validity, cancel/checkpoint behavior
- independent reviewer model/provider/account
- subscription-policy disposition (`interactive_only`, `supported_tool_only`,
  `candidate_for_r4`, or `payg_required`)

For a matched job, calculate frontier-token savings as:

`all_Sol_baseline_frontier_tokens - (frontier_lead_tokens + frontier_review_tokens + frontier_repair_tokens)`

Worker-model tokens or subscription Credits are reported separately; they are
not subtracted from or relabeled as Sol/frontier tokens. This preserves the
meaning of the existing R1 metric while exposing whether apparent frontier
savings merely moved cost/quota into another provider.

## Promotion rule

No online benchmark promotes a model. A candidate can move behind an existing
logical alias only after matched Mastermind shadow jobs show acceptable
completion quality, validation pass rate, repair rate, latency, and frontier-
token savings, and after its provider transport independently passes the R4
terms/credential/structured-output/session/cancel/checkpoint/security gates.
Live worker-slot activation and MCP write authority remain separate decisions.

## Primary sources reviewed 2026-08-16

- Anthropic Sonnet 5: https://www.anthropic.com/news/claude-sonnet-5
- Anthropic Claude Code on Pro/Max: https://support.claude.com/en/articles/11145838-use-claude-code-with-your-pro-or-max-plan
- Anthropic Fable 5 plan treatment: https://support.claude.com/en/articles/15424964-claude-fable-5-on-your-plan
- Z.AI Coding Plan FAQ: https://docs.z.ai/devpack/faq
- Z.AI GLM-5.1: https://docs.z.ai/guides/llm/glm-5.1
- Z.AI GLM-5-Turbo: https://docs.z.ai/guides/llm/glm-5-turbo
- Z.AI GLM-4.7: https://docs.z.ai/guides/llm/glm-4.7
- Alibaba Token Plan (Team Edition): https://www.alibabacloud.com/help/en/model-studio/token-plan-overview
- Alibaba Qwen 3.7 Max model info: https://www.alibabacloud.com/help/en/model-studio/qwen3-7-max
- DeepSeek V4 Pro GA: https://api-docs.deepseek.com/news/news260813/
- Kimi K2.7 Code: https://www.kimi.com/en/resources/kimi-k2-7-code
- MiniMax M2.5: https://www.minimax.io/news/minimax-m25
- Cursor Grok 4.6: https://cursor.com/grok
- SpaceXAI Grok Build: https://x.ai/news/grok-build-cli
- SpaceXAI Grok Build 0.1: https://x.ai/news/grok-build-0-1
- SpaceXAI Grok 4.5: https://x.ai/news/grok-4-5
- SpaceXAI Composer 2.5 in Grok Build: https://x.ai/news/composer-2-5
