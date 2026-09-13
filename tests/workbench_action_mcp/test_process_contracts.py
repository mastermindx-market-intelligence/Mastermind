from __future__ import annotations

import dataclasses

import pytest

from integrations.workbench_action_mcp.contracts import ActionTokenCodec, PreparedTextPatch
from integrations.workbench_action_mcp.process_contracts import (
    COMMAND_TOKEN_SCHEMA,
    CommandTokenCodec,
    PreparedCommand,
    ProcessContractError,
    ValidationRecipe,
    recipe_digest,
    validate_recipe,
    validate_recipe_set,
)


def recipe() -> ValidationRecipe:
    return ValidationRecipe(
        recipe_id="git.diff-check",
        description="Validate whitespace errors in the selected worktree.",
        argv=("/usr/bin/git", "diff", "--check"),
        timeout_seconds=20,
        max_output_bytes=65536,
    )


def prepared(now: int = 1_000_000) -> PreparedCommand:
    selected = recipe()
    return PreparedCommand(
        schema=COMMAND_TOKEN_SCHEMA,
        command_id="1" * 32,
        subject_digest="2" * 64,
        client_ref="fixture-client",
        resource="https://workbench.example/mcp",
        project_ref="project:alpha",
        context_ref="context:alpha",
        responsibility_ref="responsibility:alpha",
        operation_ref="operation:alpha",
        owner_ref="owner:alpha",
        generation="generation:alpha",
        root_device=1,
        root_inode=2,
        committed_head="3" * 40,
        recipe_id=selected.recipe_id,
        recipe_digest=recipe_digest(selected),
        timeout_seconds=10,
        max_output_bytes=32768,
        issued_at_ms=now,
        expires_at_ms=now + 60_000,
    )


def test_recipe_validation_is_closed_sorted_and_shell_free() -> None:
    selected = recipe()
    assert validate_recipe(selected) == selected
    assert validate_recipe_set((selected,)) == (selected,)
    with pytest.raises(ProcessContractError):
        validate_recipe(dataclasses.replace(selected, argv=("/bin/zsh", "-c", "true")))
    with pytest.raises(ProcessContractError):
        validate_recipe_set(
            (
                dataclasses.replace(selected, recipe_id="z.recipe"),
                dataclasses.replace(selected, recipe_id="a.recipe"),
            )
        )


def test_command_token_is_canonical_tamper_evident_and_expires() -> None:
    key = b"k" * 32
    codec = CommandTokenCodec(key)
    value = prepared()
    token = codec.encode(value)
    assert codec.decode(token, now_ms=value.issued_at_ms + 1) == value
    tampered = token[:-1] + ("A" if token[-1] != "A" else "B")
    with pytest.raises(ProcessContractError):
        codec.decode(tampered, now_ms=value.issued_at_ms + 1)
    with pytest.raises(ProcessContractError):
        codec.decode(token, now_ms=value.expires_at_ms)


def test_command_token_domain_is_not_patch_token_domain() -> None:
    key = b"x" * 32
    command = CommandTokenCodec(key).encode(prepared())
    patch = PreparedTextPatch(
        schema="mastermind.workbench_text_patch.v1",
        action_id="4" * 32,
        subject_digest="2" * 64,
        client_ref="fixture-client",
        resource="https://workbench.example/mcp",
        project_ref="project:alpha",
        context_ref="context:alpha",
        responsibility_ref="responsibility:alpha",
        operation_ref="operation:alpha",
        owner_ref="owner:alpha",
        generation="generation:alpha",
        root_device=1,
        root_inode=2,
        committed_head="3" * 40,
        relative_path="a.txt",
        mode="CREATE",
        preimage_sha256=None,
        postimage_sha256="5" * 64,
        old_text=None,
        new_text="hello\n",
        issued_at_ms=1_000_000,
        expires_at_ms=1_060_000,
    )
    patch_token = ActionTokenCodec(key).encode(patch)
    with pytest.raises(Exception):
        ActionTokenCodec(key).decode(command, now_ms=1_000_001)
    with pytest.raises(ProcessContractError):
        CommandTokenCodec(key).decode(patch_token, now_ms=1_000_001)
