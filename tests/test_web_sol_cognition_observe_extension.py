"""Actual browser listeners with simulated IO; receipts cross the real Python validator."""
from pathlib import Path
import json
import os
import shutil
import subprocess


def test_observe_extension_actual_modules_and_wire_receipts():
    from tests.test_web_sol_cognition_transport_core import _real_extension_payload
    from tests.test_web_sol_cognition_transport import _result
    from integrations.chairman_surfaces import web_sol_protocol as protocol

    root = Path(__file__).resolve().parents[1]
    node = shutil.which("node")
    assert node is not None
    result = subprocess.run(
        [node, "--test", str(root / "tests/web_sol_cognition_observe_extension.test.cjs")],
        cwd=root, capture_output=True, text=True, timeout=90,
        env={**os.environ, "COGNITION_PAYLOAD": json.dumps(_real_extension_payload()),
             "COGNITION_RESULT": json.dumps(_result()),
             "CAPABILITY_DIGEST": protocol.transport_capability_digest()},
    )
    assert result.returncode == 0, result.stdout + result.stderr
    receipts = [json.loads(line.split("OBSERVATION_PROOF:", 1)[1])
                for line in result.stdout.splitlines() if "OBSERVATION_PROOF:" in line]
    assert len(receipts) >= 30
    for receipt in receipts:
        protocol.validate_receipt(receipt)
    assert {"COGNITION_RESULT_READY", "COGNITION_RESULT_PENDING", "COGNITION_RESULT_REFUSED",
            "UNKNOWN", "REQUEST_EXPIRED"} <= {r["status"] for r in receipts}
