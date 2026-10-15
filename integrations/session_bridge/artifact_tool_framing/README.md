# Separate artifact seal tool output from the final manifest

Two original Qwen reviews returned useful text but completed with rc65. The local
seal helper printed a `FABRIC_ARTIFACTS_V1` line into the captured tool transcript,
and the instructed final answer repeated that identical line. The strict completion
parser correctly rejected the two terminal manifests. `SAME_RUN_DISPOSITION.json`
binds the retained bytes and preserves both failures and their unaccepted status.

This package changes the future producer instruction and its existing local helper:

1. New packets call `artifact_production.py seal --tool-output --packet ...`.
2. That option emits `FABRIC_ARTIFACT_SEAL_V1` followed by the unchanged manifest JSON.
3. The final answer changes only the prefix to `FABRIC_ARTIFACTS_V1` and copies the
   JSON verbatim. It remains the sole terminal manifest in the transcript.

Legacy `seal --packet ...` output remains byte-compatible. The parser, supported
Markdown wrappers, scope checks, file observations, support binding, permissions,
producer receipt and acceptance paths are unchanged. Identical or conflicting
duplicate terminal lines still fail. Tool diagnostics alone cannot establish
completion, and cannot mask a wrong parent or file digest. The new diagnostic
marker is reserved in new packet bodies alongside the existing protocol markers.

## Source and qualification

The exact installed preimage is `e126d6432135725a7a7846cbe9f9749305dfe9dd7cfe37037fc413a1136248bf`.
`artifact_production.base.py` preserves it; `artifact_production.py.patch` targets
that preimage under the incumbent `ext/` directory. This is a source package,
not an installed replacement or a second runtime.

The ten focused future-protocol checks produced five RED and five PASS against
the preimage. The repaired candidate passes those ten plus the 24 existing
framing/identity/file/producer regressions: 34 PASS, no failures, errors or skips.
The baseline failures are the missing opt-in CLI/instruction/reserved-marker
behavior, not a claim that all five are independent production incidents.
`QUALIFICATION.json` pins the candidate, XML inventories and imported installed
dependencies. Tests exercise the real CLI entry point with inert binding/file
observation stand-ins, followed by the actual strict parser. They are not live
worker execution or installed adoption evidence.

Run the affected checks with the existing test interpreter:

```sh
python -m pytest -q test_tool_framing.py test_manifest_compatibility.py --tb=short
```

`test_manifest_compatibility.py` is the exact previously qualified test source
from `artifact_manifest_framing/test_manifest_framing.py`; the wrapper repair
is retained. `ARTIFACT_SOURCE` selects a base or candidate for these inert checks.

## Same-run disposition and remaining release gates

Neither historical rc65 run becomes eligible for export or acceptance from this
prospective fix. No raw output was normalized or changed, no remote observation
or export was performed, and no worker was replayed. Their retained prose may
inform the assigning parent's source repairs. The older unresolved R2 run retains
its original UNKNOWN/refusal/lease state.

Principal source adjudication, protected publication/release and separately
qualified installed adoption remain required. A future useful admitted artifact
task must prove the new protocol in its actual tool transcript and assigning
parent consumption; this package creates no worker or live effect. It does not
prove native RuntimeBinding, idle Wake or the wider integration mission.
