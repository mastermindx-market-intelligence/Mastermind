# GLM exact-account readiness

This patch applies to the exact installed source preimages in SOURCE_MANIFEST.json.
The test fixtures at `tests/fixtures/glm_account_readiness/` retain those source bytes; they contain no account configuration or
credentials. Tests apply the patch in an isolated directory with synthetic inputs.

A host's generic GLM availability does not establish that its already leased
account is available. The controller now asks the digest-pinned support helper for
one readiness bit before launch. It preserves the selected host and account and
uses the existing transport. Unknown, unavailable or malformed replies refuse
with terminal rc78; the transport status remains a separate diagnostic.

Readiness and the actual bound launcher share exact key validation. The launcher
still rechecks its lease and key before exec. Apply helper, launcher, then controller
so every intermediate installation remains compatible. No key is copied, no account
is substituted, and no prior failed run is retried. This is post-lease prelaunch
qualification, not a new placement policy or pre-lease host/account pairing claim.
