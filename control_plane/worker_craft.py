"""Role-specific Craft composition before existing worker/provider effects.

This module adds working method and commission authoring only.  It never wraps,
registers, selects, replaces, or starts a WorkerExecutionAdapter.  Callers keep the
already reviewed/bound adapter object and may pass a materialized WorkerLaunchSpec to
that exact adapter immediately before start.

The compact commission seam executes the existing checked-in Craft brief compiler from
research/worker_craft; it is an adapter to that incumbent compiler, not a second
compiler, lifecycle, queue, retry path, provider selector, credential store, or
publication owner.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import re
import stat
from pathlib import Path
from typing import Any, Mapping

from control_plane.worker_execution_contract import WorkerLaunchSpec


CRAFT_PROMPT_SCHEMA_VERSION = "mastermind.worker_craft_prompt/v1"
CRAFT_JOB_PACKET_SCHEMA = "mastermind.executive_job_packet/v1"
CRAFT_COMMISSION_OUTPUT_SCHEMA = "mastermind.craft_commission_compilation.v1"
CRAFT_DELIVERY_MODE = "prompt_method"
CRAFT_BEGIN = "<<<MASTERMIND_CRAFT_METHOD_V1>>>"
CRAFT_END = "<<<END_MASTERMIND_CRAFT_METHOD_V1>>>"
MAX_CRAFT_SOURCE_BYTES = 64 * 1024
MAX_CRAFTED_PROMPT_BYTES = 512 * 1024
MAX_COMMISSION_BYTES = 512 * 1024
DEFAULT_CRAFT_ROOT = (
    Path(__file__).resolve().parent.parent
    / "research"
    / "worker_craft"
    / "mastermind-craft"
)

_ROLE_FILES = {
    "orchestrator": "references/orchestrator.md",
    "designer": "references/designer.md",
    "frontend": "references/frontend.md",
    "backend": "references/backend.md",
    "researcher": "references/researcher.md",
    "data-scientist": "references/data-scientist.md",
    "reviewer": "references/reviewer.md",
    "verifier": "references/verifier.md",
}
_ROLE_RE = re.compile(r"[a-z][a-z0-9-]{0,31}\Z")


class CraftPromptError(ValueError):
    """Craft source, role selection, prompt composition, or commission refusal."""


@dataclasses.dataclass(frozen=True)
class CraftMethodReceipt:
    schema_version: str
    role: str
    delivery_mode: str
    native_skill_attested: bool
    package_root: str
    skill_sha256: str
    common_sha256: str
    role_sha256: str
    method_digest: str


@dataclasses.dataclass(frozen=True)
class CraftPromptApplication:
    receipt: CraftMethodReceipt
    original_prompt_sha256: str
    crafted_prompt_sha256: str


@dataclasses.dataclass(frozen=True)
class CraftLaunchMaterialization:
    """Pure pre-start result; the provider adapter is intentionally absent."""

    launch_spec: WorkerLaunchSpec
    application: CraftPromptApplication


@dataclasses.dataclass(frozen=True)
class CraftCommissionMaterialization:
    """Exact compiler bytes and authoring digests; no runtime/provider identity."""

    role: str
    commission_bytes: bytes
    commission_sha256: str
    compact_input_sha256: str
    normalized_brief_sha256: str
    method_sha256: str
    compiler_sha256: str


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _validated_role(value: object) -> str:
    role = str(value or "").strip().lower()
    if _ROLE_RE.fullmatch(role) is None or role not in _ROLE_FILES:
        raise CraftPromptError("craft_role_invalid")
    return role


def _safe_label(value: object) -> str:
    if not isinstance(value, str):
        return ""
    label = value.strip().lower().replace("_", "-").replace(" ", "-")
    if len(label) > 96 or any(ord(ch) < 0x20 for ch in label):
        return ""
    return label


def resolve_craft_role(
    packet: Mapping[str, Any], *, fixed_role: str | None = None
) -> str:
    """Select one method from trusted packet fields, never objective prose."""

    if fixed_role is not None:
        return _validated_role(fixed_role)
    explicit = packet.get("craft_role")
    if explicit is not None:
        return _validated_role(explicit)

    orchestration = packet.get("orchestration")
    orchestration_role = (
        _safe_label(orchestration.get("role"))
        if isinstance(orchestration, Mapping)
        else ""
    )
    if orchestration_role in {"plan", "aggregation"}:
        return "orchestrator"
    if orchestration_role == "review":
        return "reviewer"

    department = _safe_label(packet.get("department"))
    department_rules = (
        (("product-design", "design-systems", "ux", "ui-design", "design"), "designer"),
        (("frontend", "front-end", "ui-engineering", "web-ui"), "frontend"),
        (("data-science", "data-scientist", "quant-research", "quant"), "data-scientist"),
        (("research-intelligence", "research"), "researcher"),
        (("security-review", "red-team", "audit", "review"), "reviewer"),
        (("verification", "quality-assurance", "release-verification", "qa"), "verifier"),
        (("orchestration", "executive"), "orchestrator"),
        (("backend", "back-end", "data-engineering", "platform", "product-engineering"), "backend"),
    )
    for labels, role in department_rules:
        if department in labels:
            return role

    task_kind = _safe_label(packet.get("task_kind"))
    fallback = {
        "planning": "orchestrator",
        "escalation": "orchestrator",
        "judgment": "reviewer",
        "review": "reviewer",
        "research": "researcher",
        "tests": "verifier",
        "implementation": "backend",
        "mechanical": "backend",
    }
    try:
        return fallback[task_kind]
    except KeyError as exc:
        raise CraftPromptError("craft_role_unresolved") from exc


def _root(root: Path | str) -> Path:
    value = Path(root)
    try:
        info = value.lstat()
    except OSError as exc:
        raise CraftPromptError("craft_root_unavailable") from exc
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        raise CraftPromptError("craft_root_invalid")
    return value.resolve(strict=True)


def _read_source(root: Path, relative: str) -> tuple[str, str]:
    candidate = root.joinpath(*relative.split("/"))
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(root)
        before = candidate.lstat()
    except (OSError, ValueError) as exc:
        raise CraftPromptError("craft_source_unavailable") from exc
    if (
        stat.S_ISLNK(before.st_mode)
        or not stat.S_ISREG(before.st_mode)
        or before.st_nlink != 1
        or before.st_size <= 0
        or before.st_size > MAX_CRAFT_SOURCE_BYTES
    ):
        raise CraftPromptError("craft_source_invalid")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    try:
        descriptor = os.open(candidate, flags)
    except OSError as exc:
        raise CraftPromptError("craft_source_unavailable") from exc
    try:
        opened = os.fstat(descriptor)
        if (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns) != (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
        ):
            raise CraftPromptError("craft_source_changed")
        data = bytearray()
        while len(data) <= MAX_CRAFT_SOURCE_BYTES:
            chunk = os.read(
                descriptor,
                min(65536, MAX_CRAFT_SOURCE_BYTES + 1 - len(data)),
            )
            if not chunk:
                break
            data.extend(chunk)
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    if len(data) != before.st_size or len(data) > MAX_CRAFT_SOURCE_BYTES:
        raise CraftPromptError("craft_source_changed")
    if (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns) != (
        opened.st_dev,
        opened.st_ino,
        opened.st_size,
        opened.st_mtime_ns,
    ):
        raise CraftPromptError("craft_source_changed")
    raw = bytes(data)
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise CraftPromptError("craft_source_not_utf8") from exc
    return text, _sha256(raw)


def load_craft_method(
    role: str, *, root: Path | str = DEFAULT_CRAFT_ROOT
) -> tuple[str, CraftMethodReceipt]:
    selected = _validated_role(role)
    package_root = _root(root)
    skill_text, skill_digest = _read_source(package_root, "SKILL.md")
    common_text, common_digest = _read_source(package_root, "references/common.md")
    role_text, role_digest = _read_source(package_root, _ROLE_FILES[selected])
    del skill_text
    projection = {
        "schema_version": CRAFT_PROMPT_SCHEMA_VERSION,
        "role": selected,
        "skill_sha256": skill_digest,
        "common_sha256": common_digest,
        "role_sha256": role_digest,
    }
    method_digest = _sha256(_canonical_bytes(projection))
    receipt = CraftMethodReceipt(
        schema_version=CRAFT_PROMPT_SCHEMA_VERSION,
        role=selected,
        delivery_mode=CRAFT_DELIVERY_MODE,
        native_skill_attested=False,
        package_root="research/worker_craft/mastermind-craft",
        skill_sha256=skill_digest,
        common_sha256=common_digest,
        role_sha256=role_digest,
        method_digest=method_digest,
    )
    header = (
        f"{CRAFT_BEGIN}\n"
        f"role: {selected}\n"
        f"delivery_mode: {CRAFT_DELIVERY_MODE}\n"
        "native_skill_attested: false\n"
        f"method_digest: {method_digest}\n"
        "This method supplies working practice only. It grants no tool, authority, "
        "workspace, network, credential, lifecycle, or production permission.\n\n"
    )
    rendered = (
        header
        + "## Shared method\n\n"
        + common_text.strip()
        + "\n\n## Selected role method\n\n"
        + role_text.strip()
        + f"\n{CRAFT_END}"
    )
    return rendered, receipt


def extract_job_packet(prompt: str) -> tuple[dict[str, Any], int, int]:
    if not isinstance(prompt, str) or not prompt:
        raise CraftPromptError("job_prompt_invalid")
    marker = f'"schema_version": "{CRAFT_JOB_PACKET_SCHEMA}"'
    marker_index = prompt.find(marker)
    if marker_index < 0:
        raise CraftPromptError("job_packet_missing")
    decoder = json.JSONDecoder()
    start = prompt.rfind("{", 0, marker_index + 1)
    while start >= 0:
        try:
            value, consumed = decoder.raw_decode(prompt[start:])
        except json.JSONDecodeError:
            value = None
            consumed = 0
        if isinstance(value, dict) and value.get("schema_version") == CRAFT_JOB_PACKET_SCHEMA:
            return value, start, start + consumed
        start = prompt.rfind("{", 0, start)
    raise CraftPromptError("job_packet_invalid")


def apply_craft_to_prompt(
    prompt: str,
    *,
    fixed_role: str | None = None,
    root: Path | str = DEFAULT_CRAFT_ROOT,
) -> tuple[str, CraftPromptApplication]:
    if CRAFT_BEGIN in prompt or CRAFT_END in prompt:
        raise CraftPromptError("craft_prompt_already_materialized")
    packet, start, _end = extract_job_packet(prompt)
    role = resolve_craft_role(packet, fixed_role=fixed_role)
    method, receipt = load_craft_method(role, root=root)
    prefix = prompt[:start].rstrip()
    crafted = prefix + "\n\n" + method + "\n\n" + prompt[start:]
    if len(crafted.encode("utf-8")) > MAX_CRAFTED_PROMPT_BYTES:
        raise CraftPromptError("crafted_prompt_too_large")
    application = CraftPromptApplication(
        receipt=receipt,
        original_prompt_sha256=_sha256(prompt.encode("utf-8")),
        crafted_prompt_sha256=_sha256(crafted.encode("utf-8")),
    )
    return crafted, application


def materialize_launch_spec(
    spec: WorkerLaunchSpec,
    *,
    fixed_role: str | None = None,
    root: Path | str = DEFAULT_CRAFT_ROOT,
) -> CraftLaunchMaterialization:
    """Return a prompt-enriched spec without touching or representing an adapter."""

    if not isinstance(spec, WorkerLaunchSpec):
        raise TypeError("materialize_launch_spec requires WorkerLaunchSpec")
    crafted, application = apply_craft_to_prompt(
        spec.prompt,
        fixed_role=fixed_role,
        root=root,
    )
    return CraftLaunchMaterialization(
        launch_spec=dataclasses.replace(spec, prompt=crafted),
        application=application,
    )


def _load_commission_compiler(
    root: Path | str,
) -> tuple[dict[str, Any], str]:
    package_root = _root(root)
    source_text, compiler_digest = _read_source(package_root, "scripts/brief.py")
    filename = str(package_root / "scripts" / "brief.py")
    namespace: dict[str, Any] = {
        "__file__": filename,
        "__name__": "_mastermind_craft_brief_compiler",
    }
    try:
        code = compile(source_text, filename, "exec")
        exec(code, namespace)
    except Exception as exc:
        raise CraftPromptError("craft_commission_compiler_unavailable") from exc
    compile_fn = namespace.get("compile_commission")
    brief_error = namespace.get("BriefError")
    if (
        not callable(compile_fn)
        or not isinstance(brief_error, type)
        or not issubclass(brief_error, Exception)
    ):
        raise CraftPromptError("craft_commission_compiler_contract_invalid")
    return namespace, compiler_digest


def materialize_worker_commission(
    request: dict[str, Any],
    *,
    root: Path | str = DEFAULT_CRAFT_ROOT,
) -> CraftCommissionMaterialization:
    """Invoke the incumbent Craft compiler and return exact immutable commission bytes."""

    if type(request) is not dict:
        raise CraftPromptError("craft_commission_request_invalid")
    package_root = _root(root)
    namespace, compiler_digest = _load_commission_compiler(package_root)
    compile_fn = namespace["compile_commission"]
    brief_error = namespace["BriefError"]
    try:
        result = compile_fn(request, method_root=package_root / "references")
    except brief_error as exc:
        raise CraftPromptError("craft_commission_refused:" + str(exc)) from exc
    if not isinstance(result, dict):
        raise CraftPromptError("craft_commission_compiler_contract_invalid")
    if (
        result.get("schema_version") != CRAFT_COMMISSION_OUTPUT_SCHEMA
        or result.get("execution_authority") is not False
        or result.get("runtime_admission") != "NOT_REQUESTED"
        or result.get("source_verification") != "NOT_PERFORMED"
        or result.get("provider_selection") != "NOT_PERFORMED"
        or result.get("model_selection") != "NOT_PERFORMED"
        or result.get("account_selection") != "NOT_PERFORMED"
    ):
        raise CraftPromptError("craft_commission_compiler_contract_invalid")
    markdown = result.get("instructions_markdown")
    if not isinstance(markdown, str):
        raise CraftPromptError("craft_commission_compiler_contract_invalid")
    try:
        content = markdown.encode("utf-8")
    except UnicodeError as exc:
        raise CraftPromptError("craft_commission_encoding_invalid") from exc
    if not content or len(content) > MAX_COMMISSION_BYTES:
        raise CraftPromptError("craft_commission_size_invalid")
    digest = _sha256(content)
    if result.get("commission_sha256") != digest:
        raise CraftPromptError("craft_commission_digest_mismatch")
    required_digests = (
        "compact_input_sha256",
        "normalized_brief_sha256",
        "method_sha256",
    )
    if any(
        not isinstance(result.get(field), str)
        or re.fullmatch(r"[0-9a-f]{64}", result[field]) is None
        for field in required_digests
    ):
        raise CraftPromptError("craft_commission_compiler_contract_invalid")
    role = result.get("role")
    if not isinstance(role, str) or role not in _ROLE_FILES:
        raise CraftPromptError("craft_commission_compiler_contract_invalid")
    return CraftCommissionMaterialization(
        role=role,
        commission_bytes=content,
        commission_sha256=digest,
        compact_input_sha256=result["compact_input_sha256"],
        normalized_brief_sha256=result["normalized_brief_sha256"],
        method_sha256=result["method_sha256"],
        compiler_sha256=compiler_digest,
    )


__all__ = [
    "CRAFT_BEGIN",
    "CRAFT_DELIVERY_MODE",
    "CRAFT_END",
    "CRAFT_PROMPT_SCHEMA_VERSION",
    "CraftCommissionMaterialization",
    "CraftLaunchMaterialization",
    "CraftMethodReceipt",
    "CraftPromptApplication",
    "CraftPromptError",
    "apply_craft_to_prompt",
    "extract_job_packet",
    "load_craft_method",
    "materialize_launch_spec",
    "materialize_worker_commission",
    "resolve_craft_role",
]
