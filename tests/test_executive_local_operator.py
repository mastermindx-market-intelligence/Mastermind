"""Local operator mode (L4): off-by-default and fail-closed config gates.

The public tunnel reaches this gateway over loopback TCP, so loopback or
headers never carry admission; the socket door exists only when the installed
config block parses, and admission is the kernel peer uid.
"""
import pytest

from integrations.executive_mcp.local_operator import (
    LocalOperatorConfigError,
    parse_local_operator_config,
)

FAKE_SUBJECT = "test-local-operator-000"


def _block(**updates):
    value = {
        "socket_path": "/tmp/local-operator-test.sock",
        "allowed_uids": [501],
        "operator_subject": FAKE_SUBJECT,
    }
    value.update(updates)
    return value


def test_absent_block_keeps_mode_off():
    """(1) No block in config: parse returns None; no socket may be created."""
    assert parse_local_operator_config(None) is None


@pytest.mark.parametrize(
    "block",
    [
        _block(socket_path="relative/path.sock"),          # relative path
        _block(socket_path=""),                            # empty path
        _block(socket_path=b"/tmp/bytes.sock"),            # wrong type
        _block(socket_path="/tmp/a\0b.sock"),              # NUL byte
        _block(allowed_uids=[]),                           # empty uid list
        _block(allowed_uids=[501, 501]),                   # duplicate uids
        _block(allowed_uids=[501, True]),                  # bool is not an int uid
        _block(allowed_uids=[-2]),                         # negative uid
        _block(allowed_uids="501"),                        # wrong type
        _block(operator_subject=""),                       # empty subject
        _block(operator_subject=" padded "),               # padded subject
        _block(operator_subject="line\nbreak"),            # control character
        _block(operator_subject="x" * 129),                # oversized subject
        {"socket_path": "/tmp/s.sock", "allowed_uids": [1]},  # missing key
        _block(extra_key=1),                               # unexpected key
        ["socket_path", "/tmp/s.sock"],                    # not a mapping
    ],
)
def test_malformed_blocks_fail_closed(block):
    """(5) Every malformed row raises: no socket may be created."""
    with pytest.raises(LocalOperatorConfigError):
        parse_local_operator_config(block)


def test_well_formed_block_parses():
    parsed = parse_local_operator_config(_block(allowed_uids=[501, 0]))
    assert parsed.socket_path.as_posix() == "/tmp/local-operator-test.sock"
    assert parsed.allowed_uids == (501, 0)  # order preserved; membership only
    assert parsed.operator_subject == FAKE_SUBJECT
