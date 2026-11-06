"""Shared runtime custody: closed inputs and real Linux descriptor lifetime."""
from __future__ import annotations
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
import pytest

SOURCE = Path(__file__).resolve().parents[1] / "ops/native_fabric/quota_continuity/candidate/paid_initializer.py"


@pytest.fixture
def owner(monkeypatch):
    spec = importlib.util.spec_from_file_location("_shared_runtime_test_owner", SOURCE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    proxy = SimpleNamespace(**vars(os))
    proxy.supports_fd = set(os.supports_fd) | {os.execve}
    def forbidden_open(*args, **kwargs):
        raise AssertionError("runtime input refusal must precede filesystem acquisition")
    proxy.open = forbidden_open
    monkeypatch.setattr(module, "os", proxy)
    monkeypatch.setattr(sys, "platform", "linux")
    return module


def inputs():
    image = {"path": "/usr/bin/python3.12", "real_path": "/usr/bin/python3.12", "sha256": "a" * 64}
    startup = {"profile": "cpython-3.12-linux-root-prefix.v1",
               **{key: "/usr" for key in ("prefix", "exec_prefix", "base_prefix", "base_exec_prefix")}}
    return {"bootstrap_python": dict(image), "launch_python": dict(image), "startup": startup}


@pytest.mark.parametrize(("section", "field", "value"), [
    ("bootstrap_python", "unexpected", "x"),
    ("launch_python", "sha256", "A" * 64),
    ("launch_python", "sha256", None),
    ("bootstrap_python", "path", "usr/bin/python3.12"),
    ("launch_python", "path", "/usr/bin/not-python"),
    ("launch_python", "real_path", "/usr/../usr/bin/python3.12"),
    ("startup", "profile", "unqualified"),
    ("startup", "prefix", "/usr/"),
    ("startup", "base_prefix", True),
    ("startup", "unexpected", "x"),
])
def test_closed_runtime_inputs_refuse_before_acquisition(owner, section, field, value):
    data = inputs()
    data[section][field] = value
    with pytest.raises(owner.InitializerCommitmentRefused):
        with owner.held_runtime_custody(**data):
            pytest.fail("invalid runtime admitted")


def test_boundary_refusal_precedes_acquisition(owner):
    def boundary():
        raise owner.InitializerCommitmentRefused("source fence")
    with pytest.raises(owner.InitializerCommitmentRefused, match="source fence"):
        with owner.held_runtime_custody(**inputs(), boundary_check=boundary):
            pytest.fail("refused source admitted")


def test_no_site_policy_is_checked_and_never_backfilled(owner, monkeypatch):
    data = inputs()
    data["startup"]["profile"] = owner.NO_SITE_PROFILE
    calls = []
    def policy():
        calls.append("check")
        raise owner.InitializerCommitmentRefused("missing early policy")
    monkeypatch.setattr(owner, "require_no_site_policy", policy)
    with pytest.raises(owner.InitializerCommitmentRefused, match="missing early policy"):
        with owner.held_runtime_custody(**data):
            pytest.fail("late policy admitted")
    assert calls == ["check"]


# Actual descriptor/path checks run in the existing isolated system interpreter.
# Drift and ACL errors below are explicitly synthetic; no system file is changed.
CHILD = r'''
import sys
if sys.version_info[:2] != (3, 12) or not (sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode):
    raise SystemExit(78)
for name in ("site", "sitecustomize", "usercustomize"):
    if name in sys.modules: raise SystemExit(78)
    sys.modules[name] = None
import errno, hashlib, importlib.util, json, os, types
source, case = sys.argv[1:]
spec = importlib.util.spec_from_file_location("_shared_runtime_linux_owner", source)
owner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(owner)
proxy = types.SimpleNamespace(**vars(os))
owner.os = proxy
opened = set()
flag = {"drift": False, "boundary": False, "mutated": False}
def tracked_open(*args, **kwargs):
    fd = os.open(*args, **kwargs)
    opened.add(fd)
    return fd
proxy.open = tracked_open
if case == "partial_acl":
    def denied_acl(*args, **kwargs): raise OSError(errno.EACCES, "synthetic ACL refusal")
    proxy.getxattr = denied_acl
if case == "alias_drift":
    def changed_alias(name, *args, **kwargs):
        if flag["drift"] and name == "/usr/bin/python3": return "synthetic-replacement"
        return os.readlink(name, *args, **kwargs)
    proxy.readlink = changed_alias
if case == "node_entry":
    original_init = owner._IgnoredNoSiteNode.__init__
    original_check = owner._IgnoredNoSiteNode.check
    def initialized_node(self, directory):
        original_init(self, directory)
        if type(self) is owner._IgnoredNoSiteNode: self._test_enter_refusal = True
    def entry_refusal(self):
        if getattr(self, "_test_enter_refusal", False):
            raise owner.InitializerCommitmentRefused("synthetic node entry refusal")
        original_check(self)
    owner._IgnoredNoSiteNode.__init__ = initialized_node
    owner._IgnoredNoSiteNode.check = entry_refusal
def forbidden_private(*args, **kwargs): raise AssertionError("private initializer IO")
owner._capture_environment = forbidden_private
actual = os.path.realpath("/proc/self/exe")
with open(actual, "rb") as stream: digest = hashlib.sha256(stream.read()).hexdigest()
logical = "/usr/bin/python3" if case == "alias_drift" else "/usr/bin/python3.12"
image = {"path": logical, "real_path": actual, "sha256": digest}
data = {"bootstrap_python": dict(image), "launch_python": dict(image),
        "startup": {"profile": owner.NO_SITE_PROFILE,
                    **{key: getattr(sys, key) for key in ("prefix", "exec_prefix", "base_prefix", "base_exec_prefix")}}}
def boundary():
    if flag["boundary"]: raise owner.InitializerCommitmentRefused("synthetic final boundary")
    if case == "detached" and not flag["mutated"]:
        flag["mutated"] = True
        data["bootstrap_python"]["path"] = "/absent/python3.12"
        data["launch_python"]["sha256"] = "0" * 64
        data["startup"]["prefix"] = "/absent"
def enter_and_return():
    with owner.held_runtime_custody(**data, boundary_check=boundary) as runtime:
        assert os.fstat(runtime.launch_fd).st_size > 0
        runtime.check()
        runtime.recheck_image_aliases()
        if case == "alias_drift":
            flag["drift"] = True
            runtime.check()
        if case == "final_boundary": flag["boundary"] = True
        return runtime.launch_fd
refused = False
try:
    final_fd = enter_and_return()
except owner.InitializerCommitmentRefused:
    refused = True
assert refused == (case in ("partial_acl", "alias_drift", "final_boundary", "node_entry")), case
assert opened
for fd in opened:
    try: os.fstat(fd)
    except OSError as error: assert error.errno == errno.EBADF
    else: raise AssertionError("held descriptor leaked")
print(json.dumps({"case": case, "refused": refused, "all_descriptors_closed": True, "opened": len(opened)}))
'''


@pytest.mark.skipif(sys.platform != "linux" or not Path("/usr/bin/python3.12").is_file(),
                    reason="requires the Linux CPython 3.12 system runtime")
@pytest.mark.parametrize("case", ["early_return", "detached", "partial_acl", "alias_drift", "final_boundary", "node_entry"])
def test_real_runtime_custody_and_failure_cleanup(case):
    result = subprocess.run(["/usr/bin/python3.12", "-I", "-S", "-B", "-c", CHILD, str(SOURCE), case],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=30,
                            env={key: value for key, value in os.environ.items()
                                 if key not in ("BASH_ENV", "ENV", "PYTHONHOME", "PYTHONEXECUTABLE", "__PYVENV_LAUNCHER__")
                                 and not key.startswith(("BASH_FUNC_", "LD_"))})
    assert result.returncode == 0, result.stderr
    record = json.loads(result.stdout)
    assert record["case"] == case and record["all_descriptors_closed"] is True
