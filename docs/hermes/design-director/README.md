# Hermes Design Director

A native skill for the existing `design-lead` profile: select real references, compile
Astra briefs, validate exact returns, review screenshots, continue the original task
and prepare meaningful engineering handoffs. No dispatcher, credential store, job
ledger, approval service or timer is added.

**Scope:** offline native-skill implementation with real attended Paper refinement
proof. Autonomous Hermes → personal Astra Pro launch, live Slack callback, qualified
vision-model routing and repeated production journeys remain unproven. Read
`EVIDENCE.md`; the full original outcome remains in `COMMISSION.md` and `PLAN.md`.

## Operator path

1. Load `mastermind-design-director` in the existing Hermes `design-lead` profile.
2. Recover the original assignment and current source/Paper targets. Retrieve and
   inspect a small useful reference set, then compile the complete creative brief.
3. Use an actually qualified existing target or one account-owner-assisted Astra
   dispatch with the brief, images and return template. Record delivery and START separately.
4. Validate the return, re-read Paper and review every required image/state. Continue
   the original session only for meaningful changes, preserving accepted requirements.
5. Record the design decision and component/data/state specification. Verify actual
   software separately. Notify through the existing authorized transport and receipt.

## Package and validation

Native skill: `skills/mastermind-design-director/SKILL.md`; progressive references and
four actual screenshot files live alongside it. `scripts/director.py` provides nine
offline commands. Three example assignments/briefs and a real refinement return live
under this document directory. Tests exercise malformed/stale/mismatched evidence,
coverage, original-session preservation and honest notification/status boundaries.

Python 3.10+ plus Pillow is required for image decode. The observed host's existing
Python 3.14 has Pillow 12.3.0. No dependency installation is bundled.

```bash
python3 skills/mastermind-design-director/scripts/director.py validate-corpus
python3 skills/mastermind-design-director/scripts/director.py brief --assignment docs/hermes/design-director/examples/financial.assignment.json
python3 -m unittest discover -s tests -p test_hermes_design_director.py -v
```

The helper bounds file size/pixels, decodes PNG/JPEG, rejects traversal/symlinks,
checks digests/chronology, and requires original requirement coverage. It cannot
authenticate external receipts or see images for a model. A caller's observation
claim still needs real review. Recommendation never means automatic acceptance.

## Supported native installation

After protected source release, use the actual accepted commit:

```bash
hermes --profile design-lead skills install 'https://raw.githubusercontent.com/mastermindx-market-intelligence/Mastermind/ACCEPTED_COMMIT/skills/mastermind-design-director/SKILL.md' --yes
```

Do not use `--force`, which bypasses the native scan. The existing installer
quarantines, scans and records the bundle. Read back its profile-specific directory,
invoke the native skill loader in that profile and run `validate-corpus` with the
existing qualified Python. Recognition is not proof of an agent consuming the skill.
Do not force-reload a live conversation; use the next normal authorized session.
Existing role, memory, models and credentials are preserved by this package.

The installed native URL source accepts a direct `.md` URL, not a GitHub tree URL.
The main skill explicitly lists every support file so the installer carries the
script, templates, reference manifest and binary screenshots from the same commit.
This behavior was inspected in the installed `UrlSource` implementation; do not
substitute an unpinned registry identifier or hand-copy around a scan failure.
