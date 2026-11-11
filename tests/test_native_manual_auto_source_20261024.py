"""F1: real native preview/request AUTO contract from SHA-sealed source only.

No real provider, host, token, lease, state directory, live process, or release
selection is accessed. Source is recreated in a disposable isolated review stage.
"""
from __future__ import annotations

import hashlib
import base64
import json
import zlib
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
NATIVE = ROOT / "ops/native_fabric/quota_continuity"
PATCH = ROOT / "ops/native_fabric/patches/native_generation_manual_preview_20261022.patch"
FIXTURE = ROOT / "ops/native_fabric/qualification/native_manual_preview_fixture.py"
# The six converged AUTO pre-release members are busy-scoped sources; the
# reviewed default candidate/ keeps master's pre-busy bytes.
BUSY_SOURCE = NATIVE / "candidate/broker_busy_2121"
HISTORICAL_TASK = ROOT / "research/proposals/fabric_refusal_diagnostics_20261102/fabric_task.py.base"
PRE_LONG_HORIZON_TASK_SHA = "ca091b1e21f5b9d3349e7ce31ae46dff6173d27b5f36d432179418415f03eb88"
PRE_POLL255_TASK_SHA = "778f4f3ebf03f5ce93e60081dc8a739ae90fb4cbeb32d01bbcc7b008c813a23b"
PRE_POLL255_WITH_UBUNTU4_TASK_SHA = "36fbd16469befa0f4ade8d75fe15b3384a042b726668879c59ae03c82d194058"
PRE_REMOTE_CWD_TASK_SHA = "a653f55fb41fc26cd2efd6e18cb4747025bc85e00ad1ebf11898a6c2d12e41cd"
PRE_REFUSAL_DIAGNOSTICS_TASK_SHA = "72f6b0d70d4596c1d059cf57504ff7fd39ca6d3464d96e9f9c6c8172b1a69037"
PRE_ADMISSION_TASK_SHA = "2d66d51376b4bfd9740947988777809ee53c0314d7155ad2bd73c9a9ec44b7e4"
CURRENT_TASK_SHA = "1bdec660216cd3218d46c5740eee7d4f24a74c3f2dc23b61083dfc503c9d1d68"
# The 2121 converge composes the AUTO prelease busy fallback onto the exact
# current epoch: applying the busy inverses below to the busy source must land
# on CURRENT_TASK_SHA. The busy task is the converged candidate fabric_task.
BUSY_TASK_SHA = "0e85036189cc074c3b1a463304f1ccadba82038beadff3b51255c1ef2ec68d66"
BUSY_PICK_SHA = "c433384faab5862a05dcc4bd84273ee1b5aa9293271166079c2874375e46a057"
SOURCE = {
    "ext/fabric_task.py": ("fabric_task.py", "3ceba9777a475fb1cfc568f13035b4c23ae15c7bd54316c4cb006335557a545b"),
    "ext/pick.py": ("pick.py", "a3c3a9822779e244f4140dc1223c4a2617243ed35c12c0358527d637fc1fc1ee"),
    "pool": ("pool_launcher.sh", "4026eb128fe803e575151bbeec49a4d8f5838408db1177feedd64ad24f4f2059"),
}
AFTER = {
    "ext/fabric_task.py": "48699864fdc9e96d12f51ff22fef74bd438a2fcd500f25c836e6fab2dea728d7",
    "ext/pick.py": "9bbb96c8da84e38bbd802fdd373a0e8ba386395abc5a80bc8628b49d5afd8174",
    "pool": "12602edd2f0bf3a5a789eb2b77043a1973bbed533ff35d307357e00be1531679",
}
COMPOSED_PICK = "5d37967731337fa6d49a6a119d415c66fcc35802c167b16de7e8a1751f950892"


def _preobserver_picker():
    """Keep F1/R28's exact protected predecessor; S9 is prospective only."""
    value = json.loads((ROOT / "tests/fixtures/fabric-selection-preobserver-pick-9f65957e.json").read_bytes())
    assert value["schema"] == "fabric.selection-preobserver-source.v1"
    assert value["commit"] == "9f65957e29eba92245d78609f032aaea523b7cb4"
    assert value["path"] == "ops/native_fabric/quota_continuity/candidate/pick.py"
    assert value["blob"] == "dd542dbc5bb746c0ad1428b177b25a98b7a02536"
    raw = zlib.decompress(base64.b64decode(value["zlib_base64"], validate=True))
    assert len(raw) == value["bytes"] == 118474
    assert hashlib.sha256(raw).hexdigest() == value["sha256"] == "4311200ae485ffd19b2560434e46c0c01899fbb58f0793c198292dba6004503b"
    return raw


def _pre_refusal_diagnostics_task(value: bytes) -> bytes:
    """Undo only the exact diagnostic successor inside the disposable F1 stage."""
    assert hashlib.sha256(value).hexdigest() == PRE_ADMISSION_TASK_SHA
    pairs = (
        (
            b"# Closed diagnostics only: these labels grant no routing, retry or acceptance.\n"
            b"# Never retain arbitrary picker text, provider output, paths or account detail.\n"
            b"_REQUEST_REFUSAL_CODES = frozenset({\n"
            b"    \"NO_OPERATOR_AVAILABLE\", \"NO_POOL_AVAILABLE\", \"NO_ROUTE\",\n"
            b"    \"ROUTE_INCOMPLETE\", \"REQUEST_ROUTING_RETURN_UNQUALIFIED\",\n"
            b"    \"REQUEST_MAX_TURNS_INVALID\", \"REQUEST_MAX_TURNS_ROUTE_UNSUPPORTED\",\n"
            b"    \"ECONOMIC_POLICY_REFUSED\", \"UNCLASSIFIED_PRELAUNCH_REFUSAL\",\n"
            b"})\n"
            b"\n"
            b"\n"
            b"def _safe_request_refusal_code(exc: BaseException) -> str:\n"
            b"    unknown = \"UNCLASSIFIED_PRELAUNCH_REFUSAL\"\n"
            b"    if type(exc) is not FabricTaskError:\n"
            b"        return unknown\n"
            b"    args = exc.args\n"
            b"    if not args or type(args[0]) is not str or len(args[0]) > 1024:\n"
            b"        return unknown\n"
            b"    message = args[0]\n"
            b"    # The deadline-aware picker runs in an owned subprocess. It returns only\n"
            b"    # this fixed no-operator marker; historical receipts omitted the cause.\n"
            b"    if message == \"NONE reason=no_operator_available\":\n"
            b"        return \"NO_OPERATOR_AVAILABLE\"\n"
            b"    if message == \"NONE reason=no_pool_available\":\n"
            b"        return \"NO_POOL_AVAILABLE\"\n"
            b"    code = message.partition(\":\")[0]\n"
            b"    return code if code in _REQUEST_REFUSAL_CODES else unknown\n"
            b"\n"
            b"\n",
            b"",
        ),
        (
            b"                refusal_diagnostic: dict[str, str] = {}\n",
            b"",
        ),
        (
            b"                    code = proof.get(\"refusal_code\")\n"
            b"                    refusal_diagnostic[\"request_refusal_code\"] = (\n"
            b"                        code if type(code) is str and code in _REQUEST_REFUSAL_CODES\n"
            b"                        else \"UNCLASSIFIED_PRELAUNCH_REFUSAL\")\n",
            b"",
        ),
        (
            b"                    \"same_run_replay_allowed\": False, **refusal_diagnostic}\n",
            b"                    \"same_run_replay_allowed\": False}\n",
        ),
        (
            b"                    \"refusal_code\": _safe_request_refusal_code(exc),\n",
            b"",
        ),
    )
    for newer, older in pairs:
        assert value.count(newer) == 1
        value = value.replace(newer, older, 1)
    assert hashlib.sha256(value).hexdigest() == PRE_REFUSAL_DIAGNOSTICS_TASK_SHA
    return value



def _pre_busy_task(value: bytes) -> bytes:
    """Undo only the hash-pinned prelease capacity additions in a copy.

    Retain the exact current native source for the frozen F1/Poll255 inverse.
    Never rewrite the candidate, runtime or historical fixture.
    """
    assert hashlib.sha256(value).hexdigest() == BUSY_TASK_SHA
    inverses = (
        (
            b'            proof = quota_circuit.validate_prelease_refusal(here, rid, root, parent,\n'
            b'                                                           packet_limit=MAX_RESULT_BYTES)\n'
            b'            busy = proof["kind"] == "prelease_broker_busy"\n',
            b'            quota_circuit.validate_prelease_refusal(here, rid, root, parent,\n'
            b'                                                   packet_limit=MAX_RESULT_BYTES)\n',
        ),
        (
            b'                "state": "TERMINAL_FAILURE", "rc": 75,\n'
            b'                "signal": "capacity" if busy else "quota",\n'
            b'                "reason": proof["kind"], "root_id": root, "parent_run_id": parent,\n',
            b'                "state": "TERMINAL_FAILURE", "rc": 75, "signal": "quota",\n'
            b'                "reason": "prelease_quota_cooldown", "root_id": root, "parent_run_id": parent,\n',
        ),
        (b'    capacity_excluded_pools: list[str] | None = None,\n', b''),
        (
            b'    if capacity_excluded_pools is not None:\n'
            b'        if (type(capacity_excluded_pools) is not list\n'
            b'                or not 1 <= len(capacity_excluded_pools) < 3\n'
            b'                or any(type(p) is not str or p not in pick._HOST_POOL_MODES\n'
            b'                       for p in capacity_excluded_pools)\n'
            b'                or len(set(capacity_excluded_pools)) != len(capacity_excluded_pools)\n'
            b'                or request_capacity_preflight is not True\n'
            b'                or pool is not None or requested_model is not None\n'
            b'                or prefer is not None or strict_manual_pin):\n'
            b'            raise FabricTaskError("CAPACITY_EXCLUSION_NOT_QUALIFIED")\n',
            b'',
        ),
        (
            b'                **({"excluded_pools": capacity_excluded_pools} if capacity_excluded_pools else {}),\n',
            b'',
        ),
    )
    for newer, older in inverses:
        assert value.count(newer) == 1
        value = value.replace(newer, older, 1)
    assert hashlib.sha256(value).hexdigest() == CURRENT_TASK_SHA
    return value


def _inverse_busy_picker(value: bytes) -> bytes:
    """Undo only the hash-pinned pool-exclusion selector additions in a copy."""
    assert hashlib.sha256(value).hexdigest() == BUSY_PICK_SHA
    inverses = (
        (
            b'                excluded_hosts: Optional[List[str]] = None,\n'
            b'                excluded_pools: Optional[List[str]] = None) -> str:\n'
            b'    """Select a new request, preserving Grok model affinity on quota exhaustion."""\n',
            b'                excluded_hosts: Optional[List[str]] = None) -> str:\n'
            b'    """Select a new request, preserving Grok model affinity on quota exhaustion."""\n',
        ),
        (
            b'    if excluded_pools is not None:\n'
            b'        common["excluded_pools"] = excluded_pools\n',
            b'',
        ),
        (
            b'                excluded_hosts: Optional[List[str]] = None,\n'
            b'                excluded_pools: Optional[List[str]] = None) -> str:\n'
            b'    """Read-only selection; host name or auto also requires placement eligibility."""\n'
            b'    if excluded_pools is not None:\n'
            b'        if (not host or pool is not None or requested_model is not None\n'
            b'                or type(excluded_pools) is not list\n'
            b'                or not 1 <= len(excluded_pools) < 3\n'
            b'                or any(type(item) is not str or item not in _HOST_POOL_MODES\n'
            b'                       for item in excluded_pools)\n'
            b'                or len(set(excluded_pools)) != len(excluded_pools)):\n'
            b'            return "NONE reason=invalid excluded_pools or manual pin"\n',
            b'                excluded_hosts: Optional[List[str]] = None) -> str:\n'
            b'    """Read-only selection; host name or auto also requires placement eligibility."""\n',
        ),
        (
            b'            # Only candidates excluded by an already-proven pre-task broker\n'
            b'            # refusal are removed. Normal economics/quality/independence and\n'
            b'            # host admission continue in the incumbent single picker.\n'
            b'            for excluded_pool in excluded_pools or ():\n'
            b'                routes.pop(excluded_pool, None)\n',
            b'',
        ),
    )
    for newer, older in inverses:
        assert value.count(newer) == 1, newer[:70]
        value = value.replace(newer, older, 1)
    assert hashlib.sha256(value).hexdigest() == COMPOSED_PICK
    return value

def _pre_ubuntu4_task(value: bytes) -> bytes:
    """Undo only the three Ubuntu4 hunks before the frozen F1 inverse."""
    pairs = (
        (b'{"ubuntu0", "ubuntu1", "ubuntu2", "ubuntu3", "ubuntu4"}',
         b'{"ubuntu0", "ubuntu1", "ubuntu2", "ubuntu3"}'),
        (b'host=(?P<host>ubuntu[0-4])', b'host=(?P<host>ubuntu[0-3])'),
        (b'(Grok on Mac or Ubuntu4, MiniMax on M1 or Ubuntu4)',
         b'(Grok on Mac, MiniMax on M1 or Ubuntu4)'),
    )
    for newer, older in pairs:
        assert value.count(newer) == 1
        value = value.replace(newer, older, 1)
    assert hashlib.sha256(value).hexdigest() == "778f4f3ebf03f5ce93e60081dc8a739ae90fb4cbeb32d01bbcc7b008c813a23b"
    return value


def _inverse_manual_member(value: bytes, member: str) -> bytes:
    """Undo only SHA-bound reviewed F1 hunks in disposable source bytes."""
    blob = PATCH.read_bytes()
    heading = ("diff --git a/" + member + " b/" + member + "\n").encode()
    assert blob.count(heading) == 1
    section = blob.split(heading, 1)[1].split(b"\ndiff --git ", 1)[0]
    groups = []
    group = None
    for line in section.splitlines(keepends=True):
        if line.startswith(b"@@ "):
            group = []
            groups.append(group)
        elif group is not None and line[:1] in (b" ", b"+", b"-"):
            group.append(line)
    assert groups
    for group in reversed(groups):
        newer = b"".join(x[1:] for x in group if x[:1] in (b" ", b"+"))
        older = b"".join(x[1:] for x in group if x[:1] in (b" ", b"-"))
        assert value.count(newer) == 1
        value = value.replace(newer, older, 1)
    return value


def _inverse_judgment(value: bytes) -> bytes:
    """Preserve R28 review routing in release while testing its pre-F1 base."""
    pairs = (
        (b'"operator", "reviewer", "review", "adjudicate", "decompose", "audit", "repair",',
         b'"operator", "reviewer", "adjudicate", "decompose", "audit", "repair",'),
        (b'    # Independent review/audit remain judgment even when legacy execute_classes includes them.\n'
         b'    # Preserve explicit-pool gates above; do not score implicit reviewers into Qwen.\n'
         b'    if tc not in {"review", "audit"} and (is_execute_class(tc, doc) or tc in LABOR_CLASSES_R30):\n',
         b'    if is_execute_class(tc, doc) or tc in LABOR_CLASSES_R30:\n'),
    )
    for newer, older in pairs:
        assert value.count(newer) == 1
        value = value.replace(newer, older, 1)
    assert hashlib.sha256(value).hexdigest() == AFTER["ext/pick.py"]
    return value


COMPOSED_JUDGMENT_PICK = "4008caca8c6a0e2145e7cb90965740ce24445e3300a8e3693d7a96130df236df"


def _restore_historical_picker(current: bytes) -> bytes:
    """Reconstruct only the exact reviewed #1797 hunks in the disposable F1 stage."""
    replacements = (
        (b'"operator", "reviewer", "review", "adjudicate", "decompose", "audit", "repair",',
         b'"operator", "reviewer", "adjudicate", "decompose", "audit", "repair",'),
        (b'    # Independent review/audit remain judgment even when legacy execute_classes includes them.\n'
         b'    # Preserve explicit-pool gates above; do not score implicit reviewers into Qwen.\n'
         b'    if tc not in {"review", "audit"} and (is_execute_class(tc, doc) or tc in LABOR_CLASSES_R30):\n',
         b'    if is_execute_class(tc, doc) or tc in LABOR_CLASSES_R30:\n'),
    )
    assert hashlib.sha256(current).hexdigest() == COMPOSED_JUDGMENT_PICK
    for newer, older in replacements:
        assert current.count(newer) == 1
        current = current.replace(newer, older, 1)
    assert hashlib.sha256(current).hexdigest() == SOURCE["ext/pick.py"][1]
    return current


def sha(path: Path) -> str:
    assert path.is_file() and not path.is_symlink()
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_real_native_auto_pre_effect_source_contract(tmp_path):
    """Reproduce the full native release source's F1 fix without a live install."""
    assert sha(PATCH) == "6b1dade16fe58b732064d66e0645396dd6dd02fc255c3befbf0d03e105b23e6b"
    assert sha(FIXTURE) == "75edb2345e90f2f5a758020acef494aa9090b4c97e020bbafb6f3ee5be63c794"
    builder = NATIVE / "rollout/build_review_stage.py"
    built = tmp_path / "built"
    proc = subprocess.run([sys.executable, str(builder), "--output", str(built),
                           "--broker-busy-epoch"],
                          cwd=ROOT, capture_output=True, text=True, timeout=55)
    assert proc.returncode == 0, proc.stderr[-2500:]
    stage = built / "native-code-stage"
    for relative, (name, original_sha) in SOURCE.items():
        source = (BUSY_SOURCE if name in ("pick.py", "fabric_task.py")
                  else NATIVE / "candidate") / name
        # Current source includes later routing and namespace-bound readers.
        # Reconstruct the exact historical F1 epoch only in this private stage.
        current = source.read_bytes()
        assert (stage / relative).read_bytes() == current
        if relative == "ext/pick.py":
            # The converged candidate picker is the busy-fallback composition;
            # its pre-busy predecessor is the exact composed pick above.
            assert sha(source) == BUSY_PICK_SHA
            pre_busy = _inverse_busy_picker(current)
            assert hashlib.sha256(pre_busy).hexdigest() == COMPOSED_PICK
            current = _inverse_judgment(_preobserver_picker())
        elif relative == "ext/fabric_task.py":
            # Undo only the exact busy fallback additions in disposable bytes
            # before the older epoch inverses; the staged copy keeps the
            # historical hashes frozen.
            assert sha(source) == BUSY_TASK_SHA
            current = _pre_busy_task(current)
            assert hashlib.sha256(current).hexdigest() == CURRENT_TASK_SHA
            (stage / relative).write_bytes(current)
            # Undo only the exact forward repair in this private stage, then
            # retain every historical inverse and fixture at its original hash.
            admission_patch = ROOT / "tests/fixtures/fabric-native-admission-integrity-20261107.patch"
            assert sha(admission_patch) == "68c1abf049ee9e4c04fc749eebb9a4b99ba71a71c22945e0f5d02bc8fe107753"
            reversed_repair = subprocess.run(
                ["git", "apply", "--reverse", "--unidiff-zero", "--include=fabric_task.py", str(admission_patch)],
                cwd=stage / "ext", capture_output=True, text=True, timeout=18,
            )
            assert reversed_repair.returncode == 0, reversed_repair.stderr[-1800:]
            predecessor = (stage / relative).read_bytes()
            assert hashlib.sha256(predecessor).hexdigest() == PRE_ADMISSION_TASK_SHA
            latest = _pre_refusal_diagnostics_task(predecessor)
            # Undo only the remote cwd default before the exact older epochs.
            remote_cwd = (
                b'    # Resolve an implicit working directory on the receiving host.\n'
                b'    # The receiving host still validates explicit --cwd values.\n'
                b'    p_request.add_argument("--cwd", default="~")\n'
            )
            caller_cwd = b'    p_request.add_argument("--cwd", default=os.getcwd())\n'
            assert latest.count(remote_cwd) == 1
            latest = latest.replace(remote_cwd, caller_cwd, 1)
            assert hashlib.sha256(latest).hexdigest() == PRE_REMOTE_CWD_TASK_SHA
            start = b'# These reviewed wrapper bytes classify normal SSH255 as controller uncertainty\n'
            end = b'def inspect_run(run_id: str, *, owner_ext: Path | None = None) -> dict[str, Any]:\n'
            hook = (b'    if state == "EFFECT_UNKNOWN" and _qualify_completed_poll255(rid, original_log, **owner):\n'
                    b'        state, rc, signal = "TERMINAL", 0, "ok"\n\n')
            assert latest.count(start) == latest.count(end) == latest.count(hook) == 1
            first, last = latest.index(start), latest.index(end)
            assert first < last
            pre_poll = (latest[:first] + latest[last:]).replace(hook, b'', 1)
            assert hashlib.sha256(pre_poll).hexdigest() == PRE_POLL255_WITH_UBUNTU4_TASK_SHA
            # Preserve the independent Ubuntu4 boundary before the frozen history.
            pre_poll = _pre_ubuntu4_task(pre_poll)
            assert hashlib.sha256(pre_poll).hexdigest() == PRE_POLL255_TASK_SHA
            # Only the two finite budget constants differ at this boundary.
            assert pre_poll.count(b'request_remaining_seconds <= 14400') == 1
            assert pre_poll.count(b'time.monotonic_ns() + 14400 * 1_000_000_000') == 1
            precursor = pre_poll.replace(
                b'request_remaining_seconds <= 14400',
                b'request_remaining_seconds <= 7200', 1,
            ).replace(
                b'time.monotonic_ns() + 14400 * 1_000_000_000',
                b'time.monotonic_ns() + 7200 * 1_000_000_000', 1,
            )
            assert precursor != pre_poll
            assert hashlib.sha256(precursor).hexdigest() == PRE_LONG_HORIZON_TASK_SHA
            assert sha(HISTORICAL_TASK) == AFTER[relative]
            current = HISTORICAL_TASK.read_bytes()
        else:
            assert sha(source) == AFTER[relative]
        historical = _inverse_manual_member(current, relative)
        assert hashlib.sha256(historical).hexdigest() == original_sha
        (stage / relative).write_bytes(historical)
    for action in ("--check", None):
        args = ["git", "apply"] + ([action] if action else []) + [str(PATCH)]
        proc = subprocess.run(args, cwd=stage, capture_output=True, text=True, timeout=18)
        assert proc.returncode == 0, proc.stderr[-1800:]
    assert all(sha(stage / name) == digest for name, digest in AFTER.items())
    env = {k: v for k, v in os.environ.items() if not (
        k.startswith(("OPENAI_", "CODEX_", "ANTHROPIC_", "GITHUB_"))
        or k in ("PYTHONPATH", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY")
    )}
    env.update(MMX_NATIVE_PREVIEW_CANDIDATE=str(stage), PYTHONDONTWRITEBYTECODE="1",
               PYTHONPATH=os.pathsep.join((str(stage / "ext"), str(NATIVE / "source"))))
    proc = subprocess.run([sys.executable, str(FIXTURE), "-q"], cwd=stage,
                          env=env, capture_output=True, text=True, timeout=35)
    assert proc.returncode == 0, (proc.stdout + proc.stderr)[-3800:]
    assert re.search(r"Ran 14 tests", proc.stderr) and "\nOK\n" in proc.stderr
    # The historical F1 regression is preserved; independently verify R28
    # judgment routing stays present in the CURRENT composed native source.
    assert all(sha(stage / name) == digest for name, digest in AFTER.items())
    assert sha(BUSY_SOURCE / "pick.py") == BUSY_PICK_SHA
    assert sha(BUSY_SOURCE / "fabric_task.py") == BUSY_TASK_SHA
    assert b'if tc not in {"review", "audit"}' in (
        BUSY_SOURCE / "pick.py").read_bytes()
    # Neither stage nor source is published/selected by this test.
