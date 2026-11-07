"""Exact macOS install spelling through the real no-shell argument compiler."""
import errno
import pytest
from tests.test_fabric_attended_claude import _binary, _prepare
from control_plane.fabric_attended_claude import _reviewed_binary, AttendedClaudePreparationError
from integrations.session_bridge.bound_launch_capture.fabric_reserved_attended_launch import ReservedAttendedLaunch
from integrations.session_bridge.bound_launch_capture.runtime import lane_runtime

CANONICAL='/Library/Application Support/MastermindExecutive/bin/claude-2.1.296'


def test_exact_canonical_space_path_reaches_popen_as_one_argument(monkeypatch):
    descriptor=_prepare(binary=_binary(path=CANONICAL,real_path=CANONICAL))
    prepared=ReservedAttendedLaunch('a'*64,descriptor,3,0,())
    arguments=prepared.lane_runtime_arguments()
    assert arguments['command'][0] == CANONICAL and arguments['shell'] is False
    calls=[]
    def preexec_boundary(argv, **kw):
        calls.append((argv,kw))
        raise OSError(errno.ENOENT,'inert mocked pre-exec boundary')
    monkeypatch.setattr(lane_runtime.subprocess,'Popen',preexec_boundary)
    with pytest.raises(lane_runtime.OwnedProcessStartError):
        lane_runtime.begin_owned_process(**arguments)
    assert len(calls)==1
    assert calls[0][0][0] == CANONICAL and calls[0][1]['shell'] is False
    assert calls[0][1]['executable'] is None


@pytest.mark.parametrize('bad', [CANONICAL+';touch',CANONICAL+'$(whoami)',CANONICAL+'`id`',
    CANONICAL+'\n',CANONICAL+'\t',CANONICAL+'\\x',CANONICAL+'/../other',
    '/some other/directory/claude','/Library/Application Support/MastermindExecutive/other/claude-2.1.296'])
def test_space_compatibility_does_not_expand_shell_or_host_path_scope(bad):
    with pytest.raises(AttendedClaudePreparationError):
        _reviewed_binary(_binary(path=bad,real_path=bad))
