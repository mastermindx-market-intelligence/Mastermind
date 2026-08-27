from __future__ import annotations

from pathlib import Path

import pytest

from integrations.slack_executive import c1_runtime


@pytest.mark.parametrize(
    "payload",
    (
        " INERT-C1-TOKEN\n",
        "INERT-C1-TOKEN \n",
        "\tINERT-C1-TOKEN\n",
        "INERT-C1-TOKEN\t\n",
    ),
)
def test_c1_token_file_refuses_leading_or_trailing_whitespace_instead_of_repairing(
    tmp_path: Path,
    payload: str,
) -> None:
    path = tmp_path / "relay.token"
    path.write_text(payload, encoding="utf-8")
    path.chmod(0o400)

    with pytest.raises(RuntimeError, match="C1_TOKEN_FILE_INVALID"):
        c1_runtime.read_token_file(path, expected_path=path)
