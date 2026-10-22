"""Opt-in file-production postcondition under the incumbent remote executor.

No dispatch, lease, retry, transport, credential, permission repair or acceptance.
Only new contract directories are created; nothing is moved or removed.
"""
from __future__ import annotations
import argparse
from contextlib import ExitStack
import hashlib
import os
from pathlib import Path
import re
import stat
import sys
import artifact_reader as reader

REQUEST_PREFIX = 'FABRIC_ARTIFACT_REQUEST_V1 '
RESULT_PREFIX = 'FABRIC_ARTIFACTS_V1 '
SCHEMA = 'mastermind.fabric_artifact_production.v1'
RESULT_SCHEMA = 'mastermind.fabric_artifact_manifest.v1'
MODES = {'grok', 'go-codex', 'glm', 'qwen'}
ORDINARY_MODES = {'glm', 'qwen'}
RESERVED_NAMES = {'request.json', 'receipt.json'}
IDENT = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z')
HEX = re.compile(r'[0-9a-f]{64}\Z')


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def valid_identity(value):
    return isinstance(value, str) and IDENT.fullmatch(value)


def validate_contract(value):
    keys = {'schema', 'root', 'parent', 'run_id', 'names', 'body_sha256', 'support_digest'}
    if not isinstance(value, dict) or set(value) != keys or value['schema'] != SCHEMA:
        raise ValueError('artifact_contract_schema')
    if not all(valid_identity(value[k]) for k in ('root', 'parent', 'run_id')):
        raise ValueError('artifact_contract_identity')
    names = value['names']
    if not isinstance(names, list) or not 1 <= len(names) <= reader.MAX_FILES:
        raise ValueError('artifact_contract_names')
    for name in names:
        if not isinstance(name, str) or not reader.COMPONENT.fullmatch(name) or name in RESERVED_NAMES:
            raise ValueError('artifact_contract_name')
    if len(set(names)) != len(names):
        raise ValueError('artifact_contract_duplicate_name')
    if (not isinstance(value['body_sha256'], str) or not HEX.fullmatch(value['body_sha256'])
            or not isinstance(value['support_digest'], str) or not HEX.fullmatch(value['support_digest'])):
        raise ValueError('artifact_contract_digest')
    return value


def directory(contract):
    scope = {k: contract[k] for k in ('root', 'parent', 'run_id')}
    return '/tmp/fabric-' + sha(reader.canonical(scope))[:40]


def paths(contract):
    return [directory(contract) + '/' + n for n in contract['names']]


def source_digest(here):
    # Same fixed public-code manifest as remote_sub; no credentials or state.
    import support_bundle
    files = {}
    for name in support_bundle.SOURCE_FILES:
        path = (Path(here).parent / "orch/fabric/pools.yaml"
                if name == "pools.yaml" and not os.path.lexists(Path(here) / name)
                else Path(here) / name)
        if not path.is_file() or path.is_symlink():
            raise ValueError("artifact_support_source_unavailable")
        files[name] = sha(path.read_bytes())
    return sha(reader.canonical({"schema": "remote-support-code.v1", "files": files}))


def encode_packet(body, *, root, parent, run_id, names, support_digest):
    if not isinstance(body, str):
        raise ValueError('artifact_contract_body')
    if REQUEST_PREFIX in body or RESULT_PREFIX in body:
        raise ValueError('artifact_contract_reserved_marker')
    value = dict(schema=SCHEMA, root=root, parent=parent, run_id=run_id,
                 names=names, body_sha256='0'*64, support_digest=support_digest)
    validate_contract(value)
    instruction = (
        '\n\nREQUIRED MACHINE-CHECKED ARTIFACT DELIVERY:\n'
        'This request opts into the existing Fabric artifact contract. The executor creates a NEW private directory: '
        + directory(value) + '\nWrite the following NEW files directly at these exact absolute paths (no relocation or copying old refused artifacts):\n'
        + '\n'.join(paths(value))
        + '\nUse ordinary permitted file/terminal tools. If an absolute path is refused or remapped, stop and report it; never change permissions or use another carrier. '
        'Do not recreate, chmod, rename, or delete the directory. Create files with mode0600 (for example os.open with O_WRONLY|O_CREAT|O_EXCL and0o600). Files must be regular, owned and nonempty; no symlinks or chmod of existing files. '
        'After writing, run the installed pure local seal helper:\n'
        'python3 "$HOME/lanes/support-releases/' + support_digest + '/ext/artifact_production.py" seal --packet "$HOME/lanes/tmp/'
        + run_id + '.txt"\n'
        'Include its ONE complete FABRIC_ARTIFACTS_V1 JSON line verbatim in the final result, including every path, byte count and SHA-256. '
        'Do not add emphasis, backticks, code fences or prose to that line. '
        'This advertises verified delivery only; it does not grant business acceptance. Missing files, missing/changed manifest or digest mismatch makes completion fail even if the model exits0. '
        'No descendants, retries or old-worker replay are authorized by this contract.\n'
    )
    body += instruction
    value['body_sha256'] = sha(body.encode())
    return REQUEST_PREFIX + reader.canonical(value).decode() + '\n' + body


def parse_packet(prompt):
    if not prompt.startswith(REQUEST_PREFIX):
        return None
    line, sep, body = prompt.partition('\n')
    if not sep or len(line.encode()) > reader.MAX_REQUEST:
        raise ValueError('artifact_contract_header')
    value = validate_contract(reader.strict_json(line[len(REQUEST_PREFIX):]))
    if sha(body.encode()) != value['body_sha256']:
        raise ValueError('artifact_contract_body_changed')
    return value


def bind(contract, key, mode, env, here):
    if Path(here).parent.name != contract["support_digest"]:
        raise ValueError("artifact_contract_support_mismatch")
    if mode not in MODES:
        raise ValueError('artifact_contract_mode_unavailable')
    for field, variable in [('root', 'POOL_ORCHESTRATOR_ID'), ('parent', 'POOL_PARENT_RUN_ID'), ('run_id', 'REMOTE_SUB_RUN_ID')]:
        if contract[field] != env.get(variable):
            raise ValueError('artifact_contract_scope_mismatch')
    if contract['run_id'] != key or not valid_identity(env.get('LANE_REMOTE_HOST')):
        raise ValueError('artifact_contract_scope_mismatch')


class NewDirectory:
    """Hold only a newly created owned directory; never adopt or clean an old one."""
    def __init__(self, contract):
        self.name = directory(contract).split('/')[-1]
        self.tmp = self.fd = None
        self.identity = None

    def __enter__(self):
        try:
            self.tmp = os.open('/tmp', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            os.mkdir(self.name, 0o700, dir_fd=self.tmp)
            created = os.stat(self.name, dir_fd=self.tmp, follow_symlinks=False)
            self.fd = os.open(self.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=self.tmp)
            s = os.fstat(self.fd)
            if (reader.identity(created) != reader.identity(s)
                    or s.st_uid != os.getuid() or stat.S_IMODE(s.st_mode) != 0o700):
                raise ValueError('artifact_directory_not_private')
            self.identity = (s.st_dev, s.st_ino)
            self.verify()
            # No preexisting payload may cross the admission boundary, even if
            # a same-uid process replaced the path immediately after mkdir.
            if os.listdir(self.fd):
                raise ValueError('artifact_directory_not_empty_at_admission')
            if reader.identity(s) != reader.identity(os.fstat(self.fd)):
                raise ValueError('artifact_directory_changed_at_admission')
            self.verify()
            return self
        except BaseException:
            self.__exit__(None, None, None)
            raise

    def verify(self):
        current = os.stat(self.name, dir_fd=self.tmp, follow_symlinks=False)
        opened = os.fstat(self.fd)
        if (not stat.S_ISDIR(current.st_mode) or (current.st_dev, current.st_ino) != self.identity
                or (opened.st_dev, opened.st_ino) != self.identity
                or current.st_uid != os.getuid() or stat.S_IMODE(current.st_mode) != 0o700):
            raise ValueError('artifact_directory_changed')

    def __exit__(self, *_):
        for field in ('fd', 'tmp'):
            fd = getattr(self, field)
            if fd is not None:
                os.close(fd)
                setattr(self, field, None)


def read_owned_files(owner, paths_to_read):
    """Verify one bounded bundle through the executor's held directory.

    Open and capture every before-identity first, read the bytes, then capture all
    after-identities. Their unchanged intervals overlap during the byte reads.
    This proves a common snapshot interval, not perpetual post-return immutability.
    """
    owner.verify()
    parent_before = os.fstat(owner.fd)
    with ExitStack() as opened:
        entries = []
        remaining = reader.MAX_TOTAL
        for path in paths_to_read:
            directory_name, name = reader.validate_path(path)
            if directory_name != owner.name:
                raise ValueError('artifact_directory_scope')
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=owner.fd)
            opened.callback(os.close, fd)
            before = os.fstat(fd)
            if (not stat.S_ISREG(before.st_mode) or before.st_uid != os.getuid()
                    or stat.S_IMODE(before.st_mode) != 0o600):
                raise ValueError('artifact_file_not_private_regular')
            if not 0 < before.st_size <= min(reader.MAX_FILE, remaining):
                raise ValueError('artifact_file_size')
            remaining -= before.st_size
            entries.append((path, name, fd, before))
        result = []
        for path, name, fd, before in entries:
            chunks = []
            budget = before.st_size + 1
            while budget:
                chunk = os.read(fd, min(budget, 65536))
                if not chunk:
                    break
                chunks.append(chunk)
                budget -= len(chunk)
            raw = b''.join(chunks)
            if len(raw) != before.st_size:
                raise ValueError('artifact_file_changed')
            result.append({'path': path, 'bytes': len(raw), 'sha256': sha(raw)})
        for path, name, fd, before in entries:
            if (reader.identity(before) != reader.identity(os.fstat(fd))
                    or reader.identity(before) != reader.identity(os.stat(name, dir_fd=owner.fd, follow_symlinks=False))):
                raise ValueError('artifact_file_changed')
        if reader.identity(parent_before) != reader.identity(os.fstat(owner.fd)):
            raise ValueError('artifact_directory_changed_during_bundle_read')
        owner.verify()
        return result


def observed_manifest(contract, host, owner=None):
    validate_contract(contract)
    if not valid_identity(host):
        raise ValueError('artifact_manifest_host')
    files = []
    remaining = reader.MAX_TOTAL
    if owner is not None:
        files = read_owned_files(owner, paths(contract))
        return dict(schema=RESULT_SCHEMA, request_sha256=sha(reader.canonical(contract)),
                    root=contract['root'], parent=contract['parent'], run_id=contract['run_id'], host=host, files=files)
    for path in paths(contract):
        item = reader.read_one(path, remaining)
        if item['status'] != 'RETRIEVED' or not 0 < item['bytes'] <= remaining:
            raise ValueError('artifact_file_unavailable')
        # This new production contract is stricter than legacy export modes.
        # It observes only; existing files are never chmodded.
        if item['observed_file']['mode'] != 0o600:
            raise ValueError('artifact_file_not_private')
        remaining -= item['bytes']
        files.append({k: item[k] for k in ('path', 'bytes', 'sha256')})
    return dict(schema=RESULT_SCHEMA, request_sha256=sha(reader.canonical(contract)),
                root=contract['root'], parent=contract['parent'], run_id=contract['run_id'], host=host, files=files)


def manifest_from_stdout(stdout, *, root, parent, run_id, host):
    if not isinstance(stdout, str):
        raise ValueError('artifact_manifest_text')
    matches = []
    for line in stdout.splitlines():
        # Permit only the exact full-line Markdown emphasis wrapper. Preserve
        # original stdout bytes for all digests and count wrapped/plain duplicates.
        marker_wrapper = '**' + RESULT_PREFIX.rstrip() + '**'
        if line.startswith(marker_wrapper):
            prefix = marker_wrapper + ' `'
            if (not line.startswith(prefix) or not line.endswith('`')
                    or len(line.encode()) > reader.MAX_REQUEST):
                raise ValueError('artifact_manifest_wrapper')
            line = RESULT_PREFIX + line[len(prefix):-1]
        elif line.startswith('**' + RESULT_PREFIX):
            if not line.endswith('**') or len(line.encode()) > reader.MAX_REQUEST:
                raise ValueError('artifact_manifest_wrapper')
            line = line[2:-2]
        if line.startswith(RESULT_PREFIX):
            matches.append(line)
    if len(matches) != 1 or len(matches[0].encode()) > reader.MAX_REQUEST:
        raise ValueError('artifact_manifest_missing_or_duplicate')
    value = reader.strict_json(matches[0][len(RESULT_PREFIX):])
    if (not isinstance(value, dict) or set(value) != {'schema','request_sha256','root','parent','run_id','host','files'}
            or value['schema'] != RESULT_SCHEMA or not isinstance(value['request_sha256'], str)
            or not HEX.fullmatch(value['request_sha256'])
            or any(value[k] != v for k,v in dict(root=root,parent=parent,run_id=run_id,host=host).items())):
        raise ValueError('artifact_manifest_scope')
    files = value['files']
    if not isinstance(files,list) or not 1 <= len(files) <= reader.MAX_FILES:
        raise ValueError('artifact_manifest_files')
    expected_directory = directory(dict(root=root,parent=parent,run_id=run_id))
    seen = set(); total = 0
    for item in files:
        if not isinstance(item,dict) or set(item) != {'path','bytes','sha256'}:
            raise ValueError('artifact_manifest_entry')
        reader.validate_path(item['path'])
        if (item['path'].rsplit('/',1)[0] != expected_directory or item['path'] in seen
                or item['path'].rsplit('/',1)[1] in RESERVED_NAMES):
            raise ValueError('artifact_manifest_path')
        if type(item['bytes']) is not int or not 0 < item['bytes'] <= reader.MAX_FILE:
            raise ValueError('artifact_manifest_size')
        if not isinstance(item['sha256'], str) or not HEX.fullmatch(item['sha256']):
            raise ValueError('artifact_manifest_digest')
        seen.add(item['path']); total += item['bytes']
    if total > reader.MAX_TOTAL:
        raise ValueError('artifact_manifest_total')
    return value


def verify_completion(contract, owner, stdout, host):
    owner.verify()
    expected = observed_manifest(contract, host, owner=owner)
    actual = manifest_from_stdout(stdout,root=contract['root'],parent=contract['parent'],run_id=contract['run_id'],host=host)
    if actual != expected:
        raise ValueError('artifact_manifest_mismatch')
    owner.verify()
    return actual


def record_glm_completion(receipt_path, contract, manifest, stdout):
    """Compatibility entry point for existing GLM callers."""
    return record_ordinary_completion(receipt_path, contract, manifest, stdout, mode="glm")


def record_ordinary_completion(receipt_path, contract, manifest, stdout, *, mode):
    """Add verified production evidence to the executor's existing receipt.

    Ordinary attended GLM/Qwen has no native/Go settlement envelope. Do not invent one or a
    lease join: retain the exact opt-in contract in the existing process receipt
    only after successful cleanup and file verification. Old runs stay ineligible.
    A failed publication makes the executor fail; it never retries the child.
    """
    from lane_runtime import cleanup_receipt_is_proven
    if mode not in ORDINARY_MODES:
        raise ValueError("artifact_completion_mode_unavailable")
    validate_contract(contract)
    actual = manifest_from_stdout(stdout, root=contract['root'], parent=contract['parent'],
                                  run_id=contract['run_id'], host=manifest['host'])
    if actual != manifest or actual['request_sha256'] != sha(reader.canonical(contract)):
        raise ValueError('artifact_completion_manifest_mismatch')
    if [item['path'] for item in actual['files']] != paths(contract):
        raise ValueError('artifact_completion_file_scope')
    fd = os.open(receipt_path, os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        before = os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode) or before.st_uid != os.getuid()
                or before.st_mode & 0o002 or not 0 < before.st_size <= 65536):
            raise ValueError('artifact_process_receipt_unsafe')
        raw = os.read(fd, 65537)
        if len(raw) != before.st_size or reader.identity(before) != reader.identity(os.fstat(fd)):
            raise ValueError('artifact_process_receipt_changed')
        row = reader.strict_json(raw)
        if (type(row) is not dict or row.get('schema') != 'mastermind.local_owned_process_receipt.v1'
                or row.get('label') != contract['run_id']
                or type(row.get('returncode')) is not int or row['returncode'] != 0
                or row.get('timed_out') is not False or row.get('runtime_failure_code') is not None
                or row.get('stdout_truncated') is not False or row.get('stderr_truncated') is not False
                or type(row.get('stdout_bytes')) is not int or row['stdout_bytes'] != len(stdout.encode('utf-8'))
                or not cleanup_receipt_is_proven(row.get('cleanup', {}))):
            raise ValueError('artifact_process_receipt_unqualified')
        if 'artifact_production' in row:
            raise ValueError('artifact_process_already_sealed')
        row['artifact_production'] = dict(schema='mastermind.fabric_artifact_completion.v1',
            mode=mode, contract=contract, manifest=manifest, stdout_sha256=sha(stdout.encode('utf-8')))
        encoded = reader.canonical(row) + b'\n'
        if len(encoded) > 65536:
            raise ValueError('artifact_process_receipt_limit')
        # Hold the original inode; never overwrite a pathname replacement.
        if reader.identity(before) != reader.identity(os.stat(receipt_path, follow_symlinks=False)):
            raise ValueError('artifact_process_receipt_changed')
        os.lseek(fd, 0, os.SEEK_SET)
        remaining = encoded
        while remaining:
            count = os.write(fd, remaining)
            if count <= 0:
                raise OSError('artifact_process_short_write')
            remaining = remaining[count:]
        os.ftruncate(fd, len(encoded))
        os.fsync(fd)
        after = os.fstat(fd)
        os.lseek(fd, 0, os.SEEK_SET)
        if (os.read(fd, 65537) != encoded
                or reader.identity(after) != reader.identity(os.stat(receipt_path, follow_symlinks=False))
                or reader.identity(after) != reader.identity(os.fstat(fd))):
            raise ValueError('artifact_process_publication_unconfirmed')
    finally:
        os.close(fd)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['seal'])
    parser.add_argument('--packet',required=True)
    args=parser.parse_args()
    # No directory creation/adoption here; the incumbent executor already owns it.
    contract=parse_packet(Path(args.packet).read_text())
    if contract is None:
        raise ValueError('artifact_contract_missing')
    bind(contract,os.environ.get('REMOTE_SUB_RUN_ID'),os.environ.get('MODE', 'go-codex'),os.environ,Path(__file__).resolve().parent)
    print(RESULT_PREFIX+reader.canonical(observed_manifest(contract,os.environ['LANE_REMOTE_HOST'])).decode())


if __name__ == '__main__':
    try:
        main()
    except (ValueError,OSError,TypeError,KeyError,RecursionError):
        print('ARTIFACT_SEAL_REFUSED',file=sys.stderr)
        raise SystemExit(65)
