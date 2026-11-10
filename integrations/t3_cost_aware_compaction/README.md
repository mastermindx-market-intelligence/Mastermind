# Mastermind T3 cost-aware adaptive compaction

**Owner boundary:** local configuration policy for existing T3 Claude provider homes.
T3/Claude Code remain the actual session, compaction, token usage, cache, and lifecycle
owners. This service does not send messages, invoke /compact, restart sessions,
summarize histories, provision provider accounts, or alter Capacity Fabric routing.

## What is installed

A five-minute, low-priority macOS LaunchAgent calls compaction.py --apply.
It reads only local Claude Code token usage metadata from bounded tails of
recent JSONL transcripts and optionally the local T3 rate catalog. It then
atomically updates modelSettings[model].autoCompactWindow within the THREE
currently enabled T3 provider homes. It does not read prompt, message, or tool
content into its retained output, nor write running T3 server settings.

Claude Code/T3 apply the updated per-model thresholds to subsequent new
provider processes/turn launches. Already running turns are unaffected.
Other T3 settings, plugin config, and environment variables are preserved.

## Policy

- Fable 5.x: 200K baseline, 175K-350K dynamic range.
- Opus 5.5/5/4.8/4.7: 250K baseline, 225K-400K dynamic range.
- Opus 4.6: 180K fixed (not necessarily using its 1M variant).
- GLM 5.3, GLM Flash, DeepSeek/MiniMax/Qwen Flash, Fable free: 900K
  fixed, capped by the underlying model and gateway. Actual 1M eligibility
  must be checked at the gateway independently.

Premium models receive up to +100K when observed cache reuse is high and local
API-equivalent input cost is low. Lower cache reuse and high cost may cause -25K.
Fewer than six qualified usage samples, missing rate data, or a malformed
price record resets the model to baseline rather than guessing. Changes
are limited to 50K per update and respect per-model floors.

Price limitation: the T3 LiteLLM-style catalog is a cost proxy and may
not represent exact Capacity Fabric negotiated or Claude subscription billing.
Fable 5.2 uses 5.1's catalog price as a labelled proxy when 5.2 is absent.
No savings or live effective thresholds are claimed from config alone.

## Verify

python3 ~/.t3/tools/adaptive_compaction/compaction.py
python3 -m unittest discover -s ~/.t3/tools/adaptive_compaction -p 'test_*.py' -v
cat ~/.t3/tools/adaptive_compaction/latest-decisions.json
launchctl print gui/$(id -u)/com.mastermind.t3.adaptive-compaction

latest-decisions.json retains aggregate usage counts, cache ratios,
API-equivalent cost estimates and policy decisions only; no transcripts
or credentials. New threshold applies at next Claude process launch.

## Rollback / pause

Pause: launchctl bootout gui/$(id -u)/com.mastermind.t3.adaptive-compaction.
Revert per-provider settings from settings.json.bak-adaptive-compaction-*
backup only after stopping this agent and reconciling later legitimate user
changes. Do not restore a whole stale file over newer live settings:
selectively restore its modelSettings keys. The agent never kills T3.

Re-apply with the installer. Managed fields can be changed in its
source policy; edits are not automatic model admission or capacity guarantees.

## Source

Source + focused tests belong in Mastermind integrations/t3_cost_aware_compaction/
for durable rollout. Deployed copy: ~/.t3/tools/adaptive_compaction/.