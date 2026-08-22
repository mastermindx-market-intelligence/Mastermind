# Executive OS Personal-Pro Slack carrier framing amendment

**Date:** 2026-08-21  
**Parent:** MAS-48 / MAS-106  
**Status:** RECORDS-ONLY CARRIER AMENDMENT. NO RUNTIME OR PRODUCTION AUTHORITY IS ARMED.  
**Precedence:** Mastermind #91, #96, #99, #100, #103 remain controlling except for the narrow Slack source-message preservation assumption explicitly amended here.

## 0. Verdict

MAS-106 / S0 V1 is **BLOCKED by a real platform falsifier**.

The disposable Slack app/fixture infrastructure was successfully provisioned and isolated, but the first real Personal-Pro ChatGPT -> Slack source message did not arrive byte-identical to the text supplied by the calling conversation.

Observed live in private channel `C0BRUL9F2V7`:

```text
EXECOS/CEO_REQUEST_V1
{"operation_key":"s0-carrier-seat-2-001","objective":"S0 inert carrier fixture — DO NOT EXECUTE","department":"executive-infrastructure","priority":0,"execution_profile":"research_only"}
*Sent using* <@...ChatGPT...>
```

The first two lines were the intended inert carrier fixture. The ChatGPT Slack action appended an AI-origin attribution line before the disposable fixture bot received the event. The immediately preceding harmless Unicode probe was transformed in the same visible way.

The fixture bot hashed the post-transformation Slack text, proving the mutation occurred before the consumer boundary.

This satisfies the frozen S0 kill condition from #99: the exact source message was materially altered by the real carrier. The worker correctly stopped before testing additional seats, widening scopes, adding persistence or beginning B2.

**S0 V1 result:** `BLOCK`  
**Exact-byte whole-message carrier:** `REJECTED_BY_DESIGN` for the ChatGPT Slack send action observed in this workspace.

This is not an Executive OS, CeoIngress, Socket Mode, Slack fixture-app or permissions failure.

## 1. What remains valid

The failure does **not** invalidate:

- the Personal-Pro Shared Project / protected Skillpack shell;
- PR-A / #100 dedicated CeoIngress submit/status implementation;
- R0 / #103 diagnostic hot-state source law;
- B1 / MAS-108 read-plane implementation work;
- C1 production read proof architecture;
- Executive OS as the sole Job/Attempt/Worker/Event lifecycle authority;
- Slack as transport rather than lifecycle authority;
- deterministic operation-key / `slack-*` Executive intent identity;
- one-carrier-until-reconciled law;
- no Slack lifecycle/dedupe/replay database law;
- effect-unknown canonical status reconciliation.

Therefore **B1 may continue** and, after accepted B1, **C1 may proceed**. S0 remains a required kill gate for B2 only.

B2 and C2 remain held.

## 2. Why blind suffix stripping is rejected

The implementation must not respond to this falsifier by casually doing:

```text
if text.endswith("Sent using @ChatGPT"):
    text = strip_suffix(text)
```

inside B2.

That would:

- silently change an already-frozen carrier contract after a failed platform proof;
- make source canonicalization dependent on an undocumented string manipulation hidden inside implementation;
- risk accepting unreviewed trailing content;
- conflate transport decoration with the canonical business payload;
- erase the S0 regression instead of learning from it.

Any attribution tolerance must therefore be a reviewed **carrier framing contract** with discriminating tests and a new S0 proof before B2 implementation is released.

## 3. Narrow amendment: canonical payload span vs transport trailer

The product remains human-readable. Do not replace the command with opaque base64 merely to avoid Slack formatting.

The proposed next carrier contract keeps:

```text
EXECOS/CEO_REQUEST_V1
{one canonical single-line JSON object}
```

as the **canonical payload span**.

The complete Slack message may additionally contain one reviewed **transport trailer** after that span.

Conceptually:

```text
<canonical payload line 1>
<canonical payload line 2>
<optional reviewed transport trailer>
```

### 3.1 Canonical payload span

For the next S0 experiment, canonical payload extraction is mechanically defined as:

1. line 1 must equal exactly `EXECOS/CEO_REQUEST_V1`;
2. line 2 must be exactly one UTF-8 JSON object line;
3. no raw newline is permitted inside the JSON line; string newlines are JSON escapes;
4. canonical business parsing, `operation_key`, request normalization, fingerprinting and future deterministic `slack-*` intent identity use **only lines 1 and 2**;
5. the payload span bytes are preserved and compared independently of transport decoration.

The Relay never derives business meaning from a transport trailer.

### 3.2 Transport trailer

A trailer is transport evidence, not Executive authority, request content or operation identity.

The first framed-carrier experiment may recognize only:

- no trailer; or
- exactly one platform attribution line in the Slack event's raw-text representation corresponding to the ChatGPT action attribution observed by S0.

The accepted implementation must bind the expected workspace ChatGPT attribution identity/configuration explicitly. It must not accept arbitrary free-form trailing lines and must not use fuzzy matching.

The attribution line:

- grants no authority;
- is not hashed into the Executive request fingerprint;
- is not copied into CeoIngress request fields;
- may be recorded only as bounded transport evidence;
- cannot repair a wrong sender/channel/event type;
- cannot substitute for explicit Chairman intent.

An unknown trailer, more than one trailer line, or arbitrary text after the canonical payload causes a transport refusal before Executive submission.

## 4. Source reread / edit law under framing

B2, if later authorized, must retain the pre-submit source reread from #99.

For a candidate observed from an original message-create event:

1. capture the exact extracted canonical payload span;
2. immediately before starting canonical submit, reread the exact source Slack message;
3. re-run the same strict framing parser;
4. payload span missing, changed or invalid -> refuse;
5. trailer outside the reviewed grammar -> refuse;
6. exact payload span unchanged + trailer still reviewed -> source is stable for transport purposes.

Once canonical synchronous submission starts, later Slack edits/deletes still cannot cancel the Executive mutation; canonical status wins.

No edit/delete event originates work.

## 5. Sender and attribution are not cryptographic authority

The approved Slack sender identity remains a transport eligibility fence. The ChatGPT attribution trailer is useful platform provenance evidence, but it is not a signature and must not be treated as cryptographic proof that a model rather than a human caused the write.

Executive authority continues to come from:

- the accepted explicit Chairman/Sol workflow;
- exact configured Slack workspace/channel/sender eligibility;
- the high-level request vocabulary;
- trusted Executive derivation/policy;
- current grounding/admission checks;
- canonical idempotency/replay.

Do not enlarge caller authority because the trailer exists.

## 6. Bounds

The original 4,500-byte source ceiling assumed the source body was the whole posted message. The platform now contributes transport bytes.

For the framed-carrier experiment:

- full received Slack `text` hard ceiling remains `<= 4,500` UTF-8 bytes;
- canonical payload span target hard ceiling is `<= 4,350` UTF-8 bytes, reserving bounded room for reviewed transport attribution and line separation;
- both values are measured from actual received Slack event text;
- oversize refuses; no truncation;
- the JSON object remains human-readable and one line.

If measured platform attribution cannot fit safely inside this reserve, return to Sol rather than expanding the ceiling casually.

## 7. S0-R1 required experiment

The original S0 run is preserved as a failed regression and must never be rewritten to PASS.

A new framed-carrier experiment, **S0-R1**, is required before B2 can be commissioned.

Use the already-isolated disposable fixture app/channel if still valid and secret-safe. Do not reuse it as production Relay infrastructure.

S0-R1 must run across ChatGPT1, ChatGPT2 and ChatGPT3 and prove:

1. exact Slack source sender IDs;
2. line 1 discriminator preserved exactly;
3. line 2 canonical JSON bytes preserved exactly;
4. transport trailer shape observed and classified independently;
5. payload extraction returns the exact supplied two-line payload on every seat;
6. Unicode and escaped-newline values preserve payload semantics/bytes;
7. a near-4,350-byte canonical payload remains stable and total received text stays within 4,500 bytes;
8. deterministic source parent identity recovery;
9. same-turn receipt readback with a small fixed read budget;
10. thread replies do not originate new work;
11. bot/self recursion refusal;
12. wrong sender/channel refusal;
13. unknown/additional trailer refusal in fixture/parser probes;
14. edit/delete source reread behavior;
15. duplicate event/message behavior;
16. Socket Mode reconnect;
17. daemon restart + bounded history recovery;
18. ACK-then-process-crash recovery shape;
19. no durable lifecycle/dedupe/replay state;
20. zero Executive mutation.

### 7.1 New discriminating payload tests

At minimum, the fixture parser must prove:

- exact two-line payload + expected attribution trailer -> payload accepted by fixture parser;
- exact two-line payload and no trailer -> parser behavior explicitly recorded;
- payload JSON modified by one byte + expected trailer -> different payload hash / no false equality;
- unknown third line -> refuse;
- expected attribution plus an extra fourth line -> refuse;
- attribution text inserted inside line 2 -> invalid JSON/refuse;
- a second `EXECOS/CEO_REQUEST_V1` after the payload -> refuse;
- leading prose before discriminator -> refuse;
- payload with raw third business line -> refuse;
- thread copy/reply containing the same payload -> not an origin candidate.

## 8. S0-R1 kill law

S0-R1 **BLOCKS B2** if any approved Personal-Pro seat cannot provide all of:

- deterministic exact canonical payload-span extraction;
- trusted configured sender provenance;
- deterministic parent recovery;
- bounded same-turn receipt readback;
- safe reconnect/duplicate handling without another durable store.

Also BLOCK if platform mutation occurs **inside** either canonical payload line, or if platform-added content cannot be distinguished with a small exact grammar.

If S0-R1 blocks, do not create S0-R2 by repeatedly special-casing platform behavior. Direct ChatGPT->Slack command transport is then rejected for this V1 product and Sol must choose a different carrier architecture.

## 9. Alternative carrier boundary if S0-R1 fails

A future alternative may preserve Personal-Pro cognition while changing only the modifying carrier, but it requires a new architecture ruling.

Candidates may include a first-party explicit confirmation handoff into another approved write surface or a later product capability that exposes exact structured app actions. Do not silently fail over to MCP, GitHub, Linear, file-upload comments, browser automation hacks or employee credential copying.

In particular, do not exploit a different Slack action merely because it happens not to add attribution. The absence of attribution on another action path is not a reviewed command transport contract.

## 10. Effect on wave sequence

Current safe sequence becomes:

```text
SHELL-1  PROVEN_LIVE
PR-A     BUILT_NOT_PROVEN
R0       SPEC_ONLY -> B1 authorized

B1       may continue independently
  -> C1 after B1 acceptance

S0 V1    BLOCK / whole-message exact-byte carrier rejected
  -> carrier-framing amendment accepted
  -> S0-R1 framed-carrier proof

B2       HOLD until BOTH C1 accepted and S0-R1 PASS + explicit Sol release
  -> C2 only after accepted B2
```

No S0 failure may retroactively weaken B1/C1 or widen B2.

## 11. Required durable closeout

After this records-only amendment is accepted:

- preserve MAS-106 as the immutable S0 V1 BLOCK/falsifier rather than rewriting it;
- project its status as a completed failed experiment / rejected exact-byte carrier;
- create one distinct S0-R1 tracking wave for the framed-carrier proof;
- keep MAS-102/B2 blocked behind C1 + S0-R1 + explicit Sol release;
- amend the current Agent OS MAS-48 decision/handoff with the S0 falsifier and framed retry law;
- do not add live state to the protected Skillpack.

## 12. Acceptance / stop condition

This records-only amendment is accepted only if:

- current protected Mastermind authority is pinned;
- S0 live evidence is preserved as BLOCK, not cosmetically reclassified;
- no PR-A/R0/B1 runtime file changes;
- no new transport store/authority is authorized;
- B2/C2 remain held;
- exact-head CI is green;
- Sol accepts the narrow framing amendment.

Stop at source law. Do not implement B2 in this PR and do not continue the failed S0 experiment until this amendment is canonical.