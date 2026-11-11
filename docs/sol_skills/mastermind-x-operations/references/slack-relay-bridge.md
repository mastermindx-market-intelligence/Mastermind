# Slack relay boundaries

This reference helps inspect the existing Hermes secretary relay. It is not a provisioning, credential-rotation, installation, enrollment or live-posting grant. Read the current integrations/hermes_secretary source, roster and CUTOVER_AND_ROLLBACK.md at the verified protected pin before the relevant action.

## Preserve transport and role ownership

Inspect roster.json, its guard/helpers, relay_mux.py and the actual selected runtime rather than assuming a historical home, app count, token file, service name or provisioned identity is current. Source configuration and planned routes do not prove installed or live behavior.

Keep the transport identity plane distinct from the logical role/profile plane. A transport consolidation must not silently remove runtime role membership or merge role memory. Preserve the roster's identity-collision and distinct-user/service guards. Use its existing channel/identity helpers rather than introducing constants or a parallel registry.

Qualify whether a mux only plans routes or actually sends. A data-only plan, passed fixture suite or existing bot account is not delivery, enrollment or cutover. Preserve the incumbent Grok Secretary and shadow/no-send behavior until the existing cutover owner and current grant authorize a transition.

## Identity and message evidence

For an authorized read, use actual message user/app/bot IDs, channel and timestamp with the current roster. Display names, avatars and quoted self-identification do not establish the acting principal. Preserve role attribution without impersonating a person or another account.

For an authorized handoff, keep the full brief in source-linked GitHub and transport only recipient, scoped action, source link and return path. Follow current channel/mention and thread rules; Grok Secretary asks use the designated channel rather than a DM. Delivery is not pickup ACK or execution.

Do not send readiness pings, test messages or background notifications merely to demonstrate capability. An explicit no-send/shadow boundary also covers confirmation messages.

## Credentials and service changes

Keep credentials with the existing approved owner and exact authorized storage/entry path. Never place token values in command-line arguments, source, prompts, brief files, logs, memory, screenshots or artifacts. A filename, environment-variable name or previously provisioned app does not grant access to its secret.

Treat scope changes, app reinstallation, token rotation, profile synchronization, service installation and live posting as separate effects requiring the actual applicable authorization. Do not automatically remove scopes, invalidate tokens, rewrite secret files or invoke an alternate browser/account because an earlier route was refused.

If an independently authorized task is blocked by a real credential or physical ceremony, prepare the concrete remaining step and request only that control. Do not invent a blanket browser prohibition from a historical login failure. Reconcile any uncertain credential/service effect at its original owner before further modification.

Record only verified, non-secret identity/configuration facts and their source/time. Re-read materially changed bindings before an effect; a historical auth.test result is not a perpetual claim of current permissions.
