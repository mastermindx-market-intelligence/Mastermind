#!/usr/bin/env python3
"""Install T3 skills and reuse the existing qualified computer/browser MCP owners.

No provider activation, credentials, permission grants, process restart or new daemon.
Preview binds all preimages and proposed bytes. Apply refuses a changed plan; rollback
restores only exact postimages. Receipts contain hashes and paths, never config values.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile

SKILLS = ("mastermind-computer-use", "mastermind-browser-use")
QUIET_SHA256 = "09924847ff1fe85c328476b719dfa459a95e92ced6013c0b73eb077d3ea7d822"
PEEKABOO_SHA256 = "6e2d9f91cf95689cc061d138cb26f023b511c434f571436c1ae139d040a0f3b4"
SCHEMA = "mastermind.t3_computer_use_install.v1"


class SetupError(RuntimeError):
    pass


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read_regular(path: Path, maximum: int = 8 * 1024 * 1024) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    fd = os.open(path, flags)
    try:
        before = os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode) or before.st_size > maximum
                or before.st_uid != os.getuid() or before.st_mode & 0o022):
            raise SetupError(f"Unsafe file: {path}")
        data = os.read(fd, maximum + 1)
        after = os.fstat(fd)
        if len(data) > maximum or (before.st_ino, before.st_size, before.st_mtime_ns) != (
                after.st_ino, after.st_size, after.st_mtime_ns):
            raise SetupError(f"File changed while reading: {path}")
        return data
    finally:
        os.close(fd)


def parse_json(raw: bytes, path: Path) -> dict:
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise SetupError(f"Duplicate JSON key in {path}: {key}")
            result[key] = value
        return result
    obj = json.loads(raw, object_pairs_hook=pairs)
    if not isinstance(obj, dict):
        raise SetupError(f"Expected object: {path}")
    return obj


def load_json(path: Path) -> dict:
    return parse_json(read_regular(path), path)


def current(path: Path) -> dict:
    if path.is_symlink():
        return {"kind": "symlink", "target": os.readlink(path)}
    if path.exists():
        return {"kind": "file", "sha256": digest(read_regular(path))}
    return {"kind": "absent"}


def public_operation(op: dict) -> dict:
    return {key: value for key, value in op.items() if key != "content"}


def make_plan(t3_home: Path, source_root: Path, user_home: Path | None = None) -> dict:
    t3_home = t3_home.resolve()
    user_home = (user_home or Path.home()).resolve()
    settings_path = t3_home / "userdata/settings.json"
    settings_raw = read_regular(settings_path)
    settings = parse_json(settings_raw, settings_path)
    instances = settings.get("providerInstances", {})
    if not isinstance(instances, dict):
        raise SetupError("providerInstances is not an object")
    providers = []
    for name, instance in instances.items():
        if not isinstance(instance, dict) or instance.get("enabled") is not True:
            continue
        if instance.get("driver") != "claudeAgent":
            raise SetupError(f"Enabled provider {name} needs its own adapter; not changed")
        home_value = instance.get("config", {}).get("homePath")
        if not isinstance(home_value, str) or not Path(home_value).is_absolute():
            raise SetupError(f"Enabled provider {name} has no explicit absolute home")
        provider_home = Path(home_value).resolve()
        if not provider_home.is_relative_to(t3_home / "providers") or not provider_home.is_dir():
            raise SetupError(f"Provider {name} is outside the verified T3 provider homes")
        providers.append((name, provider_home))
    if not providers or len({p for _, p in providers}) != len(providers):
        raise SetupError("Missing or ambiguously shared enabled provider homes")

    quiet = user_home / ".cursor/quiet-computer-use/quiet_mcp.py"
    peekaboo = quiet.parent / "vendor/peekaboo-macos-arm64/peekaboo"
    browser = t3_home / "mcp/mmx-browser/server.js"
    runtime = browser.with_name("runtime.json")
    node = user_home / ".local/share/mastermind-runtime/node/bin/node"
    if digest(read_regular(quiet)) != QUIET_SHA256:
        raise SetupError("Existing quiet adapter differs from the qualified revision")
    if not peekaboo.is_file() or not os.access(peekaboo, os.X_OK) or file_digest(peekaboo) != PEEKABOO_SHA256:
        raise SetupError("Existing signed Peekaboo binary differs from the qualified artifact")
    read_regular(browser)
    descriptor = load_json(runtime)
    if descriptor.get("schema") != "mastermind.browser.mcp_runtime/v1":
        raise SetupError("Existing Mastermind browser descriptor has an unknown schema")
    if not node.is_file() or not os.access(node, os.X_OK):
        raise SetupError("Existing Mastermind browser Node runtime is unavailable")
    expected = {
        "peekaboo": {"type": "stdio", "command": "/usr/bin/python3", "args": [str(quiet)]},
        "mmx-browser": {"type": "stdio", "command": str(node), "args": [str(browser)]},
    }
    operations = []
    dependencies = [{"path": str(settings_path), "sha256": digest(settings_raw)},
                    {"path": str(quiet), "sha256": QUIET_SHA256},
                    {"path": str(peekaboo), "sha256": PEEKABOO_SHA256},
                    {"path": str(browser), "sha256": digest(read_regular(browser))},
                    {"path": str(runtime), "sha256": digest(read_regular(runtime))}]

    def file_change(path: Path, data: bytes, expected_before: dict | None = None):
        if not path.parent.resolve().is_relative_to(t3_home):
            raise SetupError(f"Target parent escapes T3 home: {path}")
        before = current(path)
        if expected_before is not None and before != expected_before:
            raise SetupError(f"Configuration changed while planning: {path}")
        if before["kind"] == "symlink":
            raise SetupError(f"Refusing to replace a symlink: {path}")
        after = {"kind": "file", "sha256": digest(data)}
        if before != after:
            operations.append({"path": str(path), "before": before, "after": after,
                               "content": data.decode("utf-8")})

    for skill in SKILLS:
        skill_source = source_root / "skills" / skill / "SKILL.md"
        data = read_regular(skill_source)
        text = data.decode("utf-8")
        if not text.startswith(f"---\nname: {skill}\ndescription: ") or "\n---\n" not in text[4:]:
            raise SetupError(f"Invalid skill frontmatter: {skill}")
        file_change(t3_home / "skills" / skill / "SKILL.md", data)

    for name, provider_home in sorted(providers):
        config_path = provider_home / ".claude.json"
        config_raw = read_regular(config_path)
        config = parse_json(config_raw, config_path)
        servers = config.setdefault("mcpServers", {})
        if not isinstance(servers, dict):
            raise SetupError(f"Invalid MCP map in {name}")
        changed = False
        for server_name, desired in expected.items():
            old = servers.get(server_name)
            comparable = dict(old) if isinstance(old, dict) else old
            if isinstance(comparable, dict) and comparable.get("env") == {}:
                comparable.pop("env")  # existing Claude configs commonly persist an empty env
            if old is not None and comparable != desired:
                raise SetupError(f"Conflicting {server_name} server in {name}; preserved")
            if old is None:
                servers[server_name] = desired
                changed = True
        if changed:
            file_change(config_path, (json.dumps(config, ensure_ascii=False, indent=2) + "\n").encode(),
                        {"kind": "file", "sha256": digest(config_raw)})
        else:
            dependencies.append({"path": str(config_path), "sha256": digest(config_raw)})
        for skill in SKILLS:
            target = t3_home / "skills" / skill
            link = provider_home / "skills" / skill
            if not link.parent.resolve().is_relative_to(t3_home):
                raise SetupError(f"Skill parent escapes T3 home: {link}")
            before = current(link)
            if before["kind"] == "symlink" and link.resolve() == target.resolve():
                continue
            if before["kind"] != "absent":
                raise SetupError(f"Conflicting provider skill preserved: {link}")
            operations.append({"path": str(link), "before": before,
                               "after": {"kind": "symlink", "target": str(target)}})
    public = {"schema": SCHEMA, "t3_home": str(t3_home), "providers": [n for n, _ in sorted(providers)],
              "dependencies": dependencies, "operations": [public_operation(op) for op in operations]}
    plan_sha256 = digest(json.dumps(public, sort_keys=True, separators=(",", ":")).encode())
    return dict(public, plan_sha256=plan_sha256, operations=operations)


def atomic_file(path: Path, data: bytes, expected: dict, mode: int = 0o600):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".t3-computer-use-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            os.fchmod(stream.fileno(), mode)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if current(path) != expected:
            raise SetupError(f"Preimage changed; preserved: {path}")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def apply_plan(plan: dict, expected_plan_sha256: str) -> dict:
    if plan["plan_sha256"] != expected_plan_sha256:
        raise SetupError("Preview is stale; no changes applied")
    for dependency in plan["dependencies"]:
        if file_digest(Path(dependency["path"])) != dependency["sha256"]:
            raise SetupError(f"Dependency changed: {dependency['path']}")
    for op in plan["operations"]:
        if not Path(op["path"]).parent.resolve().is_relative_to(Path(plan["t3_home"])):
            raise SetupError(f"Target parent changed: {op['path']}")
        if current(Path(op["path"])) != op["before"]:
            raise SetupError(f"Preimage changed: {op['path']}")
    if not plan["operations"]:
        return {"schema": SCHEMA, "state": "ALREADY_INSTALLED", "providers": plan["providers"]}
    backup_root = Path(plan["t3_home"]) / "backups/computer-use"
    backup_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    backup_dir = Path(tempfile.mkdtemp(prefix="install-", dir=backup_root))
    receipt_path = backup_dir / "receipt.json"
    receipt = {"schema": SCHEMA, "state": "APPLYING", "plan_sha256": expected_plan_sha256,
               "t3_home": plan["t3_home"], "providers": plan["providers"], "operations": []}

    def save():
        atomic_file(receipt_path, (json.dumps(receipt, indent=2) + "\n").encode(), current(receipt_path))

    save()
    try:
        for index, op in enumerate(plan["operations"]):
            path = Path(op["path"])
            entry = dict(public_operation(op), state="PREPARED")
            if op["before"]["kind"] == "file":
                backup = backup_dir / f"{index:02d}.before"
                before = read_regular(path)
                if digest(before) != op["before"]["sha256"]:
                    raise SetupError(f"Preimage changed before backup: {path}")
                atomic_file(backup, before, {"kind": "absent"})
                entry["backup"] = str(backup)
            receipt["operations"].append(entry)
            save()  # an interrupted write remains reconcilable at its original target
            if op["after"]["kind"] == "symlink":
                path.parent.mkdir(parents=True, exist_ok=True)
                os.symlink(op["after"]["target"], path)  # exclusive creation, never replace
            else:
                atomic_file(path, op["content"].encode(), op["before"])
            if current(path) != op["after"]:
                raise SetupError(f"Postimage verification failed: {path}")
            entry["state"] = "VERIFIED"
            save()
        receipt["state"] = "INSTALLED_NOT_CONSUMER_PROVEN"
        save()
    except Exception:
        receipt["state"] = "PARTIAL_RECONCILE_ORIGINAL_TARGETS"
        save()
        raise SetupError(f"Apply stopped; reconcile exact targets using {receipt_path}") from None
    return {"schema": SCHEMA, "state": receipt["state"], "receipt": str(receipt_path),
            "receipt_sha256": digest(read_regular(receipt_path)), "providers": plan["providers"],
            "changed_paths": [op["path"] for op in receipt["operations"]]}


def rollback(receipt_path: Path, expected_sha256: str) -> dict:
    raw = read_regular(receipt_path)
    if digest(raw) != expected_sha256:
        raise SetupError("Receipt changed; refusing rollback")
    receipt = load_json(receipt_path)
    if receipt.get("schema") != SCHEMA or receipt.get("state") != "INSTALLED_NOT_CONSUMER_PROVEN":
        raise SetupError("Only a verified completed installation can be rolled back automatically")
    root = Path(receipt["t3_home"]).resolve()
    if not receipt_path.resolve().is_relative_to(root / "backups/computer-use"):
        raise SetupError("Receipt is outside the installation backup owner")
    for op in receipt["operations"]:
        path = Path(op["path"])
        if not path.parent.resolve().is_relative_to(root) or current(path) != op["after"]:
            raise SetupError(f"Later change preserved; rollback stopped: {path}")
        if op["before"]["kind"] == "file":
            backup = Path(op["backup"])
            if backup.parent.resolve() != receipt_path.parent.resolve() or digest(read_regular(backup)) != op["before"]["sha256"]:
                raise SetupError("Backup mismatch; refusing rollback")
    for op in reversed(receipt["operations"]):
        path = Path(op["path"])
        if current(path) != op["after"]:
            raise SetupError(f"Concurrent update preserved: {path}")
        if op["before"]["kind"] == "file":
            atomic_file(path, read_regular(Path(op["backup"])), op["after"])
        else:
            path.unlink()
    receipt["state"] = "ROLLED_BACK"
    atomic_file(receipt_path, (json.dumps(receipt, indent=2) + "\n").encode(), {"kind": "file", "sha256": expected_sha256})
    return {"schema": SCHEMA, "state": "ROLLED_BACK", "receipt": str(receipt_path)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["plan", "apply", "verify", "rollback"])
    parser.add_argument("--t3-home", type=Path, default=Path.home() / ".t3")
    parser.add_argument("--source-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--expected-plan-sha256")
    parser.add_argument("--receipt", type=Path)
    parser.add_argument("--expected-receipt-sha256")
    args = parser.parse_args()
    try:
        if args.action == "rollback":
            if not args.receipt or not args.expected_receipt_sha256:
                parser.error("rollback needs --receipt and --expected-receipt-sha256")
            result = rollback(args.receipt, args.expected_receipt_sha256)
        else:
            plan = make_plan(args.t3_home, args.source_root)
            if args.action == "apply":
                if not args.expected_plan_sha256:
                    parser.error("apply needs the preceding preview's --expected-plan-sha256")
                result = apply_plan(plan, args.expected_plan_sha256)
            else:
                result = dict(plan, operations=[public_operation(op) for op in plan["operations"]])
                result["state"] = "INSTALLED_NOT_CONSUMER_PROVEN" if not plan["operations"] else "CHANGES_NEEDED"
        print(json.dumps(result, indent=2))
        return 0
    except (SetupError, OSError, ValueError) as error:
        print(json.dumps({"schema": SCHEMA, "state": "REFUSED", "reason": str(error)}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
