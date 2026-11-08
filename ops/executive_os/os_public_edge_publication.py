"""Explicit, once-only publication around the existing single-release OS consumer.

The host exports a custodial build attestation, not a remote signature. The root
publisher prepares the route union before the existing host installs anything,
then retires old routes only after observing the newly selected bytes. Import is
inert. No installer, SSH, recovery, service reload or startup configuration owner
is composed here. An unfinished phase intent requires external reconciliation.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import http.client
import json
import os
from pathlib import Path
import re
import stat
import subprocess

from integrations.mastermind_executive_app.os_assets import OS_ASSET_PROFILE_FILE_COUNTS
from ops.executive_os import os_public_edge_transition as planner
from ops.executive_os import deepseek_public_edge as dsh_planner
from ops.executive_os import os_release_assets as assets
from ops.executive_os import release_manifest
from ops.executive_os.executive_mcp_entry import load_os_app
from ops.executive_os.install_source_policy import validate_acceptance_source
from ops.executive_os.os_public_edge import HOST, asset_routes

SCHEMA = "mastermind.os_public_edge_publication.v1"
MAX_BYTES = 4 * 1024 * 1024
DESCRIPTOR = "stage.json"
OPERATION = "caddy-publication"


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def require(ok, message):
    if not ok:
        raise ValueError(message)


def decode(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "duplicate JSON key")
            result[key] = value
        return result
    def constant(_):
        raise ValueError("nonfinite JSON")
    require(type(raw) is bytes and 0 < len(raw) <= MAX_BYTES, "JSON byte budget")
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)


def _sha(value, length=64):
    require(type(value) is str and re.fullmatch(r"[0-9a-f]{%d}" % length, value),
            "exact source or digest required")
    return value


def _root():
    require(os.geteuid() == 0, "explicit root publisher required")


def _owner(info):
    require(info.st_uid == 0 and not info.st_mode & 0o022, "unsafe custody")


def _identity(info):
    return [info.st_dev, info.st_ino, info.st_uid, info.st_gid, info.st_mode]


class PrivateDirectory:
    """Held directory descriptor; every operation checks the original pathname.

    Files are exclusive and immutable. No replaced directory or file can supply
    a success receipt, and a partial write is never overwritten on re-entry.
    """
    def __init__(self, path):
        self.path = Path(path)
        assets._sealed_path(self.path, directory=True)
        self.fd = os.open(self.path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            self.identity = _identity(os.fstat(self.fd))
            self.check()
        except BaseException:
            os.close(self.fd)
            raise

    def check(self):
        assets._sealed_path(self.path, directory=True)
        info = os.fstat(self.fd)
        _owner(info)
        require(stat.S_ISDIR(info.st_mode) and stat.S_IMODE(info.st_mode) == 0o700,
                "private directory mode required")
        require(_identity(info) == self.identity == _identity(self.path.lstat()),
                "private directory replaced")

    def close(self):
        os.close(self.fd)

    def names(self):
        self.check()
        return set(os.listdir(self.fd))

    def read(self, name):
        require(type(name) is str and re.fullmatch(r"[a-z0-9.-]+", name), "private filename")
        self.check()
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=self.fd)
        try:
            before = os.fstat(fd)
            _owner(before)
            require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1
                    and stat.S_IMODE(before.st_mode) == 0o600
                    and 0 < before.st_size <= MAX_BYTES, "private file custody or size")
            assets._no_acl(self.path / name, before, descriptor=fd)
            chunks, size = [], 0
            while size <= MAX_BYTES:
                part = os.read(fd, min(65536, MAX_BYTES + 1 - size))
                if not part:
                    break
                chunks.append(part)
                size += len(part)
            after = os.fstat(fd)
            current = os.stat(name, dir_fd=self.fd, follow_symlinks=False)
            stamp = lambda s: (_identity(s), s.st_size, s.st_mtime_ns, s.st_ctime_ns, s.st_nlink)
            require(stamp(before) == stamp(after) == stamp(current) and size == before.st_size,
                    "private file changed")
            self.check()
            return b"".join(chunks)
        finally:
            os.close(fd)

    def write(self, name, raw):
        require(type(name) is str and re.fullmatch(r"[a-z0-9.-]+", name), "private filename")
        require(type(raw) is bytes and 0 < len(raw) <= MAX_BYTES, "private file byte budget")
        self.check()
        fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                     0o600, dir_fd=self.fd)
        try:
            with os.fdopen(fd, "wb", closefd=False) as stream:
                stream.write(raw)
                stream.flush()
                os.fchmod(fd, 0o600)
                os.fsync(fd)
        finally:
            os.close(fd)
        os.fsync(self.fd)
        require(self.read(name) == raw, "private write readback differs")


@contextmanager
def private(path):
    value = PrivateDirectory(path)
    try:
        yield value
    finally:
        value.close()


def _new_directory(path):
    path = Path(path)
    assets._sealed_path(path.parent, directory=True)
    require(path.is_absolute() and path.parent.resolve() == path.parent,
            "direct absolute private parent required")
    path.mkdir(mode=0o700, exist_ok=False)
    fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _manifest(files):
    value = decode(files["asset-manifest.json"])
    asset_routes(value)
    require(set(files) == {"asset-manifest.json", *(row["path"] for row in value["files"])},
            "captured asset set differs")
    for row in value["files"]:
        raw = files[row["path"]]
        require(len(raw) == row["byte_count"] and digest(raw) == row["sha256"],
                "captured asset bytes differ")
    return value


def stage_host(*, old_root, old_sha, old_tree, new_bundle, source_repo,
               new_sha, new_tree, new_digest, live_config, relay_port, out):
    _root()
    for value in (old_sha, old_tree, new_sha, new_tree):
        _sha(value, 40)
    _sha(new_digest)
    require(validate_acceptance_source(source_repo=Path(source_repo), expected_sha=new_sha)
            == new_tree, "new source tree differs")
    old_root = Path(old_root)
    seal = release_manifest.verify(old_root, old_sha, old_tree)
    assets._sealed_path(old_root / release_manifest.MANIFEST_NAME)
    require(decode(assets._read(old_root / release_manifest.MANIFEST_NAME)) == seal,
            "old release seal JSON differs")
    old_app = load_os_app(old_root)
    old_manifest, old_files = assets._capture_dist(old_root, sealed=True)
    require(_manifest(old_files) == old_manifest, "old manifest differs")
    expected_assets = {("/os/" if row["path"] == "index.html" else "/os/" + row["path"]):
                       (old_files[row["path"]], row["mime"]) for row in old_manifest["files"]}
    require(old_app._assets == expected_assets, "old selected consumer bytes differ")
    require(release_manifest.verify(old_root, old_sha, old_tree) == seal, "old release changed")
    checked = assets.qualify(Path(new_bundle), expected_sha=new_sha, tree_sha=new_tree,
                             source_repo=Path(source_repo), expected_digest=new_digest)
    receipt = decode(checked.receipt)
    new_manifest = _manifest(checked.files)
    assets._sealed_path(Path(live_config))
    fullconfig = decode(assets._read(Path(live_config)))
    planned = planner.plan(old_source=old_sha, new_source=new_sha, fullconfig=fullconfig,
                           current_manifest=old_manifest, candidate_manifest=new_manifest,
                           relay_port=relay_port)
    prepared = planner.prepare_config(fullconfig=fullconfig, current_manifest=old_manifest,
                                       candidate_manifest=new_manifest, relay_port=relay_port)
    final = planner.final_config(fullconfig=fullconfig, current_manifest=old_manifest,
                                 candidate_manifest=new_manifest, relay_port=relay_port)
    captured = {"live.json": canonical(fullconfig), "prepare.json": canonical(prepared),
                "final.json": canonical(final), "new-receipt.json": checked.receipt}
    indexes = {}
    for kind, files in (("old", old_files), ("new", checked.files)):
        indexes[kind] = {}
        for i, name in enumerate(sorted(files)):
            label = f"{kind}-{i:02d}.blob"
            captured[label] = files[name]
            indexes[kind][name] = label
    descriptor = {
        "schema": SCHEMA, "host": HOST, "relay_port": relay_port,
        "old": {"source": old_sha, "tree": old_tree, "seal_digest": digest(canonical(seal))},
        "new": {"source": new_sha, "tree": new_tree, "bundle_digest": checked.digest},
        "custody": "root-owned transport required; not a remote signature",
        "indexes": indexes, "plan": planned,
        "files": {name: {"sha256": digest(raw), "bytes": len(raw)}
                  for name, raw in sorted(captured.items())},
    }
    require(receipt["source_sha"] == new_sha and receipt["source_tree"] == new_tree,
            "qualified receipt binding differs")
    require(validate_acceptance_source(source_repo=Path(source_repo), expected_sha=new_sha)
            == new_tree, "new protected source changed during capture")
    _new_directory(out)
    with private(out) as stage:
        for name, raw in captured.items():
            stage.write(name, raw)
        raw = canonical(descriptor)
        stage.write(DESCRIPTOR, raw)  # last: partial captures never qualify
        return {"schema": SCHEMA, "state": "STAGED", "stage_digest": digest(raw),
                "new_source": new_sha, "new_bundle_digest": checked.digest,
                "transport_custody": "REQUIRED", "published": False}


def _load_stage(stage, expected_digest):
    raw = stage.read(DESCRIPTOR)
    require(digest(raw) == _sha(expected_digest), "stage digest differs")
    d = decode(raw)
    require(type(d) is dict and set(d) == {"schema", "host", "relay_port", "old", "new",
            "custody", "indexes", "plan", "files"} and d["schema"] == SCHEMA
            and d["host"] == HOST and d["custody"] == "root-owned transport required; not a remote signature",
            "stage schema differs")
    require(set(d["old"]) == {"source", "tree", "seal_digest"}
            and set(d["new"]) == {"source", "tree", "bundle_digest"}, "source fields differ")
    for kind in ("old", "new"):
        _sha(d[kind]["source"], 40)
        _sha(d[kind]["tree"], 40)
    _sha(d["old"]["seal_digest"])
    _sha(d["new"]["bundle_digest"])
    require(type(d["indexes"]) is dict and set(d["indexes"]) == {"old", "new"}, "asset indexes differ")
    required = {"live.json", "prepare.json", "final.json", "new-receipt.json"}
    manifests, captures = {}, {}
    for kind in ("old", "new"):
        index = d["indexes"][kind]
        # Staged indexes also contain the manifest: validate their bounded size
        # against the same closed profiles as the final asset/route validator.
        require(type(index) is dict and len(index) in {count + 1 for count in OS_ASSET_PROFILE_FILE_COUNTS},
                "asset index topology")
        require(list(sorted(index.values())) == [f"{kind}-{i:02d}.blob" for i in range(len(index))],
                "asset index labels differ")
        required.update(index.values())
        captures[kind] = {name: stage.read(label) for name, label in index.items()}
        manifests[kind] = _manifest(captures[kind])
    require(type(d["files"]) is dict and set(d["files"]) == required, "stage files differ")
    require(stage.names() in (required | {DESCRIPTOR}, required | {DESCRIPTOR, OPERATION}),
            "unexpected staged entry")
    contents = {name: stage.read(name) for name in required}
    require(d["files"] == {name: {"sha256": digest(raw), "bytes": len(raw)}
                            for name, raw in contents.items()}, "stage bytes changed")
    receipt = decode(contents["new-receipt.json"])
    require(receipt["source_sha"] == d["new"]["source"] and receipt["source_tree"] == d["new"]["tree"],
            "build source differs")
    bundle_digest = assets._hash(assets._canonical({"receipt": digest(contents["new-receipt.json"]),
        "files": {name: digest(raw) for name, raw in sorted(captures["new"].items())}}))
    require(bundle_digest == d["new"]["bundle_digest"], "build bundle binding differs")
    live, prepared, final = (decode(contents[name + ".json"]) for name in ("live", "prepare", "final"))
    kwargs = dict(fullconfig=live, current_manifest=manifests["old"],
                  candidate_manifest=manifests["new"], relay_port=d["relay_port"])
    # Canonical equality preserves numeric types. Python dict equality would
    # accept a floating-point body cap as equal to the required integer after
    # a forged stage repaired its outer file digests.
    require(canonical(d["plan"]) == canonical(planner.plan(
                old_source=d["old"]["source"], new_source=d["new"]["source"], **kwargs))
            and canonical(prepared) == canonical(planner.prepare_config(**kwargs))
            and canonical(final) == canonical(planner.final_config(**kwargs)),
            "transition bindings differ")
    return d, manifests, live, prepared, final


def _http(port, method, path, *, body=None, headers=None, maximum=MAX_BYTES):
    """Fixed numeric loopback peer: no proxies, redirects or automatic retry."""
    require(port == 2019 or 49152 <= port <= 50200, "fixed loopback port required")
    return _loopback_http(port, method, path, body=body, headers=headers, maximum=maximum)


def _loopback_http(port, method, path, *, body=None, headers=None, maximum=MAX_BYTES):
    require(port in (2019, 4181) or 49152 <= port <= 50200, "closed loopback port required")
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=20)
    try:
        connection.request(method, path, body=body, headers=headers or {})
        response = connection.getresponse()
        pairs = response.getheaders()
        require(all(sum(k.lower() == key for k, _ in pairs) <= 1
                    for key in ("content-type", "content-length", "etag")), "ambiguous HTTP headers")
        data = response.read(maximum + 1)
        require(len(data) <= maximum, "HTTP byte budget")
        return response.status, {k.lower(): v for k, v in pairs}, data
    finally:
        connection.close()


def _config():
    status, headers, raw = _http(2019, "GET", "/config/")
    etag = headers.get("etag")
    require(status == 200 and type(etag) is str and 0 < len(etag) <= 1024
            and "\r" not in etag and "\n" not in etag, "config status or ETag missing")
    return decode(raw), etag


def _listener(port, pid):
    require(type(pid) is int and pid > 0, "exact listener PID required")
    answer = subprocess.run(["/usr/bin/ss", "-H", "-ltnp", f"sport = :{port}"],
                            capture_output=True, text=True, timeout=10, check=True)
    lines = [line for line in answer.stdout.splitlines() if line.strip()]
    require(len(lines) == 1, "relay listener is not unique")
    fields = lines[0].split(None, 5)
    require(len(fields) == 6 and fields[0] == "LISTEN" and fields[3] == f"127.0.0.1:{port}"
            and re.findall(r"pid=(\d+),", fields[5]) == [str(pid)], "relay listener identity differs")


def _served(manifest, port):
    for row in manifest["files"]:
        paths = ["/os/", "/os/auth/callback"] if row["path"] == "index.html" else ["/os/" + row["path"]]
        for path in paths:
            status, headers, raw = _http(port, "GET", path, headers={"Host": HOST,
                "X-Forwarded-Proto": "https", "X-Forwarded-For": "127.0.0.1"}, maximum=row["byte_count"])
            require(status == 200 and headers.get("content-type") == row["mime"]
                    and len(raw) == row["byte_count"] and digest(raw) == row["sha256"],
                    "selected relay asset differs")


def _validate(stage, phase, candidate):
    name = "prepare.json" if phase == "prepare" else "final.json"
    return _validate_file(stage, name, candidate)


def _validate_file(stage, name, candidate):
    require(name in ("prepare.json", "final.json", "candidate.json"), "fixed candidate required")
    require(decode(stage.read(name)) == candidate, "validation bytes differ")
    subprocess.run(["/usr/bin/caddy", "validate", "--config", str(stage.path / name)],
                   capture_output=True, timeout=30, check=True)
    require(decode(stage.read(name)) == candidate, "validation input changed")


def _binding(stage, operation, d, expected_digest, phase, base, candidate, predecessor):
    return {"schema": SCHEMA, "phase": phase, "stage_digest": expected_digest,
            "stage_identity": stage.identity, "operation_identity": operation.identity,
            "new_source": d["new"]["source"], "new_bundle_digest": d["new"]["bundle_digest"],
            "base_digest": digest(canonical(base)), "config_digest": digest(canonical(candidate)),
            "predecessor_digest": predecessor}


def _success(stage, operation, d, expected_digest, phase, base, candidate, predecessor):
    names = {"prepare-intent.json", "prepare-receipt.json"}
    if phase == "finalize":
        names |= {"finalize-intent.json", "finalize-receipt.json"}
    require(operation.names() == names, "phase journal unresolved or changed")
    intent = decode(operation.read(phase + "-intent.json"))
    expected = _binding(stage, operation, d, expected_digest, phase, base, candidate, predecessor)
    require(type(intent) is dict and set(intent) == {*expected, "etag", "listener_pid"}
            and all(intent[k] == v for k, v in expected.items())
            and type(intent["etag"]) is str and 0 < len(intent["etag"]) <= 1024
            and type(intent["listener_pid"]) is int and intent["listener_pid"] > 0,
            "phase intent binding differs")
    raw = operation.read(phase + "-receipt.json")
    expected_receipt = {**expected, "state": "PREPARED" if phase == "prepare" else "FINAL",
                        "intent_digest": digest(canonical(intent)), "http_status": 200}
    require(decode(raw) == expected_receipt, "phase success receipt differs or incomplete")
    require(operation.names() == names, "phase journal changed during verification")
    return digest(raw)


def verify_cutover(*, stage_path, stage_digest, new_sha, new_digest):
    _root()
    with private(stage_path) as stage:
        d, _, live, prepared, _ = _load_stage(stage, stage_digest)
        require(d["new"]["source"] == _sha(new_sha, 40)
                and d["new"]["bundle_digest"] == _sha(new_digest), "cutover target differs")
        with private(stage.path / OPERATION) as operation:
            require(operation.names() == {"prepare-intent.json", "prepare-receipt.json"},
                    "cutover phase unresolved or already finalized")
            predecessor = _success(stage, operation, d, stage_digest, "prepare", live, prepared, None)
            intent = decode(operation.read("prepare-intent.json"))
            _listener(d["relay_port"], intent["listener_pid"])
            require(canonical(_config()[0]) == canonical(prepared), "prepared configuration no longer current")
            return {"schema": SCHEMA, "state": "CUTOVER_READY", "stage_digest": stage_digest,
                    "prepare_receipt_digest": predecessor, "new_source": new_sha,
                    "new_bundle_digest": new_digest, "installed": False}


def publish(*, stage_path, stage_digest, listener_pid, phase):
    _root()
    require(phase in ("prepare", "finalize"), "unknown publication phase")
    with private(stage_path) as stage:
        d, manifests, live, prepared, final = _load_stage(stage, stage_digest)
        predecessor = None
        if phase == "prepare":
            require(OPERATION not in stage.names(), "original operation already exists; no replay")
            base, candidate, manifest = live, prepared, manifests["old"]
        else:
            with private(stage.path / OPERATION) as operation:
                require(operation.names() == {"prepare-intent.json", "prepare-receipt.json"},
                        "original operation incomplete or final phase already attempted")
                predecessor = _success(stage, operation, d, stage_digest, "prepare", live, prepared, None)
            base, candidate, manifest = prepared, final, manifests["new"]
        current, etag = _config()
        require(canonical(current) == canonical(base), "live full configuration drift")
        _listener(d["relay_port"], listener_pid)
        _validate(stage, phase, candidate)
        _served(manifest, d["relay_port"])
        _listener(d["relay_port"], listener_pid)
        observed_config, observed_etag = _config()
        require(canonical(observed_config) == canonical(base) and observed_etag == etag,
                "configuration or ETag changed during qualification")
        require(_load_stage(stage, stage_digest)[0] == d, "stage changed during qualification")
        if phase == "prepare":
            _new_directory(stage.path / OPERATION)
        with private(stage.path / OPERATION) as operation:
            if phase == "finalize":
                require(operation.names() == {"prepare-intent.json", "prepare-receipt.json"}, "phase raced")
                require(_success(stage, operation, d, stage_digest, "prepare", live, prepared, None)
                        == predecessor, "prepare receipt changed")
            binding = _binding(stage, operation, d, stage_digest, phase, base, candidate, predecessor)
            return _commit_publication(
                stage, operation, schema=SCHEMA, phase=phase, binding=binding, etag=etag,
                candidate=candidate, listener_pid=listener_pid,
                state="PREPARED" if phase == "prepare" else "FINAL",
                requalify=lambda: require(_load_stage(stage, stage_digest)[0] == d,
                                          "stage changed after publication"),
                verify_success=lambda: _success(stage, operation, d, stage_digest, phase,
                                                 base, candidate, predecessor),
            )

def _commit_publication(stage, operation, *, schema, phase, binding, etag, candidate,
                        listener_pid, state, requalify, verify_success):
    """The one intent/ETag/POST/readback/receipt transaction for both consumers."""
    intent = {**binding, "etag": etag, "listener_pid": listener_pid}
    try:
        operation.write(phase + "-intent.json", canonical(intent))
        stage.check()
        operation.check()
        status, _, _ = _http(2019, "POST", "/config/", body=canonical(candidate),
                             headers={"Content-Type": "application/json", "If-Match": etag})
        require(status == 200, "publication status refused; reconciliation required")
        after, _ = _config()
        require(canonical(after) == canonical(candidate), "publication readback differs; reconciliation required")
        requalify()
        receipt = {**binding, "state": state, "intent_digest": digest(canonical(intent)),
                   "http_status": status}
        operation.write(phase + "-receipt.json", canonical(receipt))
        verify_success()
        return receipt
    except BaseException as exc:
        operation.write(phase + "-reconciliation.json", canonical({
            "schema": schema, "state": "RECONCILIATION_REQUIRED", "phase": phase,
            "stage_digest": binding["stage_digest"], "error_type": type(exc).__name__}))
        raise


DSH_SCHEMA = "mastermind.dsh_public_edge_publication.v1"


def _dsh_artifact(area, expected_digest):
    from integrations.deepseek_harness.package_attended import (
        PIN, PUBLICATION_SCHEMA, PUBLICATION_CUSTODY,
    )
    raw = area.read("artifact-receipt.json")
    require(digest(raw) == _sha(expected_digest), "native artifact receipt digest differs")
    record = decode(raw)
    require(type(record) is dict and set(record) == {
        "schema", "custody", "source", "donor_sha", "host", "native_port", "relay_port",
        "package_manifest_sha256", "build_qualification_sha256", "package_entries", "app_config_sha256",
        "company_client_sha256", "company_patch_sha256", "native_client_build_sha256",
        "assets", "installed", "public_route_qualified", "provider_calls"},
        "native artifact receipt shape differs")
    require(record["schema"] == PUBLICATION_SCHEMA and record["custody"] == PUBLICATION_CUSTODY
            and record["donor_sha"] == PIN and record["host"] == dsh_planner.HOST
            and record["native_port"] == 4180 and record["relay_port"] == 4181
            and record["installed"] is False and record["public_route_qualified"] is False
            and type(record["provider_calls"]) is int and record["provider_calls"] == 0
            and type(record["package_entries"]) is int and record["package_entries"] > 0,
            "native artifact qualification differs")
    require(type(record["source"]) is dict and set(record["source"]) == {"sha", "tree"},
            "native source binding required")
    for value in record["source"].values():
        _sha(value, 40)
    for key in ("package_manifest_sha256", "build_qualification_sha256", "app_config_sha256", "company_client_sha256",
                "company_patch_sha256", "native_client_build_sha256"):
        _sha(record[key])
    require(type(record["assets"]) is list and len(record["assets"]) == 2,
            "native script and stylesheet evidence required")
    captures = {"artifact-receipt.json": raw}
    for row, suffix, mime in zip(record["assets"], ("js", "css"), ("text/javascript", "text/css")):
        require(type(row) is dict and set(row) == {"url", "mime", "bytes", "sha256", "capture"}
                and type(row["url"]) is str and re.fullmatch(
                    r"/assets/index-[A-Za-z0-9_-]+\." + suffix, row["url"])
                and row["mime"] == mime and row["capture"] == "client." + suffix + ".blob"
                and type(row["bytes"]) is int and 0 < row["bytes"] <= MAX_BYTES,
                "native public asset binding refused")
        payload = area.read(row["capture"])
        require(len(payload) == row["bytes"] and digest(payload) == _sha(row["sha256"]),
                "native captured asset bytes differ")
        captures[row["capture"]] = payload
    return record, captures


def stage_dsh(*, artifact_path, artifact_digest, source_repo, source_sha, source_tree, out):
    """Capture one closed DSH site addition through the incumbent edge owner."""
    _root()
    _sha(source_sha, 40)
    _sha(source_tree, 40)
    require(validate_acceptance_source(source_repo=Path(source_repo), expected_sha=source_sha)
            == source_tree, "native protected source tree differs")
    with private(artifact_path) as artifact:
        record, captured = _dsh_artifact(artifact, artifact_digest)
        require(artifact.names() == set(captured), "unexpected native artifact entry")
    require(record["source"] == {"sha": source_sha, "tree": source_tree},
            "native export source differs from protected source")
    from integrations.deepseek_harness.package_attended import protected_build
    build_raw, build = protected_build(Path(source_repo), source_sha)
    require(digest(build_raw) == record["build_qualification_sha256"]
            and all(build[key] == record[key] for key in ("package_manifest_sha256",
                "app_config_sha256", "company_client_sha256", "native_client_build_sha256")),
            "native artifact differs from protected build qualification")
    live, etag = _config()
    candidate = dsh_planner.candidate_config(live)
    captured.update({"live.json": canonical(live), "candidate.json": canonical(candidate)})
    descriptor = {
        "schema": DSH_SCHEMA, "host": dsh_planner.HOST, "relay_port": 4181,
        "source": record["source"], "artifact_digest": artifact_digest, "observed_etag": etag,
        "custody": "root-owned transport required; not a remote signature",
        "files": {name: {"sha256": digest(raw), "bytes": len(raw)}
                  for name, raw in sorted(captured.items())},
    }
    require(validate_acceptance_source(source_repo=Path(source_repo), expected_sha=source_sha)
            == source_tree, "native source changed during capture")
    _new_directory(out)
    with private(out) as area:
        for name, raw in captured.items():
            area.write(name, raw)
        raw = canonical(descriptor)
        area.write(DESCRIPTOR, raw)
        _load_dsh_stage(area, digest(raw))
    return {"schema": DSH_SCHEMA, "state": "STAGED", "stage_digest": digest(raw),
            "published": False, "installed": False}


def _load_dsh_stage(stage, expected_digest):
    raw = stage.read(DESCRIPTOR)
    require(digest(raw) == _sha(expected_digest), "native stage digest differs")
    d = decode(raw)
    require(type(d) is dict and set(d) == {"schema", "host", "relay_port", "source",
        "artifact_digest", "observed_etag", "custody", "files"}
        and d["schema"] == DSH_SCHEMA and d["host"] == dsh_planner.HOST
        and d["relay_port"] == 4181
        and d["custody"] == "root-owned transport required; not a remote signature"
        and type(d["observed_etag"]) is str and 0 < len(d["observed_etag"]) <= 1024,
        "native stage descriptor refused")
    expected_names = {"artifact-receipt.json", "client.js.blob", "client.css.blob",
                      "live.json", "candidate.json"}
    require(type(d["files"]) is dict and set(d["files"]) == expected_names
            and stage.names() <= expected_names | {DESCRIPTOR, OPERATION},
            "native stage file set differs")
    contents = {}
    for name, meta in d["files"].items():
        payload = stage.read(name)
        require(type(meta) is dict and set(meta) == {"sha256", "bytes"}
                and meta == {"sha256": digest(payload), "bytes": len(payload)},
                "native stage bytes differ")
        contents[name] = payload
    record, _ = _dsh_artifact(stage, d["artifact_digest"])
    require(record["source"] == d["source"], "native stage source differs")
    live, candidate = decode(contents["live.json"]), decode(contents["candidate.json"])
    require(canonical(candidate) == canonical(dsh_planner.candidate_config(live)), "native candidate differs")
    return d, record, live, candidate


def _dsh_http(path, *, maximum):
    require(path == "/" or re.fullmatch(r"/assets/index-[A-Za-z0-9_-]+\.(?:js|css)", path),
            "fixed native probe path required")
    return _loopback_http(4181, "GET", path, maximum=maximum,
                          headers={"Host": dsh_planner.HOST, "Accept-Encoding": "identity"})


def _served_dsh(record):
    status, headers, raw = _dsh_http("/", maximum=1024)
    require(status == 401 and headers.get("cache-control") == "no-store"
            and headers.get("content-type") == "text/plain; charset=utf-8"
            and raw == b"dsh web authentication required; reopen the URL printed by dsh web.\n",
            "native unauthenticated index differs")
    for row in record["assets"]:
        status, headers, raw = _dsh_http(row["url"], maximum=row["bytes"])
        require(status == 200 and headers.get("content-type", "").split(";")[0] == row["mime"]
                and len(raw) == row["bytes"] and digest(raw) == row["sha256"],
                "native public asset served bytes differ")


def _dsh_binding(stage, operation, d, expected_digest, base, candidate):
    return {"schema": DSH_SCHEMA, "phase": "dsh", "stage_digest": expected_digest,
            "stage_identity": stage.identity, "operation_identity": operation.identity,
            "source": d["source"], "artifact_digest": d["artifact_digest"],
            "base_digest": digest(canonical(base)), "config_digest": digest(canonical(candidate))}


def _dsh_success(stage, operation, d, expected_digest, base, candidate):
    require(operation.names() == {"dsh-intent.json", "dsh-receipt.json"},
            "native publication journal unresolved or changed")
    binding = _dsh_binding(stage, operation, d, expected_digest, base, candidate)
    intent = decode(operation.read("dsh-intent.json"))
    require(type(intent) is dict and set(intent) == {*binding, "etag", "listener_pid"}
            and all(intent[key] == value for key, value in binding.items())
            and type(intent["etag"]) is str and 0 < len(intent["etag"]) <= 1024
            and type(intent["listener_pid"]) is int and intent["listener_pid"] > 0,
            "native publication intent differs")
    receipt = decode(operation.read("dsh-receipt.json"))
    require(receipt == {**binding, "state": "PUBLISHED", "intent_digest": digest(canonical(intent)),
                        "http_status": 200}, "native publication receipt differs")
    return receipt


def publish_dsh(*, stage_path, stage_digest, listener_pid):
    _root()
    with private(stage_path) as stage:
        d, record, base, candidate = _load_dsh_stage(stage, stage_digest)
        require(OPERATION not in stage.names(), "original operation already exists; no replay")
        current, etag = _config()
        require(canonical(current) == canonical(base) and etag == d["observed_etag"], "native full configuration drift")
        _listener(4181, listener_pid)
        _validate_file(stage, "candidate.json", candidate)
        _served_dsh(record)
        _listener(4181, listener_pid)
        observed_config, observed_etag = _config()
        require(canonical(observed_config) == canonical(base) and observed_etag == etag,
                "configuration or ETag changed during qualification")
        require(_load_dsh_stage(stage, stage_digest)[0] == d, "native stage changed during qualification")
        _new_directory(stage.path / OPERATION)
        with private(stage.path / OPERATION) as operation:
            binding = _dsh_binding(stage, operation, d, stage_digest, base, candidate)
            return _commit_publication(
                stage, operation, schema=DSH_SCHEMA, phase="dsh", binding=binding, etag=etag,
                candidate=candidate, listener_pid=listener_pid, state="PUBLISHED",
                requalify=lambda: require(_load_dsh_stage(stage, stage_digest)[0] == d,
                                          "native stage changed after publication"),
                verify_success=lambda: _dsh_success(stage, operation, d, stage_digest, base, candidate),
            )



def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    stage = sub.add_parser("stage-host")
    for name in ("old-root", "new-bundle", "source-repo", "live-config", "out"):
        stage.add_argument("--" + name, type=Path, required=True)
    for name in ("old-sha", "old-tree", "new-sha", "new-tree", "new-digest"):
        stage.add_argument("--" + name, required=True)
    stage.add_argument("--relay-port", type=int, required=True)
    dsh = sub.add_parser("stage-dsh")
    for name in ("artifact-path", "source-repo", "out"):
        dsh.add_argument("--" + name, type=Path, required=True)
    for name in ("artifact-digest", "source-sha", "source-tree"):
        dsh.add_argument("--" + name, required=True)
    for name in ("prepare", "verify-cutover", "finalize", "publish-dsh"):
        command = sub.add_parser(name)
        command.add_argument("--stage-path", type=Path, required=True)
        command.add_argument("--stage-digest", required=True)
        if name == "verify-cutover":
            command.add_argument("--new-sha", required=True)
            command.add_argument("--new-digest", required=True)
        else:
            command.add_argument("--listener-pid", type=int, required=True)
    args = vars(parser.parse_args(argv))
    command = args.pop("command")
    if command == "stage-host":
        result = stage_host(**args)
    elif command == "stage-dsh":
        result = stage_dsh(**args)
    elif command == "publish-dsh":
        result = publish_dsh(**args)
    elif command == "verify-cutover":
        result = verify_cutover(**args)
    else:
        result = publish(**args, phase=command)
    print(canonical(result).decode())


if __name__ == "__main__":
    main()
