"""Drop-in SDK setup for an already-admitted OpenAI-SDK Fabric worker.

Does not select a Fabric pool, model, account, worker or execution root.
"""
import os
from openai import OpenAI


def new_client() -> OpenAI:
    return OpenAI(
        base_url=os.environ.get("FABRIC_OPENAI_BASE_URL", "http://127.0.0.1:8311/v1"),
        api_key=os.environ["FABRIC_PROXY_TOKEN"],
        timeout=900.0,  # long enough for 600s queued time plus inference; tune per job SLA
        max_retries=0,  # transport failures must not cause untracked replay
    )


if __name__ == "__main__":
    client = new_client()
    # Use an exact catalog slug returned by GET /v1/models, not a Fabric pool alias.
    model = os.environ["EXPLABS_MODEL"]
    result = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": "Say ok"}],
        extra_headers={"Idempotency-Key": os.environ["FABRIC_REQUEST_ID"]},
    )
    print(result.choices[0].message.content)
