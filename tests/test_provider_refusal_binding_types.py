"""Exact type boundaries for optional local-refusal provenance metadata."""
from __future__ import annotations
import pytest
from test_provider_start_run_binding import RunBindingHarness, FIXED_REFUSAL, bound_id

@pytest.mark.parametrize("operation", ["bind", "read"])
def test_exception_dictionary_subclass_is_not_executed(monkeypatch, tmp_path, operation):
    h = RunBindingHarness(monkeypatch, tmp_path)
    error = h.route("initial-sdk")
    assert bound_id(h.cb, error) == h.created[0]
    accesses = []
    class ForeignDict(dict):
        def __contains__(self, key):
            accesses.append("contains")
            raise AssertionError("Custom mapping replaced pending refusal")
        def __getitem__(self, key):
            accesses.append("getitem")
            raise AssertionError("Custom mapping supplied identity")
        def __setitem__(self, key, value):
            accesses.append("setitem")
            raise AssertionError("Custom mapping intercepted binding")
        def get(self, *args):
            accesses.append("get")
            raise AssertionError("Custom mapping fabricated provenance")
    error.__dict__ = ForeignDict(error.__dict__)
    if operation == "bind":
        h.cb._bind_provider_refusal_run(error, h.created[0], "autonomous", "deep")
    assert bound_id(h.cb, error) is None
    assert accesses == []

@pytest.mark.parametrize("value,valid", [
    ("source-1", True), ("A"*160, True), ("source_1.2:+-3", True),
    ("", False), ("A"*161, False), ("../foreign", False),
    ("source\n", False), (True, False), ({"run_id":"source"}, False),
])
def test_run_id_uses_exact_bounded_ascii_consumer_grammar(monkeypatch, tmp_path, value, valid):
    h = RunBindingHarness(monkeypatch, tmp_path)
    error = h.cb.ProviderStartRefused(FIXED_REFUSAL)
    h.cb._bind_provider_refusal_run(error, value, "autonomous", "deep")
    assert bound_id(h.cb, error) == (value if valid else None)
    assert error.args == (FIXED_REFUSAL,)

@pytest.mark.parametrize("field", ["run_id", "book", "role"])
def test_malformed_typed_fields_never_supply_custom_equality(monkeypatch, tmp_path, field):
    h = RunBindingHarness(monkeypatch, tmp_path)
    accesses=[]
    class Foreign:
        def __eq__(self, other):
            accesses.append("eq")
            raise AssertionError("Malformed typed field compared")
        def __str__(self):
            accesses.append("str")
            raise AssertionError("Malformed typed field coerced")
    values={"run_id":"source-1","book":"autonomous","role":"deep"}
    values[field]=Foreign()
    error=h.cb.ProviderStartRefused(FIXED_REFUSAL)
    error.__dict__["_provider_refusal_run"]=h.cb._ProviderRefusalRunBinding(**values)
    assert bound_id(h.cb,error) is None
    h.cb._bind_provider_refusal_run(error,"source-1","autonomous","deep")
    assert bound_id(h.cb,error) is None
    assert accesses==[]

def test_string_subclass_does_not_become_identity(monkeypatch, tmp_path):
    h=RunBindingHarness(monkeypatch,tmp_path)
    class ForeignString(str):
        pass
    for field in ("run_id","book","role"):
        values={"run_id":"source-1","book":"autonomous","role":"deep"}
        values[field]=ForeignString(values[field])
        error=h.cb.ProviderStartRefused(FIXED_REFUSAL)
        h.cb._bind_provider_refusal_run(error,**values)
        assert bound_id(h.cb,error) is None
