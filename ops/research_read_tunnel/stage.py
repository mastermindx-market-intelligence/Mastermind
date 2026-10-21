"""Produce inert, exact-source Research Read candidates. Never install or start.

The selected Macro archive roots are an owner-reviewed import closure input;
this stager verifies their bytes, not production dependency sufficiency.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import tarfile

SCHEMA = "mastermind.research_read_stage.v1"
_SHA = re.compile(r"[0-9a-f]{40}\Z")
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
MAX_BYTES = 64 * 1024 * 1024
MAX_MEMBERS = 8192
UNIT_PATH = "ops/research_read_tunnel/mastermind-research-read.service"
LOCK_PATH = "requirements/research-read-linux-x86_64-py312.lock"
SERVER_PATH = "scripts/mastermind_research_read_server.py"
PRODUCER_PATH = "ops/research_producer/launch.py"
MASTERMIND_ROOTS = ("common", "control_plane", "integrations", SERVER_PATH, LOCK_PATH)


class StageRefused(ValueError):
    def __init__(self, code="STAGE_SOURCE_REFUSED"):
        self.code = code
        super().__init__(code)


def _git(source, *args, binary=False):
    environment = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    environment["GIT_OPTIONAL_LOCKS"] = "0"
    try:
        return subprocess.run(["git", "-C", str(source), *args], capture_output=True,
                              text=not binary, check=True, timeout=30, env=environment).stdout
    except (OSError, subprocess.SubprocessError):
        raise StageRefused() from None


def qualify_source(source: Path, commit: str, tree: str):
    try:
        if (not source.is_absolute() or not source.is_dir()
                or any(path.is_symlink() for path in (source, *source.parents))
                or type(commit) is not str or _SHA.fullmatch(commit) is None
                or type(tree) is not str or _SHA.fullmatch(tree) is None):
            raise StageRefused()
        if _git(source, "rev-parse", "HEAD").strip() != commit:
            raise StageRefused("STAGE_COMMIT_MISMATCH")
        if _git(source, "rev-parse", "HEAD^{tree}").strip() != tree:
            raise StageRefused("STAGE_TREE_MISMATCH")
        if _git(source, "status", "--porcelain", "--untracked-files=all"):
            raise StageRefused("STAGE_SOURCE_DIRTY")
    except StageRefused:
        raise
    except Exception:
        raise StageRefused() from None


def _paths(roots):
    if type(roots) not in (list, tuple) or not roots or len(roots) > 64:
        raise StageRefused("STAGE_PATH_REFUSED")
    checked = []
    for value in roots:
        if type(value) is not str or not value or len(value) > 500:
            raise StageRefused("STAGE_PATH_REFUSED")
        path = PurePosixPath(value)
        if (value == "." or path.is_absolute() or str(path) != value or ".." in path.parts
                or any(part in {".git", ".lane"} or part.startswith(".env") for part in path.parts)
                or any(char in value for char in ("\\", "\x00", "*", "?", "[", "]", ":"))
                or value.startswith("-")):
            raise StageRefused("STAGE_PATH_REFUSED")
        checked.append(value)
    if len(set(checked)) != len(checked):
        raise StageRefused("STAGE_PATH_REFUSED")
    return tuple(checked)


def source_archive(source: Path, commit: str, tree: str, roots):
    qualify_source(source, commit, tree)
    paths = _paths(roots)
    count, size = 0, 0
    expected = {}
    # Bound source member sizes before retaining the archive in memory.
    listing = _git(source, "ls-tree", "-r", "-l", commit, "--", *paths)
    for row in listing.splitlines():
        header, name = row.split("\t", 1)
        mode, kind, _oid, length = header.split()
        if mode not in {"100644", "100755"} or kind != "blob" or length == "-":
            raise StageRefused("STAGE_MEMBER_REFUSED")
        _paths((name,))
        expected[name] = (int(length), _oid)
        count += 1
        size += int(length)
    if not count or count > MAX_MEMBERS or size + count * 2048 > MAX_BYTES:
        raise StageRefused("STAGE_ARCHIVE_BOUND")
    for root in paths:
        if not _git(source, "ls-tree", commit, "--", root).strip():
            raise StageRefused("STAGE_REQUIRED_SOURCE_MISSING")
    raw = _git(source, "archive", "--format=tar", commit, "--", *paths, binary=True)
    if len(raw) > MAX_BYTES:
        raise StageRefused("STAGE_ARCHIVE_BOUND")
    members = []
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:") as archive:
        rows = archive.getmembers()
        if len(rows) > MAX_MEMBERS:
            raise StageRefused("STAGE_ARCHIVE_BOUND")
        for member in rows:
            _paths((member.name.rstrip("/"),))
            if not member.isdir() and not member.isfile():
                raise StageRefused("STAGE_MEMBER_REFUSED")
            if member.isfile():
                body = archive.extractfile(member).read()
                identity = (len(body), hashlib.sha1(b"blob " + str(len(body)).encode()
                                                   + b"\x00" + body).hexdigest())
                if expected.get(member.name) != identity:
                    raise StageRefused("STAGE_ARCHIVE_IDENTITY_REFUSED")
                members.append({"path": member.name, "bytes": len(body),
                                "sha256": hashlib.sha256(body).hexdigest()})
    if {row["path"] for row in members} != set(expected):
        raise StageRefused("STAGE_ARCHIVE_IDENTITY_REFUSED")
    # Reject a source change during capture, including untracked content.
    qualify_source(source, commit, tree)
    return raw, members


def render_unit(template: str, *, commit: str, lock_sha256: str):
    if (_SHA.fullmatch(commit) is None or _DIGEST.fullmatch(lock_sha256) is None
            or template.count("@MASTERMIND_COMMIT@") != 2
            or template.count("@LOCK_SHA256@") != 1):
        raise StageRefused("STAGE_UNIT_REFUSED")
    rendered = template.replace("@MASTERMIND_COMMIT@", commit).replace("@LOCK_SHA256@", lock_sha256)
    required = {
        "User=mastermind-research", "Group=mastermind-research",
        f"WorkingDirectory=/opt/mastermind-research/releases/{commit}",
        f"ExecStart=/opt/mastermind-research/venvs/{lock_sha256}/bin/python -I -B "
        f"/opt/mastermind-research/releases/{commit}/{SERVER_PATH} "
        "--config /etc/mastermind/research-read-deployment.json",
        "EnvironmentFile=/etc/mastermind/research-read.env", "NoNewPrivileges=true",
        "ProtectSystem=strict", "ProtectHome=true", "PrivateTmp=true", "UMask=0077",
        "ReadWritePaths=/var/lib/mastermind-research/audit",
        "RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6",
        "CapabilityBoundingSet=", "AmbientCapabilities=",
    }
    allowed = required | {"[Unit]", "[Service]", "[Install]", "Type=simple",
        "Description=Mastermind Research Read MCP (pinned candidate)",
        "After=network-online.target", "Wants=network-online.target",
        "Restart=on-failure", "RestartSec=5", "WantedBy=multi-user.target"}
    lines = [line for line in rendered.splitlines() if line]
    if any(lines.count(line) != 1 for line in required) or any(line not in allowed for line in lines):
        raise StageRefused("STAGE_UNIT_REFUSED")
    return rendered



# Exact accepted proposal bytes; changing deployment semantics needs owner review.
CITATION_PROPOSALS = (
    ("ops/research_read_tunnel/mastermind-research-citation.socket", "mastermind-research-citation.socket", "ab706bf82e8c1b62993696a177078a6b26cec69d46e3a8abaf5044a4da277c77"),
    ("ops/research_read_tunnel/mastermind-research-read-citation.conf", "mastermind-research-read-citation.conf", "f72a49374a0ed0518b646adf0bc4708bbb5da897eb275be215989b96d8ec9a7c"),
    ("ops/research_read_tunnel/research-citation.tmpfiles.conf", "research-citation.tmpfiles.conf", "94418065cb60c201bcdda08ff214bd2680762ec6ef51e06777eb1cf4f233cfd5"),
    ("ops/research_read/research_evidence_http.caddy.fragment", "research_evidence_http.caddy.fragment", "e2c7c47ac550512b25202c8f94b8d9fef429134308a8c43de6c40e5b4849f44e"),
)


@dataclass(frozen=True)
class CitationProposalParameters:
    """Explicit trusted-owner inputs, not host custody or installation proof."""
    caddy_uid: int
    caddy_gid: int
    os_relay_port: int

    def __post_init__(self):
        if (type(self.caddy_uid) is not int or not 1 <= self.caddy_uid < 2**31
                or type(self.caddy_gid) is not int or not 1 <= self.caddy_gid < 2**31
                or type(self.os_relay_port) is not int or not 1 <= self.os_relay_port <= 65535):
            raise StageRefused("STAGE_PROPOSAL_REFUSED")


def render_citation_proposal(source_path, template, *, parameters, commit, lock_sha256):
    """Render ONLY reviewed fixed proposals; never an arbitrary target/template."""
    pins = {path: digest for path, _name, digest in CITATION_PROPOSALS}
    if (type(source_path) is not str or source_path not in pins
            or type(template) is not str or type(parameters) is not CitationProposalParameters
            or type(commit) is not str or _SHA.fullmatch(commit) is None
            or type(lock_sha256) is not str or _DIGEST.fullmatch(lock_sha256) is None):
        raise StageRefused("STAGE_PROPOSAL_REFUSED")
    try:
        if hashlib.sha256(template.encode("utf-8", errors="strict")).hexdigest() != pins[source_path]:
            raise StageRefused("STAGE_PROPOSAL_REFUSED")
        rendered = template
        for token, value in (("__QUALIFIED_CADDY_UID__", parameters.caddy_uid),
                             ("__QUALIFIED_CADDY_GID__", parameters.caddy_gid),
                             ("__OS_RELAY_PORT__", parameters.os_relay_port),
                             ("@MASTERMIND_COMMIT@", commit), ("@LOCK_SHA256@", lock_sha256)):
            rendered = rendered.replace(token, str(value))
        if re.search(r"__[A-Z0-9_]+__|@[A-Z0-9_]+@", rendered):
            raise StageRefused("STAGE_PROPOSAL_REFUSED")
        return rendered
    except UnicodeError:
        raise StageRefused("STAGE_PROPOSAL_REFUSED") from None


def _citation_artifacts(source, commit, lock_sha256, parameters):
    if type(parameters) is not CitationProposalParameters:
        raise StageRefused("STAGE_PROPOSAL_REFUSED")
    blobs, members = {}, []
    for source_path, name, source_sha256 in CITATION_PROPOSALS:
        # A Git symlink, executable or missing template cannot supply config bytes.
        row = _git(source, "ls-tree", "-l", commit, "--", source_path).strip()
        try:
            header, actual_path = row.split("\t")
            mode, kind, _oid, size = header.split()
            if mode != "100644" or kind != "blob" or actual_path != source_path or not 0 < int(size) <= 16384:
                raise ValueError()
        except ValueError:
            raise StageRefused("STAGE_PROPOSAL_REFUSED") from None
        raw = _git(source, "show", f"{commit}:{source_path}", binary=True)
        try:
            rendered = render_citation_proposal(source_path, raw.decode("utf-8", errors="strict"),
                parameters=parameters, commit=commit, lock_sha256=lock_sha256).encode("utf-8")
        except UnicodeError:
            raise StageRefused("STAGE_PROPOSAL_REFUSED") from None
        if name in blobs or len(PurePosixPath(name).parts) != 1:
            raise StageRefused("STAGE_PROPOSAL_REFUSED")
        _paths((name,))
        blobs[name] = rendered
        members.append({"path": name, "bytes": len(rendered),
            "sha256": hashlib.sha256(rendered).hexdigest(),
            "source_path": source_path, "source_sha256": source_sha256})
    return blobs, {"schema": "mastermind.research_read_citation_proposals.v1",
        "state": "INERT_PROPOSAL", "parameters": asdict(parameters), "members": members,
        "custody": "OWNER_QUALIFICATION_REQUIRED; active Caddy overlay, no file-only reload"}


def prepare_bundle(*, mastermind_source: Path, mastermind_commit: str, mastermind_tree: str,
                   macro_source: Path, macro_commit: str, macro_tree: str,
                   macro_roots, output: Path, citation_parameters: CitationProposalParameters | None = None,
                   include_producer: bool = False):
    """Write a NEW candidate directory; no overwrites or install effects."""
    try:
        if type(include_producer) is not bool:
            raise StageRefused("STAGE_PRODUCER_OPTION_REFUSED")
        qualify_source(mastermind_source, mastermind_commit, mastermind_tree)
        # The launcher must exist at the exact selected commit before staging.
        lock = _git(mastermind_source, "show", f"{mastermind_commit}:{LOCK_PATH}", binary=True)
        template = _git(mastermind_source, "show", f"{mastermind_commit}:{UNIT_PATH}")
        unit = render_unit(template, commit=mastermind_commit,
                           lock_sha256=hashlib.sha256(lock).hexdigest()).encode()
        proposal_blobs, proposal_receipt = ({}, None) if citation_parameters is None else _citation_artifacts(
            mastermind_source, mastermind_commit, hashlib.sha256(lock).hexdigest(), citation_parameters)
        mm, mm_members = source_archive(mastermind_source, mastermind_commit,
                                        mastermind_tree, MASTERMIND_ROOTS + ((PRODUCER_PATH,) if include_producer else ()))
        macro, macro_members = source_archive(macro_source, macro_commit, macro_tree, macro_roots)
        blobs = {"mastermind-release.tar": mm, "macro-release.tar": macro,
                 "mastermind-research-read.service": unit}
        if set(blobs) & set(proposal_blobs):
            raise StageRefused("STAGE_PROPOSAL_REFUSED")
        blobs.update(proposal_blobs)
        manifest = {"schema": SCHEMA, "state": "INERT_CANDIDATE",
                    "mastermind_commit": mastermind_commit, "mastermind_tree": mastermind_tree,
                    "macro_commit": macro_commit, "macro_tree": macro_tree,
                    "dependency_lock_sha256": hashlib.sha256(lock).hexdigest(),
                    "macro_import_closure": "OWNER_QUALIFICATION_REQUIRED",
                    "files": [{"path": name, "bytes": len(raw),
                               "sha256": hashlib.sha256(raw).hexdigest()} for name, raw in blobs.items()],
                    "members": {"mastermind": mm_members, "macro": macro_members}}
        if proposal_receipt is not None:
            proposal_metadata = (json.dumps(proposal_receipt, sort_keys=True, indent=2) + "\n").encode()
            name = "research-citation-proposals.json"
            if name in blobs:
                raise StageRefused("STAGE_PROPOSAL_REFUSED")
            blobs[name] = proposal_metadata
            manifest["files"].append({"path": name, "bytes": len(proposal_metadata),
                                      "sha256": hashlib.sha256(proposal_metadata).hexdigest()})
        blobs["manifest.json"] = (json.dumps(manifest, sort_keys=True, indent=2) + "\n").encode()
        if (not output.is_absolute() or output.exists()
                or any(path.is_symlink() for path in output.parents)):
            raise StageRefused("STAGE_OUTPUT_REFUSED")
        output.mkdir(mode=0o700)
        for name, raw in blobs.items():
            descriptor = os.open(output / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(raw)
        return manifest
    except StageRefused:
        raise
    except Exception:
        raise StageRefused() from None


def main(argv=None):
    """Thin local CLI over the same inert stager; never installs or dispatches."""
    import argparse
    import sys
    parser = argparse.ArgumentParser(description="Prepare an inert exact-source Research Read bundle")
    for name in ("mastermind-source", "mastermind-commit", "mastermind-tree",
                 "macro-source", "macro-commit", "macro-tree", "output"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--macro-root", action="append", required=True)
    parser.add_argument("--include-producer", action="store_true",
                        help="Include the separate producer operations launcher; no execution or admission")
    for name in ("caddy-uid", "caddy-gid", "os-relay-port"):
        parser.add_argument("--" + name, type=int)
    args = parser.parse_args(argv)
    values = (args.caddy_uid, args.caddy_gid, args.os_relay_port)
    if any(value is not None for value in values) and not all(value is not None for value in values):
        parser.error("citation proposal parameters must be supplied together")
    try:
        parameters = None if all(value is None for value in values) else CitationProposalParameters(*values)
        manifest = prepare_bundle(mastermind_source=Path(args.mastermind_source),
            mastermind_commit=args.mastermind_commit, mastermind_tree=args.mastermind_tree,
            macro_source=Path(args.macro_source), macro_commit=args.macro_commit, macro_tree=args.macro_tree,
            macro_roots=args.macro_root, output=Path(args.output), citation_parameters=parameters,
            include_producer=args.include_producer)
    except StageRefused as error:
        print(error.code, file=sys.stderr)
        return 2
    print(json.dumps(manifest, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
