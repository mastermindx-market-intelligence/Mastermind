"""Native evidence is usable without importing a transport or callback owner."""
import subprocess
import sys
from pathlib import Path


def test_native_evidence_loads_in_sealed_runtime_without_integrations():
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run([sys.executable, "-S", "-c",
        "import sys; import control_plane.native_continuation; "
        "assert not any(n == 'integrations' or n.startswith('integrations.') for n in sys.modules); "
        "assert 'mcp' not in sys.modules"], cwd=root, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr


def test_native_contract_compatibility_exports_preserve_exact_object_identity():
    from control_plane import native_conversation_protocol as protocol
    from control_plane import native_conversation_read_contract as read
    from integrations.deepseek_harness import native_protocol as original_protocol
    from integrations.deepseek_harness import native_read_port as original_read
    from integrations.session_bridge import deepseek_native as bridge
    for name in ("NativeClaim", "NativeTerminal", "NativeResult", "NativeProtocolError",
                 "NativeOwnerFacts", "native_observation"):
        assert getattr(original_protocol, name) is getattr(protocol, name)
    for name in ("NativeReadUnavailable", "canonical", "native_read_frame",
                 "validate_native_read_request", "validate_native_read_response", "_result_data"):
        assert getattr(original_read, name) is getattr(read, name)
    for name in ("DeepSeekNativeAssociation", "validate_native_read_arguments", "principal_namespace"):
        assert getattr(bridge, name) is getattr(read, name)


def test_sealed_read_contract_imports_without_transport_or_integration_owner():
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run([sys.executable, "-S", "-B", "-c",
        "import sys; import control_plane.native_conversation_read_contract; "
        "assert not any(n == 'integrations' or n.startswith('integrations.') for n in sys.modules); "
        "assert 'mcp' not in sys.modules and 'acp' not in sys.modules"],
        cwd=root, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr


def test_native_static_capabilities_share_original_implementation():
    from control_plane.native_conversation_result import native_operator_capabilities
    from integrations.deepseek_harness.operator_adapter import NativeOperatorAdapter
    assert NativeOperatorAdapter.describe_capabilities() == native_operator_capabilities()
