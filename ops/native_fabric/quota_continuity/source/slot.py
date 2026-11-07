#!/usr/bin/env python3
"""Pool semaphore for external CLI sub-agents (seat 7cd4fae1).
Usage: slot.py <pool> [--wait SECS] -- <command...>
Pool admission: qwen/minimax/GLM retain their account budgets. Grok and
Cursor have no artificial provider slot count: the cluster broker derives an
envelope from qualified hosts, and remotely leased local flocks use host limits.
glm and glm-frontier retain their separate model tags, but BOTH use
one host-local GLM semaphore and the same broker account leases.

Acquire order (W4-K2 R24): local flock (host safety net) FIRST, then the
cluster lease broker (the only grantor). LANE_LEASED=1 means a Studio-side
budget of N leases already covers this remote lane — do not acquire again
(that would double-count). Heartbeat starts immediately after the lease is
granted. When the broker heartbeat returns EXPIRED/not-held, the holder
sets LEASE_LOST, signals SIGTERM (SIGKILL after 30 s), and exits 76. Never
prints key values. Never kills a running agent — release is on process exit.

KITREL-E (2026-09-15): per-pool admission documents so arming one MiniMax
pool can never disarm another. See ``_minimax_safe_pool_slug``,
``_minimax_resolve_pool_path`` and ``_minimax_binding_row_absent``.
"""
import os
import fcntl, math, os, signal, socket, subprocess, sys, threading, time
from dataclasses import dataclass
import hashlib
import json
import re
import stat as stat_module
import types

from lane_runtime import (
    LaneRuntimeConfigError,
    cleanup_receipt_is_proven,
    parse_bounded_seconds,
    settle_owned_process_session,
)

CAPS = {"qwen": 8, "minimax": 7, "grok": None, "cursor": None, "glm": 0, "glm-frontier": 0, "go": 9, "ocfree": 3}
HERE = os.path.dirname(os.path.abspath(__file__))
BROKER = os.path.join(HERE, "lease_broker.py")
HOSTS_JSON_PATH = os.path.join(HERE, "hosts.json")
MINIMAX_SENTINEL = os.path.join(HERE, "state", "MINIMAX_DISARMED")
# Fabric remote releases are content-addressed; owner-issued activation artifacts
# remain in the host's existing non-release state home. Keep the per-release
# sentinel AND this host-wide sentinel active so no disarm is overlooked.
MINIMAX_OWNER_STATE_DIR = (
    os.path.join(os.path.expanduser("~"), "lanes", "ext", "state")
    if os.environ.get("LANE_LEASED") == "1"
    else os.path.join(HERE, "state")
)
MINIMAX_HOST_SENTINEL = os.path.join(
    MINIMAX_OWNER_STATE_DIR, "MINIMAX_DISARMED"
)
MINIMAX_REALM_ID = "minimax-token-plan"
# KITREL-E defect 1: pool `minimax-codex` is remapped from the false-claim
# `openai-compatible` row to the NEW row designed in DRAFT Mastermind PR #665
# (`minimax-token-plan.codex-responses`, harness codex-cli, adapter codex-cli,
# implementation_state BUILT_NOT_PROVEN). Pool `minimax` and its binding id
# are UNTOUCHED. The pinned checkout at MINIMAX_COMMIT does not yet contain
# the new row, so the gate still refuses `minimax-codex` — for a NEW,
# DISTINCT reason (`binding_row_absent`) added by this lane.
MINIMAX_BINDING_IDS = {
    "minimax": "minimax-token-plan.claude-code-anthropic",
    "minimax-codex": "minimax-token-plan.codex-responses",
}
# R2 (seat ruling orch/fabric/MINIMAX_KIT_ADMISSION_RULING_2026-09-15.md): admission requires the
# canonical row's HARNESS identity to match the pool, and its implementation_state to have left
# SPEC_ONLY. `autonomous_allowed` is deliberately NOT consulted: it is false for every
# subscription profile by canonical design — control_plane/claude_subscription_worker.py:321-322
# refuses to compose any binding whose autonomous_allowed is true.
MINIMAX_REQUIRED_HARNESS = {
    "minimax": ("claude-code-anthropic", "claude-code"),
    # KITREL-E: pool `minimax-codex` requires the codex-cli harness, matching the
    # `minimax-token-plan.codex-responses` row's harness_id. The token suffix
    # ("codex-responses") must equal the second dotted segment of the binding id.
    "minimax-codex": ("codex-responses", "codex-cli"),
}
MINIMAX_ADMITTING_STATES = ("BUILT_NOT_PROVEN", "PROVEN_LIVE")
MINIMAX_CHECKOUT_ROOT = os.environ.get("MINIMAX_CHECKOUT_ROOT") or (
    "/Volumes/Mastermind/agent-workspaces/claude/44ff44e73b840f81/"
    "hf1-pair-census-744bb191d9784afc"
)   # R34 (2026-09-18): remote lanes hosts have no Studio SSD; HOST_ENV.sh points this at a
    # protected-master Mastermind checkout (config/ + control_plane/ sparse) so the canonical
    # bindings stay readable. NOTE the default worktree's copy is stale vs protected master.
MINIMAX_COMMIT = "4d1f45bf600afc2d264a74852c69887084aa52ff"
REVIEWED_REALM_PATH = os.path.join(
    MINIMAX_CHECKOUT_ROOT, "control_plane", "codex_provider_realm.py"
)
MINIMAX_BINDING_PATH = os.path.join(
    MINIMAX_CHECKOUT_ROOT, "config", "subscription_harness_bindings.v1.json"
)
MINIMAX_RECEIPT_OWNER_PATH = os.path.join(
    MINIMAX_CHECKOUT_ROOT, "control_plane", "codex_provider_realm.py"
)
MINIMAX_ACTIVATION_GATES = (
    "adapter_implemented",
    "provider_realm_enrolled",
    "capacity_known",
    "real_canary_passed",
    "usage_policy_satisfied",
)

# Owner-issued admission inputs (Chairman key rotation 2026-09-14). Both files are
# written by the credential OWNER, never by a lane, and both are bound to the CURRENT
# key fingerprint so a receipt for a superseded key can never admit.
#
# KITREL-E defect 2: each MiniMax pool now has its OWN activation fact and
# generation receipt file (see ``_minimax_resolve_pool_path``). The legacy single
# file ``minimax_activation_fact.json`` / ``minimax_generation_receipt.json``
# is accepted only when its ``binding_id`` matches the requested pool's binding
# id. Pool `minimax` today reads the legacy file (its binding_id matches); pool
# `minimax-codex` reads ONLY its per-pool file (``…minimax-codex.json``) — so
# arming one pool can never disarm another.
MINIMAX_KEY_CONFIG_PATH = os.path.expanduser("~/.minimax/config.json")
MINIMAX_KEY_CONFIG_MODE = 0o600
MINIMAX_RECEIPT_PATH = os.path.join(MINIMAX_OWNER_STATE_DIR, "minimax_generation_receipt.json")
MINIMAX_ACTIVATION_FACT_PATH = os.path.join(
    MINIMAX_OWNER_STATE_DIR, "minimax_activation_fact.json"
)
MINIMAX_RECEIPT_SCHEMA = "ProviderRealmEnrollmentReceipt/v1"
MINIMAX_ISSUER_PREFIX = "chairman"

LEASE_LOST_RC = 76
CHILD_TIMEOUT_RC = 124
SIGKILL_GRACE_S = 30
# An outer owned-process parent gives slot a short SIGTERM window before its
# own fail-closed escalation. Slot must settle the separately owned provider
# session inside that window so nested custody cannot orphan grandchildren.
PARENT_SIGNAL_SETTLE_GRACE_S = 0.2
LEASE_MONITOR_POLL_S = 0.25
# Defer malformed configuration to the typed pre-admission refusal in main.
# Import-time ValueError would abort before slot could return its stable rc=78.
try:
    LEASE_TTL_S = float(os.environ.get("LANE_LEASE_TTL_S", "180"))
except (TypeError, ValueError):
    LEASE_TTL_S = float("nan")
DEFAULT_CHILD_TIMEOUT_S = 7200.0
MAX_CHILD_TIMEOUT_S = 7200.0


def _child_runtime_limit():
    """Return the hard wall-clock fuse for one admitted provider child."""
    raw = os.environ.get("SLOT_CHILD_TIMEOUT_SECONDS")
    if raw is None or str(raw).strip() == "":
        raw = os.environ.get("POOL_CHILD_TIMEOUT_SECONDS")
    return parse_bounded_seconds(
        raw,
        default=DEFAULT_CHILD_TIMEOUT_S,
        minimum=1.0,
        maximum=MAX_CHILD_TIMEOUT_S,
        key="SLOT_CHILD_TIMEOUT_SECONDS",
    )


@dataclass(frozen=True)
class LeaseHeartbeat:
    state: str
    reason: str = ""
    ttl: float | None = None

    def __bool__(self):
        return self.state == "held"


def _glm_concurrency_caps():
    """glm_keys.config()['concurrency_caps'] when present (never prints values)."""
    try:
        if HERE not in sys.path:
            sys.path.insert(0, HERE)
        import glm_keys
        raw = glm_keys.config().get("concurrency_caps")
        return raw if isinstance(raw, dict) else {}
    except Exception:
        return {}


def _glm_yaml_caps():
    """pools.yaml pools.glm.per_model_caps (R24a hints)."""
    try:
        import yaml
        path = os.path.join(HERE, "..", "orch", "fabric", "pools.yaml")
        with open(path, encoding="utf-8") as fh:
            doc = yaml.safe_load(fh) or {}
        raw = ((doc.get("pools") or {}).get("glm") or {}).get("per_model_caps")
        caps = {}
        if isinstance(raw, dict):
            for k, v in raw.items():
                try:
                    caps[str(k)] = int(v)
                except (TypeError, ValueError):
                    pass
        return caps
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# KITREL-E — per-pool document helpers
# ---------------------------------------------------------------------------

_MINIMAX_POOL_SLUG_RE = re.compile(r"[^A-Za-z0-9._-]")


def _minimax_safe_pool_slug(pool):
    """Sanitize a pool name into a filename-safe slug. Returns None for any
    name that could resolve to a path outside ``ext/state/`` (path separators,
    NUL bytes, leading dot, traversal ``..``, or any character outside
    ``[A-Za-z0-9._-]``).

    Contract: a None return means "this pool has no document" — the caller must
    NOT fall through to the legacy file, because the legacy file's binding_id
    check would still apply and the pool name itself is untrusted.
    """
    if not isinstance(pool, str) or not pool:
        return None
    if pool.startswith("."):
        return None
    if ".." in pool:
        return None
    if _MINIMAX_POOL_SLUG_RE.search(pool):
        return None
    return pool


def _minimax_resolve_pool_path(pool, basename):
    """Resolve the per-pool / legacy single-file path for the given ``basename``
    in {``activation_fact``, ``generation_receipt``}. First-match-wins:

    1. PER-POOL: ``<state_dir>/minimax_<basename>.<pool>.json`` (when it exists).
    2. LEGACY:  ``<state_dir>/minimax_<basename>.json`` (the historical single
       file path; its binding_id must match the pool's binding_id to admit).

    Returns None if the pool name is unsafe (per ``_minimax_safe_pool_slug``).
    Never returns a path outside the directory the legacy constant points at.

    The legacy constants are read at call time (not captured at import) so
    monkeypatching ``MINIMAX_ACTIVATION_FACT_PATH`` / ``MINIMAX_RECEIPT_PATH``
    in tests still steers resolution into ``tmp_path``.
    """
    slug = _minimax_safe_pool_slug(pool)
    if slug is None:
        return None
    if basename == "activation_fact":
        legacy = MINIMAX_ACTIVATION_FACT_PATH
    elif basename == "generation_receipt":
        legacy = MINIMAX_RECEIPT_PATH
    else:
        return None
    state_dir = os.path.dirname(legacy)
    per_pool = os.path.join(state_dir, "minimax_%s.%s.json" % (basename, slug))
    return per_pool if os.path.exists(per_pool) else legacy


def _minimax_file(path):
    try:
        if not os.path.isfile(path):
            raise OSError("canonical source is missing")
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except (OSError, UnicodeError):
        return None


def _minimax_canonical_source(path):
    """Read canonical text from one fixed commit, or retain legacy file mode.

    An explicitly configured object root never falls back. No checkout change,
    credential read, source execution, replacement ref, or network fetch occurs.
    """
    if "MINIMAX_GIT_OBJECT_ROOT" not in os.environ:
        return _minimax_file(path)
    root = os.environ["MINIMAX_GIT_OBJECT_ROOT"]
    allowed = {
        REVIEWED_REALM_PATH: "control_plane/codex_provider_realm.py",
        MINIMAX_BINDING_PATH: "config/subscription_harness_bindings.v1.json",
    }
    relative = allowed.get(path)
    if not root or not os.path.isabs(root) or relative is None:
        return None
    if not re.fullmatch(r"[0-9a-f]{40}", MINIMAX_COMMIT):
        return None
    # A minimal environment drops inherited Git directory/config/object overrides.
    env = {
        "PATH": os.environ.get("PATH", os.defpath),
        "GIT_CONFIG_SYSTEM": os.devnull,
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_NO_REPLACE_OBJECTS": "1",
        "GIT_NO_LAZY_FETCH": "1",
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_OPTIONAL_LOCKS": "0",
    }
    command = ["git", "--no-replace-objects", "-C", root]
    def run(*args):
        return subprocess.run(command + list(args), env=env,
                              stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                              timeout=5, check=False)
    try:
        if not os.path.isdir(root):
            return None
        # Reject partial/promisor repositories as well as disabling lazy fetch:
        # older Git versions may not recognize GIT_NO_LAZY_FETCH.
        config = run("config", "--includes", "--get-regexp",
                     r"^(extensions\.partialclone|remote\..*\.(promisor|partialclonefilter))$")
        if config.returncode not in (0, 1) or config.stdout:
            return None
        kind = run("cat-file", "-t", MINIMAX_COMMIT)
        if kind.returncode != 0 or kind.stdout.strip() != b"commit":
            return None
        blob = run("cat-file", "blob", MINIMAX_COMMIT + ":" + relative)
        if blob.returncode != 0 or len(blob.stdout) > 4 * 1024 * 1024:
            return None
        return blob.stdout.decode("utf-8")
    except (OSError, UnicodeError, subprocess.SubprocessError):
        return None


def _reviewed_minimax_realm():
    """Read only the protected reviewed-dict text; never execute its code."""
    source = _minimax_canonical_source(REVIEWED_REALM_PATH)
    if source is None:
        return False
    try:
        match = re.search(
            r"(?ms)^REVIEWED_CODEX_PROVIDER_REALMS\s*=\s*\{(.*?)^\}", source,
        )
        if not match:
            return False
        reviewed = match.group(1)
        if re.search(r'["\']%s["\']' % re.escape(MINIMAX_REALM_ID), reviewed):
            return True
        assignment = re.search(
            r"(?ms)^\w+\s*=\s*CodexProviderRealm\(.*?realm_id=[\"']%s[\"']"
            % re.escape(MINIMAX_REALM_ID),
            source,
        )
        return assignment is not None
    except ValueError:
        return False


def _canonical_minimax_binding(pool):
    source = _minimax_canonical_source(MINIMAX_BINDING_PATH)
    if source is None:
        return None
    try:
        document = json.loads(source)
    except ValueError:
        return None
    bindings = document.get("bindings") if isinstance(document, dict) else None
    if not isinstance(bindings, dict):
        return None
    matches = []
    for binding_id, row in bindings.items():
        if not isinstance(row, dict):
            continue
        if binding_id in MINIMAX_BINDING_IDS.values():
            gates = row.get("activation_gates")
            if not isinstance(gates, list) or tuple(gates) != MINIMAX_ACTIVATION_GATES:
                return None
            matches.append((binding_id, row))
    wanted = MINIMAX_BINDING_IDS.get(pool)
    return next((match for match in matches if match[0] == wanted), None)


def _minimax_binding_row_absent(pool):
    """KITREL-E: distinct from ``canonical_source_unreadable``. True iff the
    canonical bindings file PARSED successfully and ``bindings`` is a dict, but
    the pool's binding id is NOT a key in it.

    The pre-existing ``_canonical_minimax_binding`` returns None for THREE
    distinct cases (file unreadable, file unparseable, row absent). The gate
    chains historically rolled those into one refusal reason; this lane
    splits out the third case so a missing row is observable as
    ``binding_row_absent`` — and the other two remain ``canonical_source_unreadable``.
    """
    binding_id = MINIMAX_BINDING_IDS.get(pool)
    if binding_id is None:
        return False
    source = _minimax_canonical_source(MINIMAX_BINDING_PATH)
    if source is None:
        return False
    try:
        document = json.loads(source)
    except ValueError:
        return False
    bindings = document.get("bindings") if isinstance(document, dict) else None
    if not isinstance(bindings, dict):
        return False
    return binding_id not in bindings


def _minimax_commit_matches():
    try:
        git_dir = os.path.join(MINIMAX_CHECKOUT_ROOT, ".git")
        if not os.path.exists(git_dir):
            return False
        proc = subprocess.run(
            ["git", "-C", MINIMAX_CHECKOUT_ROOT, "rev-parse", "HEAD"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=5,
            check=False,
        )
        return proc.returncode == 0 and proc.stdout.strip() == MINIMAX_COMMIT
    except (OSError, subprocess.SubprocessError):
        return False


def _minimax_json(path):
    """Parse an owner-written JSON admission input; None on any damage."""
    source = _minimax_file(path)
    if source is None:
        return None
    try:
        document = json.loads(source)
    except ValueError:
        return None
    return document if isinstance(document, dict) else None


def _minimax_harness_matches(pool, binding_id, row):
    """The canonical row must BE this pool's harness, by id suffix and by its own
    harness_id field — a row that merely claims the binding id is not enough."""
    required = MINIMAX_REQUIRED_HARNESS.get(pool)
    if required is None:
        return False
    harness_token, harness_id = required
    if not isinstance(binding_id, str) or "." not in binding_id:
        return False
    if binding_id.split(".", 1)[1] != harness_token:
        return False
    return row.get("harness_id") == harness_id


def _minimax_key_fingerprint():
    """sha256(current api_key)[:12] — the ONLY key-derived value this module
    produces. Never returns, logs or raises the key itself. None when the
    credential file is missing, not a regular file, not mode 0600, unparsable,
    or carries no api_key string."""
    path = MINIMAX_KEY_CONFIG_PATH
    try:
        info = os.stat(path)
    except OSError:
        return None
    if not stat_module.S_ISREG(info.st_mode):
        return None
    if stat_module.S_IMODE(info.st_mode) != MINIMAX_KEY_CONFIG_MODE:
        return None
    try:
        with open(path, encoding="utf-8") as handle:
            document = json.load(handle)
    except (OSError, UnicodeError, ValueError):
        return None
    if not isinstance(document, dict):
        return None
    key = document.get("api_key")
    if not isinstance(key, str) or not key:
        return None
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:12]


def _minimax_canary_receipt_passes(path):
    """True only for a canary receipt that PASSED and names the CURRENT key
    fingerprint. A receipt for a superseded key can never satisfy the gate."""
    if not isinstance(path, str) or not path:
        return False
    if not os.path.isabs(path):
        path = os.path.join(os.path.dirname(MINIMAX_ACTIVATION_FACT_PATH), path)
    document = _minimax_json(path)
    if document is None:
        return False
    if document.get("passed") is not True:
        return False
    fingerprint = _minimax_key_fingerprint()
    if fingerprint is None:
        return False
    return document.get("key_fingerprint_sha256_12") == fingerprint


def _minimax_activation_fact(pool):
    """Owner-written activation fact for this binding. Never fabricated: the
    file is authored by the credential owner, matched to the pool binding, and
    its real_canary_passed claim is re-derived from the referenced canary
    receipt against the CURRENT key fingerprint (a stale or failed canary
    forces the gate to stay unmet).

    KITREL-E defect 2: the document is resolved per-pool from
    ``_minimax_resolve_pool_path`` (per-pool file takes precedence; legacy
    single file is accepted only when its binding_id matches this pool's).
    """
    binding_id = MINIMAX_BINDING_IDS.get(pool)
    if binding_id is None:
        return None
    fact_path = _minimax_resolve_pool_path(pool, "activation_fact")
    if fact_path is None:
        return None
    document = _minimax_json(fact_path)
    if document is None:
        return None
    issuer = document.get("issuer")
    if not isinstance(issuer, str) or not issuer.startswith(MINIMAX_ISSUER_PREFIX):
        return None
    if document.get("binding_id") != binding_id:
        return None

    def _generation(name):
        value = document.get(name)
        return value if type(value) is int else 0

    canary_path = document.get("canary_receipt_path")
    real_canary_passed = (
        document.get("real_canary_passed") is True
        and _minimax_canary_receipt_passes(canary_path)
    )
    return types.SimpleNamespace(
        binding_id=binding_id,
        issuer=issuer,
        issued_at=document.get("issued_at"),
        adapter_id=document.get("adapter_id"),
        realm_generation=_generation("realm_generation"),
        capacity_state=document.get("capacity_state"),
        capacity_source=document.get("capacity_source"),
        capacity_generation=_generation("capacity_generation"),
        capacity_observed_at=document.get("capacity_observed_at"),
        real_canary_passed=real_canary_passed,
        canary_receipt_path=canary_path,
        usage_policy_satisfied=document.get("usage_policy_satisfied") is True,
        usage_policy_authority=document.get("usage_policy_authority"),
    )


def _minimax_generation_receipt(pool):
    """Owner-issued credential/enrollment generation receipt. Never fabricated:
    it must parse as ProviderRealmEnrollmentReceipt/v1, be issued by the
    credential owner, match this pool's canonical binding row, and name the
    CURRENT key fingerprint — so a receipt left behind by a rotated-out key
    admits nothing.

    KITREL-E defect 2: the document is resolved per-pool from
    ``_minimax_resolve_pool_path`` (per-pool file takes precedence; legacy
    single file is accepted only when its binding_id matches this pool's).
    """
    binding_id = MINIMAX_BINDING_IDS.get(pool)
    if binding_id is None:
        return None
    binding = _canonical_minimax_binding(pool)
    if binding is None:
        return None
    row = binding[1]
    receipt_path = _minimax_resolve_pool_path(pool, "generation_receipt")
    if receipt_path is None:
        return None
    document = _minimax_json(receipt_path)
    if document is None:
        return None
    if document.get("schema") != MINIMAX_RECEIPT_SCHEMA:
        return None
    issuer = document.get("issuer")
    if not isinstance(issuer, str) or not issuer.startswith(MINIMAX_ISSUER_PREFIX):
        return None
    if document.get("binding_id") != binding_id:
        return None
    if document.get("profile_id") != row.get("profile_id"):
        return None
    generation = document.get("generation")
    if type(generation) is not int or generation < 1:
        return None
    if document.get("enrollment_state") != "enrolled":
        return None
    for field in ("issued_at", "rotated_at", "rotation_source"):
        value = document.get(field)
        if not isinstance(value, str) or not value:
            return None
    fingerprint = _minimax_key_fingerprint()
    if fingerprint is None:
        return None
    if document.get("key_fingerprint_sha256_12") != fingerprint:
        return None
    return types.SimpleNamespace(
        binding_id=binding_id,
        profile_id=row.get("profile_id"),
        generation=generation,
        enrollment_state="enrolled",
        key_fingerprint_sha256_12=fingerprint,
        issuer=issuer,
        issued_at=document["issued_at"],
        rotated_at=document["rotated_at"],
        rotation_source=document["rotation_source"],
    )


def _is_minimax_pool(pool):
    return pool == "minimax" or pool.startswith("minimax-")


def _pool_refusal_reason(pool):
    if not _is_minimax_pool(pool):
        return None
    if pool not in MINIMAX_BINDING_IDS:
        return "canonical_source_unreadable"
    if "MINIMAX_GIT_OBJECT_ROOT" not in os.environ and not _minimax_commit_matches():
        return "canonical_source_unreadable"
    source_ok = (
        _minimax_canonical_source(REVIEWED_REALM_PATH) is not None
        and _minimax_canonical_source(MINIMAX_BINDING_PATH) is not None
        and _minimax_canonical_source(MINIMAX_RECEIPT_OWNER_PATH) is not None
    )
    if not source_ok:
        return "canonical_source_unreadable"
    if not _reviewed_minimax_realm():
        return "realm_unreviewed"
    binding = _canonical_minimax_binding(pool)
    if binding is None:
        # KITREL-E: split this case — when the file PARSED but lacked the
        # pool's row, return the distinct reason `binding_row_absent`. The
        # other sub-cases (file unreadable, file unparseable, row's gates
        # malformed) keep the historical `canonical_source_unreadable`.
        if _minimax_binding_row_absent(pool):
            return "binding_row_absent"
        return "canonical_source_unreadable"
    binding_id, row = binding
    if binding_id != MINIMAX_BINDING_IDS[pool]:
        return "canonical_source_unreadable"
    if not _minimax_harness_matches(pool, binding_id, row):
        return "harness_mismatch"
    state = row.get("implementation_state")
    if state == "SPEC_ONLY":
        # Pool minimax-codex reaches the historical `binding_spec_only` only
        # if its pool binding id does in fact map to a SPEC_ONLY row at the
        # pinned commit. After the KITREL-E remap, the codex-responses row is
        # absent at the pinned commit, so the gate never reaches this branch
        # for `minimax-codex` today — it refuses earlier with `binding_row_absent`.
        return "binding_spec_only"
    if state not in MINIMAX_ADMITTING_STATES:
        return "binding_state_unrecognized"
    admission = _minimax_activation_fact(pool)
    if admission is None:
        return "activation_gate_unmet:adapter_implemented"
    gate_values = {
        "adapter_implemented": (
            getattr(admission, "adapter_id", None) == row.get("adapter_id")
        ),
        "provider_realm_enrolled": getattr(admission, "realm_generation", 0) >= 1,
        "capacity_known": (
            getattr(admission, "capacity_state", None) == "AVAILABLE"
            and getattr(admission, "capacity_source", None) == "CAPACITY"
            and getattr(admission, "capacity_generation", 0) >= 1
        ),
        "real_canary_passed": getattr(admission, "real_canary_passed", False) is True,
        "usage_policy_satisfied": (
            getattr(admission, "usage_policy_satisfied", False) is True
        ),
    }
    for gate in MINIMAX_ACTIVATION_GATES:
        if gate_values.get(gate) is not True:
            return "activation_gate_unmet:%s" % gate
    receipt = _minimax_generation_receipt(pool)
    if (
        receipt is None
        or getattr(receipt, "binding_id", None) != binding_id
        or getattr(receipt, "profile_id", None) != row.get("profile_id")
        or type(getattr(receipt, "generation", None)) is not int
        or receipt.generation < 1
        or getattr(receipt, "enrollment_state", None) != "enrolled"
    ):
        return "credential_generation_missing"
    if os.path.exists(MINIMAX_SENTINEL) or os.path.exists(MINIMAX_HOST_SENTINEL):
        return "sentinel"
    return None


def _pool_ledger_refusal(pool, refusal):
    try:
        subprocess.run(
            [
                sys.executable,
                os.path.join(HERE, "pool_ledger.py"),
                "append",
                "--pool",
                pool,
                "--task-class",
                pool,
                "--rc",
                "78",
                "--signal",
                refusal,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        pass


def _pool_cap(pool):
    if pool in ("grok", "cursor"):
        # No provider semaphore quota. Remote lanes already hold the Studio
        # broker lease and a physical LaneLease; local flock uses host capacity.
        if os.environ.get("LANE_LEASED") == "1":
            if not os.environ.get("LANE_MAX_ACTIVE"):
                return 0
            try:
                from lane_runtime import load_runtime_config
                return load_runtime_config(
                    os.environ, cpu_count=os.cpu_count() or 1
                ).max_active
            except (LaneRuntimeConfigError, ValueError, TypeError):
                return 0
        try:
            if HERE not in sys.path:
                sys.path.insert(0, HERE)
            from lease_broker import default_broker
            return max(0, int(default_broker().pool_cap(pool)))
        except Exception:
            return 0

    if pool == "qwen":
        try:
            if HERE not in sys.path:
                sys.path.insert(0, HERE)
            import bailian_keys
            return int(bailian_keys.total_cap())
        except Exception:
            return CAPS[pool]
    if pool in ("glm", "glm-frontier"):
        # Model identity is retained for the broker; local slots are NOT
        # separate quotas. Derive room from the incumbent shared GLM accounts.
        try:
            if HERE not in sys.path:
                sys.path.insert(0, HERE)
            from lease_broker import default_broker
            return max(0, int(default_broker().pool_cap("glm")))
        except Exception:
            # Remotely leased workers may lack the controller's accounts.yaml.
            # Keep their host safety net without minting another broker lease.
            if os.environ.get("LANE_LEASED") == "1":
                try:
                    import glm_keys
                    return max(0, int(glm_keys.cap()))
                except Exception:
                    pass
            return 0
    if _is_minimax_pool(pool) and _pool_refusal_reason(pool):
        return 0
    if pool in MINIMAX_BINDING_IDS:
        return CAPS["minimax"]
    return CAPS[pool]


def _glm_quota_state():
    try:
        import quota_remote
        decision = quota_remote.glm_quota_decision(read_remote=False)
        return decision.get("state")
    except Exception:
        return None


def _orchestrator_id():
    for key in ("POOL_ORCHESTRATOR_ID", "CLAUDE_SESSION_ID"):
        val = (os.environ.get(key) or "").strip()
        if val:
            return val
    host = (socket.gethostname() or "studio").split()[0]
    return f"ppid-{host}-{os.getppid()}"


def _local_disk_free_gib(entry):
    """Return the physical host's bottleneck free space in GiB.

    On macOS, a separate worktree volume does not protect the system Data
    volume that carries temp files, app state, and common Git object stores.
    Refuse if either required filesystem cannot be observed.
    """
    paths = []
    worktree_root = entry.get("worktree_root")
    if isinstance(worktree_root, str) and worktree_root.strip():
        paths.append(worktree_root.strip())
    if sys.platform == "darwin":
        paths.append("/System/Volumes/Data" if os.path.exists("/System/Volumes/Data") else "/")
    if not paths:
        return None
    values = []
    for path in dict.fromkeys(paths):
        try:
            st = os.statvfs(path)
        except OSError:
            return None
        values.append((st.f_bavail * st.f_frsize) / (1024 ** 3))
    return min(values) if values else None


def _local_host_admission_refusal(pool):
    """Return a typed refusal when this process is on the registry local seat.

    Remote hosts remain governed by host_pick/host_queue. The local seat must
    honor both local_only_engines and its physical-host load gate before any
    provider flock or broker lease is acquired.
    """
    try:
        with open(HOSTS_JSON_PATH, encoding="utf-8") as fh:
            doc = json.load(fh)
    except (OSError, ValueError):
        return "host_policy_unavailable"
    local_entries = [
        (key, entry) for key, entry in doc.items()
        if isinstance(entry, dict) and entry.get("local") is True
    ]
    if len(local_entries) != 1:
        return "host_policy_unavailable"
    key, entry = local_entries[0]
    host = (socket.gethostname() or "").split(".", 1)[0]
    names = {str(x).split(".", 1)[0] for x in (entry.get("hostnames") or [])}
    if not host or host not in names:
        return None
    aliases = {
        "qwen": "bailian",
        "minimax-codex": "minimax",
        "glm-codex": "glm",
        "glm-frontier": "glm",
    }
    family = aliases.get(pool, pool)
    allowed = {str(x).strip().lower() for x in (entry.get("local_only_engines") or [])}
    if family.lower() not in allowed:
        return f"local_seat_remote_required host={key} family={family}"
    minimum_free = entry.get("min_free_gb")
    if not isinstance(minimum_free, (int, float)) or minimum_free < 0:
        return "host_policy_unavailable"
    free_gib = _local_disk_free_gib(entry)
    if free_gib is None:
        return "host_policy_unavailable"
    if free_gib < float(minimum_free):
        return (
            f"local_seat_disk_gate host={key} free_gb={free_gib:.1f} "
            f"min_gb={float(minimum_free):.1f}"
        )
    gate = entry.get("load_gate")
    if not isinstance(gate, (int, float)) or gate < 0:
        return "host_policy_unavailable"
    try:
        load1 = float(os.getloadavg()[0])
    except (AttributeError, OSError, ValueError):
        return "host_policy_unavailable"
    if load1 >= float(gate):
        return f"local_seat_load_gate host={key} load1={load1:.2f} gate={float(gate):.2f}"
    return None


def _parse_lease_line(text):
    lease_id = account = ""
    for tok in (text or "").split():
        if tok.startswith("LEASE="):
            lease_id = tok.split("=", 1)[1].strip()
        elif tok.startswith("ACCOUNT="):
            account = tok.split("=", 1)[1].strip()
    return lease_id, account


_BROKER_SSH_TARGET_RE = re.compile(
    r"^(?:[A-Za-z0-9][A-Za-z0-9_.-]{0,63}@)?"
    r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,253}$"
)


def _broker_command(args):
    """Use the canonical local broker, or the restricted Studio RPC for one
    guarded GLM->MiniMax visual child. The SSH path transports broker commands;
    it is not a second admission authority."""
    target = (os.environ.get("POOL_BROKER_SSH_TARGET") or "").strip()
    key = (os.environ.get("POOL_BROKER_SSH_KEY") or "").strip()
    if target or key:
        if os.environ.get("GLM_VISION_DELEGATION_DEPTH") != "1":
            raise OSError("broker_ssh_outside_visual_child")
        if not target or not key or not _BROKER_SSH_TARGET_RE.fullmatch(target):
            raise OSError("broker_ssh_config_invalid")
        if not os.path.isfile(os.path.expanduser(key)):
            raise OSError("broker_ssh_key_missing")
        return [
            "ssh", "-T", "-i", os.path.expanduser(key),
            "-o", "BatchMode=yes", "-o", "IdentitiesOnly=yes",
            "-o", "ClearAllForwardings=yes", "-o", "RequestTTY=no",
            "-o", "StrictHostKeyChecking=yes", "-o", "ConnectTimeout=5",
            target, *args,
        ]
    if not os.path.isfile(BROKER):
        raise OSError("broker_missing")
    return [sys.executable, BROKER, *args]


def _broker_model_for_pool(pool):
    if pool == "glm-frontier":
        return "glm-5.3"
    if pool == "glm":
        return "glm-5.3-flash"
    return ""


def _broker_acquire(pool, wait):
    if os.environ.get("LANE_LEASED") == "1":
        return "", os.environ.get("POOL_ACCOUNT") or ""
    oid = _orchestrator_id()
    host = (os.environ.get("POOL_BROKER_HOST") or socket.gethostname() or "studio").split()[0]
    task_class = os.environ.get("POOL_TASK_CLASS") or "unknown"
    args = [
        "acquire",
        "--orchestrator-id", oid,
        "--pool", pool,
        "--task-class", task_class,
        "--host", host,
        "--pid", str(os.getpid()),
        "--wait", str(int(wait)),
    ]
    broker_model = _broker_model_for_pool(pool)
    if broker_model:
        args += ["--model", broker_model]
    prefer = (os.environ.get("POOL_ACCOUNT") or "").strip()
    if prefer:
        args += ["--account", prefer]
    try:
        cmd = _broker_command(args)
        p = subprocess.run(cmd, capture_output=True, text=True)
    except OSError as exc:
        print("SLOT_TIMEOUT pool=%s reason=broker_exec %s" % (pool, type(exc).__name__), file=sys.stderr)
        return None
    out = ((p.stdout or "") + "\n" + (p.stderr or "")).strip()
    lease_id, account = _parse_lease_line(p.stdout or "")
    if p.returncode != 0 or not lease_id:
        reason = "broker_wait"
        for line in out.splitlines():
            if line.startswith("WAIT "):
                reason = line.split("reason=", 1)[-1].strip() or reason
        print("SLOT_TIMEOUT pool=%s reason=%s" % (pool, reason), file=sys.stderr)
        return None
    os.environ["POOL_LEASE_ID"] = lease_id
    if account:
        os.environ["POOL_ACCOUNT"] = account
    os.environ["POOL_ORCHESTRATOR_ID"] = oid
    print("LEASE_ACQUIRED pool=%s lease=%s account=%s" % (pool, lease_id, account or "-"),
          file=sys.stderr, flush=True)
    return lease_id, account


def _broker_cmd(verb, lease_id):
    if not lease_id or os.environ.get("LANE_LEASED") == "1":
        return
    args = [verb, lease_id]
    oid = (os.environ.get("POOL_ORCHESTRATOR_ID") or "").strip()
    if verb == "release" and oid:
        args += ["--orchestrator-id", oid]
    try:
        subprocess.run(_broker_command(args), capture_output=True, text=True, timeout=30)
    except Exception:
        pass


def _broker_heartbeat(lease_id):
    """Return a typed broker answer without exposing broker output."""
    if not lease_id or os.environ.get("LANE_LEASED") == "1":
        # LANE_LEASED has no broker heartbeat; trust the outer Studio budget.
        return LeaseHeartbeat("held", "lane_leased")
    try:
        p = subprocess.run(
            _broker_command(["heartbeat", lease_id]),
            capture_output=True, text=True, timeout=30,
        )
    except subprocess.TimeoutExpired:
        return LeaseHeartbeat("unknown", "broker_timeout")
    except Exception:
        return LeaseHeartbeat("unknown", "broker_exception")
    out = (p.stdout or "") + "\n" + (p.stderr or "")
    reason_match = re.search(r"(?:^|\s)reason=([a-z_]+)", out)
    reason = reason_match.group(1) if reason_match else ""
    ttl_match = re.search(r"(?:^|\s)ttl=([0-9]+(?:\.[0-9]+)?)", out)
    ttl = float(ttl_match.group(1)) if ttl_match else None
    if p.returncode == 0 and re.search(r"(?:^|\s)ok=yes(?:\s|$)", out):
        return LeaseHeartbeat("held", reason or "held", ttl)
    if re.search(r"(?:^|\s)ok=no(?:\s|$)", out) and reason in {"not_held", "expired", "nonrenewable"}:
        return LeaseHeartbeat("revoked", reason, ttl)
    return LeaseHeartbeat("unknown", "broker_rc" if p.returncode else "broker_output", ttl)


def _heartbeat_loop(lease_id, stop, interval, lease_lost):
    """Heartbeat thread; transient broker uncertainty gets a TTL grace period."""
    last_held = time.monotonic()
    ttl = LEASE_TTL_S
    # A NaN/Infinity TTL defeats the unknown-heartbeat expiry comparison and
    # could leave a provider running after lease custody becomes unprovable.
    # Reject invalid local grace even when this helper is called directly.
    if not math.isfinite(ttl) or not 0.01 <= ttl <= 7500:
        lease_lost.reason = "lease_ttl_invalid"
        lease_lost.set()
        return
    first = True
    while True:
        cadence = interval if first else min(interval, max(0.01, ttl / 4.0))
        first = False
        if stop.wait(cadence):
            return
        current = (os.environ.get("POOL_LEASE_ID") or lease_id or "").strip()
        result = _broker_heartbeat(current)
        if isinstance(result, bool):
            result = LeaseHeartbeat("held" if result else "revoked", "held" if result else "not_held")
        if result.state == "held":
            if result.ttl is not None:
                # Do not let a malformed or implausibly long broker TTL
                # expand the lease-unknown grace beyond the worker's maximum
                # 7200s deadline plus 300s settlement allowance.
                if not math.isfinite(result.ttl) or not 0.01 <= result.ttl <= 7500:
                    lease_lost.reason = "broker_ttl_invalid"
                    lease_lost.set()
                    return
                ttl = result.ttl
            last_held = time.monotonic()
        elif result.state == "revoked":
            lease_lost.reason = result.reason or "revoked"
            lease_lost.set()
            return
        elif time.monotonic() - last_held >= ttl:
            lease_lost.reason = result.reason or "broker_unknown"
            lease_lost.set()
            return


def _record_lease_lost(pool, reason):
    try:
        subprocess.run(
            [sys.executable, os.path.join(HERE, "pool_ledger.py"), "append",
             "--pool", pool, "--task-class", pool, "--rc", str(LEASE_LOST_RC),
             "--signal", "lease_lost", "--reason", reason or "revoked"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        pass


def _local_semaphore_pool(pool):
    """The two GLM model labels contend for the SAME local lock files."""
    return "glm" if pool in ("glm", "glm-frontier") else pool


def _acquire_flock(pool, cap, wait):
    """Acquire a host-local flock file (W4-K2 R24 first step).
    Returns (fh, waited_s) on success, or (None, elapsed_s) on timeout."""
    d = os.path.join(HERE, "slots", pool)
    os.makedirs(d, exist_ok=True)
    t0 = time.time()
    fh = None
    while fh is None:
        for n in range(cap):
            f = open(os.path.join(d, f"{n}.lock"), "w")
            try:
                fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
                fh = f
                break
            except OSError:
                f.close()
        if fh is None:
            if time.time() - t0 > wait:
                return None, time.time() - t0
            time.sleep(15)
    fh.write("%s %s\n" % (os.getpid(), int(time.time())))
    fh.flush()
    return fh, time.time() - t0


def _release_flock(fh):
    if fh is None:
        return
    try:
        fcntl.flock(fh, fcntl.LOCK_UN)
    except Exception:
        pass
    try:
        fh.close()
    except Exception:
        pass


def _start_heartbeat(lease_id, interval=45):
    """Start the heartbeat thread and return (stop, lease_lost, thread).
    Heartbeat is a daemon thread; call stop.set() before process exit."""
    stop = threading.Event()
    lease_lost = threading.Event()
    hb = None
    if lease_id:
        hb = threading.Thread(
            target=_heartbeat_loop,
            args=(lease_id, stop, interval, lease_lost),
            daemon=True,
        )
        hb.start()
    return stop, lease_lost, hb


def _settle_child_session(child, reason, grace=None):
    receipt = settle_owned_process_session(
        child,
        grace=SIGKILL_GRACE_S if grace is None else float(grace),
        reason=reason,
    )
    if cleanup_receipt_is_proven(receipt):
        return True
    label = (os.environ.get("SLOT_POOL_LABEL") or "slot").strip()
    print(
        "%s CHILD_CLEANUP_UNPROVEN status=%s error=%s"
        % (label, receipt.get("status"), receipt.get("error_code")),
        file=sys.stderr,
        flush=True,
    )
    return False


def _run_child_with_lease_monitor(cmd, lease_lost):
    """Run one admitted provider child under lease-loss and wall-clock fuses.

    The provider wrapper owns a separate process session. Slot temporarily
    handles parent termination signals so an outer owned-process timeout can
    ask slot to settle that nested session before the outer owner escalates.
    """
    label = (os.environ.get("SLOT_POOL_LABEL") or "").strip()
    timeout_s = _child_runtime_limit()
    parent_stop = threading.Event()
    parent_stop.signum = None

    def _parent_signal(signum, _frame):
        parent_stop.signum = int(signum)
        parent_stop.set()

    old_handlers = {}
    if threading.current_thread() is threading.main_thread():
        for signum in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
            old_handlers[signum] = signal.getsignal(signum)
            signal.signal(signum, _parent_signal)
    try:
        try:
            child = subprocess.Popen(cmd, start_new_session=True)
        except Exception:
            return 1
        started = time.monotonic()
        while True:
            rc = child.poll()
            if rc is not None:
                return rc if _settle_child_session(child, "normal_completion") else LEASE_LOST_RC
            if parent_stop.is_set():
                signum = int(getattr(parent_stop, "signum", 0) or signal.SIGTERM)
                if label:
                    print(
                        "%s PARENT_SIGNAL signum=%d" % (label, signum),
                        file=sys.stderr,
                        flush=True,
                    )
                if not _settle_child_session(
                    child,
                    "parent_signal",
                    grace=PARENT_SIGNAL_SETTLE_GRACE_S,
                ):
                    return LEASE_LOST_RC
                return 128 + signum
            if lease_lost.is_set():
                if label:
                    print(
                        "%s LEASE_LOST reason=%s"
                        % (label, getattr(lease_lost, "reason", "revoked")),
                        file=sys.stderr,
                        flush=True,
                    )
                if not _settle_child_session(child, "lease_lost"):
                    return LEASE_LOST_RC
                return LEASE_LOST_RC
            if time.monotonic() - started >= timeout_s:
                if label:
                    print(
                        "%s CHILD_TIMEOUT seconds=%g" % (label, timeout_s),
                        file=sys.stderr,
                        flush=True,
                    )
                if not _settle_child_session(child, "timeout"):
                    return LEASE_LOST_RC
                return CHILD_TIMEOUT_RC
            time.sleep(LEASE_MONITOR_POLL_S)
    finally:
        for signum, previous in old_handlers.items():
            signal.signal(signum, previous)


def main(argv=None):
    a = sys.argv[1:] if argv is None else list(argv)
    if len(a) < 3:
        print(__doc__)
        return 2
    pool = a[0]
    known_pool = pool in CAPS or pool in MINIMAX_BINDING_IDS
    if not known_pool:
        print(__doc__)
        return 2
    wait = 3600.0
    if len(a) >= 2 and a[1] == "--wait":
        if len(a) < 4:
            print("slot.py: invalid --wait", file=sys.stderr)
            return 2
        try:
            wait = float(a[2])
        except (TypeError, ValueError):
            print("slot.py: invalid --wait", file=sys.stderr)
            return 2
        if not math.isfinite(wait) or not 0 <= wait <= 3600:
            print("slot.py: --wait must be between 0 and 3600 seconds", file=sys.stderr)
            return 2
        a = a[3:]
    else:
        a = a[1:]
    if not a or a[0] != "--" or len(a) < 2:
        print("expected -- <command...>", file=sys.stderr)
        return 2
    cmd = a[1:]
    os.environ["SLOT_POOL_LABEL"] = pool
    try:
        _child_runtime_limit()
    except LaneRuntimeConfigError as exc:
        print("slot.py: admission_denied reason=%s" % str(exc), file=sys.stderr)
        return 78
    # The local lease heartbeat is the custody signal for an unleased worker.
    # A NaN/Infinity/oversized TTL would make broker uncertainty effectively
    # unbounded. Validate before any host/provider lease admission.
    if os.environ.get("LANE_LEASED") != "1" and (
        not math.isfinite(LEASE_TTL_S) or not 0.01 <= LEASE_TTL_S <= 7500
    ):
        print("slot.py: admission_denied reason=lease_ttl_invalid", file=sys.stderr)
        return 78
    host_refusal = _local_host_admission_refusal(pool)
    if host_refusal:
        print(f"slot.py: pool={pool} admission_denied reason={host_refusal}", file=sys.stderr)
        _pool_ledger_refusal(pool, host_refusal)
        return 78
    cap = _pool_cap(pool)
    if cap == 0:
        refusal = _pool_refusal_reason(pool) or "realm_unreviewed"
        print("slot.py: pool=%s admission_denied reason=%s" % (pool, refusal),
              file=sys.stderr)
        _pool_ledger_refusal(pool, refusal)
        return 78

    # W4-K2 R24: local flock FIRST (host safety net)…
    fh, waited = _acquire_flock(_local_semaphore_pool(pool), cap, wait)
    if fh is None:
        print("SLOT_TIMEOUT pool=%s after %ss (local flock)" % (pool, int(wait)),
              file=sys.stderr)
        return 75
    print("FLOCK_ACQUIRED pool=%s wait=%ss" % (pool, int(waited)),
          file=sys.stderr, flush=True)

    # …then the cluster lease broker (the only grantor).
    acquired = _broker_acquire(pool, wait)
    if acquired is None:
        _release_flock(fh)
        return 75
    lease_id, _account = acquired

    # W4-K2 R24: heartbeat starts immediately after lease grant.
    stop, lease_lost, _hb = _start_heartbeat(lease_id, interval=45)

    try:
        rc = _run_child_with_lease_monitor(cmd, lease_lost)
        if rc == LEASE_LOST_RC:
            _record_lease_lost(pool, getattr(lease_lost, "reason", "revoked"))
        return rc
    finally:
        stop.set()
        current = (os.environ.get("POOL_LEASE_ID") or lease_id or "").strip()
        _broker_cmd("release", current)
        if lease_id and current and current != lease_id:
            _broker_cmd("release", lease_id)
        _release_flock(fh)


if __name__ == "__main__":
    sys.exit(main())
