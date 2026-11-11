# The review panel: how a critical diff is reviewed (plan V4 section 26)

A diff on a critical surface (admission, credentials, exactly-once, source authority, an
installer, a cut-over) is accepted only after this panel has read it. The panel replaced the
single Opus review on 2026-11-11, after a measured comparison on one commit
(`~/.mastermind/mmos_evidence/r2cal-20261111/SCORE.md`): three DeepSeek reviewers with one
narrow question each found more than one Opus reviewer with the whole scope, and the narrow
question, not the model, is what found the hardest defect.

## Who runs it

The principal, or a lane driver for its own children's diffs before it returns. A lane's own
panel does not replace the principal's: the principal runs one on the merged result.

## Set-up

1. Commit first. Export the files under review at that commit to a scratch folder, for
   example `git archive <commit> <paths> | tar -x -C /tmp/<name>/src`. Reviewers read the
   export, not the checkout. Do not change those files until every reviewer has returned.
2. One reviewer per question, each `deepseek-v4.1-flash` at effort `max`, started together.
   Each gets its own result folder `/tmp/<name>/<q>/`.
3. One `kimi-k3.1-pro` reviewer with the attacker's brief when the Kimi pool is free. If it
   fails with a full pool, wait five minutes and restart the same thread once; if it fails
   again, go on without it and say so.
4. Reviewers are blind to each other, to the lane's own attack round and to earlier findings.
   Their session start shows the checkout's recent commit subjects and the memory index, so a
   commit subject must not describe the defect a reviewer is meant to find unprompted.

## The questions

Use every question that applies to the diff; add a fifth when the surface has its own.

1. **Trust.** Whose words or bytes does this code trust, and can the wrong ones win? Follow
   every piece of text or data from where it enters to where it is acted on: issue text,
   comments, thread messages, file contents, environment values, addresses, names.
2. **Failure.** For every call that leaves the process (HTTP, subprocess, file write): what
   happens when it fails, times out, or succeeds without its answer arriving? What is done
   twice, what is lost, what is left half-written?
3. **States.** List every state the record can be in and every reason this code can be
   started. For each pair, what does it do? Look for the pairs the author did not walk
   through: a person changed the record by hand, two runs overlap, the run is a retry.
4. **Install and undo.** Installation, cut-over, upgrade and rollback: what is replaced while
   something else is reading it, what a second run does, what rollback restores and loses.

Attacker's brief (Kimi): you control one input the code reads (name which). Get it to run a
program of your choosing, disclose a credential, or act as someone else.

## What every reviewer is told

- Read only `/tmp/<name>/src`. Write only your result folder. No network, no server, no
  `launchctl`, no git, no real run of an installer or a shell script. Probes are small Python
  files in your folder that import the code under review and use fakes.
- Write `findings.md` in your folder within the first ten minutes and keep adding to it.
  (Long runs are sometimes cut by a gateway error; the file is what survives.)
- First line: your model. Then one table: number, severity (HIGH, MEDIUM, LOW), state
  (REPRODUCED with the probe file's name, TRACED, or PLAUSIBLE), file and lines, what goes
  wrong, the concrete trigger. A finding without a trigger is not a finding.
- Then "What I checked and found sound" and "Lines not read". Do not summarise.

## What the principal does with the results

- Verifies every HIGH finding against the code, and any finding it will act on, before
  acting. A finding is scored real, false, by design, or not on the installed system.
- Sends real findings to the lane that owns the file, each with a failing test first.
- Records what the panel missed whenever a later check finds it, in the scoring file, so the
  questions improve. Question 3 exists because the first panel's three misses were of that
  kind.
- A panel that finds nothing proves nothing by itself.
- Opus is used for one case only: a change that cannot be undone once applied, where the
  panel's answers disagree.
