# Go public-reader proof and request-checked streaming checkpoint

## Outcome and status

Preserve a coding agent's model, transcript, completed tools and workspace while consuming current provider offerings safely. The new capability is a real public-reader canary plus an executable request-time offer check connected, in an offline composition proof, to a single-account streaming edge. This is not an installed coding-agent lane or a live multi-account router.

Current scope: public metadata reader exercised against the actual provider; request guard and streaming source BUILT_NOT_PROVEN for production; full integration PARTIAL. No key was read or enrolled, no authenticated usage request or provider inference was sent, and no live worker, proxy, route, scheduler or paid-overflow setting was created.

Procedure: protected Mastermind bffe2ca8506346ea278c8ee469bf1ac30a4de008, compatible Skillpack 1.0.1 / bootstrap 1. Chairman's current continuation supplied source-work intent. Existing source carriers remained Macro #7143 and Mastermind #622. Native inspection refusals were not bypassed.

## Exact implementation

- Macro #7143 request guard: ab710f4a653fcec4cf2505ed7ab49c7faf19b623, parent 4681a2c832ecbf489a13e79af69ab42315fe818f.
- Mastermind #622 streaming implementation and tests: bd46e6c7c728c4fab31aa03ecaaa8a6eb10b599c, parent 097e1bac090be8f254013a2729e0f7ef69c94054.
- The original public reader stayed byte-identical: engine/provider_subscription_catalog_opencode.py, Git blob 48663e139631cb708206fa861b4f1b6a60727e81. Its CLI blob is a53db41e978cd7176a58f165a54c0365e42e65a7.
- The existing pooled kernel also stayed unchanged, including its prohibition on generic AuthError rollover. The new streaming path performs no account rollover at all.

New tested Git blobs:

| Path | Blob |
|---|---|
| Macro engine/provider_subscription_guard_opencode.py | 896aefaa75bf0a83179cc6354a80ededc3681d6d |
| Macro tests/test_opencode_go_request_offer.py | 3d70bddac1268ce4228d8a7c525d7f535ec7c543 |
| Mastermind control_plane/opencode_go_stream.py | 589160104acd41e97b9688de1d97858ef0730a71 |
| Mastermind tests/test_opencode_go_stream.py | d36c6171ab165f8510ad0fb8c572a1c269635140 |
| Mastermind docs/evidence/opencode_go/test_offer_stream_composition.py | f6b61815366f7d4ddab272e55ca9af594b30ebfb |

Published blob identities matched the tested local bytes before branch updates. No source branch was rebased, reset or force-updated.

## Native public-reader canary

After current device discovery and a successful ping, two independent read-only checks ran on the authorized MacBook through Remote Desktop Commander. They used no credentials and touched no existing worktree or worker process.

The first diagnostic fetched the fixed public URLs with redirects refused:

| Public GET | HTTP | Bytes | Observed at | SHA-256 |
|---|---|---|---|---|
| https://opencode.ai/zen/go/v1/models | 200 | 3063 | 2026-09-14T17:58:42.484599+00:00 | 101f8a6e890158964ff70db72c62ad1cbe2cb32d669c5308b07be79af8946d86 |
| https://opencode.ai/docs/go/ | 200 | 88499 | 2026-09-14T17:58:42.986967+00:00 | 16beadc3099dbdef127a680758617371ec3e2832548d4f3c1d77404636ce062e |

The second check acquired the two exact reader/CLI source files at Macro 4681a2c832ecbf489a13e79af69ab42315fe818f into a disposable temporary directory, verified their Git blob identities, then invoked the actual CLI with --live under isolated Python. It made its own fresh public GETs and returned:

- exit_code: 0;
- models: 37;
- acquisition_origin: public_metadata_not_account_entitlement;
- inventory_generation: d5346e27713c411fce038180ee3b1e306cc4c29700de69b49fc19b6f24a93930;
- terms_generation: d92f8fc572b759d5bf2ed7c8e7ef3d2a41f9fec683f8e7837be68c467c153d93;
- production_armed: false.

The diagnostic raw-body hashes above are NOT claimed to identify the separate CLI requests. The CLI canary did not export raw response bytes. Its temporary source directory was context-managed and removed on exit. This supersedes the earlier uncertainty about whether the unmodified public collector can parse actual HTML. It does not prove continuous monitoring, installation, account entitlement or model inference.

## Request-time behavior

The new Macro guard consumes existing metadata plus expected offer/policy digests and exclusive validity deadlines supplied by the existing reviewed plan/policy owner. It does not mint those approvals. It refuses future-dated/stale inventory or terms, missing models, changed economic assumptions, protocol mismatch, changed privacy facts, expired review evidence, unknown privacy and training-enabled private workloads.

Promotion and conditional-retention deadlines must be explicit owner inputs. No provider cutover timezone is guessed from prose. Re-reading an unchanged page cannot extend these owner deadlines. Missing or expired condition deadlines refuse the request. The context/time-specific dollar-quote evaluator remains the existing model-economics owner's pending work; this guard is not a replacement calculator.

A new ID in the inventory alone does not change the current model's offer digest. Material shared economic conditions and the current global privacy digest remain conservative invalidation boundaries. This is not a claim that all unrelated documentation edits are harmless or that new models are automatically trusted.

## Streaming behavior

control_plane/opencode_go_stream.py reuses the existing request-freezing, account-choice and credential-injection helpers. A required request_check callback runs before key loading and again before POST. A missing callback, non-None callback result or raised refusal blocks the request. Runtime composition must wire real canonical evidence; a no-op test callback is not production admission.

The edge accepts foreground stream=true requests, contacts the fixed OpenCode host, streams raw bytes to the existing harness consumer, observes protocol terminal events, and never owns tool execution or conversation memory. HTTP redirects, auth errors, quota errors and all other statuses receive no hidden retry or account switch. EOF before a terminal event, malformed/error events, partial-stream failure, sink failure after submission, deadline expiry and ambiguous cleanup cannot become successful completion. Local cancellation after submission preserves effect uncertainty; closing a socket is not proof of provider cancellation.

There is no localhost service, new authentication boundary, broker, quota store or transcript in this increment. A terminal stream event means only wire completion, not coding-task acceptance. Connection timeouts and between-I/O deadline checks are not a guaranteed hard wall-clock bound for synchronous DNS, slowly arriving HTTP headers or a blocking caller callback; the existing worker supervisor must supply the outer execution/cancellation bound. No independent watchdog was introduced.

## Executed proof

Linux isolated fixture: 198 tests passed in the combined run (previous 132 plus 20 offer-guard checks, 39 streaming checks and 7 cross-repository composition checks). Compile checks also passed. This is not full-repository CI or an independent review.

The streaming suite includes a real local HTTP server and http.client connection. The server flushes the first SSE chunk and waits for the consumer to acknowledge it before sending the terminal event. The test proves progressive delivery rather than whole-response buffering, exact request body/session preservation, one request and explicit fixture-server shutdown. The provider, account and admission are synthetic; this is not a real Go inference or TLS deployment proof.

The cross-repository test imports the actual Macro parser/guard and actual Mastermind streaming edge. A valid offer reaches one synthetic stream with its prior tool-result context. A removed model, stale inventory, changed fractions or changed privacy blocks before key loading. Evidence expiring during the key callback blocks before POST. An unrelated inventory-only model addition does not interrupt the existing model. The workspace marker is preserved in every case.

## Integration gates and exact continuation

Mastermind #583 is merged, but #622 remains a conflicting old-parent stack. Its genuine pre-existing delta from 808101957bc483ac2d9f9491df897166166e8b50 to 097e1bac090be8f254013a2729e0f7ef69c94054 was verified through GitHub as exactly five added Go paths. A later native read-only source-tree verification was platform-blocked; it was not retried through another device, worker or carrier. No latest-parent merge, conflict resolution or compatibility claim was made. New streaming files were added only to the existing draft branch.

Next Sol integration action, after the source-inspection permission boundary is resolved: reconcile #622 with landed #583 on the same branch without restoring obsolete enrollment/ACL code; obtain current-base CI and independent review; then compose one installed, disabled single-account binding using existing provider-home enrollment and canonical capacity/plan/policy inputs. Do not use fixture callbacks or caller-supplied digests as authorization. Disable harness/SDK retry behavior consistently with the transport contract.

Only after the applicable native, enrollment, account-access, quota, policy and runtime gates pass may one real coding-agent task run. Acceptance requires a real streamed response, real tool use, preserved workspace/context, cancellation/partial-stream evidence and a visible task result. Dynamic owner publication, time/context-specific economic quoting, shared reservations and production rollout remain pending. Multi-account deployment still has the unresolved provider-policy and identity gates documented in prior checkpoints.

No Fable/worker assignment, watcher or automation was created. The prior checkpoint is superseded only for actual public-reader proof and these new source capabilities; its remaining activation and no-duplicate boundaries remain in force.
