# Reuse decisions

Primary-source review: 2026-11-08. Links below are mutable upstream references; pin an
exact upstream revision before any future vendoring. This implementation contains
original synthesis and links, not copied external skill code or proprietary assets.

| Candidate | Decision | Source/license and qualification |
|---|---|---|
| Hermes Skills Hub + skills.sh | Reuse existing discovery/installer; inspect source and provenance | [Hermes skills](https://hermes-agent.nousresearch.com/docs/user-guide/features/skills), [optional catalog](https://hermes-agent.nousresearch.com/docs/reference/optional-skills-catalog), [MIT](https://raw.githubusercontent.com/NousResearch/hermes-agent/main/LICENSE); [skills.sh docs](https://www.skills.sh/docs) and [terms](https://www.skills.sh/terms). Indexed skills retain their own licenses; popularity is not trust. |
| Anthropic frontend-design | Adapt subject-grounded brief, deliberate hierarchy and screenshot critique as original workflow guidance | [Skill](https://github.com/anthropics/skills/blob/main/skills/frontend-design/SKILL.md), [skill-local Apache-2.0](https://github.com/anthropics/skills/blob/main/skills/frontend-design/LICENSE.txt). Local product doctrine wins; no universal hero/card/novelty prescription. |
| OpenAI skills/plugins | Reuse inspect → interact → inspect → evidence method; postpone wholesale import | [Legacy README](https://github.com/openai/skills/blob/main/README.md) now deprecates that catalog in favor of [plugins](https://github.com/openai/plugins). [Legacy Playwright skill](https://github.com/openai/skills/blob/main/skills/.curated/playwright/SKILL.md) has its own [Apache-2.0 license](https://github.com/openai/skills/blob/main/skills/.curated/playwright/LICENSE.txt). Codex paths/manifests/tool assumptions do not automatically work in Hermes. |
| axe-core | Integrate explicit automated-accessibility evidence category; reuse an existing qualified consumer runner | [Source/limitations](https://github.com/dequelabs/axe-core), [MPL-2.0](https://raw.githubusercontent.com/dequelabs/axe-core/develop/LICENSE). Needs rendered DOM; Paper pixels cannot be scanned. Incomplete findings need manual review; a clean scan is not conformance. |
| Playwright screenshots | Reuse existing consumer path and exact viewport/theme/locale/state baselines | [Official comparisons](https://playwright.dev/docs/test-snapshots), [Apache-2.0](https://raw.githubusercontent.com/microsoft/playwright/main/LICENSE). Same rendering environment matters. Snapshot update is not product approval; keep functional journeys separate. |
| Storybook | Reuse existing component/state inventory; postpone new service installation | [Accessibility](https://storybook.js.org/docs/writing-tests/accessibility-testing), [visual testing](https://storybook.js.org/docs/writing-tests/visual-testing), [MIT](https://raw.githubusercontent.com/storybookjs/storybook/next/LICENSE). Component proof is not route proof. Chromatic cloud upload and spend need existing authority. |
| shadcn/ui and Recharts | Reuse primitives only when the consumer already uses a compatible qualified stack | [Chart docs](https://ui.shadcn.com/docs/components/base/chart), [shadcn MIT](https://raw.githubusercontent.com/shadcn-ui/ui/main/LICENSE.md), [Recharts MIT](https://raw.githubusercontent.com/recharts/recharts/main/LICENSE). Current examples use Recharts v3; inspect installed version. Do not import demo values, default palette or layout as financial truth. |

No extra dependency, cloud upload, new browser runner or third-party skill installation
was performed for these selections. Current integration is the brief/critique/handoff
method and explicit evidence requirements. Actual consumer tools must be discovered
and exercised in the relevant frontend repository before claiming executable integration.
