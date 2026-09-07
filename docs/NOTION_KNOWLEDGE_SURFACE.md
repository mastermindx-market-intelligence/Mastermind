# Mastermind-X Notion Knowledge Surface — N0 Operator Guide

This guide operates the bounded N0 bootstrap frozen in
`docs/superpowers/specs/2026-09-07-notion-knowledge-surface-n0.md`.

N0 creates a human-facing workspace shell only. Notion is **not** an Executive OS,
Agent OS, priority queue, source-law owner, or task dispatcher.

## One-time Notion setup

Create or select one private Notion page to be the Mastermind root, preferably named
`Mastermind-X`.

Create a scoped internal Notion connection for N0 with only:

- **Read content**
- **Insert content**

N0 does not require Update content, comment capabilities, or user-information access.
Share only the chosen Mastermind root page with that connection. Access inherited to the
root's children is sufficient for N0; do not grant unrelated workspace pages merely for
convenience.

Keep the connection token outside Git and chat. On the approved execution host, provide it
through the process environment or an approved secret mechanism:

```bash
export NOTION_API_KEY='...'
export NOTION_PARENT_PAGE_ID='...'
```

Never commit those values or place them in a PR, issue, prompt, receipt, or screenshot.

## 1. Read-only remote plan

From an exact checkout containing the accepted N0 source:

```bash
python3 scripts/notion_knowledge_surface.py
```

With both environment values present and no `--apply`, this proves the parent identity,
reads its current children, and prints a plan. It performs no Notion write.

Expected first-run plan: eight `create` actions unless exact reviewed children already exist.
Any duplicate exact child or inaccessible parent is a refusal.

## 2. Apply once

After reviewing the plan:

```bash
python3 scripts/notion_knowledge_surface.py --apply
```

The bootstrap creates only missing reviewed children:

1. `00 — Chairman Board Book`
2. `01 — Programs`
3. `02 — Decisions`
4. `03 — Research Library`
5. `04 — Product & Architecture`
6. `05 — Operating Manual`
7. `06 — Chairman Notes & Inputs`
8. `99 — Archive`

Before any write, a same-name database selected for reuse must prove exactly one data source
and the reviewed property-name/type schema. The client paces requests and never automatically
retries a mutation.

If a mutation response is ambiguous, the bootstrap re-reads the exact parent. It records
`reconciled` only when the exact intended object is observed; otherwise it stops with an
unknown effect rather than creating again.

## 3. Immediate idempotency proof

Run the exact apply command a second time:

```bash
python3 scripts/notion_knowledge_surface.py --apply
```

Acceptance requires:

- `created_count` is `0`;
- every N0 child resolves to `reuse`;
- all four databases prove their reviewed schemas again;
- no duplicate child exists.

Do not continue to N1 if this proof fails.

## 4. Human-visible proof

Open the Mastermind root in Notion and verify all eight children are visible and usable.
Specifically confirm:

- `05 — Operating Manual` is a presentation/index page, not treated as governing procedure;
- the four projection databases expose canonical metadata fields;
- `06 — Chairman Notes & Inputs` is clearly a human-input surface and has no implication that
  an entry starts runtime work;
- there is no separate tasks/worker-liveness/priority database.

Record the parent page ID and returned N0 object IDs only as a non-secret deployment receipt.
Do not record the Notion token.

## Capability state

Repository source + green CI is `BUILT_NOT_PROVEN` at best.

N0 becomes `PROVEN_LIVE` only after the real remote plan, one apply, zero-create second apply,
database-schema proof, and human-visible inspection above all pass on the intended workspace.

## Held next waves

- **N1:** canonical Mastermind → Notion projection for Programs, Decisions, Research,
  Product/Architecture, Board Book, and Operating Manual/index content.
- **N2:** signed Chairman Notes intake into a candidate-input/quarantine seam; never direct
  Executive Job creation.
- **N3:** governed worker Notion capability through the existing capability registry and
  provider attestation architecture.

Do not start any held wave merely because N0 source merges. Each wave needs its own accepted
scope and proof boundary.
