"""Drop-in SDK setup for an already-admitted OpenAI-SDK Fabric worker.

Does not select a Fabric pool, model, account, worker or execution root.
"""
import os
from openai import OpenAI


def new_client(*, request_id: str | None = None) -> OpenAI:
    # A client bound to an idempotency key is for ONE logical request only.
    # Supply a new request_id (or extra_headers override) for each distinct call.
    stable_id = (request_id if request_id is not None else os.environ.get("FABRIC_REQUEST_ID", "")).strip()
    return OpenAI(
        base_url=os.environ.get("FABRIC_OPENAI_BASE_URL", "http://127.0.0.1:8311/v1"),
        api_key=os.environ["FABRIC_PROXY_TOKEN"],
        timeout=900.0,  # long enough for 600s queued time plus inference; tune per job SLA
        max_retries=0,  # transport failures must not cause untracked replay
        default_headers={"Idempotency-Key": stable_id} if stable_id else None,
    )


if __name__ == "__main__":
    # Required for the sample inference, not for a read-only model catalog call.
    request_id = os.environ["FABRIC_REQUEST_ID"].strip()
    if not request_id:
        raise ValueError("FABRIC_REQUEST_ID must be nonempty for one logical inference call")
    client = new_client(request_id=request_id)
    # Use an exact catalog slug returned by GET /v1/models, not a Fabric pool alias.
    model = os.environ["EXPLABS_MODEL"]
    result = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": "Say ok"}],
    )
    print(result.choices[0].message.content)
