"""Inactive preparation: pure observation normalization, never authority.

No filesystem, process, socket, clock, broker, or provider operations occur here.
Arguments must eventually come from the incumbent trusted observation owner.
These public Python values are forgeable and MUST NOT be admitted as a live
guard, permission, freshness proof, or replacement for the full release reader.
There is intentionally no production entrypoint, serialization loader, grant
decision, installer invocation, or forward-core API in this module.
"""
from dataclasses import dataclass
import re

LABEL = "com.mastermind.executive.privileged"
MAIN_IMAGE = "/Library/Frameworks/Python.framework/Versions/3.12/Resources/Python.app/Contents/MacOS/Python"
MAX_OUTPUT = 65536
MAX_ROWS = 8192


class ObservationRejected(ValueError):
    pass


def _require(condition, code):
    if not condition:
        raise ObservationRejected(code)


def _integer(value, maximum, *, zero=False):
    return type(value) is int and (0 if zero else 1) <= value <= maximum


def _command_output(rc, out, err):
    _require(type(rc) is int and type(out) is bytes and type(err) is bytes,
             "COMMAND_SHAPE")
    _require(len(out) + len(err) <= MAX_OUTPUT, "OUTPUT_BOUND")


def normalize_disabled(rc, out, err):
    """Closed flat and observed macOS print-disabled document grammars."""
    _command_output(rc, out, err)
    _require(rc == 0 and not err and out.endswith(b"\n"), "DISABLED_UNAVAILABLE")
    try:
        lines = out.decode("ascii").split("\n")[:-1]
    except UnicodeError:
        raise ObservationRejected("DISABLED_ENCODING") from None
    _require(2 <= len(lines) <= MAX_ROWS, "DISABLED_DOCUMENT")
    # The native macOS document has one leading blank line, a tab-indented
    # header/brace, and two-tab rows. Accept that exact envelope, not arbitrary
    # strip/lstrip that could silently discard diagnostic text or extra data.
    if lines[:2] == ["", "\tdisabled services = {"]:
        _require(lines[-1] == "\t}" and
                 all(line.startswith("\t\t") for line in lines[2:-1]),
                 "DISABLED_DOCUMENT")
        lines = ["disabled services = {"] + [line[1:] for line in lines[2:-1]] + ["}"]
    _require(2 <= len(lines) <= MAX_ROWS and lines[0] == "disabled services = {"
             and lines[-1] == "}", "DISABLED_DOCUMENT")
    rows = {}
    for line in lines[1:-1]:
        match = re.fullmatch(r'[ \t]+"([A-Za-z0-9_.:-]{1,256})" => (true|false|disabled|enabled)', line)
        _require(match is not None, "DISABLED_ROW")
        label, value = match.groups()
        _require(label not in rows, "DISABLED_DUPLICATE")
        rows[label] = value
    _require(rows.get(LABEL) in ("true", "disabled"), "DISABLED_NOT_PROVEN")
    return "DISABLED"


def normalize_root_inventory(rc, out, err):
    """Parse *all* rows of fixed ps pid=,uid= output; never filter by comm.

    Returns PIDs only, without asserting acquisition completeness or stability.
    The trusted producer must bind the fixed command, output bounds, endpoint,
    child settlement and observations around it. PID1/root is a truncation
    sanity check, not completeness proof. A partial valid subset is forgeable.
    """
    _command_output(rc, out, err)
    _require(rc == 0 and not err and out.endswith(b"\n"), "INVENTORY_UNAVAILABLE")
    try:
        lines = out.decode("ascii").split("\n")[:-1]
    except UnicodeError:
        raise ObservationRejected("INVENTORY_ENCODING") from None
    _require(0 < len(lines) <= MAX_ROWS, "INVENTORY_BOUND")
    rows = {}
    for line in lines:
        match = re.fullmatch(r'[ \t]*([1-9][0-9]{0,9})[ \t]+(0|-?[1-9][0-9]{0,9})[ \t]*', line)
        _require(match is not None, "INVENTORY_ROW")
        pid, uid = map(int, match.groups())
        # Apple ps prints uint32 uid_t with signed UIDFMT "d" (e.g. -2).
        # Bound the signed representation before converting; no negative value
        # can wrap to root, and every row still participates in validation.
        if uid < 0:
            _require(uid >= -(2**31), "INVENTORY_RANGE")
            uid += 2**32
        _require(_integer(pid, 2**31 - 1) and _integer(uid, 2**32 - 1, zero=True),
                 "INVENTORY_RANGE")
        _require(pid not in rows, "INVENTORY_DUPLICATE")
        rows[pid] = uid
    _require(rows.get(1) == 0, "INVENTORY_NO_SYSTEM_INIT")
    return tuple(sorted(pid for pid, uid in rows.items() if uid == 0))


@dataclass(frozen=True, slots=True)
class Instance:
    pid: int
    unique_id: int
    pidversion: int


def _instance(value):
    _require(type(value) is Instance
             and _integer(value.pid, 2**31 - 1)
             and _integer(value.unique_id, 2**64 - 1)
             and _integer(value.pidversion, 2**31 - 1), "INSTANCE_SHAPE")


@dataclass(frozen=True, slots=True)
class ImageSample:
    before: Instance
    after: Instance
    image_before: str
    image_after: str


def normalize_image(sample):
    """Compare kernel-supplied samples; never qualify an image from its name."""
    _require(type(sample) is ImageSample, "IMAGE_SHAPE")
    _instance(sample.before)
    _instance(sample.after)
    _require(sample.before == sample.after, "PROCESS_INSTANCE_DRIFT")
    for path in (sample.image_before, sample.image_after):
        _require(type(path) is str and path.startswith("/") and len(path) <= 4096
                 and all(32 <= ord(c) < 127 for c in path)
                 and not any(part in ("", ".", "..") for part in path.split("/")[1:]),
                 "IMAGE_UNAVAILABLE_OR_UNNORMALIZED")
    _require(sample.image_before == sample.image_after, "PROCESS_IMAGE_DRIFT")
    return (sample.before, sample.image_before)


def account_root_samples(before_pids, after_pids, samples):
    """Require stable full membership and one positive image row per root PID.

    No exemptions: acquisition must keep/settle its own child correctly or
    refuse. ALL rows are returned; no process is exonerated from its path.
    Production must classify physical images and separately join the exact
    observer/current broker to the qualified runtime. This is not exclusion.
    """
    for pids in (before_pids, after_pids):
        _require(type(pids) is tuple and 0 < len(pids) <= MAX_ROWS, "CENSUS_SHAPE")
        _require(all(_integer(p, 2**31 - 1) for p in pids)
                 and tuple(sorted(set(pids))) == pids and 1 in pids, "CENSUS_PID_SET")
    _require(before_pids == after_pids, "CENSUS_MEMBERSHIP_DRIFT")
    _require(type(samples) is tuple and len(samples) == len(before_pids), "CENSUS_COVERAGE")
    normalized = tuple(normalize_image(s) for s in samples)
    _require(tuple(sorted(x.pid for x, _ in normalized)) == before_pids, "CENSUS_COVERAGE")
    return tuple(sorted(normalized, key=lambda row: row[0].pid))


@dataclass(frozen=True, slots=True)
class DistinctOwners:
    transport_launchd: Instance
    action_broker: Instance


def normalize_distinct_owners(transport_before, transport_after, broker_before, broker_after):
    """Identity consistency only. No assertion of peer origin or socket custody.

    euid/audit/boot/release/config/source/namespace/connection joins are NOT
    inferred from these tuples and remain the incumbent producers' obligations.
    """
    for value in (transport_before, transport_after, broker_before, broker_after):
        _instance(value)
    _require(transport_before == transport_after and broker_before == broker_after,
             "OWNER_INSTANCE_DRIFT")
    _require(transport_before.pid == 1 and broker_before.pid != 1,
             "OWNER_ROLE_CONFUSION")
    return DistinctOwners(transport_before, broker_before)
