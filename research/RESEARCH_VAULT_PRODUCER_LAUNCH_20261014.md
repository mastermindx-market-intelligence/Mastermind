# Pinned Research producer launcher

The recurring Research workflow currently executes changing repository heads.
The selected reader expects one exact producer commit. A constant declared SHA
while executing changing code would be false provenance. Original private
journals and the working corpus must also survive runner checkout cleanup.

`ops.research_producer.launch` supplies the invocation mechanism.
It reuses the existing archive manifest and `verify_archive_release`; it creates
no release authority, scheduler, queue, writer lease, deployment or retry engine.
There is no workflow change in this candidate.

## Configuration and invocation

An owner-secured JSON configuration has exactly these fields:

```text
schema = mastermind.research_producer_launch.v1
mastermind_release, mastermind_commit, mastermind_tree
macro_release, macro_commit, macro_tree
manifest_path, manifest_sha256
retention_root, public_checkout, runner_work_root
```

The release/manifest fields use the existing staged archive contract. Both
release roots and the manifest belong to the invoking UID. The expected manifest
digest must be obtained from the actual authorized release owner. The existing stager includes this operations module only when
`include_producer=True` (CLI `--include-producer`) is explicitly selected.
The default reader archive excludes it, and the read-only MCP package retains
its existing no-write fence. The Macro closure must include `engine`, `lib`, and
`scripts/ingest_research.py`; metadata-only fixtures previously missed `lib` and
failed actual PDF extraction. Dependency qualification remains a separate duty.

The existing same-owner retention root must be mode0700, outside both releases,
the public checkout and the runner work root, without symlink traversal. The
public checkout remains separate from the executed source. All paths are
explicit. No fallback to a temporary/shared directory is supplied.

The CLI takes `--config`, `--run-id` and `--attempt`. Its default performs a
read-only preflight and emits an `INERT_PRODUCER_PLAN`. Only an explicit
`--execute` starts a child. The workflow owner supplies the original GitHub run
and attempt; these argument strings do not authenticate the caller or confer
writer authority. The repository identity is fixed to the existing Macro repo.

Run the file directly with the qualified interpreter, independent of the runner's
working directory or `PYTHONPATH`:

```sh
"$PINNED_PYTHON" -I -B "$MASTERMIND_RELEASE/ops/research_producer/launch.py" \
  --config "$OWNER_CONFIG" --run-id "$GITHUB_RUN_ID" --attempt "$GITHUB_RUN_ATTEMPT"
```

The standalone entry point adds only its own resolved release root before
importing its verifier. This does not replace archive verification or host
installation qualification. The same command remains inert without `--execute`.

Before an effectful invocation, the existing owner must qualify protected source,
dependencies, active/pending/manual writers, original unknown effects and the
supported recovery path. Neither a ready plan nor the execute flag supplies
those facts. An absent directory or new workflow attempt cannot authorize
replay of an old BUILDING generation.

## Retained evidence and public output

Execution exclusively reserves `macro-<run>-<attempt>` under the private root.
It never adopts or deletes an existing occupant. `launch.json` binds the selected
source/manifest and claimed original run. A fresh isolated Python child verifies
both archives again before importing the Macro engine, and uses the pinned CLI
with an explicit public mirror and original journal path. Python bytecode is
disabled. Poppler and other temporary files use a new private `tmp` directory.
The CLI reserves its own private journal workspace and corpus.

Raw stdout/stderr go only to mode0600 `output.log`, bounded at32MiB. The parent
extracts one strictly formatted original capture notice directly from that
child's output stream; it never rehashes a later journal to manufacture a capture.
Duplicate, incomplete or oversized output suppresses the capture claim. After
the bound it drains the process without killing it, because termination cannot
settle an in-flight Store request. There is no automatic timeout or retry here;
the incumbent workflow retains its own lifecycle policy.

The private `process-result.json` and public response contain only fixed-schema
source/run metadata, exit code, capture digest if observed and explicit absence
of completion/recovery authority. An exited process plus capture does not prove
COMPLETE, all-writer settlement, dependency qualification or user acceptance.
Failure after reservation reports `ORIGINAL_RUN_UNSETTLED` and preserves the
original carrier. Raw errors, private paths and private report bodies are never
forwarded through the public response.

The launcher refuses admission below2GiB free on the retention volume. This is
headroom, not a retention policy or disk reservation. It does not delete old
evidence to make room. A retention/archival policy needs the existing evidence
owner's positive disposition and must preserve unresolved original operations.
No such policy or host installation is supplied by this source change.

## Validation boundary

The focused tests use real isolated child processes and synthetic archive
manifests with fake producer source. They cover default no effects, archive
tampering before and after parent preflight, original-run collision, path/mode
refusal, private logs and temporary files, exact source/run arguments, bounded
output, missing/duplicate/truncated capture, nonzero exits, and result persistence
failure after the child has executed. They do not exercise live R2 credentials.

The first broader run passed97 of105 cases;8 owner-binding cases could not import
JWT in the default Python environment. Those8 passed unchanged in the existing
qualified Research test environment. No source change was needed for that
environment repair. This is105 distinct passing cases, not one all-green run.

The committed launcher at14fdc017bcb7c461150adb95cd5a8b675b20d1b2 also ran the
actual Macro CLI atbe01e9ec44532d4e6352f00a9be4dfd0cabd0dbb through the existing
stager:806 Mastermind and2008 Macro members verified before/after execution.
With a sanitized credential-free child environment, the actual CLI refused the
absent Store with exit1, preserved exactly one original journal header and its
stream-captured digest, and created no public mirror. Reusing the original run
was refused before child execution. This is actual launcher/CLI integration on
the no-Store path; it does not prove a live generation or dependency installation.

Normal Fabric review `rv-producer-launch-review-01a13301-r1` exhausted host lane
admission before model execution, endingrc75. A later admitted bounded review,
`rv-producer-launch-review-01a13301-r2`, returned no actionable defect and was
accepted after correcting report overstatements about run-ID bounds, same-owner
filesystem races and reservation error handling. It reviewed the original module
placement. The relocation and standalone bootstrap are root-verified deltas;
they are not represented as independently reviewed final bytes. Protected merge,
installed host/dependency proof and live writer adoption remain separate gates.


## Qualified offline dependency candidate

The observed mac-builder-3 environment runs Python3.12.13 on arm64 and remains
mutable: the legacy workflow installs dependencies into a shared per-runner
venv. Source pinning does not freeze that environment. This change neither
modifies that venv nor directs the recurring workflow to a new one.

`requirements/research-producer-macos-arm64-py312.lock` pins the12 observed
producer dependency versions to12 downloaded wheels (17,456,927bytes). Its
SHA256 is0c43d2132a6afaba75e5b5720c234d1b565679b650d7c04c024a1a12d711206a.
A new external-SSD venv installed them offline with `--require-hashes` and
`--no-index`; `pip check` passed. The existing reader archive's Linux dependency
lock remains unchanged; this separate producer lock is not implicitly selected
or installed by the source archive verifier or launcher.

That isolated environment ran the actual pinned be01e9ec CLI against a new
synthetic LocalStore using installed Poppler. All3members reached COMPLETE/full;
receipt/PDF/immutable derivative/corpus hashes and the original journal capture
matched; the public mirror excluded generation metadata. Four Poppler processes
ran, temporary PDFs were cleaned, and network use was refused. This direct CLI
fixture qualifies the dependency closure for that extraction/publication path;
it does not test live R2, the production launcher with a live Store, or arbitrary
optional producer features. Interpreter and Poppler byte observations do not
prove an immutable host installation. Selecting and qualifying the separate
venv remains part of the held concrete deployment action.

## CI boundary repair (2026-10-15)

Hosted run38604579228 correctly rejected the original placement because the
read-only MCP package contained the producer's private journal writes. The
launcher now lives in `ops/research_producer/launch.py`; it is never imported by
the reader. The stager's explicit producer option includes that exact file in
the manifest while preserving the default reader-only archive. The original
no-write fence is unchanged. Focused packaging and actual child-process checks
cover the new import and archive paths: 114 affected cases passed in the
qualified Python 3.12 environment, including the unchanged static fence. Earlier
no-Store integration evidence applies to the prior module path. Separate exact
44f1c6b relocation probes verified the actual CLI's no-Store refusal, a four-member
COMPLETE generation through actual boto3 against a loopback synthetic S3 service,
and refusal after a lost conditional-write acknowledgement. Those probes do not
prove live R2 or installed writer admission.

The direct `-I -B` entry point initially failed with `ModuleNotFoundError` because
the earlier probes supplied its import root. Three causal standalone cases failed
on44f1c6b. After the bounded bootstrap repair, all36 launcher/static-fence cases
pass. From an unrelated directory with a hostile `PYTHONPATH`, the actual file
performs inert preflight, runs its synthetic child, and rejects changed producer
source before reservation. No foreign module executes and no bytecode is written.
