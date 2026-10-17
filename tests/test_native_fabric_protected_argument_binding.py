"""The #1391 native-binding slot cannot receive ordinary scheduling metadata."""
from __future__ import annotations
import ast
from pathlib import Path
import re
import types

import pytest

ROOT = Path(__file__).resolve().parents[1]
PATCH = ROOT / "ops/native_fabric/routing_audit_20261013/protected_composition/logical_priority_after_native.patch"


def patched_ordinary_call():
    # Actual existing acquire call's stable prefix and changed tail, as retained
    # in the source patch. No broker, database or provider operation is invoked.
    text = PATCH.read_text()
    match = re.search(r"(?m)^\+\s+(job_class(?:=job_class)?),$", text)
    assert match, "missing ordinary priority call site"
    return ast.parse(
        "self._try_acquire(orch,pool,account,task_class,host,pid,ttl,waiter_id,"
        "model,operator_child_id," + match.group(1) + ")", mode="eval",
    )


def native_first_target(orch, pool, account, task_class, host, pid, ttl,
                        waiter_id, model="", operator_child_id=None,
                        native_binding=None, job_class=None):
    # #1391 appends native_binding to the established positional signature.
    # Further optional additions must preserve that existing parameter meaning.
    return native_binding, job_class


@pytest.mark.parametrize("logical", ["heal", "review", "mechanical", ""])
def test_ordinary_priority_never_populates_native_binding(logical):
    values = dict(orch="root", pool="synthetic", account=None, task_class="remote-minimax",
                  host="synthetic", pid=1, ttl=None, waiter_id=None, model="MiniMax-M3",
                  operator_child_id=None, job_class=logical)
    values["self"] = types.SimpleNamespace(_try_acquire=native_first_target)
    result = eval(compile(patched_ordinary_call(), "<actual-patch-call>", "eval"), {}, values)
    assert result == (None, logical)


def test_optional_priority_is_forwarded_by_keyword():
    call = patched_ordinary_call().body
    assert len(call.args) == 10
    assert [item.arg for item in call.keywords] == ["job_class"]


def test_patch_preserves_native_parameter_before_new_optional_priority():
    text = PATCH.read_text()
    assert ('         native_binding: Optional[dict] = None,\n'
            '+        job_class: Optional[str] = None,\n') in text


def test_existing_native_keyword_call_keeps_its_binding():
    binding = {"test_only": "immutable-original-binding"}
    assert native_first_target("root", "synthetic", "acct", "remote-minimax", "host",
        1, None, None, "MiniMax-M3", None, native_binding=binding) == (binding, None)


def test_existing_native_positional_slot_is_preserved():
    binding = {"test_only": "original-positional-slot"}
    assert native_first_target("root", "synthetic", "acct", "remote-minimax", "host",
        1, None, None, "MiniMax-M3", None, binding) == (binding, None)
