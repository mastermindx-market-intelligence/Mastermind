#!/usr/bin/env python3
"""Exact host_pull.py read-hosts and write-state logic moved out of Bash
here-document pipes. No new scheduler, credential authority or lease logic.
"""
import sys

_STAGE_PREFIX = "HOST_PULL_STAGE_V1"


def probe_diagnostic(output, returncode):
    """Closed secret-free projection; it cannot authorize observation success."""
    import re
    if type(returncode) is not int or not 0 <= returncode <= 255:
        returncode = None
    stages = [("PHYSICAL_BEGIN", None), ("PHYSICAL_EXIT", "physical"),
              ("READINESS_BEGIN", None), ("READINESS_EXIT", "optional_readiness")]
    result = {"schema": "mastermind.host_pull_probe_diagnostic.v1",
              "transport": {"state": "RETURNED_ZERO" if returncode == 0 else
                            "RETURNED_NONZERO" if type(returncode) is int and 0 <= returncode <= 255
                            else "UNKNOWN", "exit_status": returncode},
              "framing": "MISSING", "physical": {"state": "NOT_OBSERVED", "exit_status": None},
              "optional_readiness": {"state": "NOT_OBSERVED", "exit_status": None}}
    index = 0
    for line in output.splitlines():
        if not line.startswith(_STAGE_PREFIX):
            continue
        if index >= len(stages):
            result["framing"] = "INVALID"
            return result
        name, target = stages[index]
        expected = _STAGE_PREFIX + " " + name
        if target is None:
            valid = line == expected
        else:
            match = re.fullmatch(re.escape(expected) + r" ([0-9]|[1-9][0-9]{1,2})", line)
            valid = match is not None and int(match[1]) <= 255
        if not valid:
            result["framing"] = "INVALID"
            return result
        if target is None:
            key = "physical" if index == 0 else "optional_readiness"
            result[key]["state"] = "STARTED_UNCONFIRMED"
        else:
            code = int(match[1])
            result[target] = {"state": "RETURNED_ZERO" if code == 0 else "RETURNED_NONZERO",
                              "exit_status": code}
        index += 1
    result["framing"] = "COMPLETE" if index == 4 else "INCOMPLETE" if index else "MISSING"
    # A zero transport result must agree with the mandatory physical probe.
    # Optional-readiness exit status is retained as DATA, never physical reachability.
    # Nonzero transport still fails closed even when framed output looks complete.
    if index == 4 and returncode == 0 and result["physical"]["exit_status"] != 0:
        result["framing"] = "INVALID"
    return result


def classify_host_env(raw):
    """Tiny literal grammar, never a shell evaluator or permission decision."""
    import re
    try:
        text = raw.decode("ascii")
    except (UnicodeError, AttributeError):
        return "UNKNOWN"
    seen = False
    for line in text.split("\n"):
        if not line.strip() or line.lstrip(" \t").startswith("#"):
            continue
        # Only this config selector is actually consumed by the pinned GLM
        # validator. Qwen's config path is fixed; no other env name is needed.
        if seen or not re.fullmatch(
                r"[ \t]*(?:export )?GLM_CONFIG=(?:/home/ubuntu0/\.glm/config\.json|"
                r"'/home/ubuntu0/\.glm/config\.json'|\"/home/ubuntu0/\.glm/config\.json\")[ \t]*", line):
            return "UNKNOWN"
        seen = True
    return "LITERAL_CONFIG_ONLY"


def inspect_host_env():
    """Read exactly one fixed hook. Only digest/finite states leave this call."""
    import hashlib
    import os
    import stat
    result = {"schema": "mastermind.host_env_inspection.v1", "status": "UNAVAILABLE",
              "custody": "UNKNOWN", "syntax": "UNKNOWN", "sha256": None}
    fds = []
    edges = []
    try:
        uid = os.geteuid()
        if uid == 0:
            raise ValueError()
        flags = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK
        def identity(info):
            return (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid,
                    info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
        fd = os.open("/", flags | os.O_DIRECTORY)
        fds.append(fd)
        for name in ("home", "ubuntu0", "lanes", "ext"):
            child = os.open(name, flags | os.O_DIRECTORY, dir_fd=fd)
            fds.append(child)
            info = os.fstat(child)
            if info.st_uid not in (0, uid) or info.st_mode & 0o022:
                raise ValueError()
            edges.append((fd, name, child, identity(info)))
            fd = child
        leaf = os.open("HOST_ENV.sh", flags, dir_fd=fd)
        fds.append(leaf)
        before = os.fstat(leaf)
        if (not stat.S_ISREG(before.st_mode) or before.st_uid != uid
                or before.st_mode & 0o022 or before.st_nlink != 1
                or not 0 <= before.st_size <= 65536):
            raise ValueError()
        chunks = []
        length = 0
        while length <= 65536:
            chunk = os.read(leaf, min(4096, 65537-length))
            if not chunk:
                break
            chunks.append(chunk)
            length += len(chunk)
        raw = b"".join(chunks)
        if (len(raw) != before.st_size or len(raw) > 65536
                or identity(before) != identity(os.fstat(leaf))
                or identity(before) != identity(os.stat("HOST_ENV.sh", dir_fd=fd, follow_symlinks=False))):
            raise ValueError()
        for parent, name, child, expected in edges:
            if (identity(os.fstat(child)) != expected
                    or identity(os.stat(name, dir_fd=parent, follow_symlinks=False)) != expected):
                raise ValueError()
        result.update(status="OBSERVED", custody="QUALIFIED",
                      syntax=classify_host_env(raw), sha256=hashlib.sha256(raw).hexdigest())
    except (OSError, ValueError):
        result.update(status="UNQUALIFIED", custody="UNQUALIFIED")
    finally:
        for fd in reversed(fds):
            os.close(fd)
    return result


def prepare_host_env_inspection(registry_path, host):
    """Fixed selected owner, no caller command/path or normal observation."""
    import inspect
    import json
    import shlex
    from glm_host_account_source import owned_bytes
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError()
            result[key] = value
        return result
    if host != "ubuntu0":
        raise ValueError()
    registry = json.loads(owned_bytes(registry_path), object_pairs_hook=pairs)
    entry = registry.get(host) if type(registry) is dict else None
    if (type(entry) is not dict or entry.get("ssh_alias") != "mmx-ubuntu0"
            or entry.get("local") is not None and entry.get("local") is not False
            or entry.get("platform") != "linux"
            or entry.get("worktree_root") != "/home/ubuntu0/.mastermind/worktrees"
            or type(entry.get("roles")) is not list or "lanes" not in entry["roles"]):
        raise ValueError()
    program = (inspect.getsource(classify_host_env) + "\n" + inspect.getsource(inspect_host_env)
               + "\nimport json\nprint(json.dumps(inspect_host_env(),sort_keys=True,separators=(',',':')))\n")
    return "mmx-ubuntu0", "/usr/bin/python3 -I -S -B -c " + shlex.quote(program)


def host_env_inspection_result(output, returncode):
    """Reject arbitrary/duplicate/mixed output; no raw transport data retained."""
    import json
    import re
    result = {"schema": "mastermind.host_env_inspection.v1", "status": "UNAVAILABLE",
              "custody": "UNKNOWN", "syntax": "UNKNOWN", "sha256": None}
    if type(returncode) is not int or returncode != 0 or len(output) > 1024:
        return result
    def pairs(items):
        value = {}
        for key, item in items:
            if key in value:
                raise ValueError()
            value[key] = item
        return value
    try:
        value = json.loads(output, object_pairs_hook=pairs)
        if type(value) is not dict or set(value) != set(result) or value["schema"] != result["schema"]:
            raise ValueError()
        if value["status"] == "OBSERVED":
            if (value["custody"] != "QUALIFIED" or value["syntax"] not in ("UNKNOWN", "LITERAL_CONFIG_ONLY")
                    or type(value["sha256"]) is not str or not re.fullmatch(r"[0-9a-f]{64}", value["sha256"])):
                raise ValueError()
        elif value != dict(result, status="UNQUALIFIED", custody="UNQUALIFIED"):
            raise ValueError()
        return value
    except (ValueError, TypeError):
        return result


def physical_occupancy(expected_sha256):
    """Run only held, selected-release-identical incumbent occupancy bytes."""
    import hashlib
    import os
    import stat
    import sys
    fds, edges = [], []
    def identity(info):
        return (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid,
                info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
    try:
        uid = os.geteuid()
        if uid == 0:
            raise ValueError()
        flags = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK
        parent = os.open('/', flags | os.O_DIRECTORY)
        fds.append(parent)
        for name in ('home', 'ubuntu0', 'lanes', 'ext'):
            child = os.open(name, flags | os.O_DIRECTORY, dir_fd=parent)
            fds.append(child)
            info = os.fstat(child)
            if info.st_uid not in (0, uid) or info.st_mode & 0o022:
                raise ValueError()
            edges.append((parent, name, child, identity(info)))
            parent = child
        leaf = os.open('lane_runtime.py', flags, dir_fd=parent)
        fds.append(leaf)
        before = os.fstat(leaf)
        if (not stat.S_ISREG(before.st_mode) or before.st_uid != uid
                or before.st_mode & 0o022 or before.st_nlink != 1
                or not 0 < before.st_size <= 1048576):
            raise ValueError()
        raw = bytearray()
        while len(raw) <= 1048576:
            chunk = os.read(leaf, min(65536, 1048577 - len(raw)))
            if not chunk:
                break
            raw.extend(chunk)
        if (len(raw) != before.st_size or hashlib.sha256(raw).hexdigest() != expected_sha256
                or identity(before) != identity(os.fstat(leaf))
                or identity(before) != identity(os.stat('lane_runtime.py', dir_fd=parent, follow_symlinks=False))):
            raise ValueError()
        for parent_fd, name, child, info in edges:
            if info != identity(os.fstat(child)) or info != identity(os.stat(name, dir_fd=parent_fd, follow_symlinks=False)):
                raise ValueError()
        # Same incumbent CLI and active directory; execute the qualified held
        # bytes, never reopen the pathname or import a host-local replacement.
        sys.argv = ['/home/ubuntu0/lanes/ext/lane_runtime.py', '--occupancy']
        namespace = sys.modules['__main__'].__dict__
        namespace['__file__'] = sys.argv[0]
        print('occupancy_source_sha256=' + expected_sha256)
        exec(compile(bytes(raw), sys.argv[0], 'exec'), namespace)
    except (OSError, ValueError):
        raise SystemExit(78) from None
    finally:
        for fd in reversed(fds):
            os.close(fd)


def prepare_physical_diagnostic(registry_path, host):
    """Fixed hook-free diagnostic, no account configuration or state writer."""
    import hashlib
    import inspect
    from pathlib import Path
    import shlex
    from glm_host_account_source import owned_bytes
    # Reuse the existing exact selected target/custody qualification. The
    # returned inspection program is discarded; no hook is opened or run.
    alias, _ = prepare_host_env_inspection(registry_path, host)
    here = Path(__file__).resolve().parent
    template = owned_bytes(here / 'host_pull_probe.template').decode('utf-8')
    digest = hashlib.sha256(owned_bytes(here / 'lane_runtime.py')).hexdigest()
    original = 'occupancy=$(python3 -B @@LR@@ --occupancy 2>/dev/null) || occupancy=""'
    if template.count(original) != 1 or template.count('@@WR@@') != 2:
        raise ValueError()
    program = inspect.getsource(physical_occupancy) + '\nphysical_occupancy(' + repr(digest) + ')\n'
    command = '/usr/bin/python3 -I -S -B -c ' + shlex.quote(program)
    template = template.replace(original, 'occupancy=$(' + command + ' 2>/dev/null) || exit 78')
    template = template.replace('@@WR@@', '/home/ubuntu0/.mastermind/worktrees')
    if '@@LR@@' in template:
        raise ValueError()
    return alias, ("printf '%s\\n' 'HOST_PULL_PHYSICAL_V1 BEGIN'\n" + template
                   + "\nphysical_rc=$?\nprintf 'HOST_PULL_PHYSICAL_V1 EXIT %s\\n' \"$physical_rc\"\nexit \"$physical_rc\"")


def physical_diagnostic_result(output, returncode, expected_occupancy_sha256):
    """Bounded DATA only. Never publish state or infer readiness/admission."""
    import math
    import re
    result = {'schema': 'mastermind.host_physical_diagnostic.v1', 'host': 'ubuntu0',
              'status': 'UNAVAILABLE', 'scope': 'DIAGNOSTIC_ONLY',
              'readiness': 'NOT_REQUESTED', 'published': False,
              'transport_exit': returncode if type(returncode) is int and 0 <= returncode <= 255 else None,
              'occupancy_source': 'UNQUALIFIED', 'physical': {}}
    if returncode != 0 or type(returncode) is not int or len(output) > 65536:
        return result
    try:
        lines = output.splitlines()
        if (lines.count('HOST_PULL_PHYSICAL_V1 BEGIN') != 1
                or lines.count('HOST_PULL_PHYSICAL_V1 EXIT 0') != 1
                or lines[0] != 'HOST_PULL_PHYSICAL_V1 BEGIN'
                or lines[-1] != 'HOST_PULL_PHYSICAL_V1 EXIT 0'):
            raise ValueError()
        values = {}
        for line in lines[1:-1]:
            if line.startswith('HOST_PULL_PHYSICAL_V1'):
                raise ValueError()
            if '=' not in line:
                continue
            key, value = line.split('=', 1)
            if key in values:
                raise ValueError()
            values[key] = value
        if (not re.fullmatch('[0-9a-f]{64}', expected_occupancy_sha256)
                or values.get('occupancy_source_sha256') != expected_occupancy_sha256):
            raise ValueError()
        physical = {}
        for key in ('ts', 'load1', 'load5', 'ncpu', 'mem_free_gb', 'disk_free_gb',
                    'process_active_lanes', 'active_lanes', 'lease_active_lanes',
                    'lease_locked_lanes', 'lease_legacy_lanes', 'lease_unlocked_lanes'):
            raw = values.get(key, '')
            if key in ('active_lanes', 'lease_active_lanes') and values.get('active_lanes_status') != 'known' and raw == '':
                physical[key] = None
                continue
            fractional = key in ('load1', 'load5', 'mem_free_gb', 'disk_free_gb')
            if not re.fullmatch(r'[0-9]+(?:\.[0-9]+)?' if fractional else r'[0-9]+', raw):
                raise ValueError()
            number = float(raw)
            if not math.isfinite(number) or number > 10**15:
                raise ValueError()
            physical[key] = number if fractional else int(raw)
        if physical['ts'] <= 0 or physical['ncpu'] <= 0:
            raise ValueError()
        status = values.get('active_lanes_status')
        if status not in ('known', 'held', 'unknown'):
            raise ValueError()
        physical['active_lanes_status'] = status
        tools = values.get('tools', '').split(',')
        if (len(tools) != len(set(tools)) or not set(tools) <=
                {'gh', 'codex', 'claude', 'node', 'python3', 'cursor-agent', 'grok', 'opencode'}):
            raise ValueError()
        physical['tools'] = tools
        # Physical gate inputs remain observations; no scoring/threshold or
        # account envelope is created, and missing readings stay absent.
        for key, raw in values.items():
            if key in ('therm_psi_io_some10', 'therm_psi_memory_some10', 'therm_cpu_tctl_mc',
                       'therm_nvme_margin_crit_mc'):
                if re.fullmatch(r'-?[0-9]+(?:\.[0-9]+)?', raw):
                    number = float(raw)
                    if math.isfinite(number) and abs(number) <= 10**15:
                        physical[key] = number
        physical['on_ac'] = values.get('on_ac') if values.get('on_ac') in ('true', 'false', 'unknown') else 'unknown'
        result.update(status='OBSERVED', occupancy_source='QUALIFIED', physical=physical)
    except (ValueError, TypeError, IndexError, OverflowError):
        pass
    return result


def read_hosts():
    import json, re, sys
    try:
        db = json.load(open(sys.argv[1]))
    except Exception as exc:
        sys.stderr.write("host_pull: hosts.json unreadable: %s\n" % type(exc).__name__)
        raise SystemExit(3)
    if not isinstance(db, dict):
        raise SystemExit("host_pull: registry must be an object")
    selected = set(sys.argv[2].split())
    once = len(sys.argv) < 4 or sys.argv[3] == "1"
    known = {name for name, entry in db.items() if not str(name).startswith("_") and isinstance(entry, dict)}
    if selected - known:
        sys.stderr.write("host_pull: unknown host(s): " + ",".join(sorted(selected - known)) + "\n")
        raise SystemExit(2)
    for name, e in sorted(db.items()):
        if str(name).startswith("_") or not isinstance(e, dict) or (selected and name not in selected):
            continue
        # The unattended lane collector must not spend most of its cycle
        # probing decommissioned minis, CI-only hardware, or candidate seats.
        # --once remains a full-fleet diagnostic and --host remains explicit.
        if not once and not selected:
            roles = e.get("roles", [])
            if (not isinstance(roles, list) or "lanes" not in roles) and not e.get("local"):
                continue
        wr = e.get("worktree_root")
        if not isinstance(wr, str) or not re.match(r"^[A-Za-z0-9_./-]+$", wr or ""):
            wr = "/home"
        alias = e.get("ssh_alias")
        if not isinstance(alias, str):
            alias = ""
        modes = e.get("allowed_modes")
        # Match incumbent host_pick structural mode and qualification rules.
        from host_pick import MODE_TOOLS
        modes_valid = modes is None or (isinstance(modes, list)
            and all(isinstance(v, str) and v in MODE_TOOLS for v in modes)
            and len(set(modes)) == len(modes))
        qualification = e.get("qualification_only_modes", [])
        qualification_valid = (isinstance(qualification, list)
            and all(isinstance(v, str) and v in MODE_TOOLS for v in qualification)
            and len(set(qualification)) == len(qualification))
        account_readiness = ("lanes" in e.get("roles", []) and modes_valid and qualification_valid
            and any((modes is None and mode == "glm" or isinstance(modes, list) and mode in modes)
                    and mode not in qualification for mode in ("glm", "qwen")))
        fields = [name, "1" if e.get("local") else "0", alias, wr]
        if len(sys.argv) > 4 and sys.argv[4] == "--glm-readiness":
            fields.append("1" if account_readiness else "0")
        print("|".join(fields))

def write_state():
    import json, os, sys, time, tempfile, stat, math, re
    state_dir, host, out = sys.argv[1], sys.argv[2], sys.argv[4]
    raw_rc = sys.argv[3]
    rc = int(raw_rc) if re.fullmatch(r"[0-9]|[1-9][0-9]{1,2}", raw_rc) else None
    if rc is not None and rc > 255:
        rc = None
    transport_alias = sys.argv[5] if len(sys.argv) > 5 else None
    diagnostic = probe_diagnostic(out, rc)
    framing_valid = diagnostic["framing"] == "COMPLETE"
    doc = {"host": host, "ts": int(time.time()), "reachable": False, "error": None,
           "probe_diagnostic": diagnostic}

    def num(s):
        try:
            return float(s)
        except (TypeError, ValueError):
            return None

    kv = {}
    duplicate = set()
    if rc == 0 and framing_valid:
        for line in out.splitlines():
            line = line.strip()
            if line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = k.strip()
            if k and all(c.isalnum() or c == "_" for c in k):
                if k in kv: duplicate.add(k)
                kv[k] = v.strip()
    if rc == 0 and framing_valid and kv.get("load1") not in (None, "") and kv.get("ncpu") not in (None, ""):
        doc["reachable"] = True
        ts = num(kv.get("ts"))
        if ts and ts > 0:
            doc["ts"] = int(ts)
        # Same existing telemetry envelope for both admitted account validators.
        # The legacy --glm-readiness column means any supported account readiness.
        for provider, mode, validator in (("glm", "glm", "glm_keys.py"),
                                           ("bailian", "qwen", "bailian_keys.py")):
            if diagnostic["optional_readiness"]["state"] != "RETURNED_ZERO":
                continue
            try:
                from pathlib import Path
                from glm_host_account_source import owned_bytes
                import hashlib
                key = provider + "_local_account_readiness"
                value = kv.get(key, "")
                if len(value.encode()) > 16384 or key in duplicate:
                    raise ValueError("readiness envelope")
                observation = json.loads(value)
                digest = hashlib.sha256(owned_bytes(Path(__file__).parent / validator)).hexdigest()
                if (observation.get("schema") != "mastermind." + provider + "_local_account_readiness.v1"
                        or observation.get("host") != host
                        or not transport_alias or observation.get("transport_alias") != transport_alias
                        or observation.get("mode") != mode
                        or observation.get("config_scope") != "launcher_" + provider + "_config.v1"
                        or observation.get("validator_sha256") != digest
                        or observation.get("status") not in ("known", "unknown")
                        or not isinstance(observation.get("accounts"), dict)
                        or len(observation["accounts"]) > 64):
                    raise ValueError("readiness identity")
                doc[key] = observation
            except (OSError, ValueError, TypeError, AttributeError, ImportError):
                pass
        doc["load1"] = num(kv.get("load1"))
        doc["load5"] = num(kv.get("load5"))
        doc["ncpu"] = int(num(kv.get("ncpu")) or 0)
        doc["mem_free_gb"] = num(kv.get("mem_free_gb"))
        doc["disk_free_gb"] = num(kv.get("disk_free_gb"))
        ac = kv.get("on_ac")
        doc["on_ac"] = ac if ac in ("true", "false", "unknown") else "unknown"
        def count(key):
            value = kv.get(key, "")
            return int(value) if value.isascii() and value.isdigit() else None
        status = kv.get("active_lanes_status", "unknown")
        active = count("active_lanes")
        process_count = count("process_active_lanes")
        doc["active_lanes"] = (
            max(active, process_count or 0) if status == "known" and active is not None else None
        )
        doc["active_lanes_status"] = status if status in ("known", "held") and (active is not None or status == "held") else "unknown"
        doc["process_active_lanes"] = process_count
        doc["lane_occupancy"] = {
            "active": count("lease_active_lanes"), "locked": count("lease_locked_lanes"),
            "legacy": count("lease_legacy_lanes"), "unlocked": count("lease_unlocked_lanes"),
            "reason": kv.get("lease_reason", "census_unavailable"),
        }
        doc["tools"] = [t for t in (kv.get("tools") or "").split(",") if t]
        # Read-only optional thermal addition. Unknown/malformed never becomes 0.
        if kv.get("therm_reader") == "hwmon_v1":
            def _milli(name):
                raw = kv.get("therm_" + name)
                if not isinstance(raw, str) or len(raw) > 10:
                    return None
                if not raw.isascii() or not raw.lstrip("-").isdigit():
                    return None
                value = int(raw)
                return round(value / 1000, 3) if -50000 <= value <= 150000 else None
            cpu_tctl = _milli("cpu_tctl_mc")
            sensor_kind = kv.get("therm_cpu_sensor_kind")
            if sensor_kind not in ("amd_tctl", "intel_package", "unknown"):
                sensor_kind = "unknown"
            fan_raw = kv.get("therm_cpu_fan_rpm", "")
            cpu_fan = (int(fan_raw) if isinstance(fan_raw, str)
                       and fan_raw.isascii() and fan_raw.isdigit()
                       and len(fan_raw) <= 5 and 1 <= int(fan_raw) <= 20000
                       else None)
            nvme_count = kv.get("therm_nvme_drive_count")
            doc["thermal"] = {
                "schema": "mastermind.fabric_host_thermal.v1",
                "source": "linux_hwmon",
                "observed_at": doc["ts"],
                "status": "OBSERVED" if cpu_tctl is not None else "CPU_TEMP_MISSING",
                "admission_authoritative": False,
                "cpu_tctl_c": cpu_tctl,
                "cpu_sensor_kind": sensor_kind,
                "cpu_package_c": _milli("cpu_package_mc"),
                "cpu_fan_rpm": cpu_fan,
                "cpu_ccd1_c": _milli("cpu_ccd1_mc"),
                "cpu_ccd2_c": _milli("cpu_ccd2_mc"),
                "nvme_hottest_c": _milli("nvme_hottest_mc"),
                "nvme_margin_max_c": _milli("nvme_margin_max_mc"),
                "nvme_margin_crit_c": _milli("nvme_margin_crit_mc"),
                "nvme_drive_count": (int(nvme_count) if isinstance(nvme_count, str)
                    and nvme_count.isascii() and nvme_count.isdigit()
                    and len(nvme_count) <= 3 else None),
            }
            # Bounded, read-only sampled process attribution. PID birth ticks
            # protect against PID reuse; argv is never present in this record.
            top_raw = kv.get("therm_top_cpu_csv", "")
            top_records = []
            if isinstance(top_raw, str) and len(top_raw) <= 512:
                for item in top_raw.split(",") if top_raw else []:
                    fields = item.split(":")
                    if len(fields) != 4 or len(top_records) >= 5:
                        top_records = []
                        break
                    pid_s, born_s, pct_s, name = fields
                    if (not pid_s.isascii() or not pid_s.isdigit()
                        or not born_s.isascii() or not born_s.isdigit()
                        or not re.fullmatch(r"[A-Za-z0-9_.+-]{1,24}",name)):
                        top_records = []
                        break
                    try:
                        pct=float(pct_s)
                    except (ValueError, OverflowError):
                        top_records=[]
                        break
                    if (not math.isfinite(pct) or not 10<=pct<=12800
                        or not 0<int(pid_s)<2**31 or not 0<int(born_s)<2**63):
                        top_records=[]
                        break
                    top_records.append({"pid":int(pid_s),"start_ticks":int(born_s),
                                        "cpu_pct":pct,"comm":name})
            doc["thermal"]["top_cpu_processes"] = top_records
            # One existing per-host snapshot carries a bounded cooldown. This
            # is evidence for the existing host picker, never a new scheduler,
            # daemon, termination policy or authority. Expired evidence drops.
            prior_tctl = None
            prior_until = 0
            prior_ts = 0
            old_path = os.path.join(state_dir, host + ".json")
            old_fd = None
            try:
                old_fd = os.open(old_path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
                info = os.fstat(old_fd)
                if not stat.S_ISREG(info.st_mode) or info.st_size > 65536:
                    raise ValueError("old snapshot not bounded regular file")
                with os.fdopen(old_fd, encoding="utf-8") as old_fh:
                    old_fd = None
                    previous = json.load(old_fh)
                previous_therm = previous.get("thermal", {}) if type(previous) is dict else {}
                previous_ts = previous.get("ts") if type(previous) is dict else None
                if (
                    type(previous_ts) is int and 0 <= doc["ts"] - previous_ts <= 900
                    and previous.get("host") == host
                    and previous.get("reachable") is True
                    and type(previous_therm) is dict
                    and previous_therm.get("schema") == "mastermind.fabric_host_thermal.v1"
                    and previous_therm.get("source") == "linux_hwmon"
                    and previous_therm.get("admission_authoritative") is False
                    and previous_therm.get("observed_at") == previous_ts
                ):
                    maybe_tctl = previous_therm.get("cpu_tctl_c")
                    if type(maybe_tctl) in (float,int) and math.isfinite(maybe_tctl) and 10 <= maybe_tctl <= 120:
                        prior_tctl, prior_ts = maybe_tctl, previous_ts
                        maybe_until = previous_therm.get("cooldown_until")
                        if (type(maybe_until) is int
                            and previous_ts <= maybe_until <= previous_ts + 600
                            and maybe_until > doc["ts"]):
                            prior_until = maybe_until
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                pass
            finally:
                if old_fd is not None:
                    os.close(old_fd)
            current_ts = doc["ts"]
            hold_until = max(prior_until, doc["ts"])
            risk = "UNKNOWN"
            rise_c_per_min = None
            if cpu_tctl is not None:
                risk = "NORMAL"
                if prior_tctl is not None and 0 < current_ts-prior_ts <= 900:
                    rise_c_per_min = round((cpu_tctl-prior_tctl) * 60.0/(current_ts-prior_ts), 2)
                if cpu_tctl >= 92:
                    hold_until = max(hold_until, current_ts + 600)
                    risk = "CRITICAL"
                elif cpu_tctl >= 85:
                    hold_until = max(hold_until, current_ts + 240)
                    risk = "HOT"
                elif (cpu_tctl >= 75 and rise_c_per_min is not None
                      and rise_c_per_min >= 10):
                    hold_until = max(hold_until, current_ts + 180)
                    risk = "RISING_FAST"
                elif hold_until > current_ts:
                    risk = "RECOVERING"
            doc["thermal"]["cooldown_until"] = int(hold_until)
            doc["thermal"]["risk"] = risk
            doc["thermal"]["rise_c_per_min"] = rise_c_per_min
        # Procfs detail supplements existing host load/memory readings; it is
        # never a second permission, routing or admission authority.
        if kv.get("therm_reader") == "hwmon_v1":
            def safe_float(name, low=0.0, high=100.0):
                raw=kv.get("therm_"+name,"")
                if not isinstance(raw,str) or len(raw)>30:
                    return None
                try:
                    n=float(raw)
                except (ValueError,TypeError,OverflowError):
                    return None
                return round(n,2) if math.isfinite(n) and low<=n<=high else None
            def core_map(name, upper):
                raw=kv.get("therm_"+name,"")
                if not isinstance(raw,str) or len(raw)>3072:
                    return {}
                out={}
                for field in raw.split(","):
                    if not field:continue
                    pieces=field.split(":",1)
                    if len(pieces)!=2 or not re.fullmatch(r"cpu[0-9]{1,3}",pieces[0]):
                        return {}
                    if pieces[0] in out or len(out)>=128:
                        return {}
                    try:
                        x=float(pieces[1])
                    except (TypeError,ValueError,OverflowError):
                        return {}
                    if not math.isfinite(x) or not 0<=x<=upper:
                        return {}
                    out[pieces[0]]=round(x,1)
                return out
            mem_free=kv.get("therm_mem_available_bytes")
            swap_used=kv.get("therm_swap_used_bytes")
            def uint(raw):
                return (int(raw) if isinstance(raw,str) and 0<len(raw)<=20
                    and raw.isascii() and raw.isdigit() else None)
            doc["granular"]={
                "schema":"mastermind.fabric_host_granular.v1",
                "source":"linux_procfs",
                "observed_at":doc["ts"],
                "admission_authoritative":False,
                "cpu_busy_pct":safe_float("cpu_total_busy_pct"),
                "per_core_busy_pct":core_map("cpu_core_busy_csv",100),
                "per_core_freq_mhz":core_map("cpu_core_freq_csv",10000),
                "psi_some_avg10":{k:safe_float("psi_"+k+"_some10") for k in ("cpu","memory","io")},
                "mem_available_bytes":uint(mem_free),
                "swap_used_bytes":uint(swap_used),
            }
        # Read-only, bounded trend summary in the existing host_pull daemon
        # log. The current state JSON remains the only picker input; no new
        # observer, historical authority, or admission decision is introduced.
        summary = "reachable=true"
        for name, value in (
            ("tctl_c", (doc.get("thermal") or {}).get("cpu_tctl_c")),
            ("load1", doc.get("load1")),
            ("cpu_busy_pct", (doc.get("granular") or {}).get("cpu_busy_pct")),
        ):
            if (type(value) in (int, float) and math.isfinite(value)
                    and 0 <= value <= (150 if name == "tctl_c" else 100)):
                summary += f" {name}={value:g}"
        if type(doc.get("active_lanes")) is int:
            summary += f" active_lanes={doc['active_lanes']}"
        therm = doc.get("thermal") or {}
        if therm.get("risk") in ("HOT","CRITICAL"):
            top = therm.get("top_cpu_processes") or []
            if top:
                summary += " sampled_top_cpu=" + ",".join(
                    f"{p['comm']}:{p['cpu_pct']:g}%/pid{p['pid']}"
                    for p in top[:3])
    elif rc is None:
        doc["error"] = "probe_status_invalid"
        summary = "reachable=false error=probe_status_invalid"
    elif rc == 0 and not framing_valid:
        doc["error"] = "probe_diagnostic_invalid"
        summary = "reachable=false error=probe_diagnostic_invalid"
    elif rc == 255:
        doc["error"] = "ssh_unreachable"
        summary = "reachable=false error=ssh_unreachable"
    elif rc >= 128:
        doc["error"] = "probe_timeout"
        summary = "reachable=false error=probe_timeout"
    elif rc == 0:
        doc["error"] = "bad_probe_output"
        summary = "reachable=false error=bad_probe_output"
    else:
        doc["error"] = "probe_exit_%d" % rc
        summary = "reachable=false error=probe_exit_%d" % rc
    path = os.path.join(state_dir, host + ".json")
    directory = os.stat(state_dir, follow_symlinks=False)
    if (not stat.S_ISDIR(directory.st_mode) or directory.st_uid != os.geteuid()
            or directory.st_mode & 0o022):
        raise SystemExit("host_pull: observation directory custody unavailable")
    fd, tmp = tempfile.mkstemp(prefix=host + ".", suffix=".tmp", dir=state_dir)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(doc, fh, indent=2, sort_keys=True)
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        # Preserve readable telemetry without inheriting an unsafe write mode.
        os.chmod(tmp, 0o644)
        current = os.stat(state_dir, follow_symlinks=False)
        if (current.st_dev, current.st_ino) != (directory.st_dev, directory.st_ino):
            raise SystemExit("host_pull: observation directory changed")
        os.replace(tmp, path)
        directory_fd = os.open(state_dir, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    # Retain this invocation's closed diagnostic in the existing collector
    # return/log as well as state: another normal producer may atomically
    # replace the shared host snapshot before its caller reads it.
    print(summary + " probe_diagnostic=" + json.dumps(diagnostic, sort_keys=True, separators=(",", ":")))

if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(2)
    command = sys.argv.pop(1)
    if command == "physical-diagnostic-prepare":
        try:
            if len(sys.argv) != 3:
                raise ValueError()
            alias, probe = prepare_physical_diagnostic(sys.argv[1], sys.argv[2])
            print(alias)
            print(probe)
        except (OSError, ValueError, TypeError, KeyError):
            sys.stderr.write('host_pull: physical diagnostic refused\n')
            raise SystemExit(78)
    elif command == "physical-diagnostic-result":
        import hashlib
        import json
        from pathlib import Path
        from glm_host_account_source import owned_bytes
        raw_code = sys.argv[1] if len(sys.argv) == 2 else ''
        code = int(raw_code) if raw_code.isascii() and raw_code.isdecimal() and len(raw_code) <= 3 else None
        try:
            digest = hashlib.sha256(owned_bytes(Path(__file__).resolve().parent / 'lane_runtime.py')).hexdigest()
            result = physical_diagnostic_result(sys.stdin.read(65537), code, digest)
        except (OSError, ValueError, TypeError):
            result = physical_diagnostic_result('', None, '')
        print(json.dumps(result, sort_keys=True, separators=(',', ':')))
        raise SystemExit(0 if result['status'] == 'OBSERVED' else 78)
    elif command == "read-hosts":
        read_hosts()
    elif command == "paid-qualification":
        try:
            # Qualification runs with -I -S; load only the pinned sibling,
            # never user sitecustomize, PYTHONPATH or another module search root.
            import importlib.util
            from pathlib import Path
            spec = importlib.util.spec_from_file_location(
                "_pinned_paid_host_qualification", Path(__file__).absolute().with_name("paid_host_qualification.py"))
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            if len(sys.argv) != 2:
                raise ValueError()
            alias, probe = module.prepare_paid_transport(sys.argv[1], sys.stdin.buffer.read(65537))
            print(alias)
            print(probe)
        except (OSError, ValueError, TypeError, KeyError):
            sys.stderr.write("host_pull: paid qualification refused\n")
            raise SystemExit(78)
    elif command == "inspect-host-env-prepare":
        try:
            if len(sys.argv) != 3:
                raise ValueError()
            alias, probe = prepare_host_env_inspection(sys.argv[1], sys.argv[2])
            print(alias)
            print(probe)
        except (OSError, ValueError, TypeError, KeyError):
            sys.stderr.write("host_pull: fixed inspection refused\n")
            raise SystemExit(78)
    elif command == "inspect-host-env-result":
        import json
        raw_code = sys.argv[1] if len(sys.argv) == 2 else ""
        code = int(raw_code) if raw_code.isascii() and raw_code.isdecimal() and len(raw_code) <= 3 else None
        result = host_env_inspection_result(sys.stdin.read(1025), code)
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        raise SystemExit(0 if result["status"] == "OBSERVED" else 78)
    elif command == "write-state":
        write_state()
    else:
        raise SystemExit(2)
