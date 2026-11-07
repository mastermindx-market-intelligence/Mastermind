# Fresh routed APPLICATION family enrollment

V10 enrolls the existing eight Mastermind/Macro consumer identities through the original family transaction. It does not require a Go grant. The same listener, Broker, credential owner and binding/intent/receipt paths remain authoritative.

| Role | Capability lane | Workload profile | Credential reference |
|---|---|---|---|
| Admin | admin-orchestrator | site_interactive | MACRO_FABRIC_APPLICATION_TOKEN |
| Text | mastermind-text | site_batch | MASTERMIND_FABRIC_APPLICATION_TOKEN |
| Chat | mastermind-chat | site_interactive | MASTERMIND_FABRIC_CHAT_TOKEN |
| Brain | brain | site_interactive | MACRO_BRAIN_FABRIC_APPLICATION_TOKEN |
| Ask | ask-brain | site_interactive | MACRO_ASK_FABRIC_APPLICATION_TOKEN |
| Batch | null | site_batch | MACRO_BATCH_FABRIC_APPLICATION_TOKEN |
| Analysis | null | lobe_analysis | MACRO_ANALYSIS_FABRIC_APPLICATION_TOKEN |
| Portfolio | null | portfolio_analysis | MACRO_PORTFOLIO_FABRIC_APPLICATION_TOKEN |

The closed specification has `schema: native-go-service-enrollment-specification.v10`, an `operation_id`, and exactly those eight role keys. Every role has `{scope, new_grants}`. Every scope requires an explicit route scope and selection purpose. Caller/native host, principal, account-profile custody and all grant evidence come from their existing owners. The last three scopes use their workload profile as the workload; the first five preserve their explicit existing workload contract.

Use the existing CLI:

```text
native_install.py prepare-go-service --go-ingress-bundle ORIGINAL_COMPLETED_INGRESS --specification QUALIFIED_SPEC --output NEW_REVIEW_BUNDLE
native_install.py apply-go-service --bundle ORIGINAL_REVIEW_BUNDLE
native_install.py reconcile-go-service --bundle ORIGINAL_REVIEW_BUNDLE
```

A completed compatible ingress and exact selected source are prerequisites. Preparation mints no credentials. Apply retains the authenticated predecessor's token prefix and mints only missing roles: zero/eight for a fresh family, one/seven for v1/v3/v4, two/six for v5, five/three for v6/v7, and eight/zero for v8/v10. The first number is retained and the second is newly minted.

Empty additions preserve the account document's exact bytes. A legacy document lacking the application-grants key is accepted only for this identity-only operation; a present list, malformed value or nonempty addition still reaches the existing complete admission parser. Existing disabled, expired, narrowed or removed grants remain exactly as observed. Explicit Admin metadata permission remains separate from inference grants.

Up to 128 new grants may be appended per operation. A later v10 successor can append another bounded set while keeping the same eight credentials. Existing route/purpose values and retained identity fields are immutable in this version; missing values may be supplied explicitly. This is not a general route-policy replacement operation.

The accounts target retains its original staged-inode/CAS protocol even when bytes are unchanged. A partial family or Hermes sibling holds competing first intents; recovery uses the original bundle and credentials. Old completed bundles cannot roll back a successor.

The source proof covers 38 new cases and 677 distinct resolved cases across the existing enrollment/startup and exact identity suites. Real HTTP startup succeeds with an empty Go profile and makes no Go upstream request. Native requests still correctly refuse when no executor/grant is registered. Positive provider execution, grants, protected-source deployment and consumer/browser acceptance remain separate runtime proof.
