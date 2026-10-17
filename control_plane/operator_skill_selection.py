"""Closed, path-free Skill selection for the existing OHF turn transport.

Selection is a request, never a package verification, grant or admission receipt.
The worker resolves its own installed path from its already-bound local package.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

MAX_OPERATOR_PROMPT_BYTES = 512 * 1024
_SELECTION_FIELDS = frozenset({
    "capability_id", "skill_content_digest", "package_generation_digest",
})
_CAPABILITY_ID = re.compile(r"[a-z][a-z0-9._-]{0,159}\Z")
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")


class OperatorSkillSelectionError(ValueError):
    """Static refusal; untrusted values must not appear in diagnostics."""


@dataclass(frozen=True)
class OperatorSkillSelection:
    capability_id: str
    skill_content_digest: str
    package_generation_digest: str

    def __post_init__(self) -> None:
        if (
            type(self.capability_id) is not str
            or _CAPABILITY_ID.fullmatch(self.capability_id) is None
            or any(
                type(value) is not str or _DIGEST.fullmatch(value) is None
                for value in (
                    self.skill_content_digest, self.package_generation_digest,
                )
            )
        ):
            raise OperatorSkillSelectionError("operator Skill selection identity is invalid")


def skill_selection_from_wire(value: Any) -> OperatorSkillSelection:
    if type(value) is not dict or set(value) != _SELECTION_FIELDS:
        raise OperatorSkillSelectionError("operator Skill selection fields are invalid")
    return OperatorSkillSelection(**value)


def skill_selection_to_wire(value: OperatorSkillSelection) -> dict[str, str]:
    if type(value) is not OperatorSkillSelection:
        raise OperatorSkillSelectionError("operator Skill selection type is invalid")
    fields = {name: getattr(value, name) for name in _SELECTION_FIELDS}
    skill_selection_from_wire(fields)
    return fields


@dataclass(frozen=True)
class OperatorSkillTurnInput:
    text: str
    selection: OperatorSkillSelection

    def __post_init__(self) -> None:
        try:
            valid_text = (
                type(self.text) is str
                and bool(self.text.strip())
                and len(self.text.encode("utf-8")) <= MAX_OPERATOR_PROMPT_BYTES
            )
        except UnicodeError:
            valid_text = False
        if not valid_text:
            raise OperatorSkillSelectionError("operator Skill text is outside the closed byte bound")
        skill_selection_to_wire(self.selection)


def operator_turn_payload(
    value: str | OperatorSkillTurnInput,
) -> tuple[str, dict[str, str] | None]:
    # Preserve the legacy string transport and its worker-side validation.
    if isinstance(value, str):
        return value, None
    if type(value) is not OperatorSkillTurnInput:
        raise OperatorSkillSelectionError("operator turn input type is invalid")
    OperatorSkillTurnInput(value.text, value.selection)
    return value.text, skill_selection_to_wire(value.selection)
