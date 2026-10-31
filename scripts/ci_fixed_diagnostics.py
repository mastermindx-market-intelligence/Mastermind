"""Prospective public test facts only; never parse logs or change test outcomes."""
from __future__ import annotations

import ast
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import subprocess

MAX_SOURCE = 2 * 1024 * 1024
MAX_SNAPSHOT = 2 ** 18
MAX_PROGRESS = 2 ** 9
MAX_FAILURES = 2 ** 7
PHASES = frozenset(('collect', 'setup', 'call', 'teardown'))
KINDS = {kind: kind.__name__ for kind in (AssertionError, ValueError, TypeError,
    KeyError, IndexError, RuntimeError, OSError, PermissionError, FileNotFoundError,
    NotADirectoryError, IsADirectoryError, TimeoutError, ImportError, ModuleNotFoundError, SyntaxError)}
PUBLIC_PATH = re.compile(r'tests/(?:[A-Za-z0-9_]+/)*test_[A-Za-z0-9_]+[.]py\Z')
IDENTIFIER = re.compile(r'[A-Za-z_][A-Za-z0-9_]{0,127}\Z')


def _integer(value, maximum=1000000):
    return type(value) is int and 0 <= value <= maximum


class PublicCatalog:
    """Exact HEAD blobs plus actual regular-source bytes and static AST names.

    A .git-less controlled snapshot gets no general catalogue. Its existing
    literal H1 metadata reporter remains independent of this optional helper.
    """
    def __init__(self, root):
        self.root = Path(root).absolute()
        self.head = None
        self.blobs = {}
        self.cache = {}
        try:
            head = subprocess.run(['git', '-C', str(self.root), 'rev-parse', '--verify', 'HEAD'],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=5, check=True).stdout.strip()
            if not re.fullmatch(rb'[0-9a-f]{40}', head):
                return
            tree = subprocess.run(['git', '-C', str(self.root), 'ls-tree', '-rz', head.decode(), '--', 'tests'],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=5, check=True).stdout
            if len(tree) > 4 * 1024 * 1024:
                return
            blobs = {}
            for row in tree.split(b'\0'):
                if not row:
                    continue
                fields, raw_path = row.split(b'\t', 1)
                mode, kind, digest = fields.split(b' ')
                try:
                    name = raw_path.decode('ascii')
                except UnicodeError:
                    continue
                if (mode in (b'100644', b'100755') and kind == b'blob'
                        and re.fullmatch(rb'[0-9a-f]{40}', digest)
                        and PUBLIC_PATH.fullmatch(name)):
                    blobs[name] = digest.decode()
            self.head, self.blobs = head.decode(), blobs
        except (OSError, ValueError, UnicodeError, subprocess.SubprocessError):
            pass

    def source(self, module):
        if type(module) is not str or module not in self.blobs:
            return None
        path = self.root / module
        directories = []
        try:
            # Descriptor-relative traversal never follows a swapped ancestor
            # into a private tree while qualifying public source bytes.
            parent = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            directories.append((parent, None, None))
            parts = module.split('/')
            for name in parts[:-1]:
                child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
                directories.append((child, parent, name))
                parent = child
            fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
            try:
                before = os.fstat(fd)
                if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
                        or not 0 < before.st_size <= MAX_SOURCE):
                    return None
                raw = os.pread(fd, before.st_size + 1, 0)
                after = os.fstat(fd)
                named = os.stat(parts[-1], dir_fd=parent, follow_symlinks=False)
                identity = lambda value: (value.st_dev, value.st_ino, value.st_mode,
                    value.st_uid, value.st_gid, value.st_nlink, value.st_size,
                    value.st_mtime_ns, value.st_ctime_ns)
                if len(raw) != before.st_size or identity(before) != identity(after) or identity(before) != identity(named):
                    return None
                for directory, ancestor, name in directories:
                    visible = self.root.lstat() if ancestor is None else os.stat(name, dir_fd=ancestor, follow_symlinks=False)
                    held = os.fstat(directory)
                    if (held.st_dev, held.st_ino, held.st_mode) != (visible.st_dev, visible.st_ino, visible.st_mode):
                        return None
            finally:
                os.close(fd)
            digest = hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
            if digest != self.blobs[module]:
                return None
            if module in self.cache:
                return self.cache[module]
            try:
                tree = ast.parse(raw)
            except (SyntaxError, UnicodeError):
                # A tracked but unparseable module can still identify a
                # collection failure; it contributes no accepted function.
                tree = None
            cases, functions = set(), set()
            def visit(nodes, classes=(), in_function=False):
                for node in nodes:
                    if isinstance(node, ast.ClassDef) and IDENTIFIER.fullmatch(node.name):
                        visit(node.body, (*classes, node.name), in_function)
                    elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and IDENTIFIER.fullmatch(node.name):
                        functions.add(node.name)
                        if not in_function and node.name.startswith('test_'):
                            cases.add('.'.join((*classes, node.name)))
                        visit(node.body, classes, True)
                    else:
                        visit(list(ast.iter_child_nodes(node)), classes, in_function)
            if tree is not None:
                visit(tree.body)
            value = dict(cases=frozenset(cases), functions=frozenset(functions),
                lines=len(raw.splitlines()), filename=str(path))
            self.cache[module] = value
            return value
        except (OSError, ValueError, SyntaxError, UnicodeError, RecursionError):
            return None
        finally:
            for directory, _, _ in reversed(directories):
                os.close(directory)

    def failure(self, nodeid, phase, *, error=None, crash=None):
        if type(nodeid) is not str or type(phase) is not str or phase not in PHASES:
            return None
        module, *parts = nodeid.split('::')
        source = self.source(module)
        if source is None:
            return None
        candidate = '.'.join(part.split('[', 1)[0] for part in parts)
        value = dict(module=module, case=candidate if candidate in source['cases'] else None,
            function=None, phase=phase, line=None, kind=KINDS.get(type(error), 'UNKNOWN'))
        if error is not None:
            trace = BaseException.__traceback__.__get__(error) if isinstance(error, BaseException) else None
            for unused in range(32):
                if trace is None:
                    break
                code = trace.tb_frame.f_code
                if (os.path.abspath(code.co_filename) == source['filename']
                        and code.co_name in source['functions']
                        and type(trace.tb_lineno) is int and 0 < trace.tb_lineno <= source['lines']):
                    value.update(function=code.co_name, line=trace.tb_lineno)
                trace = trace.tb_next
        elif crash is not None:
            filename, line = getattr(crash, 'path', None), getattr(crash, 'lineno', None)
            if (type(filename) is str and os.path.abspath(filename) == source['filename']
                    and type(line) is int and 0 < line <= source['lines']):
                value['line'] = line
        return value


class FixedDiagnostics:
    """Closed snapshots in an exclusively owned, cooperative per-job directory.

    Identity checks refuse observed replacement. Portable check-and-replace
    does not provide atomic compare-and-swap against adversarial same-UID code.
    """
    def __init__(self, catalog, directory=None):
        self.catalog = catalog
        self.progress = []
        self.failures = []
        self.truncated = False
        self.directory = None
        self.directory_identity = None
        self.file_identity = None
        self.file_size = None
        if directory is not None:
            try:
                path = Path(directory)
                info = path.lstat()
                if (path.is_absolute() and stat.S_ISDIR(info.st_mode)
                        and stat.S_IMODE(info.st_mode) == stat.S_IRWXU and info.st_uid == os.geteuid()
                        and not (path / 'ci-fixed-diagnostics.json').exists()
                        and not (path / 'ci-fixed-diagnostics.json').is_symlink()):
                    self.directory = path
                    self.directory_identity = (info.st_dev, info.st_ino, info.st_mode, info.st_uid)
            except (OSError, ValueError):
                pass
        # An interrupted collection still leaves a closed empty observation,
        # rather than inventing a last module that never started.
        self.flush()

    def progress_record(self, event, module, **fields):
        if self.catalog.source(module) is None:
            return
        if event == 'start' and not fields:
            value = dict(event=event, module=module)
        elif event == 'summary' and set(fields) == {'cases_started', 'cases_finished', 'reported_seconds'}:
            seconds = fields['reported_seconds']
            if (not _integer(fields['cases_started']) or not _integer(fields['cases_finished'])
                    or fields['cases_finished'] > fields['cases_started']
                    or type(seconds) not in (int, float) or not math.isfinite(seconds)
                    or not 0 <= seconds <= 7200):
                return
            value = dict(event=event, module=module, **fields)
        else:
            return
        self.progress.append(value)
        if len(self.progress) > MAX_PROGRESS:
            del self.progress[0]
            self.truncated = True
        self.flush()

    def failure_record(self, nodeid, phase, *, error=None, crash=None):
        value = self.catalog.failure(nodeid, phase, error=error, crash=crash)
        if value is not None:
            if len(self.failures) < MAX_FAILURES:
                self.failures.append(value.copy())
            else:
                self.truncated = True
            self.flush()
        return value

    def _closed(self):
        head=self.catalog.head
        if head is not None and (type(head) is not str or not re.fullmatch(r'[0-9a-f]{40}',head)):
            return False
        if (type(self.truncated) is not bool or type(self.progress) is not list
                or type(self.failures) is not list or len(self.progress)>MAX_PROGRESS
                or len(self.failures)>MAX_FAILURES):
            return False
        for value in self.progress:
            if type(value) is not dict or type(value.get('module')) is not str or value['module'] not in self.catalog.cache:
                return False
            if type(value.get('event')) is not str:
                return False
            if value.get('event')=='start' and set(value)=={'event','module'}:
                continue
            if value.get('event')!='summary' or set(value)!={'event','module','cases_started','cases_finished','reported_seconds'}:
                return False
            seconds=value['reported_seconds']
            if (not _integer(value['cases_started']) or not _integer(value['cases_finished'])
                    or value['cases_finished']>value['cases_started']
                    or type(seconds) not in (int,float) or not math.isfinite(seconds) or not 0<=seconds<=7200):
                return False
        for value in self.failures:
            if type(value) is not dict or set(value)!={'module','case','function','phase','line','kind'}:
                return False
            module=value['module']
            if type(module) is not str or module not in self.catalog.cache:
                return False
            source=self.catalog.cache[module]
            if (value['case'] is not None and (type(value['case']) is not str or value['case'] not in source['cases'])
                    or value['function'] is not None and (type(value['function']) is not str or value['function'] not in source['functions'])
                    or type(value['phase']) is not str or value['phase'] not in PHASES
                    or type(value['kind']) is not str or value['kind'] not in {*KINDS.values(),'UNKNOWN'}
                    or value['line'] is not None and (not _integer(value['line'],source['lines']) or value['line']==0)):
                return False
        return True

    @staticmethod
    def _private_file(info, size):
        return (stat.S_ISREG(info.st_mode) and stat.S_IMODE(info.st_mode)==0o600
            and info.st_uid==os.geteuid() and info.st_nlink==1 and info.st_size==size)

    def _destination_is_owned(self, directory):
        try:
            current=os.stat('ci-fixed-diagnostics.json',dir_fd=directory,follow_symlinks=False)
        except FileNotFoundError:
            return self.file_identity is None
        return (self.file_identity is not None
            and (current.st_dev,current.st_ino)==self.file_identity
            and self._private_file(current,self.file_size))

    def flush(self):
        if self.directory is None or not self._closed():
            return
        fd = tmp = None
        temporary_identity = None
        try:
            raw = json.dumps(dict(schema='ci.fixed-diagnostics.v1', head=self.catalog.head,
                progress=self.progress, failures=self.failures, truncated=self.truncated),
                sort_keys=True, separators=(',', ':'), allow_nan=False).encode('ascii')
            while len(raw) > MAX_SNAPSHOT and self.progress:
                del self.progress[0]
                self.truncated = True
                raw = json.dumps(dict(schema='ci.fixed-diagnostics.v1', head=self.catalog.head,
                    progress=self.progress, failures=self.failures, truncated=self.truncated),
                    sort_keys=True, separators=(',', ':'), allow_nan=False).encode('ascii')
            if len(raw) > MAX_SNAPSHOT:
                return
            fd = os.open(self.directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            info = os.fstat(fd)
            named = self.directory.lstat()
            identity = lambda x: (x.st_dev, x.st_ino, x.st_mode, x.st_uid)
            if identity(info) != self.directory_identity or identity(named) != self.directory_identity:
                return
            if not self._destination_is_owned(fd):
                return
            tmp = os.open('.ci-fixed-diagnostics.next', os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o600, dir_fd=fd)
            created = os.fstat(tmp)
            temporary_identity = (created.st_dev, created.st_ino)
            if os.write(tmp, raw) != len(raw):
                return
            os.fsync(tmp)
            if identity(self.directory.lstat()) != self.directory_identity:
                return
            held=os.fstat(tmp)
            named_tmp=os.stat('.ci-fixed-diagnostics.next',dir_fd=fd,follow_symlinks=False)
            if ((held.st_dev,held.st_ino)!=temporary_identity
                    or (named_tmp.st_dev,named_tmp.st_ino)!=temporary_identity
                    or not self._private_file(held,len(raw)) or not self._private_file(named_tmp,len(raw))
                    or not self._destination_is_owned(fd)):
                return
            os.replace('.ci-fixed-diagnostics.next', 'ci-fixed-diagnostics.json', src_dir_fd=fd, dst_dir_fd=fd)
            final = os.stat('ci-fixed-diagnostics.json', dir_fd=fd, follow_symlinks=False)
            if ((final.st_dev,final.st_ino)!=temporary_identity or not self._private_file(final,len(raw))):
                # Never adopt a replacement observed after publication. Its
                # owner retains it; disable future writes on this directory.
                self.directory=None
                return
            self.file_identity = temporary_identity
            self.file_size = len(raw)
            os.fsync(fd)
        except (OSError, ValueError, TypeError, UnicodeError):
            pass
        finally:
            if tmp is not None:
                os.close(tmp)
                if fd is not None:
                    try:
                        visible = os.stat('.ci-fixed-diagnostics.next', dir_fd=fd, follow_symlinks=False)
                        if (visible.st_dev, visible.st_ino) == temporary_identity:
                            os.unlink('.ci-fixed-diagnostics.next', dir_fd=fd)
                    except OSError:
                        pass
            if fd is not None:
                os.close(fd)
