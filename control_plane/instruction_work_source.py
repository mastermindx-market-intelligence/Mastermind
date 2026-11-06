"""Private canonical instruction source binding for existing Runtime admission.

A source identity grants no execution permission. The incumbent host must retain
its actual current principal/admission guard; no public frame issues this object.
Only a nominal installed content reader may qualify the immutable root binding.
"""
from __future__ import annotations

from dataclasses import dataclass
import inspect
import json
import re
from typing import Callable

from common.executive_workspace_contract import canonical
from common.workspace_project_instructions_contract import instruction_ref, validate_body
from common.workspace_project_plan_contract import validate_selection, validate_source
from control_plane.agentos_project_instructions import AgentOsProjectInstructionsReader

SCHEMA = "mastermind.instruction_work_source.v1"
ERROR = "INSTRUCTION_WORK_SOURCE_INVALID"
_SEAL = object()


def validate_instruction_work_source(value):
    try:
        if type(value) is not dict or set(value) != {"schema", "work_ref", "instruction_ref", "revision", "source"} or value["schema"] != SCHEMA:
            raise ValueError(ERROR)
        validate_selection({"work_ref": value["work_ref"]})
        instruction_ref(value["instruction_ref"])
        if type(value["revision"]) is not str or re.fullmatch(r"[0-9a-f]{64}", value["revision"]) is None:
            raise ValueError(ERROR)
        validate_source(value["source"], value["work_ref"])
        return json.loads(canonical(value))
    except (ValueError, TypeError, KeyError, RecursionError):
        raise ValueError(ERROR) from None


def _guard(guard):
    if (not callable(guard) or inspect.iscoroutinefunction(guard)
            or inspect.iscoroutinefunction(getattr(guard, "__call__", None))):
        raise ValueError(ERROR)
    result = guard()
    if inspect.isawaitable(result):
        if inspect.iscoroutine(result): result.close()
        raise ValueError(ERROR)
    if result is not None: raise ValueError(ERROR)


@dataclass(frozen=True, slots=True)
class InstructionWorkSource:
    _seal: object
    _reader: AgentOsProjectInstructionsReader
    _material: bytes
    _principal_guard: Callable[[], None]

    def __post_init__(self):
        if self._seal is not _SEAL or type(self._reader) is not AgentOsProjectInstructionsReader:
            raise ValueError(ERROR)

    def material(self):
        if self._seal is not _SEAL: raise ValueError(ERROR)
        return validate_instruction_work_source(json.loads(self._material))

    def check(self):
        """Recheck source and host guard before and inside the owner transaction."""
        material = self.material()
        _guard(self._principal_guard)
        body = validate_body(AgentOsProjectInstructionsReader.read(self._reader, work_ref=material["work_ref"]), {"work_ref": material["work_ref"]})
        if body["availability"] != "AVAILABLE" or body["source"] != material["source"]:
            raise ValueError(ERROR)
        rows = [row for row in body["instructions"] if row["instruction_ref"] == material["instruction_ref"]]
        if len(rows) != 1 or rows[0]["revision"] != material["revision"]:
            raise ValueError(ERROR)
        _guard(self._principal_guard)


def _issue_instruction_work_source(*, reader, work_ref, instruction_ref, revision, source, principal_guard):
    """Private host composition; no serialized/public issuer or grant fallback."""
    if type(reader) is not AgentOsProjectInstructionsReader:
        raise ValueError(ERROR)
    material = validate_instruction_work_source({"schema": SCHEMA, "work_ref": work_ref,
        "instruction_ref": instruction_ref, "revision": revision, "source": source})
    binding = InstructionWorkSource(_SEAL, reader, canonical(material), principal_guard)
    binding.check()
    return binding
