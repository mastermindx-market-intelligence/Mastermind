"""Packaging regressions: exact build provenance, inert preflight and immutable import."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess

import pytest


def helper():
    assert importlib.util.find_spec("ops.executive_os.os_release_assets") is not None, "asset packaging owner is missing"
    from ops.executive_os import os_release_assets
    return os_release_assets


def git(repo, *args):
    return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()


@pytest.fixture
def source(tmp_path):
    repo = tmp_path / "source"
    app = repo / "app/mastermind_os"
    app.mkdir(parents=True)
    (app / "package.json").write_text('{"scripts":{"build":"tsc -b && vite build"}}')
    (app / "package-lock.json").write_text('{"lockfileVersion":3}')
    (app / "source.txt").write_text("committed app bytes")
    root = Path(__file__).resolve().parents[1]
    for name in helper().LAUNCH_INPUTS:
        target = repo / name
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((root / name).read_bytes())
    git(repo, "init", "-q")
    git(repo, "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "add", ".")
    git(repo, "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-qm", "source")
    sha = git(repo, "rev-parse", "HEAD")
    git(repo, "update-ref", "refs/remotes/origin/master", sha)
    return repo, sha, git(repo, "rev-parse", "HEAD^{tree}")


NOTICE_BYTES = {
    "third-party/deepseek-client-dependency-NOTICES.txt": b"Dependency copyright notices\n",
    "third-party/deepseek-harness-LICENSE.txt": b"Harness license and copyright\n",
}


def built_dist(app, *, noir_notices=False):
    dist = app / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text('<script src="/os/assets/index-a.js"></script><link href="/os/assets/index-a.css">')
    (dist / "assets/index-a.js").write_text("committed app bytes")
    (dist / "assets/index-a.css").write_text("body{}")
    if noir_notices:
        extra = {
            "assets/atelier-office-a.jpg": b"office image",
            "assets/Manrope-Variable-a.ttf": b"Manrope font",
            "assets/Inter-Variable-a.woff2": b"Inter font",
            "licenses/fonts/Inter-OFL.txt": b"Inter license",
            "licenses/fonts/Manrope-OFL.txt": b"Manrope license",
            "licenses/fonts/Manrope-FONTLOG.txt": b"Manrope font log",
            **NOTICE_BYTES,
        }
        for name, data in extra.items():
            path = dist / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
    return {"operator_uid": 501, "tools": {"/test/node": "a" * 64, "/test/npm-cli.js": "b" * 64}}


@pytest.fixture
def bundle(tmp_path, source, monkeypatch, request):
    mod = helper()
    # Production requires root-sealed paths and a root preparer; ordinary unit
    # temporary directories only replace those OS ownership checks. Archive,
    # source policy, receipts, byte validation and import remain the real code.
    monkeypatch.setattr(mod, "require_sealed_path", lambda *a, **k: None)
    monkeypatch.setattr(mod, "_require_root", lambda: None)
    monkeypatch.setattr(mod, "_build", lambda app, **kwargs: built_dist(
        app, noir_notices=getattr(request, "param", False)))
    repo, sha, tree = source
    out = tmp_path / "bundle"
    mod.prepare(source_repo=repo, expected_sha=sha, web_client_id="test-public-client-id", output=out,
                build_user="test", node=Path("/test/node"), npm_cli=Path("/test/npm-cli.js"))
    return mod, out, sha, tree


def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def launch_manifest(profile="research_only", **extra):
    manifest = {"v": 1, "workstream": "WS:LAUNCH-FIXTURE", "priority": 5,
                "projects": [{"ref": "executive-infrastructure", "label": "Fixture department"}],
                "profiles": [{"ref": profile, "label": "Fixture profile"}]}
    if profile == "bounded_code_change":
        manifest.update({"allowedWritePaths": ["src/public-config.ts"], "validation": {"git_diff_check": True}})
    manifest.update(extra)
    return manifest


def damaged_manifest(damage):
    valid = launch_manifest()
    if damage == "duplicate_key":
        text = canonical(valid).decode()
        return (text[:-2] + ',"v":1}\n').encode()
    if damage == "unknown_field": return canonical({**valid, "token": "unaccepted"})
    if damage == "bool_priority": return canonical({**valid, "priority": True})
    if damage == "float_priority": return canonical({**valid, "priority": 1.5})
    if damage == "string_v": return canonical({**valid, "v": "1"})
    if damage == "string_attempt_limit": return canonical({**valid, "attemptLimit": "1"})
    if damage == "attempt_limit_four": return canonical({**valid, "attemptLimit": 4})
    if damage == "int_git_check":
        return canonical({**valid, "profiles": [{"ref": "bounded_code_change", "label": "Bounded"}],
                          "allowedWritePaths": ["src/public-config.ts"], "validation": {"git_diff_check": 1}})
    if damage == "noncanonical": return json.dumps(valid).encode()
    if damage == "raw_utf8_unicode":
        return json.dumps({**valid, "projects": [{"ref": "executive-infrastructure", "label": "Département"}]},
                          ensure_ascii=False).encode("utf-8")
    if damage == "surrogate":
        return canonical({**valid, "projects": [{"ref": "executive-infrastructure", "label": "bad \ud800 surrogate"}]})
    if damage == "oversized":
        return canonical({**valid, "allowedWritePaths": [f"src/{'a' * 240}" for _ in range(16)]})
    if damage == "research_with_paths": return canonical({**valid, "allowedWritePaths": ["src/public-config.ts"]})
    if damage == "research_with_validation": return canonical({**valid, "validation": {"git_diff_check": True}})
    if damage == "bounded_without_paths":
        return canonical({**valid, "profiles": [{"ref": "bounded_code_change", "label": "Bounded"}]})
    if damage == "bounded_empty_validation":
        return canonical({**valid, "profiles": [{"ref": "bounded_code_change", "label": "Bounded"}],
                          "allowedWritePaths": ["src/public-config.ts"], "validation": {}})
    if damage == "duplicate_refs":
        return canonical({**valid, "projects": [{"ref": "executive-infrastructure", "label": "A"},
                                                {"ref": "executive-infrastructure", "label": "B"}]})
    bounded = {**valid, "profiles": [{"ref": "bounded_code_change", "label": "Bounded"}],
               "validation": {"git_diff_check": True}}
    if damage == "traversal_path": return canonical({**bounded, "allowedWritePaths": ["../outside"]})
    if damage == "absolute_path": return canonical({**bounded, "allowedWritePaths": ["/tmp/outside"]})
    if damage == "backslash_path": return canonical({**bounded, "allowedWritePaths": ["src\\file"]})
    if damage == "git_segment": return canonical({**bounded, "allowedWritePaths": [".git/config"]})
    if damage == "empty_projects": return canonical({**valid, "projects": []})
    if damage == "bad_ref": return canonical({**valid, "projects": [{"ref": "Executive", "label": "No"}]})
    if damage == "bad_workstream": return canonical({**valid, "workstream": "JOB-013"})
    if damage == "control_char_label":
        return canonical({**valid, "profiles": [{"ref": "research_only", "label": "bad\nlabel"}]})
    raise AssertionError(damage)


@pytest.fixture
def launch_bundle(tmp_path, source, monkeypatch):
    mod = helper()
    monkeypatch.setattr(mod, "require_sealed_path", lambda *a, **k: None)
    monkeypatch.setattr(mod, "_require_root", lambda: None)
    calls = []

    def build(app, **kwargs):
        calls.append(kwargs)
        return built_dist(app)
    monkeypatch.setattr(mod, "_build", build)
    repo, sha, tree = source
    out = tmp_path / "launch-bundle"
    mod.prepare(source_repo=repo, expected_sha=sha, web_client_id="test-public-client-id", output=out,
                build_user="test", node=Path("/test/node"), npm_cli=Path("/test/npm-cli.js"),
                executive_resource=mod.OS_EXECUTIVE_RESOURCE, launch_manifest=canonical(launch_manifest()))
    return mod, out, sha, tree, calls


def rewrite_receipt(out, mod, mutate):
    path = out / "build-receipt.json"
    receipt = json.loads(path.read_bytes())
    mutate(receipt)
    path.chmod(0o644)
    path.write_bytes(mod._canonical(receipt))
    path.chmod(0o444)
    return receipt


def test_prepared_bytes_import_before_seal_and_same_release_is_verify_only(bundle, tmp_path):
    mod, out, sha, tree = bundle
    receipt = json.loads((out / "build-receipt.json").read_bytes())
    assert receipt["source_sha"] == sha
    assert receipt["source_tree"] == tree
    assert receipt["recipe"] == ["npm ci --ignore-scripts", "npm run build"]
    checked = mod.qualify(out, expected_sha=sha, tree_sha=tree, source_repo=out.parent / "source")
    stage = tmp_path / "stage"
    stage.mkdir()
    import os
    previous = os.umask(0o077)
    try:
        mod.import_assets(checked, stage)
    finally:
        os.umask(previous)
    assert (stage / "app/mastermind_os/dist/assets/index-a.js").read_text() == "committed app bytes"
    assert (stage / "app/mastermind_os/dist/assets/index-a.js").stat().st_mode & 0o777 == 0o444
    assert (stage / "app/mastermind_os/dist/assets").stat().st_mode & 0o777 == 0o755
    (stage / ".executive-release-manifest.json").write_text("existing immutable seal")
    before = {str(p.relative_to(stage)): p.read_bytes() for p in stage.rglob("*") if p.is_file()}
    mod.compare_existing(checked, stage)
    with pytest.raises(ValueError):
        mod.import_assets(checked, stage)
    assert before == {str(p.relative_to(stage)): p.read_bytes() for p in stage.rglob("*") if p.is_file()}


@pytest.mark.parametrize("bundle", [True], indirect=True)
def test_noir_notices_survive_capture_manifest_qualification_and_import(bundle, tmp_path):
    mod, out, sha, tree = bundle
    manifest = json.loads((out / mod.DIST / "asset-manifest.json").read_bytes())
    rows = {item["path"]: item for item in manifest["files"]}
    assert len(rows) == 11
    checked = mod.qualify(out, expected_sha=sha, tree_sha=tree, source_repo=out.parent / "source")
    stage = tmp_path / "notice-stage"
    stage.mkdir()
    mod.import_assets(checked, stage)
    for name, data in NOTICE_BYTES.items():
        assert rows[name] == {"path": name, "byte_count": len(data),
                              "sha256": hashlib.sha256(data).hexdigest(),
                              "mime": "text/plain; charset=utf-8"}
        assert checked.files[name] == data
        assert (stage / mod.DIST / name).read_bytes() == data
    mod.compare_existing(checked, stage)


@pytest.mark.parametrize("bundle", [True], indirect=True)
def test_noir_notices_load_and_serve_with_optional_mcp_sdk(bundle, monkeypatch):
    pytest.importorskip("mcp", reason="real HTTP loading belongs to the optional MCP network test environment")
    _, out, _, _ = bundle
    from ops.executive_os import executive_mcp_entry as entry
    # Only sealed host ownership is replaced for the temporary fixture. The
    # manifest, hashes, file loading, route admission and response bytes are real.
    monkeypatch.setattr(entry, "require_sealed_path", lambda *a, **k: None)
    app = entry.load_os_app(out)
    import asyncio
    async def request(path):
        messages = []
        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}
        async def send(message):
            messages.append(message)
        await app({"type": "http", "method": "GET", "path": path,
                   "raw_path": path.encode("ascii"), "query_string": b""}, receive, send)
        return messages
    for name, data in NOTICE_BYTES.items():
        messages = asyncio.run(request("/os/" + name))
        assert messages[0]["status"] == 200
        assert dict(messages[0]["headers"])[b"content-type"] == b"text/plain; charset=utf-8"
        assert messages[-1]["body"] == data
    assert asyncio.run(request("/os/third-party/unknown.txt"))[0]["status"] == 404


@pytest.mark.parametrize("bundle", [True], indirect=True)
@pytest.mark.parametrize("damage", ["missing", "renamed", "extra", "extra_directory"])
def test_noir_notice_capture_keeps_file_and_directory_sets_closed(bundle, damage):
    mod, out, _, _ = bundle
    dist = out / mod.DIST
    notice = dist / "third-party/deepseek-harness-LICENSE.txt"
    if damage == "missing":
        notice.unlink()
    elif damage == "renamed":
        notice.rename(notice.with_name("other-LICENSE.txt"))
    elif damage == "extra":
        (dist / "third-party/extra.txt").write_text("unapproved")
    else:
        (dist / "third-party/extra").mkdir()
    with pytest.raises(ValueError):
        mod._capture_dist(out, sealed=False)


@pytest.mark.parametrize("damage", ["wrong_sha", "wrong_tree", "asset_changed", "manifest_changed", "missing_manifest", "extra", "symlink", "hardlink", "fifo", "traversal"])
def test_bad_artifact_refused_without_destination_effect(bundle, tmp_path, damage):
    import os
    mod, out, sha, tree = bundle
    dist = out / "app/mastermind_os/dist"
    js = dist / "assets/index-a.js"
    js.chmod(0o644)
    (dist / "asset-manifest.json").chmod(0o644)
    if damage == "wrong_sha": sha = "a" * 40
    elif damage == "wrong_tree": tree = "b" * 40
    elif damage == "asset_changed": js.write_text("different")
    elif damage == "manifest_changed": (dist / "asset-manifest.json").write_text("{}")
    elif damage == "missing_manifest": (dist / "asset-manifest.json").unlink()
    elif damage == "extra": (dist / "extra.js").write_text("bad")
    elif damage == "symlink": js.unlink(); js.symlink_to(tmp_path / "outside")
    elif damage == "hardlink": os.link(js, tmp_path / "second-link")
    elif damage == "fifo": js.unlink(); os.mkfifo(js)
    elif damage == "traversal":
        manifest = json.loads((dist / "asset-manifest.json").read_bytes())
        manifest["files"][0]["path"] = "../outside"
        (dist / "asset-manifest.json").write_text(json.dumps(manifest))
    with pytest.raises((ValueError, OSError)):
        mod.qualify(out, expected_sha=sha, tree_sha=tree, source_repo=out.parent / "source")
    assert not (tmp_path / "stage").exists()


def test_same_sha_missing_or_different_assets_refuses_without_grafting(bundle, tmp_path):
    mod, out, sha, tree = bundle
    checked = mod.qualify(out, expected_sha=sha, tree_sha=tree, source_repo=out.parent / "source")
    stage = tmp_path / "sealed"
    stage.mkdir()
    (stage / ".executive-release-manifest.json").write_text("seal")
    with pytest.raises((ValueError, OSError)): mod.compare_existing(checked, stage)
    assert list(stage.iterdir()) == [stage / ".executive-release-manifest.json"]


def test_archive_uses_committed_bytes_and_ignores_checkout_generated_inputs(source, tmp_path, monkeypatch):
    mod = helper()
    monkeypatch.setattr(mod, "require_sealed_path", lambda *a, **k: None)
    monkeypatch.setattr(mod, "_require_root", lambda: None)
    repo, sha, tree = source
    # An ignored dotenv must neither become the build's inputs nor override the
    # closed real public configuration supplied to the builder.
    git(repo, "config", "core.excludesfile", str(tmp_path / "ignore"))
    (tmp_path / "ignore").write_text(".env\n")
    (repo / "app/mastermind_os/.env").write_text("VITE_MM_WEB_CLIENT_ID=foreign-client")
    def build(app, **kwargs):
        assert not (app / ".env").exists()
        assert kwargs["web_client_id"] == "test-public-client-id"
        assert (app / "source.txt").read_text() == "committed app bytes"
        return built_dist(app)
    monkeypatch.setattr(mod, "_build", build)
    out = tmp_path / "bundle"
    mod.prepare(source_repo=repo, expected_sha=sha, web_client_id="test-public-client-id", output=out,
                build_user="test", node=Path("/test/node"), npm_cli=Path("/test/npm-cli.js"))
    assert mod.qualify(out, expected_sha=sha, tree_sha=tree, source_repo=repo).digest


def test_changed_provenance_cannot_pass_the_prior_preflight_digest(bundle):
    mod, out, sha, tree = bundle
    first = mod.qualify(out, expected_sha=sha, tree_sha=tree, source_repo=out.parent / "source")
    p = out / "build-receipt.json"
    receipt = json.loads(p.read_bytes())
    receipt["web_client_id"] = "another-public-client-id"
    p.chmod(0o644)
    p.write_text(json.dumps(receipt))
    with pytest.raises(ValueError):
        mod.qualify(out, expected_sha=sha, tree_sha=tree, source_repo=out.parent / "source", expected_digest=first.digest)


@pytest.mark.parametrize("target", ["receipt", "assets_directory", "bundle_ancestor"])
@pytest.mark.parametrize("query_error", [False, True])
def test_write_acl_or_query_error_refuses_origin_before_hashes_can_be_admitted(bundle, monkeypatch, target, query_error):
    from control_plane.fs_security import FilesystemSecurityError
    mod, out, sha, tree = bundle
    bad = {"receipt": out / "build-receipt.json", "assets_directory": out / "app/mastermind_os/dist/assets",
           "bundle_ancestor": out.parent}[target]
    def acl(path, *, expected_identity=None, descriptor=None):
        assert expected_identity is not None
        if Path(path) == bad:
            if query_error:
                raise FilesystemSecurityError("disposable ACL query failure")
            return True
        return False
    monkeypatch.setattr(mod, "has_macos_acl", acl, raising=False)
    with pytest.raises(ValueError):
        mod.qualify(out, expected_sha=sha, tree_sha=tree, source_repo=out.parent / "source")


def test_preparer_and_publisher_reject_acl_on_output_parent(bundle, monkeypatch):
    mod, out, sha, tree = bundle
    monkeypatch.setattr(mod, "has_macos_acl", lambda path, **kw: Path(path) == out.parent, raising=False)
    with pytest.raises(ValueError):
        mod.prepare(source_repo=out.parent / "source", expected_sha=sha, web_client_id="test-public-client-id",
                    output=out.parent / "second", build_user="test", node=Path("/test/node"), npm_cli=Path("/test/npm-cli.js"))
    assert not (out.parent / "second").exists()
    with pytest.raises(ValueError):
        mod._publish_file(out.parent / "published", b"cannot publish under write ACL")
    assert not (out.parent / "published").exists()


def test_sealed_directory_allows_unrelated_child_creation_during_acl_read(tmp_path, monkeypatch):
    mod = helper()
    monkeypatch.setattr(mod, "require_sealed_path", lambda *a, **k: None)
    real_acl = mod.has_macos_acl
    observed = []

    def acl(path, **kwargs):
        result = real_acl(path, **kwargs)
        if Path(path) == tmp_path and not observed:
            before = path.lstat()
            (path / "unrelated-sibling").write_text("another owner publication")
            after = path.lstat()
            assert (before.st_dev, before.st_ino, before.st_uid, before.st_gid, before.st_mode) == (
                after.st_dev, after.st_ino, after.st_uid, after.st_gid, after.st_mode)
            assert before.st_ctime_ns != after.st_ctime_ns
            observed.append(True)
        return result

    monkeypatch.setattr(mod, "has_macos_acl", acl)
    mod._sealed_path(tmp_path, directory=True)
    assert observed == [True]


@pytest.mark.skipif(__import__("sys").platform != "darwin", reason="actual macOS ACL observer")
def test_directory_acl_added_during_observation_is_still_refused(tmp_path, monkeypatch):
    mod = helper()
    monkeypatch.setattr(mod, "require_sealed_path", lambda *a, **k: None)
    real_acl = mod.has_macos_acl
    inserted = []

    def acl(path, **kwargs):
        result = real_acl(path, **kwargs)
        if Path(path) == tmp_path and not inserted:
            subprocess.run(["/bin/chmod", "+a", "everyone allow write", str(path)], check=True)
            inserted.append(True)
        return result

    monkeypatch.setattr(mod, "has_macos_acl", acl)
    try:
        with pytest.raises(ValueError, match="ACL"):
            mod._sealed_path(tmp_path, directory=True)
        assert inserted == [True]
    finally:
        subprocess.run(["/bin/chmod", "-N", str(tmp_path)], check=True)


@pytest.mark.skipif(__import__("sys").platform != "darwin", reason="actual macOS ACL observer")
@pytest.mark.parametrize("target", ["build-receipt.json", "app/mastermind_os/dist/assets"])
def test_actual_darwin_write_acl_refuses_receipt_and_directory_without_posix_mode_change(bundle, target):
    mod, out, sha, tree = bundle
    path = out / target
    mode = path.stat().st_mode & 0o777
    subprocess.run(["/bin/chmod", "+a", "everyone allow write", str(path)], check=True)
    try:
        assert path.stat().st_mode & 0o777 == mode
        with pytest.raises(ValueError, match="ACL"):
            mod.qualify(out, expected_sha=sha, tree_sha=tree, source_repo=out.parent / "source")
    finally:
        subprocess.run(["/bin/chmod", "-N", str(path)], check=True)


def test_nonroot_operator_build_accepts_existing_user_owned_node_without_root_provisioning(tmp_path, monkeypatch, source):
    import os
    import pwd
    mod = helper()
    app = tmp_path / "work/app/mastermind_os"
    app.mkdir(parents=True)
    npm = tmp_path / "npm-cli.js"
    npm.write_text("// disposable npm entrypoint")
    npm.chmod(0o644)
    # subprocess is mocked. Use owned, single-link tools with explicit modes;
    # the CI runner's Python install is not a qualified Node fixture.
    node = tmp_path / "node"
    node.write_text("#!/bin/sh\nexit 0\n")
    node.chmod(0o755)
    repo, sha, _ = source
    reserved = mod._reserved_service_uids(repo, sha)
    calls = []
    monkeypatch.setattr(mod.os, "chown", lambda *a, **k: None)
    monkeypatch.setattr(mod.subprocess, "run", lambda args, **kwargs: calls.append((args, kwargs)))
    user = pwd.getpwuid(os.getuid())
    mod._build(app, build_user=user.pw_name, node=node, npm_cli=npm,
               web_client_id="test-public-client-id", reserved_service_uids=reserved)
    assert len(calls) == 2
    for _, kwargs in calls:
        assert kwargs["user"] == user.pw_uid != 0
        assert kwargs["group"] == user.pw_gid
        assert kwargs["extra_groups"] == []
        assert kwargs["env"]["VITE_MM_WEB_CLIENT_ID"] == "test-public-client-id"
        assert "NODE_OPTIONS" not in kwargs["env"]
        user_config = Path(kwargs["env"]["npm_config_userconfig"])
        global_config = Path(kwargs["env"]["npm_config_globalconfig"])
        assert user_config != global_config
        assert user_config.read_bytes() == global_config.read_bytes() == b""
        assert user_config.parent == global_config.parent == app.parents[1]


@pytest.mark.parametrize("uid", [0, *range(450, 459)])
def test_build_refuses_root_and_entire_source_service_reservation_before_effects(source, tmp_path, monkeypatch, uid):
    from types import SimpleNamespace
    mod = helper()
    repo, sha, _ = source
    reserved = mod._reserved_service_uids(repo, sha)
    assert list(reserved) == list(range(450, 459))
    monkeypatch.setattr(mod.pwd, "getpwnam", lambda _: SimpleNamespace(pw_uid=uid))
    monkeypatch.setattr(mod.subprocess, "run", lambda *a, **k: pytest.fail("build was invoked"))
    monkeypatch.setattr(mod.os, "chown", lambda *a, **k: pytest.fail("ownership was changed"))
    with pytest.raises(ValueError, match="non-service operator"):
        mod._build(tmp_path, build_user="fixture", node=tmp_path / "absent-node",
                   npm_cli=tmp_path / "absent-npm", web_client_id="test-public-client-id",
                   reserved_service_uids=reserved)


@pytest.mark.parametrize("uid", [0, *range(450, 459)])
def test_qualification_refuses_attestation_by_root_or_reserved_service(bundle, uid):
    mod, out, sha, tree = bundle
    path = out / mod.RECEIPT
    receipt = json.loads(path.read_bytes())
    receipt["builder"]["operator_uid"] = uid
    path.chmod(0o644)
    path.write_bytes(mod._canonical(receipt))
    path.chmod(0o444)
    with pytest.raises(ValueError, match="trusted non-root build attestation"):
        mod.qualify(out, expected_sha=sha, tree_sha=tree, source_repo=out.parent / "source")


@pytest.mark.parametrize("damage", ["group_write", "other_write", "hardlink", "not_executable"])
def test_build_rejects_unqualified_node_before_subprocess(source, tmp_path, monkeypatch, damage):
    import os
    import pwd
    mod = helper()
    repo, sha, _ = source
    reserved = mod._reserved_service_uids(repo, sha)
    node, npm = tmp_path / "node", tmp_path / "npm-cli.js"
    node.write_text("#!/bin/sh\nexit 0\n")
    node.chmod(0o755)
    npm.write_text("// fixture")
    npm.chmod(0o644)
    if damage == "group_write": node.chmod(0o775)
    elif damage == "other_write": node.chmod(0o757)
    elif damage == "hardlink": os.link(node, tmp_path / "node-link")
    else: node.chmod(0o644)
    monkeypatch.setattr(mod.subprocess, "run", lambda *a, **k: pytest.fail("build was invoked"))
    with pytest.raises(ValueError, match="custody refused|Node executable refused"):
        mod._build(tmp_path, build_user=pwd.getpwuid(os.getuid()).pw_name, node=node,
                   npm_cli=npm, web_client_id="test-public-client-id", reserved_service_uids=reserved)


def test_import_uses_captured_bytes_even_if_input_changes(bundle, tmp_path):
    mod, out, sha, tree = bundle
    checked = mod.qualify(out, expected_sha=sha, tree_sha=tree, source_repo=out.parent / "source")
    p = out / "app/mastermind_os/dist/assets/index-a.js"
    p.chmod(0o644)
    p.write_text("replacement after capture")
    stage = tmp_path / "stage"
    stage.mkdir()
    mod.import_assets(checked, stage)
    assert (stage / "app/mastermind_os/dist/assets/index-a.js").read_text() == "committed app bytes"


def test_import_fault_preserves_unsealed_staging_and_never_publishes_seal(bundle, tmp_path, monkeypatch):
    mod, out, sha, tree = bundle
    checked = mod.qualify(out, expected_sha=sha, tree_sha=tree, source_repo=out.parent / "source")
    stage = tmp_path / "stage"
    stage.mkdir()
    original = mod._publish_file
    count = 0
    def fail(path, data):
        nonlocal count
        count += 1
        if count == 2:
            raise OSError("disposable write fault")
        return original(path, data)
    monkeypatch.setattr(mod, "_publish_file", fail)
    with pytest.raises(OSError): mod.import_assets(checked, stage)
    assert len([p for p in stage.rglob("*") if p.is_file()]) == 1
    assert not (stage / ".executive-release-manifest.json").exists()


@pytest.mark.parametrize("choice", ["absent", "valid", "wrong_source", "sealed_without_assets", "sealed_identical", "sealed_different", "receipt_acl", "directory_acl", "acl_query_error"])
def test_installer_optional_preflight_refuses_before_service_stop(bundle, tmp_path, choice):
    import shlex
    import sys
    mod, out, sha, tree = bundle
    release = tmp_path / "release"
    if choice.startswith("sealed_"):
        release.mkdir()
        if choice != "sealed_without_assets":
            checked = mod.qualify(out, expected_sha=sha, tree_sha=tree, source_repo=out.parent / "source")
            mod.import_assets(checked, release)
        (release / ".executive-release-manifest.json").write_text("seal")
        if choice == "sealed_different":
            p = release / "app/mastermind_os/dist/assets/index-a.js"
            p.chmod(0o644)
            p.write_text("different")
    root = Path(__file__).resolve().parents[1]
    shim = tmp_path / "owner-shim.py"
    acl_override = ""
    if choice in ("receipt_acl", "directory_acl", "acl_query_error"):
        bad = out / "build-receipt.json" if choice != "directory_acl" else out.parent
        acl_override = (
            "from pathlib import Path\nfrom control_plane.fs_security import FilesystemSecurityError\n"
            "def acl(path, **kwargs):\n"
            f"    if Path(path) == Path({str(bad)!r}):\n"
            + ("        raise FilesystemSecurityError('disposable query failure')\n" if choice == "acl_query_error" else "        return True\n")
            + "    return False\nm.has_macos_acl = acl\n"
        )
    shim.write_text("import sys\n" + f"sys.path.insert(0, {str(root)!r})\n" +
        "from ops.executive_os import os_release_assets as m\n"
        "m._require_root = lambda: None\nm.require_sealed_path = lambda *a, **k: None\n"
        + acl_override +
        "sys.argv = sys.argv[4:]\n"
        "try: m.main()\nexcept (ValueError, OSError): sys.exit(65)\n")
    wrapper = tmp_path / "python-owner"
    wrapper.write_text(f"#!/bin/sh\nexec {shlex.quote(sys.executable)} {shlex.quote(str(shim))} \"$@\"\n")
    wrapper.chmod(0o755)
    source_text = (root / "ops/executive_os/install.sh").read_text()
    start = source_text.index("# Optional build artifact is qualified before maintenance")
    end = source_text.index('CONTROL_CONFIG="$SYSTEM_ROOT/config/control.json"', start)
    block = source_text[start:end]
    effects = tmp_path / "stopped"
    variables = {"PYTHON_BINARY": str(wrapper), "SCRIPT_DIR": str(root / "ops/executive_os"),
                 "SOURCE_REPO": str(out.parent / "source"), "EXPECTED_SHA": "a" * 40 if choice == "wrong_source" else sha,
                 "TREE_SHA": tree, "OS_WEB_ASSETS": "" if choice == "absent" else str(out),
                 "RELEASE_ROOT": str(release)}
    script = "set -euo pipefail\n" + "\n".join(f"{k}={shlex.quote(v)}" for k, v in variables.items())
    script += "\n" + block + f"\nprintf stopped > {shlex.quote(str(effects))}\n"
    result = subprocess.run(["/bin/bash", "-c", script], capture_output=True, text=True)
    permitted = choice in ("absent", "valid", "sealed_identical")
    assert result.returncode == (0 if permitted else 65), result.stderr
    assert effects.exists() is permitted


# --- Explicit public Launch build inputs: closed v2 receipts, default parity. ---

def test_disabled_prepare_keeps_the_historical_v1_receipt_and_input_set(bundle):
    mod, out, sha, tree = bundle
    receipt = json.loads((out / "build-receipt.json").read_bytes())
    assert receipt["schema"] == mod.SCHEMA and receipt["mode"] == "web"
    assert set(receipt) == {"schema", "source_sha", "source_tree", "source_inputs", "mode", "recipe",
                            "builder", "web_client_id", "asset_manifest_sha256"}
    assert set(receipt["source_inputs"]) == set(mod.INPUTS)
    assert mod.LAUNCH_INPUTS == (*mod.INPUTS, "app/mastermind_os/src/launch-config.ts")
    assert mod._receipt_launch_inputs(receipt) == (None, None)
    checked = mod.qualify(out, expected_sha=sha, tree_sha=tree, source_repo=out.parent / "source")
    assert (out / mod.RECEIPT).read_bytes() == checked.receipt


def test_disabled_prepare_ignores_ambient_vite_environment(tmp_path, source, monkeypatch):
    mod = helper()
    monkeypatch.setattr(mod, "require_sealed_path", lambda *a, **k: None)
    monkeypatch.setattr(mod, "_require_root", lambda: None)
    calls = []
    monkeypatch.setattr(mod, "_build", lambda app, **kwargs: calls.append(kwargs) or built_dist(app))
    monkeypatch.setenv("VITE_MM_LAUNCH_CONFIG", "foreign-config")
    monkeypatch.setenv("VITE_MM_EXECUTIVE_RESOURCE", mod.OS_EXECUTIVE_RESOURCE)
    monkeypatch.setenv("VITE_MM_WEB_CLIENT_ID", "foreign-client-id")
    repo, sha, tree = source
    out = tmp_path / "bundle"
    mod.prepare(source_repo=repo, expected_sha=sha, web_client_id="test-public-client-id", output=out,
                build_user="test", node=Path("/test/node"), npm_cli=Path("/test/npm-cli.js"))
    receipt = json.loads((out / "build-receipt.json").read_bytes())
    assert receipt["schema"] == mod.SCHEMA and receipt["mode"] == "web"
    assert mod.LAUNCH_CONFIG_ENV not in json.dumps(receipt)
    for kwargs in calls:
        assert kwargs["executive_resource"] is None and kwargs["launch_manifest"] is None
        assert kwargs["web_client_id"] == "test-public-client-id"
    mod.qualify(out, expected_sha=sha, tree_sha=tree, source_repo=repo)


def test_enabled_inputs_bind_exact_resource_and_canonical_manifest(launch_bundle, tmp_path):
    mod, out, sha, tree, calls = launch_bundle
    expected = canonical(launch_manifest())
    receipt = json.loads((out / "build-receipt.json").read_bytes())
    assert receipt["schema"] == mod.LAUNCH_SCHEMA and receipt["mode"] == mod.LAUNCH_MODE
    assert receipt["executive_resource"] == mod.OS_EXECUTIVE_RESOURCE
    assert receipt["launch_config"] == expected.decode("utf-8")
    assert receipt["launch_config_sha256"] == hashlib.sha256(expected).hexdigest()
    assert set(receipt["source_inputs"]) == set(mod.LAUNCH_INPUTS)
    assert len(calls) == 1
    assert calls[0]["executive_resource"] == mod.OS_EXECUTIVE_RESOURCE
    assert calls[0]["launch_manifest"] == expected
    checked = mod.qualify(out, expected_sha=sha, tree_sha=tree, source_repo=out.parent / "source")
    assert checked.receipt == (out / mod.RECEIPT).read_bytes()


def test_enabled_inputs_roundtrip_import_and_same_release_comparison(launch_bundle, tmp_path):
    mod, out, sha, tree, _ = launch_bundle
    checked = mod.qualify(out, expected_sha=sha, tree_sha=tree, source_repo=out.parent / "source")
    stage = tmp_path / "stage"
    stage.mkdir()
    mod.import_assets(checked, stage)
    assert (stage / "app/mastermind_os/dist/assets/index-a.js").read_text() == "committed app bytes"
    assert (stage / "app/mastermind_os/web-build-receipt.json").read_bytes() == checked.receipt
    (stage / ".executive-release-manifest.json").write_text("seal")
    mod.compare_existing(checked, stage)


def test_changed_launch_input_changes_receipt_and_bundle_digest(launch_bundle, tmp_path):
    mod, out, sha, tree, _ = launch_bundle
    first = mod.qualify(out, expected_sha=sha, tree_sha=tree, source_repo=out.parent / "source")
    second_out = tmp_path / "second"
    mod.prepare(source_repo=out.parent / "source", expected_sha=sha, web_client_id="test-public-client-id",
                output=second_out, build_user="test", node=Path("/test/node"), npm_cli=Path("/test/npm-cli.js"),
                executive_resource=mod.OS_EXECUTIVE_RESOURCE, launch_manifest=canonical(launch_manifest(priority=6)))
    second = mod.qualify(second_out, expected_sha=sha, tree_sha=tree, source_repo=out.parent / "source")
    assert first.digest != second.digest
    first_receipt = json.loads(first.receipt)
    second_receipt = json.loads(second.receipt)
    assert first_receipt["launch_config"] != second_receipt["launch_config"]
    assert first_receipt["launch_config_sha256"] != second_receipt["launch_config_sha256"]
    with pytest.raises(ValueError):
        mod.qualify(second_out, expected_sha=sha, tree_sha=tree, source_repo=out.parent / "source",
                    expected_digest=first.digest)


def test_v1_receipt_never_carries_and_cannot_be_rested_as_launch_evidence(bundle):
    mod, out, sha, tree = bundle
    assert mod._receipt_launch_inputs(json.loads((out / mod.RECEIPT).read_bytes())) == (None, None)
    def fabricate(receipt):
        receipt["schema"] = mod.LAUNCH_SCHEMA
        receipt["mode"] = mod.LAUNCH_MODE
    rewrite_receipt(out, mod, fabricate)
    with pytest.raises(ValueError, match="qualified OS resource|provenance"):
        mod.qualify(out, expected_sha=sha, tree_sha=tree, source_repo=out.parent / "source")


@pytest.mark.parametrize("mutate,description", [
    (lambda r: r.update(launch_config=json.dumps(launch_manifest())), "noncanonical text"),
    (lambda r: r.update(launch_config_sha256="c" * 64), "digest drift"),
    (lambda r: r.pop("launch_config_sha256"), "missing binding"),
    (lambda r: r.update(executive_resource="https://mcp.mastermind-x.com/workspace/read"), "resource drift"),
    (lambda r: r.update(executive_resource=""), "blank resource"),
    (lambda r: r.update(mode="web"), "mode drift"),
    (lambda r: r.update(schema="mastermind.os_web_build.v1"), "historical schema adoption"),
])
def test_enabled_receipt_tampers_refuse_qualification(launch_bundle, mutate, description):
    mod, out, sha, tree, _ = launch_bundle
    rewrite_receipt(out, mod, mutate)
    with pytest.raises(ValueError):
        mod.qualify(out, expected_sha=sha, tree_sha=tree, source_repo=out.parent / "source")


def test_consistently_restamped_launch_manifest_is_digest_gated_like_v1(launch_bundle):
    mod, out, sha, tree, _ = launch_bundle
    first = mod.qualify(out, expected_sha=sha, tree_sha=tree, source_repo=out.parent / "source")
    restamped = canonical(launch_manifest(priority=6))
    def restamp(receipt):
        receipt["launch_config"] = restamped.decode("utf-8")
        receipt["launch_config_sha256"] = hashlib.sha256(restamped).hexdigest()
    rewrite_receipt(out, mod, restamp)
    with pytest.raises(ValueError):
        mod.qualify(out, expected_sha=sha, tree_sha=tree, source_repo=out.parent / "source", expected_digest=first.digest)


@pytest.mark.parametrize("damage", ["duplicate_key", "unknown_field", "bool_priority", "float_priority",
                                    "string_v", "string_attempt_limit", "attempt_limit_four", "int_git_check",
                                    "noncanonical", "raw_utf8_unicode", "surrogate", "oversized",
                                    "research_with_paths", "research_with_validation", "bounded_without_paths",
                                    "bounded_empty_validation", "duplicate_refs", "traversal_path",
                                    "absolute_path", "backslash_path", "git_segment", "empty_projects",
                                    "bad_ref", "bad_workstream", "control_char_label"])
def test_manifest_input_refusals_follow_the_incumbent_decoder_law(damage):
    mod = helper()
    with pytest.raises(ValueError):
        mod.decode_launch_manifest(damaged_manifest(damage))


def test_valid_manifest_bytes_survive_exactly_including_astral_labels():
    mod = helper()
    manifest = {**launch_manifest(), "projects": [{"ref": "executive-infrastructure", "label": "Département 🚀"}]}
    raw = canonical(manifest)
    assert mod.decode_launch_manifest(raw) == raw
    bounded = canonical(launch_manifest(profile="bounded_code_change"))
    assert mod.decode_launch_manifest(bounded) == bounded


def test_decoder_limit_parity_and_documented_byte_cap():
    mod = helper()
    assert mod.LAUNCH_MANIFEST_MAX_UTF16 == 16384
    assert mod.LAUNCH_MANIFEST_MAX_BYTES < 16384
    assert mod._utf16_length("🚀") == 2 and mod._utf16_length("é") == 1
    with pytest.raises(ValueError):
        mod.decode_launch_manifest(b"")
    with pytest.raises(ValueError):
        mod.decode_launch_manifest(b" " * 4097)
    with pytest.raises(ValueError):
        mod.decode_launch_manifest(b"\xff\xfe not utf-8")
    with pytest.raises(ValueError):
        mod.decode_launch_manifest("not bytes")


@pytest.mark.parametrize("damage", ["partial_resource", "partial_manifest", "blank_resource", "wrong_resource",
                                    "duplicate_key", "noncanonical", "oversized", "surrogate",
                                    "research_with_paths", "unknown_field", "bool_priority"])
def test_enabled_preparation_refuses_completely_before_any_build_effect(tmp_path, source, monkeypatch, damage):
    mod = helper()
    monkeypatch.setattr(mod, "require_sealed_path", lambda *a, **k: None)
    monkeypatch.setattr(mod, "_require_root", lambda: None)
    calls = []
    monkeypatch.setattr(mod, "_build", lambda app, **kwargs: calls.append(kwargs) or built_dist(app))
    repo, sha, _ = source
    target = tmp_path / "refused"
    resource = mod.OS_EXECUTIVE_RESOURCE
    # A bare None pair is the disabled default; the API partial pair is one
    # side present without the other. The CLI partial flag pair is covered in
    # the command-line test.
    if damage == "partial_resource":
        raw = None
    elif damage == "partial_manifest":
        resource = None
        raw = canonical(launch_manifest())
    elif damage == "blank_resource":
        resource = ""
        raw = None
    elif damage == "wrong_resource":
        resource = "https://mcp.mastermind-x.com/workspace/read"
        raw = None
    else:
        raw = damaged_manifest(damage)
    kwargs = {"executive_resource": resource}
    if raw is not None:
        kwargs["launch_manifest"] = raw
    with pytest.raises(ValueError):
        mod.prepare(source_repo=repo, expected_sha=sha, web_client_id="test-public-client-id", output=target,
                    build_user="test", node=Path("/test/node"), npm_cli=Path("/test/npm-cli.js"), **kwargs)
    assert not target.exists()
    assert calls == []
    assert list(tmp_path.glob(".os-web-build-*")) == []


def test_build_env_carries_only_the_explicit_public_pair_ignoring_ambient_vite(source, tmp_path, monkeypatch):
    import os
    import pwd
    mod = helper()
    app = tmp_path / "work/app/mastermind_os"
    app.mkdir(parents=True)
    npm = tmp_path / "npm-cli.js"
    npm.write_text("// disposable npm entrypoint")
    npm.chmod(0o644)
    node = tmp_path / "node"
    node.write_text("#!/bin/sh\nexit 0\n")
    node.chmod(0o755)
    repo, sha, _ = source
    reserved = mod._reserved_service_uids(repo, sha)
    calls = []
    monkeypatch.setattr(mod.os, "chown", lambda *a, **k: None)
    monkeypatch.setattr(mod.subprocess, "run", lambda args, **kwargs: calls.append(kwargs))
    monkeypatch.setenv("VITE_MM_LAUNCH_CONFIG", "foreign-config")
    monkeypatch.setenv("VITE_MM_EXECUTIVE_RESOURCE", "https://foreign.example/invalid")
    monkeypatch.setenv("VITE_MM_WEB_CLIENT_ID", "foreign-client-id")
    manifest = canonical(launch_manifest())
    user = pwd.getpwuid(os.getuid())
    mod._build(app, build_user=user.pw_name, node=node, npm_cli=npm,
               web_client_id="test-public-client-id", reserved_service_uids=reserved,
               executive_resource=mod.OS_EXECUTIVE_RESOURCE, launch_manifest=manifest)
    assert len(calls) == 2
    for kwargs in calls:
        env = kwargs["env"]
        assert env["VITE_MM_WEB_CLIENT_ID"] == "test-public-client-id"
        assert env[mod.LAUNCH_RESOURCE_ENV] == mod.OS_EXECUTIVE_RESOURCE
        assert env[mod.LAUNCH_CONFIG_ENV] == manifest.decode("utf-8")
        assert sorted(name for name in env if name.startswith("VITE_")) == sorted(
            ["VITE_MM_WEB_CLIENT_ID", mod.LAUNCH_RESOURCE_ENV, mod.LAUNCH_CONFIG_ENV])
        assert "NODE_OPTIONS" not in env
    # A fresh archive workspace per build; the disabled mode forwards no launch input.
    disabled_app = tmp_path / "work2/app/mastermind_os"
    disabled_app.mkdir(parents=True)
    mod._build(disabled_app, build_user=user.pw_name, node=node, npm_cli=npm,
               web_client_id="test-public-client-id", reserved_service_uids=reserved)
    for kwargs in calls[2:]:
        assert mod.LAUNCH_CONFIG_ENV not in kwargs["env"]
        assert mod.LAUNCH_RESOURCE_ENV not in kwargs["env"]
        assert kwargs["env"]["VITE_MM_WEB_CLIENT_ID"] == "test-public-client-id"


def test_partial_pair_refused_by_the_builder_itself(source, tmp_path, monkeypatch):
    import os
    import pwd
    mod = helper()
    repo, sha, _ = source
    reserved = mod._reserved_service_uids(repo, sha)
    monkeypatch.setattr(mod.subprocess, "run", lambda *a, **k: pytest.fail("build was invoked"))
    with pytest.raises(ValueError, match="complete qualified input pair"):
        mod._build(tmp_path, build_user=pwd.getpwuid(os.getuid()).pw_name,
                   node=tmp_path / "absent-node", npm_cli=tmp_path / "absent-npm",
                   web_client_id="test-public-client-id", reserved_service_uids=reserved,
                   executive_resource=mod.OS_EXECUTIVE_RESOURCE)


def test_cli_prepare_reads_one_explicit_canonical_manifest_file_and_defaults_to_v1(bundle, tmp_path, monkeypatch, capsys):
    mod, out, sha, tree = bundle
    manifest_path = tmp_path / "launch.manifest.json"
    manifest_path.write_bytes(canonical(launch_manifest()))
    base = ["os_release_assets.py", "prepare", "--source-repo", str(out.parent / "source"),
            "--expected-sha", sha, "--web-client-id", "test-public-client-id", "--build-user", "test",
            "--node", "/test/node", "--npm-cli", "/test/npm-cli.js"]
    monkeypatch.setattr(mod.sys, "argv", base + ["--output", str(tmp_path / "cli-v1")])
    mod.main()
    capsys.readouterr()
    v1_receipt = json.loads((tmp_path / "cli-v1" / "build-receipt.json").read_bytes())
    assert v1_receipt["schema"] == mod.SCHEMA and v1_receipt["mode"] == "web"
    monkeypatch.setattr(mod.sys, "argv", base + ["--output", str(tmp_path / "cli-v2"),
                                                 "--executive-resource", mod.OS_EXECUTIVE_RESOURCE,
                                                 "--launch-manifest", str(manifest_path)])
    mod.main()
    digest = capsys.readouterr().out.strip().splitlines()[-1]
    v2_receipt = json.loads((tmp_path / "cli-v2" / "build-receipt.json").read_bytes())
    assert v2_receipt["schema"] == mod.LAUNCH_SCHEMA and v2_receipt["mode"] == mod.LAUNCH_MODE
    assert v2_receipt["launch_config"] == canonical(launch_manifest()).decode("utf-8")
    checked = mod.qualify(tmp_path / "cli-v2", expected_sha=sha, tree_sha=tree,
                          source_repo=out.parent / "source")
    assert digest == mod._hash(checked.receipt)
    assert digest != checked.digest
    monkeypatch.setattr(mod.sys, "argv", base + ["--output", str(tmp_path / "cli-partial"),
                                                 "--executive-resource", mod.OS_EXECUTIVE_RESOURCE])
    with pytest.raises(ValueError):
        mod.main()
    assert not (tmp_path / "cli-partial").exists()
