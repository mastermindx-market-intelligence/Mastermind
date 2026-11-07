# Gateway ACL bracket: controlled fixture diagnostic, 2026-11-07

## Result and boundary

Two local disposable-fixture checks passed: **2 passed, 0 skipped or failed**,
70.762 seconds controller time. The unchanged publication owner refuses a real
directory-metadata change inside its ACL observation bracket and retains its
LOCKED transaction. Creating the same owned child before publication permits
both successor publications and preserves predecessor-history bytes, inode
and modification time.

This proves the controlled source mechanism. It does **not** prove the cause of
the historical native failure, installed Root custody, live service acceptance,
or clearance of the [independent Release HOLD](https://github.com/mastermindx-market-intelligence/Mastermind/pull/2065#issuecomment-6704040875).

Executed worktree HEAD: `ce7ab5c955cd50b670ba7b1dc22bdbc1b64d3f8b`.
The tested production/fixture sources are unchanged from published c854:

| Source | Exact Git blob |
| --- | --- |
| `ops/executive_os/os_gateway_studio_reader.py` | `0d998624b90b2b06033a8e593b7e1b69704046f2` |
| `ops/executive_os/autonomy_control.py` | `83c85ced253bef0c7ce95f026b3d01b2686df5a8` |
| `tests/test_os_gateway_successor_publication.py` | `d8d78a6a8fa99ca290d4d94a97d49d1020c9a0d3` |

Local runtime: M2 Studio, Darwin, Python 3.14.7 / pytest 9.1.1.
The existing fixture remaps installed identities and service boundaries; its
transaction, filesystem, ACL-wrapper, stat comparison and publication machinery
remain real. No production source changed. The diagnostic used its own private
pytest base; ordinary fixture teardown removed only its disposable gateway trees.

## Observed refusal and retained state

The injected call executes the real `_observe_object_acl_value`, then creates
one child in the owned fixture's watched traversal-prefix directory before the
real caller performs its nine-field comparison. Only after a genuine LOCKED
marker exists does the wrapper arm.

The changed fields were exactly `st_nlink`, `st_size`, `st_mtime_ns`,
`st_ctime_ns`. Device, inode, mode, UID and GID stayed equal. The actual chain was:

- `TransactionEffectUnknown` at `execute_gateway_publication:11326`.
- `GatewayPublicationError(code="gateway_studio_invalid")`, through
  `execute_gateway_publication:11280`, `_recheck_gateway_preimages:7728`,
  `_recheck_gateway_bound:7711`, `observe_studio:6673`.
- `StudioObservationError`, through `observe_studio:6666`,
  `observe_studio_files:1416`, `descend:1043`, `open_child:869`,
  `_observe_object_acl:697`, `_require_same_object:219`, `_refuse:123`.

The injected wrapper returned normally; the production comparator caused the
refusal. All three public target files, both configs and the public predecessor
retained their exact bytes and device/inode identities. The public predecessor
remained 0444; its private marker archive remained 0400. The same marker inode,
transaction ID, operation and expected SHA remained LOCKED. Permanent predecessor
history was absent and its manifest identity remained null. No retry was issued
on that retained failed fixture.

The stable control uses a fresh fixture. It creates the same child before the
publication sequence, performs both successors, and retains the original
history's bytes/inode/mtime. This separates a changing ACL bracket from the
mere presence of an unrelated child.

## Exact executed diagnostic

The source below is the exact executed file; SHA256
`0cab810b2fea56d6787538466ff9d98888f1f0979d29c59e85684d2798b98b72`.
It is a fixture diagnostic, not a replacement implementation or an admission
override. Run it from the matching checkout with that checkout and its tests
directory on PYTHONPATH, using a fresh private pytest base. The observed command
used the local runtime, `-m pytest -q`, the diagnostic file, explicit checkout
root, private `--basetemp`, and JUnit output.

```python
"""Controlled source-mechanism diagnostic; no installed or native-cause claim."""
import json
import os
import stat
from pathlib import Path

import pytest
from ops.executive_os import autonomy_control as control
from ops.executive_os import os_gateway_studio_reader as reader
from tests import test_os_gateway_publication_owner as incumbent
from tests.test_os_gateway_successor_publication import (
    gateway, gateway_tmp_path, successor, publish, prepare_successor, history,
)

OUTPUT = Path(__file__).parent
CUSTODY = ("st_dev", "st_ino", "st_mode", "st_uid", "st_gid")
ENTRY_METADATA = {"st_nlink", "st_size", "st_mtime_ns", "st_ctime_ns"}

def identity(path):
    stamp = incumbent._TRUE_STAT(path)
    return (stamp.st_dev, stamp.st_ino)

def exception_frames(error):
    result = []
    pending = [error]
    seen = set()
    while pending and len(seen) < 9:
        item = pending.pop()
        if item is None or id(item) in seen:
            continue
        seen.add(id(item))
        frames = []
        tb = item.__traceback__
        while tb is not None:
            mod = tb.tb_frame.f_globals.get("__name__", "")
            if mod in ("ops.executive_os.autonomy_control", "ops.executive_os.os_gateway_studio_reader"):
                frames.append([mod, tb.tb_frame.f_code.co_name, tb.tb_lineno])
            tb = tb.tb_next
        result.append({"type":type(item).__name__, "frames":frames})
        pending.extend((item.__cause__, item.__context__))
    return result

def test_owned_prefix_child_during_real_acl_bracket_preserves_locked_transaction(successor, monkeypatch):
    s, request, prior = successor
    paths = (*s.target_paths(), control.CONTROL_CONFIG, control.WORKER_CONFIG, control.OS_GATEWAY_RECEIPT)
    before = {p:(p.read_bytes(), identity(p)) for p in paths}
    watched = tuple(s.tmp_path.resolve().parts[1:])
    real = reader._Walk._observe_object_acl_value
    seen = []
    def inject(walk, name, fd, pre, path):
        result = real(walk, name, fd, pre, path)
        if path != watched or seen or not control.AUTONOMY_TRANSACTION.exists():
            return result
        marker = s.host._manifest()
        if marker.get("phase") != "LOCKED":
            return result
        assert marker["operation"] == control.OS_GATEWAY_PUBLICATION
        assert marker["transaction_id"] == s.host._active_transaction.transaction_id
        assert marker["expected_sha"] == request.expected_sha
        assert walk._traversal_only(path) and path in walk._prefix_guard._held
        marker_identity = identity(control.AUTONOMY_TRANSACTION)
        os.mkdir("owned-acl-bracket-child", mode=0o700, dir_fd=fd)
        post = os.fstat(fd)
        changed = [field for field in reader._IDENTITY_FIELDS if getattr(pre,field) != getattr(post,field)]
        assert changed and set(changed) <= ENTRY_METADATA
        assert all(getattr(pre,field) == getattr(post,field) for field in CUSTODY)
        seen.append({"marker_identity":marker_identity,"transaction_id":marker["transaction_id"],"changed_fields":changed})
        return result
    monkeypatch.setattr(reader._Walk, "_observe_object_acl_value", inject)
    with pytest.raises(control.TransactionEffectUnknown) as caught:
        publish(s, request)
    error = caught.value
    assert len(seen) == 1
    assert type(error.__context__) is control.GatewayPublicationError
    assert error.__context__.code == "gateway_studio_invalid"
    assert type(error.__context__.__cause__) is reader.StudioObservationError
    frames = exception_frames(error)
    functions = {frame[1] for item in frames for frame in item["frames"]}
    assert {"execute_gateway_publication", "_recheck_gateway_preimages", "_recheck_gateway_bound",
            "observe_studio", "open_child", "_observe_object_acl", "_require_same_object", "_refuse"} <= functions
    assert (s.tmp_path / "owned-acl-bracket-child").is_dir()
    assert all(p.read_bytes() == raw and identity(p) == stamp for p,(raw,stamp) in before.items())
    assert control.OS_GATEWAY_RECEIPT.read_bytes() == prior
    assert stat.S_IMODE(control.OS_GATEWAY_RECEIPT.stat().st_mode) == 0o444
    marker = s.host._manifest()
    assert marker["phase"] == "LOCKED"
    assert marker["operation"] == control.OS_GATEWAY_PUBLICATION
    assert marker["expected_sha"] == request.expected_sha
    assert marker["transaction_id"] == seen[0]["transaction_id"]
    assert identity(control.AUTONOMY_TRANSACTION) == seen[0]["marker_identity"]
    assert marker["gateway_predecessor_archive_identity"] is None
    assert not history(request).exists()
    retained = control.AUTONOMY_TRANSACTION / control._GATEWAY_RECEIPT_ARCHIVE
    assert retained.read_bytes() == prior and stat.S_IMODE(retained.stat().st_mode) == 0o400
    (OUTPUT / "injected-result.json").write_text(json.dumps({
        "classification":"CONTROLLED_MECHANISM_PROVEN",
        "injection_count":len(seen),
        "changed_fields":seen[0]["changed_fields"],
        "custody_fields_unchanged":True,
        "public_targets_and_configs_unchanged":True,
        "public_prior_mode":"0444",
        "private_prior_mode":"0400",
        "marker_retained":"LOCKED",
        "history_absent":True,
        "exception_chain":frames,
        "historical_native_cause_proven":False,
        "release_hold_cleared":False,
    },indent=2)+"\n")

def test_same_owned_child_before_publication_preserves_successor_history(successor, monkeypatch):
    s, request, prior = successor
    (s.tmp_path / "owned-acl-bracket-child").mkdir(mode=0o700)
    publish(s, request)
    first_history = history(request)
    stamp = first_history.stat()
    next_request, second_receipt = prepare_successor(s, monkeypatch, "e"*40)
    publish(s, next_request)
    assert first_history.read_bytes() == prior
    assert (first_history.stat().st_ino, first_history.stat().st_mtime_ns) == (stamp.st_ino,stamp.st_mtime_ns)
    assert history(next_request).read_bytes() == second_receipt
    assert json.loads(control.OS_GATEWAY_RECEIPT.read_bytes())["predecessor_receipt_sha256"] == incumbent.digest(second_receipt)
    assert not control.AUTONOMY_TRANSACTION.exists()
    (OUTPUT / "stable-result.json").write_text(json.dumps({
        "classification":"STABLE_CONTROL_PASSED",
        "successor_publications":2,
        "prior_history_bytes_inode_mtime_preserved":True,
        "transaction_marker_absent":True,
        "installed_acceptance":False,
    },indent=2)+"\n")
```

## Executed result

```json
{
  "returncode": 0,
  "elapsed_seconds": 70.7624401669018,
  "counts": {
    "tests": 2,
    "errors": 0,
    "failures": 0,
    "skipped": 0
  },
  "results": {
    "injected-result.json": {
      "classification": "CONTROLLED_MECHANISM_PROVEN",
      "injection_count": 1,
      "changed_fields": [
        "st_nlink",
        "st_size",
        "st_mtime_ns",
        "st_ctime_ns"
      ],
      "custody_fields_unchanged": true,
      "public_targets_and_configs_unchanged": true,
      "public_prior_mode": "0444",
      "private_prior_mode": "0400",
      "marker_retained": "LOCKED",
      "history_absent": true,
      "exception_chain": [
        {
          "type": "TransactionEffectUnknown",
          "frames": [
            [
              "ops.executive_os.autonomy_control",
              "execute_gateway_publication",
              11326
            ]
          ]
        },
        {
          "type": "GatewayPublicationError",
          "frames": [
            [
              "ops.executive_os.autonomy_control",
              "execute_gateway_publication",
              11280
            ],
            [
              "ops.executive_os.autonomy_control",
              "_recheck_gateway_preimages",
              7728
            ],
            [
              "ops.executive_os.autonomy_control",
              "_recheck_gateway_bound",
              7711
            ],
            [
              "ops.executive_os.autonomy_control",
              "observe_studio",
              6673
            ]
          ]
        },
        {
          "type": "StudioObservationError",
          "frames": [
            [
              "ops.executive_os.autonomy_control",
              "observe_studio",
              6666
            ],
            [
              "ops.executive_os.os_gateway_studio_reader",
              "observe_studio_files",
              1416
            ],
            [
              "ops.executive_os.os_gateway_studio_reader",
              "descend",
              1043
            ],
            [
              "ops.executive_os.os_gateway_studio_reader",
              "open_child",
              869
            ],
            [
              "ops.executive_os.os_gateway_studio_reader",
              "_observe_object_acl",
              697
            ],
            [
              "ops.executive_os.os_gateway_studio_reader",
              "_require_same_object",
              219
            ],
            [
              "ops.executive_os.os_gateway_studio_reader",
              "_refuse",
              123
            ]
          ]
        }
      ],
      "historical_native_cause_proven": false,
      "release_hold_cleared": false
    },
    "stable-result.json": {
      "classification": "STABLE_CONTROL_PASSED",
      "successor_publications": 2,
      "prior_history_bytes_inode_mtime_preserved": true,
      "transaction_marker_absent": true,
      "installed_acceptance": false
    }
  },
  "script_sha256": "0cab810b2fea56d6787538466ff9d98888f1f0979d29c59e85684d2798b98b72",
  "historical_native_cause_proven": false,
  "release_hold_cleared": false
}
```

## Next evidence

The shared-checkout-ancestor fixture hypothesis is now mechanically demonstrated,
but original-run causality still needs its source-bound native exception chain
and relevant namespace observation. Preserve the existing finite failure notes
for the next natural occurrence. Keep all nine registration/ACL identity fields,
the qualified five-field traversal checks, real effect reconciliation and the
independent Release HOLD intact.
