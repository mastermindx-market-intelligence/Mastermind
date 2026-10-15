# CI observation guidance repair

The CI guard already permits a bounded same-run read after its 300-second window.
Its old message said not to wait for the timer, while assuming an asynchronous
watcher might return. A principal persisted that as a permanent ban and repeatedly
read its own checkpoint. The PreToolUse advisory also said a watcher was armed
before the tool actually ran. Neither message proved a completion return existed.

`ACTIVE_EXECUTION.md` owns the shared observation-liveness instructions. The bounded
installer below copies its marked block into the two installed account instruction
files and replaces only the known guidance strings in the existing guard/context
hooks. It does not alter permission decisions, cooldown timing/state, hook bindings,
worker routing, service settings or automation schedules. The historical guard
fixture remains unchanged and supplies the red regression witness.

## Qualify and install on an authorized host

Run from the accepted source checkout:

```sh
python3 -m pytest tests/test_ci_wait_guidance.py
python3 scripts/install_ci_wait_guidance.py
python3 scripts/install_ci_wait_guidance.py --apply --evidence /absolute/new/evidence-directory
```

The default dry-run names exactly four files under the current user's home. All
four must match the known local anchors or the already-installed correction.
Unknown or duplicated guidance, missing files and target symlinks are refused;
reconcile drift rather than overwriting another version. All targets are checked
before the first write and rechecked immediately before their individual writes.
This is an attended installation, not a lock against concurrent account installers.
Keep one writer for these four files.

Each changed file has an exact-byte backup in the new evidence directory, installed
with its previous mode. Replacement is atomic per file, not across the four files.
A failure records `PARTIAL_FAILURE` with the paths already written; do not claim
complete installation or blindly roll back over concurrent edits. Reconcile those
specific files, then resume the idempotent plan with a new evidence directory.

After installation, read back the hashes and execute the installed guard/context
in a fresh Python process with isolated **test** session state. Verify first read,
cooldown refusal, expiry admission, real refusal preservation and the request-only
watcher message. Do not reset a real operation's cooldown or execute GitHub mutations
as tests. Static Codex instruction discovery may verify file selection, but is not
proof a previously loaded conversation consumed the new instructions.

The regression suite proves the guidance and unchanged guard behavior, not a model's
future judgment. Global files apply to future local instruction loads; already-open
chats and other hosts need their own actual load/install evidence. Existing observer
prompts containing the old permanent ban need a bounded, authorized correction using
their original automation identity. Preserve notification policy, human decisions,
original grants and uncertain effects; do not create replacement observers.
