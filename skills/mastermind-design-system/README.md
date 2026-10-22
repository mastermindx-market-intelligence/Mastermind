# Mastermind Design System for Claude Code

This folder is a portable **Claude Agent Skill** generated from the live Mastermind Paper design-system projection and reconciled against the current repository design law.

## Install in Claude Code

Anthropic documents manual Claude Code skill installation by placing a skill folder under `~/.claude/skills`. Copy this entire directory there:

```bash
mkdir -p ~/.claude/skills
cp -R mastermind-claude-design-system ~/.claude/skills/mastermind-design-system
```

Then start a new Claude Code session and ask it to design, implement or review a Mastermind UI. The skill description is intentionally specific so Claude can trigger it automatically when UI/design-system work is relevant.

For team use, keep the folder in version control and deploy/sync it into each developer's Claude skills directory. `CLAUDE.md.snippet` is optional project-level glue that makes the expectation explicit even before the skill is selected.

## What this bundle contains

- `SKILL.md` — the Claude Code entry point.
- `references/` — progressive-disclosure design law: foundations, components, archetypes, states/accessibility, and extraction provenance.
- `tokens/mastermind.tokens.json` — machine-readable token projection.
- `tokens/mastermind.css` — portable CSS reference; **do not overwrite production `templates/theme.css` with it**.
- `examples/patterns.md` — canonical composition examples.
- `scripts/validate_bundle.py` — local structural validation.
- `manifest.json` — source identities/pins and bundle metadata.

## Source identities used for this extraction

- Mastermind protected procedure pin: `877b1e7f275da0b6d3558d2667778b32d628bf67`
- Macro/product design authority pin: `a136a9e67f0e435a495e1b86a63eaa924e23b683`
- Paper file: `MASTERMIND PAGES` / `01M2WGNCX9475G79JRKJTCM08P`
- Paper governed page: `Archetype Starters · Governed` / `p-5-0`
- Paper token content hash observed: `cfd3d65c`

See `references/sources.md` and `references/paper-sources.md` for the exact boards and precedence.

## Important boundary

Paper is excellent for Claude's **visual vocabulary, anatomy, composition and responsive intent**. It is not a new production token authority. The Paper boards themselves say repository law remains authority, and multiple Paper token descriptions are explicit repository projections. This bundle therefore preserves exact Paper observations while telling Claude to bind production work back to `templates/theme.css` and canonical `.mx-*` components.
