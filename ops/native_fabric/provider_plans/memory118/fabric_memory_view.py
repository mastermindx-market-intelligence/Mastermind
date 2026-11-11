"""Prospective Memory channel boundary in the incumbent child owner.

A v3 authorization is not a portable Memory credential.  The fixed selected
Memory issuer transport is not implemented in this source pin.  Until that
actual owner exists, source requests/refusals must not mint, backfill or expose a
case from a caller dict, callback, Boolean, operator token or metadata binding.
Ordinary v1 requests and v2 display-only metadata remain ordinary operations.
"""
from __future__ import annotations

SCHEMA = 'mastermind.fabric_bound_child_authorization.v3'
ISSUER_UNAVAILABLE = 'protected_memory_owner_required'
VIEW_REQUIRED = 'participant_view_required'
# Exact canonical body prefix from the frozen Linux packet contract, not an
# added packet header or any authentication fact.
PACKET_PREFIX = b'{"schema":"research_factory.market_memory_e0_participant_packet.v1",'


def _refuse(reason):
    from fabric_operator_contract import DelegationRefused
    raise DelegationRefused(reason)


def is_prospective(stored):
    # Recognition is a restriction, never authentication or a valid-row parser.
    return type(stored) is dict and stored.get('schema') == SCHEMA


def require_generic(stored):
    # Only the two incumbent public row families retain generic disclosure.
    # An unknown/new wrapper is not permission to fall back to raw results.
    if (type(stored) is not dict or stored.get('schema') not in (
            'mastermind.fabric_operator_child_request.v1',
            'mastermind.fabric_bound_child_authorization.v2')):
        _refuse(VIEW_REQUIRED)


def selected_case(owner, grant, lookup):
    """Fixed issuer entry, deliberately not an injected verifier/reader.

    This is the unqualified CLI boundary, not an issuer implementation.
    Its UID-501 packet/result store cannot hold protected Memory material.
    The installed protected owner must retain custody through source issuance,
    child execution and recipient disclosure. No value at this entry can turn
    an ordinary operator token into that owner or a source-use grant.
    """
    _refuse(ISSUER_UNAVAILABLE)


def validate_lookup(value):
    from fabric_operator_owner import safe_id
    if type(value) is not dict or set(value) != {'run_id'}:
        _refuse(VIEW_REQUIRED)
    run = value['run_id']
    if type(run) is not str:
        _refuse(VIEW_REQUIRED)
    safe_id(run)
    return run


def _stored_row(row):
    import json
    from fabric_operator_owner import canonical, digest
    if type(row) is not dict or type(row.get('request_json')) is not str:
        _refuse(VIEW_REQUIRED)
    raw = row['request_json']
    if len(raw.encode()) > 1048576:
        _refuse(VIEW_REQUIRED)
    def pairs(items):
        value = {}
        for key, item in items:
            if key in value:
                _refuse(VIEW_REQUIRED)
            value[key] = item
        return value
    try:
        stored = json.loads(raw, object_pairs_hook=pairs, parse_constant=lambda _: _refuse(VIEW_REQUIRED))
        if type(stored) is not dict or canonical(stored) != raw or digest(raw.encode()) != row.get('request_digest'):
            _refuse(VIEW_REQUIRED)
    except (ValueError, TypeError, UnicodeError, RecursionError):
        _refuse(VIEW_REQUIRED)
    return stored


def require_generic_row(row):
    require_generic(_stored_row(row))



def _refuse_case_packet(here, run_id):
    # Only fixed incumbent packet names and a public protocol prefix are read.
    # The prefix restricts disclosure; it is never an issuer/authentication fact.
    import os
    import stat
    from pathlib import Path
    for suffix in ('.operator-packet', '.request.packet'):
        path = Path(here) / 'state/remote_sub' / (run_id + suffix)
        try:
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        except FileNotFoundError:
            continue
        except OSError:
            _refuse(VIEW_REQUIRED)
        try:
            before = os.fstat(fd)
            if not stat.S_ISREG(before.st_mode) or before.st_uid != os.getuid() or before.st_mode & 0o002:
                _refuse(VIEW_REQUIRED)
            prefix = os.read(fd, len(PACKET_PREFIX))
            after = os.fstat(fd)
            current = os.stat(path, follow_symlinks=False)
            identity = lambda st: (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_mode, st.st_uid)
            if identity(before) != identity(after) or identity(before) != identity(current):
                _refuse(VIEW_REQUIRED)
            if prefix == PACKET_PREFIX:
                _refuse(VIEW_REQUIRED)
        except (OSError, ValueError, TypeError):
            _refuse(VIEW_REQUIRED)
        finally:
            os.close(fd)


def _current_authorization_row(here, run_id):
    """Closed privacy classification under the incumbent lock, including WAL.

    Read the same bounded owned files using the incumbent directory/FD reader.
    SQLite operates ONLY on disposable private copies, never the runtime DB.
    This grants no participant authority; only the disposable copy is checkpointed.
    """
    import sqlite3
    import tempfile
    from pathlib import Path
    import artifact_delivery as delivery
    query = 'SELECT run_id,request_json,request_digest FROM operator_child_authorizations WHERE run_id=?'
    try:
        return delivery._retained_broker_row(query, (run_id,), here=here)
    except ValueError as error:
        if str(error) != 'lease_snapshot_has_live_sidecar':
            raise
    with delivery.DirectoryChain(Path(here) / 'broker') as chain, delivery.LeaseSnapshotLock(chain):
        def journal_absent():
            try:
                delivery.os.stat('leases.sqlite-journal', dir_fd=chain.fd, follow_symlinks=False)
            except FileNotFoundError:
                return
            raise ValueError('lease_snapshot_has_recovery_journal')
        journal_absent()
        database = delivery.read_local_at(chain, 'leases.sqlite', 16777216)
        wal = delivery.read_local_at(chain, 'leases.sqlite-wal', 16777216)
        if (database[:16] != b'SQLite format 3\x00' or len(database) < 100
                or database[18:20] != b'\x02\x02' or 0 < len(wal) < 32):
            raise ValueError('lease_snapshot_header')
        try:
            with tempfile.TemporaryDirectory(prefix='fabric-privacy-snapshot-') as directory:
                snapshot = Path(directory) / 'leases.sqlite'
                snapshot.write_bytes(database)
                snapshot.with_name('leases.sqlite-wal').write_bytes(wal)
                connection = sqlite3.connect(snapshot.as_uri() + '?mode=rw', uri=True, timeout=0)
                try:
                    deadline = delivery.time.monotonic() + 2
                    connection.set_progress_handler(lambda: int(delivery.time.monotonic() >= deadline), 1000)
                    # SQLite validates WAL salts/checksums/committed frames. Require
                    # every captured frame to be consumed, rather than silently
                    # accepting a corrupt/uncommitted tail as older ordinary state.
                    page_size = connection.execute('PRAGMA page_size').fetchone()[0]
                    frames, remainder = divmod(len(wal) - 32, page_size + 24) if wal else (0, 0)
                    if (wal and frames < 1) or remainder:
                        raise ValueError('lease_snapshot_wal_framing')
                    checkpoint = connection.execute('PRAGMA wal_checkpoint(PASSIVE)').fetchone()
                    if tuple(checkpoint) != (0, frames, frames):
                        raise ValueError('lease_snapshot_wal_incomplete')
                    connection.execute('PRAGMA query_only=ON')
                    connection.row_factory = sqlite3.Row
                    row = connection.execute(query, (run_id,)).fetchone()
                finally:
                    connection.close()
        finally:
            journal_absent()
            if (delivery.read_local_at(chain, 'leases.sqlite', 16777216) != database
                    or delivery.read_local_at(chain, 'leases.sqlite-wal', 16777216) != wal):
                raise ValueError('lease_snapshot_changed')
            chain.verify()
        return row


def require_generic_channel(here, run_id):
    """Deny a v3 original through every generic public delivery surface.

    Reads only the incumbent broker snapshot; it never issues a capability,
    reads a worker artifact or creates/migrates a database. Missing old broker
    or old authorization table preserves non-operator v1 behavior. An unsafe
    or unsettled existing snapshot cannot authorize disclosure.
    """
    from pathlib import Path
    import sqlite3
    import artifact_delivery
    from fabric_operator_owner import safe_id
    if type(run_id) is not str:
        _refuse(VIEW_REQUIRED)
    safe_id(run_id)
    here = Path(here)
    try:
        (here / 'broker/leases.sqlite').lstat()
    except FileNotFoundError:
        _refuse_case_packet(here, run_id)
        return
    except OSError:
        _refuse(VIEW_REQUIRED)
    try:
        row = _current_authorization_row(here, run_id)
    except sqlite3.OperationalError as error:
        if str(error) == 'no such table: operator_child_authorizations':
            _refuse_case_packet(here, run_id)
            return
        _refuse(VIEW_REQUIRED)
    except (OSError, ValueError, TypeError, KeyError, sqlite3.Error):
        _refuse(VIEW_REQUIRED)
    if row is not None:
        require_generic_row(dict(row))
    _refuse_case_packet(here, run_id)
