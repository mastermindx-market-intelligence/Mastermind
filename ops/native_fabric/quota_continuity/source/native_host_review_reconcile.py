#!/usr/bin/env python3
"""Fixed native-host-review inspection proposal; SOURCE ONLY, read only.

The incumbent Fabric adapter owns authenticated transport. This module launches
nothing, imports no installed owner, takes no lock, and performs no settlement.
Only host_inspect is a public inspection entry; its request cannot choose paths,
PIDs, accounts, kernel assumptions, source, code, or an operation to mutate.
"""
from __future__ import annotations
import ast
from dataclasses import dataclass
from datetime import datetime, timezone
import errno
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import stat
import sys

SCHEMA = "mastermind.native_host_review_inspection.v1"
RUN_ID = "native-host-review-22f77378-01a0e0c7"
ROOT_ID = "01a0e0c7-1ed2-7fa0-a4b4-890d30ea6311"
HOST = "ubuntu2"
SUPPORT = "3df14e1a295570df7519adec21acf65eba6dccee80b5ab9c1e6a68a570dfb4c9"
LEASE_ID = "b17b0ca31f28"
PACKET_SHA = "898779496051a23123473d58c6c9f599ed4a541898d5a051029583e3da153d49"
MARKER_SHA = "ff7b5bc29d6d2a72a7aa660af75176a2d9b65e12a05005fa5db1f5236c4c6d44"
STDOUT_SHA = hashlib.sha256(b"REMOTE_CLEANUP_UNPROVEN OSError\n").hexdigest()
HEX = re.compile(r"[0-9a-f]{64}\Z")
REQUEST = {"schema": SCHEMA, "action": "inspect", "run_id": RUN_ID,
           "root_id": ROOT_ID, "host": HOST, "support_digest": SUPPORT}
LIMITS = ["Not an atomic cross-file snapshot",
          "Current metadata is not historical execution attestation",
          "Static source fingerprints do not attest running process source",
          "Marker PID presence or absence does not prove original child identity",
          "Argument size alone does not prove the historical exception errno",
          "No census of descendants or other potentially surviving processes",
          "No settlement eligibility, lease clearance, acceptance, retry or release decision"]
# Fixed old release generations, shared with the existing run_observation owner.
SOURCE_FILES = frozenset({"remote_sub_exec.py", "artifact_production.py", "artifact_reader.py",
    "native_remote.py", "go_remote_codex.py", "go_remote_capsule.py", "lane_runtime.py",
    "sub.sh", "slot.py", "glm_bound_claude.py", "pick.py", "model_tier.py", "codex_usage.py",
    "mm_codex_exec.sh", "glm_codex_exec.sh", "go_codex_exec.sh", "qwen_exec.sh",
    "fabric_client_projection.py", "studio_mcp_projection.sh", "mm_feeder_lib.py",
    "pool_ledger.py", "lease_broker.py", "glm_keys.py", "bailian_keys.py"})
GENERATIONS = (SOURCE_FILES, SOURCE_FILES - {"glm_bound_claude.py"},
               SOURCE_FILES - {"glm_bound_claude.py", "artifact_production.py", "artifact_reader.py"})
CODE_NAMES = ("remote_sub_exec.py", "lane_runtime.py", "native_remote.py")

class Invalid(ValueError):
    """Closed internal reason code, never source or OS exception text."""


def _require(condition, reason):
    if not condition:
        raise Invalid(reason)


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def strict_json(raw):
    def pairs(items):
        value = {}
        for key, item in items:
            _require(key not in value, "duplicate_json_key")
            value[key] = item
        return value
    def nonfinite(_):
        raise Invalid("nonfinite_json_number")
    def number(text):
        value = float(text)
        _require(value not in (float("inf"), -float("inf")), "nonfinite_json_number")
        return value
    try:
        return json.loads(raw, object_pairs_hook=pairs, parse_constant=nonfinite, parse_float=number)
    except (ValueError, UnicodeError, RecursionError) as exc:
        if isinstance(exc, Invalid):
            raise
        raise Invalid("invalid_json") from None


def _identity(s):
    return (s.st_dev, s.st_ino, s.st_mode, s.st_uid, s.st_gid, s.st_nlink,
            s.st_size, s.st_mtime_ns, s.st_ctime_ns)


def _directory_identity(s):
    return (s.st_dev, s.st_ino, s.st_mode, s.st_uid, s.st_gid)


def _metadata(s):
    return dict(device=s.st_dev, inode=s.st_ino, uid=s.st_uid,
                mode=stat.S_IMODE(s.st_mode), bytes=s.st_size, mtime_ns=s.st_mtime_ns)


class _Reader:
    """Held directory and file descriptors, no symlink traversal or arbitrary input.

    It retains every opened parent until close, including on an absent file, so
    later verify detects directory replacement. File identity is checked against
    its retained FD and visible inode both before and after a bounded read.
    """
    def __init__(self, root, uid, *, final_owner=True):
        self.uid, self.fds, self.edges, self.files = uid, [], [], []
        self.rootfd = None
        root = Path(root)
        _require(root.is_absolute() and ".." not in root.parts, "invalid_fixed_root")
        try:
            fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            self.fds.append(fd)
            self._directory(os.fstat(fd))
            for part in root.parts[1:]:
                fd = self._descend(fd, part)
            self.rootfd = fd
            _require(not final_owner or os.fstat(fd).st_uid == uid, "fixed_root_owner")
            self.verify()
        except BaseException:
            self.close()
            raise

    def _directory(self, s):
        _require(stat.S_ISDIR(s.st_mode) and s.st_uid in (0, self.uid)
                 and not s.st_mode & 0o022, "directory_custody")

    def _descend(self, parent, name):
        self._name(name)
        fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_NONBLOCK,
                     dir_fd=parent)
        self.fds.append(fd)
        observed = os.fstat(fd)
        self._directory(observed)
        self.edges.append((parent, name, fd, _directory_identity(observed)))
        self.verify()
        return fd

    @staticmethod
    def _name(name):
        _require(type(name) is str and name not in ("", ".", "..") and "/" not in name,
                 "invalid_fixed_component")

    def verify(self):
        for parent, name, fd, expected in self.edges:
            _require(_directory_identity(os.fstat(fd)) == expected
                     and _directory_identity(os.stat(name, dir_fd=parent,
                                                     follow_symlinks=False)) == expected,
                     "directory_changed")
        for parent, name, fd, expected in self.files:
            _require(_identity(os.fstat(fd)) == expected
                     and _identity(os.stat(name, dir_fd=parent, follow_symlinks=False)) == expected,
                     "file_changed")

    def read(self, parts, limit, *, content=True, mode=None, proc=False):
        parent = self.rootfd
        try:
            _require(type(parts) is tuple and bool(parts), "invalid_fixed_components")
            for part in parts[:-1]:
                parent = self._descend(parent, part)
            name = parts[-1]
            self._name(name)
            if not content:
                before = os.stat(name, dir_fd=parent, follow_symlinks=False)
                self._file(before, mode)
                _require(_identity(before) == _identity(os.stat(name, dir_fd=parent,
                                                               follow_symlinks=False)), "file_changed")
                self.verify()
                return None, before
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
            self.fds.append(fd)
            before = os.fstat(fd)
            self._file(before, mode)
            self.files.append((parent, name, fd, _identity(before)))
            _require(before.st_size <= limit, "size_limit")
            chunks, remaining = [], limit + 1
            while remaining:
                chunk = os.read(fd, min(remaining, 65536))
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            raw = b"".join(chunks)
            _require(len(raw) <= limit, "size_limit")
            _require(proc or len(raw) == before.st_size, "file_changed")
            self.verify()
            return raw, before
        except FileNotFoundError:
            self.verify()  # A failed parent check is not absence.
            raise

    def _file(self, s, mode):
        _require(stat.S_ISREG(s.st_mode) and s.st_uid == self.uid and s.st_nlink == 1
                 and not s.st_mode & 0o022 and (mode is None or stat.S_IMODE(s.st_mode) == mode),
                 "file_custody")

    def close(self):
        for fd in reversed(self.fds):
            os.close(fd)
        self.fds.clear()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


@dataclass(frozen=True)
class _Contract:
    support: str = SUPPORT
    packet_sha: str = PACKET_SHA
    packet_bytes: int = 201147
    marker_sha: str = MARKER_SHA
    marker_device: int = 66307
    marker_inode: int = 24547401
    marker_bytes: int = 647
    uid: int = 1000


class _System:
    def kernel(self):
        u = os.uname()
        return dict(host=socket.gethostname().split(".")[0], system=u.sysname,
                    machine=u.machine, release=u.release, page_size=os.sysconf("SC_PAGE_SIZE"),
                    filesystem_encoding=sys.getfilesystemencoding(), uid=os.getuid())


def _capture(fn):
    try:
        return {"status": "observed", **fn()}
    except FileNotFoundError:
        return {"status": "absent", "reason": "missing_at_observation"}
    except OSError as exc:
        if exc.errno in (errno.EACCES, errno.EPERM):
            raise
        return {"status": "unavailable", "reason": "filesystem_error", "errno": exc.errno}
    except (ValueError, TypeError, KeyError, UnicodeError, OverflowError, RecursionError, SyntaxError):
        # No potentially sensitive exception text escapes.
        return {"status": "unavailable", "reason": "validation_failed"}


def _function(tree, name):
    found = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name]
    _require(len(found) == 1, "source_function_shape")
    return found[0]


def _d(node):
    return ast.dump(node, annotate_fields=True, include_attributes=False)


def _parse(raw):
    _require(b"\0" not in raw, "source_nul")
    return ast.parse(raw.decode("utf-8"))


def _fingerprints(raw):
    remote, lane, native = (_parse(raw[name]) for name in CODE_NAMES)
    execute, owned = _function(remote, "_execute"), _function(lane, "run_owned_process")
    # Exact expression signatures, privately matched; output contains flags and hashes only.
    assignments = [n for n in ast.walk(execute) if isinstance(n, ast.Assign)]
    def assignment(name, expr):
        return sum(any(isinstance(t, ast.Name) and t.id == name for t in n.targets)
                   and _d(n.value) == _d(ast.parse(expr, mode="eval").body) for n in assignments) == 1
    flags = {
        "packet_read_text_utf8": assignment("prompt", 'packet_path.read_text(encoding="utf-8")'),
        "ordinary_prompt_is_single_argument": assignment("command", '["bash", str(here / "sub.sh"), mode, prompt, cwd]'),
        "conditional_native_override_present": any(isinstance(n, ast.If)
            and _d(n.test) == _d(ast.parse('mode in native_remote.MODES', mode='eval').body)
            and any(isinstance(t, ast.Assign) and any(isinstance(a, ast.Name) and a.id == 'command' for a in t.targets)
                    for t in n.body) for n in ast.walk(execute)),
        "owned_process_called_with_command": any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
            and n.func.id == 'run_owned_process' and len(n.args) == 1
            and isinstance(n.args[0], ast.Name) and n.args[0].id == 'command' for n in ast.walk(execute)),
        "popen_called_with_command": any(isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
            and isinstance(n.func.value, ast.Name) and n.func.value.id == 'subprocess' and n.func.attr == 'Popen'
            and len(n.args) == 1 and isinstance(n.args[0], ast.Name) and n.args[0].id == 'command'
            for n in ast.walk(owned)),
    }
    model_assignments = [n for n in native.body if isinstance(n, ast.Assign)
                        and any(isinstance(t, ast.Name) and t.id == 'MODELS' for t in n.targets)]
    modes_assignments = [n for n in native.body if isinstance(n, ast.Assign)
                        and any(isinstance(t, ast.Name) and t.id == 'MODES' for t in n.targets)]
    _require(len(model_assignments) == len(modes_assignments) == 1, "native_modes_shape")
    models = ast.literal_eval(model_assignments[0].value)
    _require(type(models) is dict and all(type(k) is str for k in models), "native_models_shape")
    _require(_d(modes_assignments[0].value) == _d(ast.parse('set(MODELS)', mode='eval').body), "native_modes_shape")
    flags['minimax_is_not_native_override'] = 'mm' not in models
    # Flags are structural comparison evidence, not a general control-flow verifier.
    return dict(signatures=flags, ast_sha256={name: _sha(_d(tree).encode())
                for name, tree in zip(CODE_NAMES, (remote, lane, native))},
                execution_path_attested=False)


def _support(reader, contract):
    prefix = ("lanes", "support-releases", contract.support)
    manifest, info = reader.read((*prefix, "RELEASE.json"), 65536, mode=0o444)
    value = strict_json(manifest)
    _require(type(value) is dict and set(value) == {'schema', 'digest', 'files', 'links'}
             and value['schema'] == 'remote-support-code.v1', "manifest_shape")
    expected_links = {'ext/'+name:'/home/ubuntu2/lanes/ext/'+name for name in (
        'active','lanes','slots','state','broker','lane_bin','hosts.json','bailian_policy.json',
        'bailian_usage.json','GROK_EXHAUSTED','glm_window_state.json','glm_shim','go_shim',
        'codex_glm','codex_go','codex_minimax')}
    expected_links.update({name:'/home/ubuntu2/lanes/'+name for name in (
        'orch','codex_bailian','minimax_claude_home','glm_claude_home','go_claude_home')})
    _require(value['links'] == expected_links, 'manifest_links')
    files = value['files']
    _require(type(files) is dict and frozenset(files) in GENERATIONS
             and all(type(v) is str and HEX.fullmatch(v) for v in files.values()), "manifest_files")
    digest = _sha(canonical({'schema':value['schema'], 'files':files}))
    _require(value['digest'] == contract.support == digest, "manifest_digest")
    code = {}
    for name in CODE_NAMES:
        raw, _ = reader.read((*prefix, 'ext', name), 2 * 1024 * 1024, mode=0o555)
        _require(_sha(raw) == files[name], "source_changed")
        code[name] = raw
    _require(reader.read((*prefix, "RELEASE.json"), 65536, mode=0o444)[0] == manifest, "manifest_changed")
    return dict(manifest_file=_metadata(info), manifest_sha256=_sha(manifest), digest=digest,
                verified_source_sha256={name:files[name] for name in CODE_NAMES},
                verified_code_files=len(CODE_NAMES), full_release_code_verified=False,
                release_links_verified=False, **_fingerprints(code))


def _packet(reader, contract, kernel):
    raw, info = reader.read(('lanes', 'tmp', RUN_ID+'.txt'), contract.packet_bytes)
    _require(len(raw) == contract.packet_bytes and _sha(raw) == contract.packet_sha, "packet_changed")
    prompt = raw.decode('utf-8').replace('\r\n', '\n').replace('\r', '\n')
    _require('\0' not in prompt, "packet_nul")
    _require(kernel['filesystem_encoding'] == 'utf-8' and kernel['page_size'] == 4096,
             "argv_encoding_or_page_size")
    size = len(prompt.encode('utf-8')) + 1
    return dict(file=_metadata(info), sha256=_sha(raw), decoded_utf8_argument_bytes_including_nul=size,
                linux_max_single_argument_bytes=32*kernel['page_size'],
                single_argument_exceeds_limit=size > 32*kernel['page_size'],
                historical_exec_errno_proven=False)


def _time(value):
    _require(type(value) is str and len(value) <= 40, "timestamp_shape")
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        _require(parsed.tzinfo is not None, "timestamp_timezone")
        return parsed.astimezone(timezone.utc)
    except (ValueError, OverflowError):
        raise Invalid('timestamp_shape') from None


def _marker(reader, contract):
    raw, info = reader.read(('lanes', 'ext', 'active', RUN_ID), 65536)
    _require((info.st_dev, info.st_ino) == (contract.marker_device, contract.marker_inode)
             and len(raw) == contract.marker_bytes and _sha(raw) == contract.marker_sha, "marker_changed")
    value = strict_json(raw)
    _require(type(value) is dict and set(value) == {'schema', 'key', 'reason', 'held_at', 'host', 'original_lease'}
             and value['schema'] == 'mastermind.local_lane_reconciliation_hold.v1'
             and value['key'] == RUN_ID and value['host'] == HOST
             and value['reason'] == 'worker_cleanup_unproven', "hold_binding")
    original = value['original_lease']
    _require(type(original) is dict and original.get('schema') == 'mastermind.local_lane_lease.v1'
             and original.get('key') == original.get('label') == RUN_ID and original.get('host') == HOST
             and original.get('reconcile_unreleased') is True, "original_lease_binding")
    pid = original.get('pid')
    _require(type(pid) is int and 1 <= pid < 2**31, "marker_pid")
    started, held = _time(original.get('started_at')), _time(value.get('held_at'))
    _require(started <= held, "hold_time_order")
    source = original.get('source_sha256')
    _require(source is None or type(source) is str and HEX.fullmatch(source), "marker_source")
    return dict(file=_metadata(info), sha256=_sha(raw), pid=pid,
                started_at=started.isoformat(), held_at=held.isoformat(), source_sha256=source,
                root_identity_proven=False, lease_identity_proven=False,
                original_child_identity_proven=False)


def _rc(reader):
    raw, info = reader.read(('lanes', 'ext', 'lanes_'+RUN_ID+'.rc'), 16)
    _require(raw in (b'76', b'76\n'), 'returncode_changed')
    return dict(file=_metadata(info), sha256=_sha(raw), returncode=76, accepted=False)


def _stdout(reader):
    # Only the fixed 32-byte cleanup diagnostic may be admitted; no content is returned.
    raw, info = reader.read(('lanes', 'ext', 'lanes_'+RUN_ID+'.stdout'), 32)
    _require(len(raw) == 32 and _sha(raw) == STDOUT_SHA, 'stdout_changed')
    return dict(file=_metadata(info), sha256=_sha(raw), fixed_cleanup_diagnostic_matches=True,
                content_returned=False, provider_output_read=False, accepted=False)


def _kernel(system, proc):
    value = system.kernel()
    _require(value['host'] == HOST and value['system'] == 'Linux' and value['machine'] == 'x86_64'
             and value['uid'] == 1000 and type(value['page_size']) is int and value['page_size'] == 4096,
             'host_kernel_or_account')
    _require(type(value['release']) is str and re.fullmatch(r'[A-Za-z0-9_.+-]{1,120}', value['release']),
             'kernel_release_shape')
    raw, _ = proc.read(('sys', 'kernel', 'random', 'boot_id'), 64, proc=True)
    # Kernel-owned sysctl read uses a separate root-owned reader, supplied internally.
    boot = raw.decode('ascii').strip()
    _require(re.fullmatch(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}', boot), 'boot_id_shape')
    return dict(**value, boot_id=boot, historical_kernel_identity_proven=False)


def _proc_identity(raw, pid):
    text = raw.decode('ascii')
    end = text.rfind(') ')
    _require(end >= 0 and text.partition(' (')[0] == str(pid), 'proc_stat_shape')
    fields = text[end+2:].split()
    _require(len(fields) >= 20 and fields[0] in set('RSDZTtXxKWPI')
             and re.fullmatch(r'[0-9]{1,20}', fields[19]), 'proc_stat_shape')
    return fields[0], int(fields[19])


def _pid(proc, pid, uid):
    prefix = (str(pid),)
    before, info = proc.read((*prefix, 'stat'), 4096, proc=True)
    state, ticks = _proc_identity(before, pid)
    status, _ = proc.read((*prefix, 'status'), 16384, proc=True)
    uid_rows = [line.split()[1:] for line in status.decode('ascii').splitlines() if line.startswith('Uid:')]
    _require(len(uid_rows) == 1 and len(uid_rows[0]) == 4
             and all(re.fullmatch(r'[0-9]{1,10}', v) for v in uid_rows[0]), 'proc_uid_shape')
    uids = [int(v) for v in uid_rows[0]]
    _require(uids == [uid]*4, 'proc_uid_mismatch')
    after, _ = proc.read((*prefix, 'stat'), 4096, proc=True)
    _require(_proc_identity(after, pid)[1] == ticks, 'proc_generation_changed')
    proc.verify()
    return dict(observed_pid_present=True, pid=pid, uid=uid, state=state, start_ticks=ticks,
                original_child_identity_proven=False, useful_progress_proven=False,
                argv_read=False, environ_read=False)


def _artifacts(reader):
    rows = {}
    for suffix in ('process.jsonl', 'usage.json'):
        def presence(suffix=suffix):
            _, info = reader.read(('lanes', 'ext', 'lanes', RUN_ID+'.'+suffix), 0, content=False)
            return dict(file=_metadata(info), content_read=False, accepted=False)
        rows[suffix] = _capture(presence)
    return dict(artifacts=rows, absence_is_only_current_observation=True)


def _inspect(reader, proc, boot_reader, system, contract):
    # Private injectable seam for inert fixtures only; public entry cannot supply it.
    out = dict(schema=SCHEMA, run_id=RUN_ID, root_id=ROOT_ID, host=HOST,
               support_digest=contract.support, original_lease_id=LEASE_ID,
               action='inspect', status='unavailable', observations={}, limits=LIMITS.copy(),
               execution_replayed=False, effect_state_changed=False,
               settlement_eligible=False, accepted=False)
    obs = out['observations']
    try:
        obs['kernel'] = _capture(lambda: _kernel(system, boot_reader))
        if obs['kernel']['status'] != 'observed':
            return out
        obs['support'] = _capture(lambda: _support(reader, contract))
        if obs['support']['status'] != 'observed':
            return out
        for key, fn in (('packet', lambda: _packet(reader, contract, obs['kernel'])),
                        ('marker', lambda: _marker(reader, contract)),
                        ('returncode', lambda: _rc(reader)), ('stdout', lambda: _stdout(reader)),
                        ('artifacts', lambda: _artifacts(reader))):
            obs[key] = _capture(fn)
        if obs['marker']['status'] == 'observed':
            obs['pid'] = _capture(lambda: _pid(proc, obs['marker']['pid'], contract.uid))
            if obs['pid']['status'] == 'absent':
                obs['pid'].update(observed_pid_present=False, original_child_identity_proven=False)
        else:
            obs['pid'] = dict(status='unavailable', reason='validated_marker_required')
        reader.verify(); proc.verify(); boot_reader.verify()
        required = ('kernel', 'support', 'packet', 'marker', 'returncode', 'stdout', 'artifacts')
        unavailable_artifacts = obs['artifacts'].get('artifacts', {})
        if (all(obs[k]['status'] == 'observed' for k in required)
                and obs['pid']['status'] in ('observed', 'absent')
                and all(v['status'] in ('observed', 'absent') for v in unavailable_artifacts.values())):
            out['status'] = 'observed'
    except OSError as exc:
        out.update(reason='os_permission_denied' if exc.errno in (errno.EACCES, errno.EPERM)
                   else 'filesystem_unavailable', errno=exc.errno, request_stopped=True)
    except (ValueError, TypeError, KeyError, UnicodeError, OverflowError, RecursionError):
        out.update(reason='final_custody_check_failed', request_stopped=True)
    return out


def host_inspect(request=None):
    """Read one frozen operation. No caller-controlled path, PID, source or mutation."""
    if request is None:
        request = REQUEST.copy()
    _require(type(request) is dict and request == REQUEST
             and all(type(v) is str for v in request.values()), 'inspection_request_mismatch')
    try:
        _require(os.getuid() == 1000, 'host_account_mismatch')
        with _Reader('/home/ubuntu2', 1000) as home, \
                _Reader('/proc', 1000, final_owner=False) as proc, \
                _Reader('/proc', 0, final_owner=False) as boot:
            return _inspect(home, proc, boot, _System(), _Contract())
    except (OSError, ValueError, TypeError, KeyError, UnicodeError, OverflowError, RecursionError):
        return dict(schema=SCHEMA, run_id=RUN_ID, root_id=ROOT_ID, host=HOST,
                    support_digest=SUPPORT, original_lease_id=LEASE_ID, action='inspect',
                    status='unavailable', reason='fixed_host_surface_unavailable', request_stopped=True,
                    observations={}, limits=LIMITS.copy(), execution_replayed=False,
                    effect_state_changed=False, settlement_eligible=False, accepted=False)


def main():
    try:
        raw = sys.stdin.buffer.read(8193)
        _require(len(raw) <= 8192, 'request_size')
        report = host_inspect(strict_json(raw) if raw else None)
    except (Invalid, OSError):
        report = dict(schema=SCHEMA, status='unavailable', reason='inspection_request_refused')
    print(canonical(report).decode())
    return 0 if report['status'] == 'observed' else 78


if __name__ == '__main__':
    raise SystemExit(main())
