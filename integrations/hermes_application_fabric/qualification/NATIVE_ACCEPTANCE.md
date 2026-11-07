# Native primary acceptance through the existing session

Use `qualification/native_acceptance.py` from the original owner's qualified Mastermind source and Hermes interpreter. This command submits one existing native session admission, or reads the result of that original admission. It does not enroll a consumer, start an agent, construct another APPLICATION client, select an account, change the profile, cancel a provider call or settle usage.

## Required existing binding

The selected native process, actual uid/home/session and original enrollment must already be qualified. Its installed primary adapter must be bound to the intended APPLICATION service, current internal role/session identity, one permitted route and physical account, fresh usable quota, output ceiling and the existing enforceable funding boundary. Native enrollment inspection alone does not prove those APPLICATION predicates.

The canonical program allows an eligible M2 or Ubuntu consumer. Use the actual platform's native identity and original transport; do not transfer a Linux role grant to an attended M2 profile. This command currently consumes the existing `mmsecretary` native contract. An ordinary attended profile is not implicitly that contract.

The native role must offer a real, authorized harmless tool suitable for the acceptance task. The base Secretary declaration is clarify-only. Do not assume `read_file` exists, install the test fixture's synthetic tool, or make Fabric worker delegation a prerequisite. Qualify the actual offered tool through its existing role/plugin owner.

## Inspect without creating enrollment

The shell variables below stand for values from the original qualified owner. They are not discovery defaults. Invoke the module in that owner's existing import environment; do not add an unrelated checkout to a live process's import path.

~~~sh
"$qualified_python" -m integrations.hermes_application_fabric.qualification.native_acceptance \
  --home "$qualified_home" --expected-pid "$qualified_native_pid" inspect \
  --implementation-sha "$qualified_implementation_sha" \
  --enrollment-request-id "$original_enrollment_request_id"
~~~

The command checks the existing native enrollment and exact current target, including actual uid, home, session, process instance, epoch, revision and generation. It performs no create, restore or enrollment operation.

## Submit once

Prepare a bounded prompt file for the actual acceptance journey. For the tool-capable turn, ask for the specifically qualified harmless tool once and a continuation based on its result. A separate ordinary turn, when required by the program, uses a distinct explicitly new submission identity. Neither turn is a retry of the other.

~~~sh
"$qualified_python" -m integrations.hermes_application_fabric.qualification.native_acceptance \
  --home "$qualified_home" --expected-pid "$qualified_native_pid" submit-once \
  --implementation-sha "$qualified_implementation_sha" \
  --enrollment-request-id "$original_enrollment_request_id" \
  --submission-id "$original_submission_id" --prompt-file "$acceptance_prompt_file"
~~~

The first JSON record is PREPARED and contains the native session ID, original submission ID and the incumbent input digest. The second contains the original admission receipt or its disposition. Capture both with the existing evidence owner. Flushing stdout is not proof of durable capture. **PREPARED alone never proves nonexecution.** A lost response, interrupted command, malformed receipt or failed output after submission must lead to original-result recovery, never another `submit-once` invocation.

The command invokes `NativeSecretaryClient.submit` once. It retains REFUSED and NOT_SUBMITTED only when the original owner returns a valid closed refusal envelope; malformed responses after the possible write are EFFECT_UNKNOWN. It does not automatically fail over even after an owner-proven refusal. Its 16 KiB prompt limit and the existing native/account output bounds remain separate.

## Recover the original result

~~~sh
"$qualified_python" -m integrations.hermes_application_fabric.qualification.native_acceptance \
  --home "$qualified_home" --expected-pid "$qualified_native_pid" read-original \
  --session-id "$original_session_id" --submission-id "$original_submission_id" \
  --input-sha256 "$original_input_sha256" --admission-id "$original_admission_id" \
  --expected-tool "$qualified_harmless_tool"
~~~

Omit `--admission-id` only when its original response was lost. The existing owner resolves the same session/submission/input digest. Do not replace those values with a new operation. After a legitimate native owner renewal, qualify its current PID through the existing owner while retaining all historical admission identifiers; recovery does not inspect or enroll a new session. An absent row remains EFFECT_UNKNOWN.

One invocation makes one read. The runner adds no polling service, retry loop or journal. Exit 0 means inspect, admission or read succeeded at that command's boundary; it does not mean the original turn is terminal or accepted. An OBSERVED queued/started/unknown admission remains nonterminal. INCOMPLETE can include a failed evidence output after admission and is never permission to resubmit.

## Evidence and its limits

Reports are limited to 96 KiB. Answers are represented by byte count and SHA-256, not printed content. The original native validators check receipt identity, terminal metadata and retained observation scope. Terminal observations cannot accompany a nonterminal admission; conflicting positive/error observation carriers are rejected.

A successful native tool summary requires one callback and one result commit, complete matching tool identities, correct event order, no error/block/unknown effect/overflow, and the incumbent unique-identity correlation. A later native assembly request is reported separately. The summary does not claim that a particular tool result was included in that request's content.

When exactly one assembly event matches the callback identity, the command emits an explicitly **derived, unverified** APPLICATION operation/request correlation using the incumbent `ApplicationBinding.request_id` encoding. This is not proof that the APPLICATION request existed. Join it to the actual original owner records before drawing that conclusion.

| Acceptance fact | Existing authoritative evidence |
|---|---|
| Authenticated native admission and original recovery | Qualified native SessionAuthority and original admission receipt |
| Actual harmless tool execution and continuation | Original native callback/result commit plus verified original tool result/history and continuation |
| APPLICATION request and selected/served model | Actual original request and immutable APPLICATION observation; configured model labels are insufficient |
| Physical account, entitlement, shared quota and lease | Original Broker/account owner records for that operation/request |
| Tokens, budget enforcement and settlement | Request-linked original usage and durable settlement/funding receipts |
| Recovery without duplicate effects | Original IDs and owner effect disposition; no second provider call or new admission on unknown |

The native observer's HTTPX-only transport contribution may be unsupported for the Fabric facade. This does not erase valid native callback evidence and does not supply provider proof. The runner always reports provider/model/account/live-acceptance flags as false; the source-linked acceptance owner joins the missing facts. Unknown cost or serving identity stays unknown.

Reader recovery is not provider cancellation. Do not close a second client or release an uncertain lease. Timeout or 429 alone never proves another provider call safe. Use existing deterministic enforcement evidence rather than deliberately exhausting a real account.

## Executed source qualification

`tests/test_hermes_primary_native_acceptance.py` has 29 passing cases against the exact native SDK validators and actual APPLICATION request encoding, with a recording native transport. The source proof and log identify all exact bytes and show zero network attempts. This is source qualification; no native host admission, provider call, enrollment, deployment or live acceptance occurred.

Run the source suite with the qualified repository environment:

~~~sh
python -m unittest discover -s tests -p test_hermes_primary_native_acceptance.py -v
~~~

See `native_acceptance_source_proof.json` for the immutable test inputs. Completed Macro projection intake reuses H4 a3d4's twelve intact blobs; it does not merge H4's unrelated history, replace the original fixture repair, or reapply provider/latency patches.
