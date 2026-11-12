# Hermes history migration

Turn a **copy** of a Hermes agent's SQLite state database into a read-only,
searchable per-teammate archive, with credential redaction and an exact
count check. The real export is run by the lane lead against a copy of the
live store — this tool never opens the live database itself.

## Commands

```bash
# Export (source must be a COPY, e.g. a file copied out of the live store)
python3.12 export_history.py export --source /path/to/copy.db \
    --profile <teammate> --out /path/to/archive_dir [--forbid-root PATH ...]

# Recompute counts: source copy vs archive.sqlite (one JSON line, exit 0 = pass)
python3.12 export_history.py verify --source /path/to/copy.db --archive /path/to/archive_dir

# Operator search over the archive (read-only)
python3.12 search_history.py <archive_dir> <query...> \
    [--role user|assistant|tool] [--since YYYY-MM-DD] [--until YYYY-MM-DD] \
    [--session <id prefix>] [--limit N (default 10, max 50)] [--json]
python3.12 search_history.py <archive_dir> --show <src_id>   # full message + 2 before/after
```

## Refusal rules (exit 1, one-line reason)

- `--source` whose realpath is under `~/.hermes` (the live store), under any
  `--forbid-root`, or that is a symlink. The source is opened only as
  `file:<path>?mode=ro` and is never written.
- `--out` whose realpath is under `~/.hermes` or `~/.mastermind/t3-team` or
  any `--forbid-root`, or that already exists and is non-empty (no overwrite).
- After writing, every file is `0400` and every directory `0500`: the archive
  is read-only by construction.

## What the archive contains

- `archive.sqlite` — every source session and message row (including
  inactive/compacted rows, flags kept), with redacted `content`, `tool_calls`
  and `title`; FTS5 indexes over message content/tool names and session titles.
- `sessions/<date>_<source>_<id prefix>.md` — human-readable transcript per
  session. Tool output is truncated at 4000 chars (full text stays in
  `archive.sqlite`, referenced by `src_id`).
- `INDEX.md` — newest-first session list with totals.
- `manifest.json` — counts, redaction counts by kind, date range, source
  sha256, and `count_check` (export exits non-zero if it fails).

**Omitted on purpose:** `reasoning`, `reasoning_content` and `api_content`
are not copied — they are internal model state, not conversation history,
and may contain unredacted sensitive material. The manifest records how many
rows had each field non-empty (`omitted_fields`); the originals stay in Hermes.

**Redaction:** credential-shaped strings (API keys, tokens, PATs, JWTs,
Bearer tokens, PEM private keys, key=value secrets, URL passwords) become
`[REDACTED:<kind>:<sha256 prefix>]`. Bare git SHAs and UUIDs are untouched.
Redaction is idempotent.

## How a teammate searches

The archive is plain files: use **Read** on `INDEX.md` to find sessions, then
**Read/Grep** over `sessions/*.md` — no tooling needed, and the files are
read-only. Operators who want ranked full-text search with role/date/session
filters use `search_history.py` (snippets mark matches with `[[...]]`;
`--show <src_id>` prints a full message with its neighbors).

## Tests

Synthetic fixtures only (tmp dirs); no real database is ever opened:

```bash
TMPDIR=/tmp env -u PYTHONPATH /opt/homebrew/bin/python3.12 -m pytest -q \
    -p no:cacheprovider tools/mmos_hermes_migration/tests/<file>
```

## stage_teammates.py

Stages per-teammate install files under `--out` from a roster spec and a plan
file: the roster with a `memory_link` block per planned teammate (each on its own
instance), the memory-link MCP and server configs (0600), and a cutover spec for
each teammate not yet moved, with `primaryThreadId` left as `FILL-AT-INSTALL`.
It reads no conversation, memory or credential.

```
python3.12 -I stage_teammates.py --roster ROSTER.json --plan PLAN.json --out DIR
```
