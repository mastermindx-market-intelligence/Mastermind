# Studio protocol: from brief to verified screen

The programme's design lead (an implementation COO, deputy or the lead it names) runs
this protocol for every user-facing change. **No UI is built before its screens exist
in Paper and have passed critique.** Paper is where the design is decided; code
implements a decided design.

The law the studio applies is not restated here:
- content: Macro `docs/DESIGN_DOCTRINE.md`;
- visual: Macro `research/MASTER_PRODUCT_DESIGN_SYSTEM_V1.md`, through the
  `mastermind-design-system` skill;
- carrier and safety: `paper-design-workflow` and its `references/t3-carriers.md`.

Read both Macro documents at one recorded commit of Macro `main`.

## Roles (one session may hold several, except where noted)

| Role | Brief | Writes Paper? | Typical model |
|---|---|---|---|
| Design lead | this file | names the writer; does not need to draw | the programme's lead |
| Art director | `agents/art-director.md` | no | strongest available vision-capable model |
| Canvas designer | `agents/canvas-designer.md` | **yes, the only writer** of its document or page | strong vision-capable model with Paper tools |
| Design critic | `agents/design-critic.md` | no (read-only, must not be the designer) | a different model from the designer |
| UI implementer | `agents/ui-implementer.md` | no | coding model in the product repo |
| Visual verifier | `agents/visual-verifier.md` | no | vision-capable model with browser access |

The critic and the verifier must be different sessions from the designer and the
implementer they judge. A self-check is recorded as `SELF_REVIEWED`, never as a critique.

## The ten steps

1. **Recover.** Read the design log (see `memory.md`), the Paper file's `00 · AGENT
   README` page, the programme's design manifest, and the held targets. Name the canvas
   writer. Continue an existing operation rather than starting a parallel one.
2. **Brief.** Write one brief from `templates/assignment.json`: user, primary question
   (the 3–4-second answer), next useful action, preserved capabilities with their
   destinations, states, viewports (1440 / 390 / 320 at minimum, plus dark/light and
   EN/ZH where the product has them), exact Paper file/page/nodes, and non-goals.
3. **References.** The art director pulls 2–4 existing boards from the inventory and
   the product's accepted shell, and names what to keep and what to avoid. Inspect
   actual screenshots, never filenames.
4. **Direction.** The art director returns a one-page direction: composition idea,
   hierarchy, type and density, the one thing the screen must make obvious. No pixels.
5. **Canvas.** The canvas designer builds in Paper: clone the accepted shell
   (`<x-paper-clone>` / `duplicate_nodes`), then compose incrementally, one visual
   group per write, with tokens. Every state on the brief gets an artboard. Screenshot
   after each meaningful group and fix what is visibly wrong.
6. **Critique.** The critic reviews screenshots against the brief and the twelve
   dimensions in `references/critique.md`, with blocking / material / polish findings.
7. **Revise.** One coherent revision per round, by the same canvas designer. At most
   two material rounds before the lead decides. Polish never forces a round.
8. **Handoff.** The lead records the design decision and writes the build contract
   (`references/handoff.md`): node ids, `get_jsx` digests, components and tokens to
   reuse, data fields, states, interactions, responsive rules.
9. **Implement.** The UI implementer builds in the product's own shell, components and
   tokens. Paper JSX is reference input, never pasted architecture.
10. **Verify.** The visual verifier renders the real page at the briefed viewports,
    themes and languages, and compares each one to its Paper artboard screenshot. It
    reports differences that matter, then the remaining real-journey proof.

Four claims stay separate in every report: rendered in Paper, design-critiqued,
observed human comprehension, product acceptance. A green build is none of them.

## Spawning specialists

Spawn a specialist with a named model (never inherited) and a self-contained brief:
1. paste its `agents/<role>.md` body;
2. add the assignment (step 2), the exact Paper ids, the design-log path, the held
   targets and the return format;
3. state its carrier (local Paper tools, guarded remote tools, or "read through a child
   on the Paper host") and whether it is the canvas writer.

Leaf children cannot spawn children, so everything they need goes in the brief. Give
read-only specialists no write tools in their brief. One canvas writer per document
or page, at any time.

## Budget

A guarded edit costs three Paper calls (pre-read, edit, post-read). Screenshot after a
meaningful change, not after every call. Do not poll. Do not buy or upgrade plans.
