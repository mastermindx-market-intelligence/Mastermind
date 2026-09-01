from __future__ import annotations

import argparse
import ast
import io
from pathlib import Path

from ops.linear_projector import host_enrollment as mod


_ROOT = Path(__file__).resolve().parents[1]
_DOC = _ROOT / "docs" / "LINEAR_PORTFOLIO_PROJECTOR_HOST.md"


class _PipedStdin:
    def __init__(self, payload: bytes) -> None:
        self.buffer = io.BytesIO(payload)


def _import_roots() -> set[str]:
    tree = ast.parse(Path(mod.__file__).read_text(encoding="utf-8"))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".", 1)[0])
    return roots


def _parser_surface(parser: argparse.ArgumentParser) -> set[str]:
    surface: set[str] = set()
    pending = [parser]
    while pending:
        current = pending.pop()
        for action in current._actions:
            surface.update(action.option_strings)
            if isinstance(action, argparse._SubParsersAction):
                surface.update(action.choices)
                pending.extend(action.choices.values())
    return surface


def test_production_module_has_no_network_linear_or_executive_imports() -> None:
    forbidden = {
        "http",
        "requests",
        "socket",
        "subprocess",
        "urllib",
        "control_plane",
        "integrations",
    }
    assert _import_roots().isdisjoint(forbidden)


def test_public_cli_has_no_generic_secret_or_service_surface() -> None:
    surface = "\n".join(sorted(_parser_surface(mod.build_parser()))).lower()
    for forbidden in (
        "path",
        "service",
        "account",
        "token",
        "secret",
        "rotate",
        "delete",
        "daemon",
        "schedule",
    ):
        assert forbidden not in surface


def test_production_enroll_refuses_piped_non_tty_stdin(monkeypatch) -> None:
    monkeypatch.setattr(mod.os, "geteuid", lambda: 0)
    monkeypatch.setattr(mod.sys, "stdin", _PipedStdin(b"projector-secret\n"))

    def _must_not_enroll(**kwargs):  # pragma: no cover - forbidden path
        raise AssertionError("production piped stdin must refuse before enroll")

    monkeypatch.setattr(mod, "enroll", _must_not_enroll)
    stdout = io.StringIO()
    stderr = io.StringIO()
    assert (
        mod.main(
            argv=["enroll", "--client-id", "client-abc123"],
            environ={},
            stdout=stdout,
            stderr=stderr,
        )
        == 2
    )
    assert stdout.getvalue() == ""
    assert stderr.getvalue() == "REFUSED: PROJECTOR_HOST_INPUT_REFUSED\n"


def test_non_secret_config_contract_has_no_secret_bearing_keys() -> None:
    document = mod.build_config_document(client_id="client-abc123")
    rendered_keys = "\n".join(document).lower()
    for forbidden in ("secret", "token", "authorization", "cookie", "refresh"):
        assert forbidden not in rendered_keys


def test_operator_runbook_is_fixed_and_contains_no_example_secret_value() -> None:
    text = _DOC.read_text(encoding="utf-8")
    assert "sudo python3 -m ops.linear_projector.host_enrollment prepare" in text
    assert (
        "sudo python3 -m ops.linear_projector.host_enrollment enroll --client-id <NON_SECRET_CLIENT_ID>"
        in text
    )
    assert (
        "sudo python3 -m ops.linear_projector.host_enrollment verify --expected-client-id <NON_SECRET_CLIENT_ID>"
        in text
    )
    assert "no OAuth/token exchange" in text
    assert "no Linear mutation" in text
    assert "lin_api_" not in text
    assert "Bearer " not in text
