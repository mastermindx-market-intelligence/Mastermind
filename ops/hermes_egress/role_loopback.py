"""Fixed, root-owned route prerequisite for the incumbent Hermes proxy.

Source only until released and installed. No daemon, credentials, arbitrary
network arguments, service activation, retry loop, or automatic stop cleanup.
Exit 78 from ExecCondition skips proxy startup without a restart storm.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import uuid


ALIASES = ("127.0.0.2", "127.0.0.3")
ROLE_UNITS = ("hermes-runtime-mmsecretary.service", "hermes-runtime-mmmeta.service")
PROXY_UNIT = "hermes-egress.service"
INSTALLED_PATH = Path("/usr/local/libexec/mastermind-hermes-loopback.py")
STATE_DIR = Path("/run/mastermind-hermes-network")
IP = "/usr/sbin/ip"
SYSTEMCTL = "/usr/bin/systemctl"
SCHEMA = "mastermind.hermes.loopback-route.v1"
REFUSED = 78
MAX_BYTES = 65536
STATES = frozenset({"ABSENT", "ADD_DISPATCHED", "ADD_ACKNOWLEDGED", "OWNED",
                    "ADD_REFUSED", "DELETE_DISPATCHED", "DELETE_ACKNOWLEDGED",
                    "DELETE_REFUSED", "REMOVED", "CANCELLED"})


class Refusal(Exception):
    """A fixed public reason, never a subprocess output or environment dump."""


def canonical(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"),
                       ensure_ascii=True, allow_nan=False) + "\n").encode("ascii")


def _pairs(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise Refusal("DUPLICATE_JSON_KEY")
        value[key] = item
    return value


def decode(raw: bytes | str):
    if len(raw) > MAX_BYTES:
        raise Refusal("OBSERVATION_TOO_LARGE")
    try:
        return json.loads(raw, object_pairs_hook=_pairs,
                          parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    except (ValueError, UnicodeError, TypeError):
        raise Refusal("OBSERVATION_INVALID") from None


def route_command(verb: str, alias: str) -> list[str]:
    if verb not in {"add", "del"} or alias not in ALIASES:
        raise Refusal("FIXED_PLAN_REQUIRED")
    return [IP, "-4", "route", verb, "local", alias + "/32", "dev", "lo",
            "table", "local", "proto", "static", "scope", "host", "src", alias]


def exact_route(rows, alias: str) -> bool:
    if not isinstance(rows, list) or len(rows) != 1 or type(rows[0]) is not dict:
        return False
    row = dict(rows[0])
    if row.pop("flags", []) != [] or row.pop("table", "local") != "local":
        return False
    if row.get("dst") == alias + "/32":
        row["dst"] = alias
    return row == {"type": "local", "dst": alias, "dev": "lo",
                   "protocol": "static", "scope": "host", "prefsrc": alias}


def validate_context(context):
    if type(context) is not dict or set(context) != {"rules", "loopback", "ordinary"}:
        raise Refusal("ROUTING_CONTEXT_INVALID")
    rules = context["rules"]
    if (not isinstance(rules, list) or not rules
            or type(rules[0]) is not dict or type(rules[0].get("priority")) is not int
            or rules[0] != {"priority": 0, "src": "all", "table": "local"}
            or any(type(r) is not dict or type(r.get("priority")) is not int
                   or r["priority"] <= 0 for r in rules[1:])):
        raise Refusal("UNIVERSAL_FIRST_LOCAL_RULE_REQUIRED")
    lo = context["loopback"]
    if (type(lo) is not dict or set(lo) != {"ifindex", "ifname", "flags", "link_type"}
            or type(lo["ifindex"]) is not int or lo["ifindex"] < 1
            or lo["ifname"] != "lo" or lo["link_type"] != "loopback"
            or not isinstance(lo["flags"], list)
            or any(not isinstance(flag, str) for flag in lo["flags"])
            or not {"UP", "LOOPBACK"}.issubset(lo["flags"])):
        raise Refusal("LOOPBACK_UNQUALIFIED")
    ordinary = context["ordinary"]
    if (not isinstance(ordinary, list) or len(ordinary) != 1
            or type(ordinary[0]) is not dict
            or ordinary[0].get("dst") != "127.0.0.0/8"
            or ordinary[0].get("type") != "local"
            or ordinary[0].get("dev") != "lo"
            or ordinary[0].get("scope") != "host"):
        raise Refusal("ORDINARY_LOOPBACK_ROUTE_REQUIRED")


def validate_receipt(value, identity, context):
    if (type(value) is not dict
            or set(value) != {"schema", "transaction", "identity", "context", "routes"}
            or value["schema"] != SCHEMA
            or not isinstance(value["transaction"], str)
            or not re.fullmatch(r"[0-9a-f]{32}", value["transaction"])
            or canonical(value["identity"]) != canonical(identity)
            or canonical(value["context"]) != canonical(context)
            or type(value["routes"]) is not dict or set(value["routes"]) != set(ALIASES)):
        raise Refusal("RECEIPT_EPOCH_OR_CONTEXT_MISMATCH")
    for alias, entry in value["routes"].items():
        if (type(entry) is not dict
                or set(entry) != {"state", "before", "after", "dispatch", "ack"}
                or not isinstance(entry["state"], str)
                or entry["state"] not in STATES or entry["before"] != []):
            raise Refusal("RECEIPT_INVALID")
        state = entry["state"]
        if state in {"ABSENT", "CANCELLED"}:
            if any(entry[k] is not None for k in ("after", "dispatch", "ack")):
                raise Refusal("RECEIPT_INVALID")
            continue
        deleting = state.startswith("DELETE_") or state == "REMOVED"
        verb = "del" if deleting else "add"
        if entry["dispatch"] != route_command(verb, alias):
            raise Refusal("RECEIPT_INVALID")
        ack = entry["ack"]
        if state.endswith("DISPATCHED"):
            if ack is not None:
                raise Refusal("RECEIPT_INVALID")
        elif type(ack) is not int or (state.endswith("REFUSED") == (ack == 0)):
            raise Refusal("RECEIPT_INVALID")
        if (state in {"OWNED", "DELETE_DISPATCHED", "DELETE_ACKNOWLEDGED", "DELETE_REFUSED"}
                and not exact_route(entry["after"], alias)):
            raise Refusal("RECEIPT_INVALID")
        if state == "REMOVED" and entry["after"] != []:
            raise Refusal("RECEIPT_INVALID")


class LinuxHost:
    """Only fixed host queries/mutations; subprocess environment is closed."""

    def run(self, argv):
        try:
            r = subprocess.run(argv, capture_output=True, timeout=8, check=False, stdin=subprocess.DEVNULL,
                               env={"PATH": "/usr/sbin:/usr/bin", "LC_ALL": "C"})
        except (OSError, subprocess.TimeoutExpired):
            raise Refusal("COMMAND_OUTCOME_UNAVAILABLE") from None
        if len(r.stdout) > MAX_BYTES or len(r.stderr) > MAX_BYTES:
            raise Refusal("COMMAND_OUTPUT_TOO_LARGE")
        return r

    def query(self, argv):
        r = self.run(argv)
        if r.returncode != 0:
            raise Refusal("HOST_QUERY_REFUSED")
        return decode(r.stdout)

    def context(self):
        links = self.query([IP, "-j", "link", "show", "dev", "lo"])
        if not isinstance(links, list) or len(links) != 1 or type(links[0]) is not dict:
            raise Refusal("LOOPBACK_UNQUALIFIED")
        value = {
            "rules": self.query([IP, "-j", "-4", "rule", "show"]),
            "loopback": {k: links[0].get(k) for k in ("ifindex", "ifname", "flags", "link_type")},
            "ordinary": self.query([IP, "-j", "-4", "route", "show", "table", "local",
                                    "exact", "127.0.0.0/8"]),
        }
        validate_context(value)
        return value

    def routes(self):
        rows = {a: self.query([IP, "-j", "-4", "route", "show", "table", "local",
                              "exact", a + "/32"]) for a in ALIASES}
        if any(not isinstance(v, list) for v in rows.values()):
            raise Refusal("ROUTE_OBSERVATION_INVALID")
        return rows

    def sources(self):
        for alias in ALIASES:
            rows = self.query([IP, "-j", "-4", "route", "get", alias])
            if (not isinstance(rows, list) or len(rows) != 1 or type(rows[0]) is not dict
                    # Qualified iproute2 omits the redundant table in this
                    # lookup. The exact local FIB row is checked separately;
                    # an explicit different table still refuses.
                    or rows[0].get("table", "local") != "local"
                    or set(rows[0]) - {"type", "dst", "dev", "table", "prefsrc", "flags", "uid", "cache"}
                    or rows[0].get("flags", []) != []
                    or any(rows[0].get(k) != v for k, v in
                           {"type": "local", "dst": alias, "dev": "lo",
                            "prefsrc": alias}.items())):
                raise Refusal("UNBOUND_SOURCE_SELECTION_UNQUALIFIED")

    def quiescent(self, *, rollback=False):
        for unit in (*ROLE_UNITS, PROXY_UNIT):
            r = self.run([SYSTEMCTL, "show", unit, "--no-pager",
                          "--property=LoadState,ActiveState,SubState,MainPID,ControlGroup"])
            if r.returncode != 0:
                raise Refusal("UNIT_STATE_UNAVAILABLE")
            try:
                fields = dict(line.split("=", 1) for line in r.stdout.decode("ascii").splitlines())
            except (ValueError, UnicodeError):
                raise Refusal("UNIT_STATE_INVALID") from None
            if (set(fields) != {"LoadState", "ActiveState", "SubState", "MainPID", "ControlGroup"}
                    or fields["LoadState"] not in {"loaded", "not-found"}
                    or fields["MainPID"] != "0"):
                raise Refusal("UNITS_NOT_QUIESCENT")
            own_condition = (unit == PROXY_UNIT and not rollback
                             and fields["ActiveState"] == "activating"
                             and fields["SubState"] == "condition"
                             and fields["ControlGroup"] == "/system.slice/" + PROXY_UNIT)
            if not own_condition and not (fields["ActiveState"] in {"inactive", "failed"}
                                          and fields["SubState"] in {"dead", "failed"}):
                raise Refusal("UNITS_NOT_QUIESCENT")
            group = fields["ControlGroup"]
            if group:
                if group != "/system.slice/" + unit:
                    raise Refusal("UNIT_CGROUP_INVALID")
                try:
                    members = (Path("/sys/fs/cgroup") / group.lstrip("/") / "cgroup.procs").read_text("ascii").split()
                    group_stat = (Path("/sys/fs/cgroup") / group.lstrip("/") / "cgroup.stat").read_text("ascii")
                    descendants = dict(line.split() for line in group_stat.splitlines()).get("nr_descendants")
                    own_group = Path("/proc/self/cgroup").read_text("ascii").splitlines()
                except (OSError, UnicodeError, ValueError):
                    raise Refusal("UNIT_CGROUP_UNAVAILABLE") from None
                if descendants != "0":
                    raise Refusal("UNIT_DESCENDANT_CGROUPS_PRESENT")
                if own_condition:
                    if set(members) != {str(os.getpid())} or "0::" + group not in own_group:
                        raise Refusal("PROXY_CONDITION_NOT_EXCLUSIVE")
                elif members:
                    raise Refusal("UNITS_NOT_QUIESCENT")


def _trusted_path(path: Path, *, directory=False):
    for parent in reversed(path.parents):
        st = parent.lstat()
        if not stat.S_ISDIR(st.st_mode) or st.st_uid != 0 or st.st_mode & 0o022:
            raise Refusal("ROOT_PATH_CUSTODY_INVALID")
    st = path.lstat()
    kind = stat.S_ISDIR(st.st_mode) if directory else stat.S_ISREG(st.st_mode)
    if not kind or st.st_uid != 0 or st.st_mode & 0o022:
        raise Refusal("ROOT_PATH_CUSTODY_INVALID")
    return st


def installed_identity():
    if not sys.platform.startswith("linux") or os.geteuid() != 0:
        raise Refusal("ROOT_LINUX_REQUIRED")
    if Path(__file__).absolute() != INSTALLED_PATH:
        raise Refusal("FIXED_ROOT_INSTALLED_HELPER_REQUIRED")
    st = _trusted_path(INSTALLED_PATH)
    if st.st_nlink != 1 or st.st_size > MAX_BYTES:
        raise Refusal("HELPER_CUSTODY_INVALID")
    fd = os.open(INSTALLED_PATH, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        actual = os.fstat(fd)
        if (actual.st_dev, actual.st_ino) != (st.st_dev, st.st_ino):
            raise Refusal("HELPER_CHANGED")
        source = os.read(fd, MAX_BYTES + 1)
    finally:
        os.close(fd)
    here = os.stat("/proc/self/ns/net")
    init = os.stat("/proc/1/ns/net")
    if (here.st_dev, here.st_ino) != (init.st_dev, init.st_ino):
        raise Refusal("PID1_NETWORK_NAMESPACE_REQUIRED")
    machine = Path("/etc/machine-id").read_text("ascii").strip()
    boot = Path("/proc/sys/kernel/random/boot_id").read_text("ascii").strip()
    if (not re.fullmatch(r"[0-9a-f]{32}", machine)
            or not re.fullmatch(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", boot)):
        raise Refusal("HOST_IDENTITY_UNAVAILABLE")
    return {"machine": machine, "boot": boot, "netns": [here.st_dev, here.st_ino],
            "helper_sha256": hashlib.sha256(source).hexdigest()}


class RootStore:
    """One root-only receipt under a nonblocking lock, separate from proxy state.

    The lock coordinates this helper only. It is not a CAS against other root
    network writers. Host admission must exclude concurrent foreign route edits.
    """

    def __init__(self, directory=STATE_DIR):
        self.directory = directory
        self.dirfd = self.lockfd = None
        self.observed = False
        self.preimage = None

    def __enter__(self):
        _trusted_path(self.directory.parent, directory=True)
        try:
            self.directory.mkdir(mode=0o700)
        except FileExistsError:
            pass
        st = _trusted_path(self.directory, directory=True)
        if stat.S_IMODE(st.st_mode) != 0o700:
            raise Refusal("STATE_DIRECTORY_PRIVATE_REQUIRED")
        self.dirfd = os.open(self.directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            opened = os.fstat(self.dirfd)
            if (opened.st_dev, opened.st_ino) != (st.st_dev, st.st_ino):
                raise Refusal("STATE_DIRECTORY_CHANGED")
            self.lockfd = os.open("lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC,
                                  0o600, dir_fd=self.dirfd)
            self._file_custody(self.lockfd)
            fcntl.flock(self.lockfd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return self
        except BaseException:
            self.__exit__(None, None, None)
            raise

    def __exit__(self, *_):
        for fd in (self.lockfd, self.dirfd):
            if fd is not None:
                os.close(fd)
        self.lockfd = self.dirfd = None

    @staticmethod
    def _file_custody(fd):
        st = os.fstat(fd)
        if (not stat.S_ISREG(st.st_mode) or st.st_uid != 0 or st.st_nlink != 1
                or stat.S_IMODE(st.st_mode) != 0o600 or st.st_size > MAX_BYTES):
            raise Refusal("RECEIPT_CUSTODY_INVALID")

    def _read_raw(self):
        lock = os.stat("lock", dir_fd=self.dirfd, follow_symlinks=False)
        held = os.fstat(self.lockfd)
        self._file_custody(self.lockfd)
        if (lock.st_dev, lock.st_ino) != (held.st_dev, held.st_ino):
            raise Refusal("LOCK_INODE_CHANGED")
        try:
            fd = os.open("receipt.json", os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC,
                         dir_fd=self.dirfd)
        except FileNotFoundError:
            return None
        try:
            self._file_custody(fd)
            raw = os.read(fd, MAX_BYTES + 1)
            return raw
        finally:
            os.close(fd)

    def read(self):
        raw = self._read_raw()
        value = None if raw is None else decode(raw)
        self.observed, self.preimage = True, raw
        return value

    def save(self, value):
        raw = canonical(value)
        if len(raw) > MAX_BYTES:
            raise Refusal("RECEIPT_TOO_LARGE")
        # A changed receipt is another writer/effect, even if its JSON is valid.
        # This check plus the lock is not a kernel CAS against a foreign root.
        if not self.observed or self._read_raw() != self.preimage:
            raise Refusal("RECEIPT_PREIMAGE_CHANGED")
        name = ".receipt-" + uuid.uuid4().hex
        fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                     0o600, dir_fd=self.dirfd)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            if self.preimage is None:
                os.link(name, "receipt.json", src_dir_fd=self.dirfd, dst_dir_fd=self.dirfd,
                        follow_symlinks=False)  # exclusive first publication
                os.unlink(name, dir_fd=self.dirfd)
            else:
                os.replace(name, "receipt.json", src_dir_fd=self.dirfd, dst_dir_fd=self.dirfd)
            os.fsync(self.dirfd)
            if self._read_raw() != raw:
                raise Refusal("RECEIPT_POSTIMAGE_CHANGED")
            self.preimage = raw
        finally:
            try:
                os.unlink(name, dir_fd=self.dirfd)
            except FileNotFoundError:
                pass


def _check_current(receipt, context, rows, *, pending=False):
    if canonical(receipt["context"]) != canonical(context):
        raise Refusal("ROUTING_CONTEXT_CHANGED")
    for alias, entry in receipt["routes"].items():
        state = entry["state"]
        if state == "OWNED":
            if canonical(rows[alias]) != canonical(entry["after"]) or not exact_route(rows[alias], alias):
                raise Refusal("OWNED_ROUTE_CHANGED")
        elif state in {"ABSENT", "REMOVED", "CANCELLED"}:
            if rows[alias] != []:
                raise Refusal("UNOWNED_ROUTE_PRESENT")
        elif not pending:
            raise Refusal("ORIGINAL_EFFECT_RECONCILIATION_REQUIRED")


def operate(verb: str, host, store, identity):
    """Finite exact-plan state machine. Tests inject host/store, never CLI flags."""
    if verb not in {"status", "ensure", "reconcile", "rollback"}:
        raise Refusal("FIXED_VERB_REQUIRED")
    context, rows = host.context(), host.routes()
    validate_context(context)
    receipt = store.read()
    if receipt is None:
        classifications = {a: ("ABSENT" if rows[a] == [] else
                               "EXTERNAL_EXACT" if exact_route(rows[a], a) else "CONFLICT")
                           for a in ALIASES}
        if verb == "status":
            return {"status": "NO_OWNED_RECEIPT", "routes": classifications}
        if verb != "ensure" or any(v != "ABSENT" for v in classifications.values()):
            raise Refusal("EXTERNAL_ROUTE_RECONCILIATION_REQUIRED")
        host.quiescent()
        receipt = {"schema": SCHEMA, "transaction": uuid.uuid4().hex,
                   "identity": identity, "context": context,
                   "routes": {a: {"state": "ABSENT", "before": [], "after": None,
                                  "dispatch": None, "ack": None} for a in ALIASES}}
        store.save(receipt)
    validate_receipt(receipt, identity, context)

    if verb == "reconcile":
        # A durable success ACK plus exact current image can reconcile. A lost
        # ACK cannot: matching state alone never turns a foreign route into ours.
        _check_current(receipt, context, rows, pending=True)
        for alias, entry in receipt["routes"].items():
            if entry["state"] == "ADD_ACKNOWLEDGED" and exact_route(rows[alias], alias):
                entry.update(state="OWNED", after=rows[alias])
                store.save(receipt)
            elif entry["state"] == "DELETE_ACKNOWLEDGED" and rows[alias] == []:
                entry.update(state="REMOVED", after=[])
                store.save(receipt)
        _check_current(receipt, host.context(), host.routes())
        return {"status": "RECONCILED", "transaction": receipt["transaction"],
                "routes": {a: e["state"] for a, e in receipt["routes"].items()}}

    _check_current(receipt, context, rows)
    if verb == "status":
        complete = all(e["state"] == "OWNED" for e in receipt["routes"].values())
        if complete:
            host.sources()
            _check_current(receipt, host.context(), host.routes())
        return {"status": "SOURCE_SELECTION_QUALIFIED" if complete else "INCOMPLETE",
                "transaction": receipt["transaction"],
                "routes": {a: e["state"] for a, e in receipt["routes"].items()}}

    if verb == "ensure" and any(e["state"] in {"REMOVED", "CANCELLED"} for e in receipt["routes"].values()):
        raise Refusal("ROLLED_BACK_TRANSACTION_RETAINED")
    targets = [a for a in (ALIASES if verb == "ensure" else reversed(ALIASES))
               if receipt["routes"][a]["state"] == ("ABSENT" if verb == "ensure" else "OWNED")]
    for alias in targets:
        host.quiescent(rollback=verb == "rollback")
        _check_current(receipt, host.context(), host.routes())  # both /32s, every dispatch
        entry = receipt["routes"][alias]
        action = "ADD" if verb == "ensure" else "DELETE"
        entry.update(state=action + "_DISPATCHED", dispatch=route_command(
            "add" if verb == "ensure" else "del", alias), ack=None)
        store.save(receipt)  # fsync intent BEFORE kernel dispatch
        try:
            result = host.run(entry["dispatch"])
        except Refusal:
            raise Refusal("ORIGINAL_EFFECT_RECONCILIATION_REQUIRED") from None
        if result.returncode < 0:
            # The ip child died by signal. A possible netlink effect is not a
            # negative kernel acknowledgement; keep the dispatched uncertainty.
            raise Refusal("COMMAND_TERMINATED_ACK_UNKNOWN")
        entry.update(state=action + ("_ACKNOWLEDGED" if result.returncode == 0 else "_REFUSED"),
                     ack=result.returncode)
        store.save(receipt)  # fsync actual ACK BEFORE claiming ownership/removal
        if result.returncode != 0:
            raise Refusal("ORIGINAL_EFFECT_RECONCILIATION_REQUIRED")
        post = host.routes()[alias]
        if canonical(host.context()) != canonical(context):
            raise Refusal("ROUTING_CONTEXT_CHANGED")
        if verb == "ensure":
            if not exact_route(post, alias):
                raise Refusal("ACKNOWLEDGED_ROUTE_POSTIMAGE_MISMATCH")
            entry.update(state="OWNED", after=post)
        else:
            if post != []:
                raise Refusal("ACKNOWLEDGED_DELETE_POSTIMAGE_MISMATCH")
            entry.update(state="REMOVED", after=[])
        store.save(receipt)
    if verb == "rollback":
        # Close an unissued step without pretending any delete was dispatched.
        for entry in receipt["routes"].values():
            if entry["state"] == "ABSENT":
                entry["state"] = "CANCELLED"
                store.save(receipt)
    _check_current(receipt, host.context(), host.routes())
    if verb == "ensure":
        host.sources()
        _check_current(receipt, host.context(), host.routes())
    return {"status": "SOURCE_SELECTION_QUALIFIED" if verb == "ensure" else "ROLLED_BACK",
            "transaction": receipt["transaction"],
            "routes": {a: e["state"] for a, e in receipt["routes"].items()}}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("verb", choices=("status", "ensure", "reconcile", "rollback"))
    args = parser.parse_args(argv)
    try:
        identity = installed_identity()
        # status is read-only if no state directory has ever been created.
        if args.verb == "status" and not STATE_DIR.exists():
            print(canonical({"status": "NO_OWNED_RECEIPT"}).decode(), end="")
            return REFUSED
        with RootStore() as store:
            result = operate(args.verb, LinuxHost(), store, identity)
        print(canonical(result).decode(), end="")
        return 0 if result["status"] in {"SOURCE_SELECTION_QUALIFIED", "ROLLED_BACK", "RECONCILED"} else REFUSED
    except (Refusal, OSError, UnicodeError):
        # No raw subprocess stderr, filesystem paths supplied by callers, or keys.
        exc = sys.exception()
        code = str(exc) if isinstance(exc, Refusal) else "HOST_OR_CUSTODY_UNAVAILABLE"
        print(canonical({"status": "REFUSED", "reason": code}).decode(), end="")
        return REFUSED


if __name__ == "__main__":
    raise SystemExit(main())
