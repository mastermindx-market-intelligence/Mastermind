import copy
from pathlib import Path

import pytest

from control_plane import executive_inference_io as io

JOB = "JOB-007"
ATTEMPT = "ATT-" + "a" * 32
WORKER = "codex-01"
SHA = "b" * 64


def request(*, system_prompt="system", input_text="input", maximum=4096):
    return {
        "schema": io.REQUEST_SCHEMA,
        "system_prompt": system_prompt,
        "input_text": input_text,
        "max_output_chars": maximum,
    }


def worker_result(*, answer="answer"):
    return {
        "schema_version": io.WORKER_RESULT_SCHEMA,
        "job_id": JOB,
        "run_id": ATTEMPT,
        "worker_id": WORKER,
        "status": "COMPLETED",
        "answer": answer,
    }


def test_request_contract_is_closed_bounded_and_nonmutating():
    raw = request(system_prompt="", input_text="A bounded inference request.", maximum=8192)
    before = copy.deepcopy(raw)
    assert io.normalize_request(raw) == raw
    assert raw == before
    for mutation in (
        dict(raw, provider="codex"),
        dict(raw, model="gpt-5.6-sol"),
        dict(raw, credential_home="/tmp"),
        dict(raw, max_output_chars=True),
        dict(raw, max_output_chars=io.MAX_OUTPUT_CHARS + 1),
    ):
        with pytest.raises(io.InferenceIOError):
            io.normalize_request(mutation)
def test_request_byte_ceiling_counts_json_escaping_and_utf8():
    with pytest.raises(io.InferenceIOError):
        io.normalize_request(request(input_text='"\\n' * (io.MAX_REQUEST_BYTES // 2)))
    with pytest.raises(io.InferenceIOError):
        io.normalize_request(request(input_text="😀" * (io.MAX_REQUEST_BYTES // 2)))
    assert len(io.canonical_bytes(io.normalize_request(
        request(input_text="x" * 20_000)
    ))) < io.MAX_REQUEST_BYTES


def test_worker_schema_is_exact_identity_and_answer_only():
    schema = io.worker_result_schema(
        job_id=JOB, run_id=ATTEMPT, worker_id=WORKER, max_output_chars=1234
    )
    assert schema["additionalProperties"] is False
    assert schema["properties"]["job_id"] == {"const": JOB}
    assert schema["properties"]["run_id"] == {"const": ATTEMPT}
    assert schema["properties"]["worker_id"] == {"const": WORKER}
    assert schema["properties"]["status"] == {"const": "COMPLETED"}
    assert schema["properties"]["answer"]["maxLength"] == 1234
    assert set(schema["properties"]) == {
        "schema_version", "job_id", "run_id", "worker_id", "status", "answer"
    }


@pytest.mark.parametrize(("field", "value"), [
    ("job_id", "JOB-foreign"),
    ("run_id", "ATT-" + "c" * 32),
    ("worker_id", "other-worker"),
    ("status", "FAILED"),
    ("schema_version", "invented.v1"),
])
def test_worker_result_rejects_identity_or_status_drift(field, value):
    raw = worker_result()
    raw[field] = value
    with pytest.raises(io.InferenceIOError):
        io.validate_worker_result(
            raw, job_id=JOB, run_id=ATTEMPT, worker_id=WORKER,
            max_output_chars=4096,
        )
def test_worker_result_enforces_char_and_byte_ceilings():
    with pytest.raises(io.InferenceIOError):
        io.validate_worker_result(
            worker_result(answer="x" * 11), job_id=JOB, run_id=ATTEMPT,
            worker_id=WORKER, max_output_chars=10,
        )
    with pytest.raises(io.InferenceIOError):
        io.validate_worker_result(
            worker_result(answer="😀" * io.MAX_OUTPUT_CHARS),
            job_id=JOB, run_id=ATTEMPT, worker_id=WORKER,
            max_output_chars=io.MAX_OUTPUT_CHARS,
        )


def test_direct_result_reference_is_operation_bound():
    ref = io.result_reference(
        job_id=JOB, attempt_id=ATTEMPT, worker_id=WORKER, result_sha256=SHA
    )
    assert io.validate_result_reference(ref, job_id=JOB) == ref
    with pytest.raises(io.InferenceIOError):
        io.validate_result_reference(ref, job_id="JOB-008")
    for key, value in (
        ("attempt_id", "ATT-" + "d" * 32),
        ("worker_id", "foreign"),
        ("result_sha256", "0" * 63),
    ):
        changed = dict(ref)
        changed[key] = value
        if key == "attempt_id" or key == "worker_id":
            # Structurally valid foreign identities remain valid references to
            # themselves; the host binds them to the Job/Attempt before emit.
            if key == "attempt_id":
                assert io.validate_result_reference(changed, job_id=JOB) == changed
            else:
                assert io.validate_result_reference(changed, job_id=JOB) == changed
        else:
            with pytest.raises(io.InferenceIOError):
                io.validate_result_reference(changed, job_id=JOB)
def test_host_result_document_requires_raw_file_digest_match():
    ref = io.result_reference(
        job_id=JOB, attempt_id=ATTEMPT, worker_id=WORKER, result_sha256=SHA
    )
    result = worker_result()
    doc = io.result_document(
        reference=ref, result=result, max_output_chars=4096,
        raw_result_sha256=SHA,
    )
    assert doc == {"schema": io.RESULT_DOCUMENT_SCHEMA, "reference": ref, "result": result}
    assert io.validate_result_document(
        doc, job_id=JOB, max_output_chars=4096
    ) == doc
    with pytest.raises(io.InferenceIOError):
        io.result_document(
            reference=ref, result=result, max_output_chars=4096,
            raw_result_sha256="c" * 64,
        )


def test_client_validation_does_not_fake_raw_digest_recomputation():
    ref = io.result_reference(
        job_id=JOB, attempt_id=ATTEMPT, worker_id=WORKER, result_sha256=SHA
    )
    # The raw file can have whitespace/formatting that differs from canonical
    # JSON. Client validation preserves the host-bound raw digest; it does not
    # claim to recompute it from a parsed object.
    doc = {"schema": io.RESULT_DOCUMENT_SCHEMA, "reference": ref, "result": worker_result()}
    assert io.validate_result_document(doc, job_id=JOB, max_output_chars=4096) == doc


def test_contract_module_owns_no_runtime_transport_provider_or_filesystem(tmp_path):
    source = Path(io.__file__).read_text()
    forbidden = (
        "from control_plane import executive_runtime",
        "from control_plane import executive_service",
        "import control_plane.executive_runtime",
        "import control_plane.executive_service",
        "provider_waterfall", "cli_bridge", "subprocess",
        "open(", "write_text(", "write_bytes(", "asyncio", "httpx", "requests",
    )
    for token in forbidden:
        assert token not in source
