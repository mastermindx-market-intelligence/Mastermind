import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "integrations" / "slack_agent_dialogue" / "metadata_verifier.py"
SCRIPT = ROOT / "scripts" / "verify_slack_agent_dialogue_metadata.py"


def test_verifier_has_no_secret_or_state_backdoors() -> None:
    text = MODULE.read_text(encoding="utf-8")
    lowered = text.lower()
    forbidden = (
        "slack_token",
        "os.getenv(",
        "os.environ[",
        "sqlite",
        "create table",
        "socket mode",
        "exec(",
        "eval(",
        "subprocess",
        "logging.",
        "requests.",
        "httpx.",
    )
    assert all(fragment not in lowered for fragment in forbidden)
    assert "Authorization" in text
    assert "Bearer {token}" in text
    assert "x-oauth-scopes" in text
    assert "SLACK_AUTH_TEST_URL" in text


def test_cli_has_no_token_argument_or_alternate_input_carrier() -> None:
    text = SCRIPT.read_text(encoding="utf-8").lower()
    assert "--token" not in text
    assert "environment" not in text
    assert "temp" not in text
    assert "file" not in text


def test_documented_direct_cli_runs_without_pythonpath(tmp_path: Path) -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-S",
            str(SCRIPT),
            "--expected-team-id",
            "T0BRD2AQXQV",
            "--expected-bot-user-id",
            "U0BST4WG996",
            "--expected-scope",
            "groups:history",
            "--expected-scope",
            "chat:write",
        ],
        cwd=ROOT,
        env={"HOME": str(tmp_path)},
        input=b"not-a-token\n",
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 2
    assert completed.stderr == b""
    assert json.loads(completed.stdout) == {
        "error": "METADATA_INPUT_REFUSED",
        "schema": "mastermind.slack_agent_dialogue.metadata_verification.v1",
        "status": "ERROR",
    }
