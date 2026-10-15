"""Actual protected observer actions; no live browser or provider submission."""
import json
import shutil
import subprocess
from pathlib import Path

from integrations.chairman_surfaces import web_sol_protocol as protocol
from tests.test_web_sol_reliability import NODE_HARNESS

ROOT = Path(__file__).resolve().parents[1]
SCENARIO = r'''
  if (scenario === "inspect-no-effect") {
    context.recordProbe(probe(), {tab: {id: 8, windowId: 10}});
    const inspect = {...request, action: "INSPECT"};
    const ambiguous = await context.handleNativeRequest(inspect, port);
    assert.equal(ambiguous.status, "AMBIGUOUS_TARGET");
    const blockedFocus = await context.handleNativeRequest(request, port);
    assert.equal(blockedFocus.status, "AMBIGUOUS_TARGET");
    assert.equal(probeSendCount, 0, "ambiguity must refuse before reprobe");
    assert.equal(activationCount, 0);
    assert.deepEqual(activatedWindows, []);
    context.removeTabMapping(8);
    const observed = await context.handleNativeRequest(inspect, port);
    assert.equal(observed.status, "INSPECTED");
    assert.equal(probeSendCount, 1, "successful INSPECT must actually observe");
    assert.equal(activationCount, 0, "successful INSPECT cannot activate a tab");
    assert.deepEqual(activatedWindows, [], "INSPECT cannot focus a window");
    console.log(JSON.stringify([ambiguous, blockedFocus, observed]));
  } else if (scenario === "false-focus") {
'''


def test_actual_ambiguous_target_and_successful_inspect_have_no_browser_effect():
    node = shutil.which("node")
    assert node is not None, "Node is required for the actual-source gate"
    # Reuse the accepted simulated IO, keeping all decisions in real source.
    harness = NODE_HARNESS.replace("let activationCount = 0;",
                                  "let activationCount = 0; let probeSendCount = 0;", 1)
    harness = harness.replace("async sendMessage() { return probe(); },",
                              "async sendMessage() { probeSendCount++; return probe(); },", 1)
    harness = harness.replace('if (scenario === "false-focus") {', SCENARIO, 1)
    completed = subprocess.run([node, "-e", harness, "inspect-no-effect",
        str(ROOT / "integrations/chairman_surfaces/web_sol_extension/background.js")],
        capture_output=True, text=True, timeout=20, check=False)
    assert completed.returncode == 0, completed.stdout + completed.stderr
    documents = json.loads(completed.stdout)
    assert [protocol.validate_receipt(doc)["status"] for doc in documents] == [
        "AMBIGUOUS_TARGET", "AMBIGUOUS_TARGET", "INSPECTED"]
    assert [doc["action"] for doc in documents] == ["INSPECT", "FOREGROUND", "INSPECT"]
