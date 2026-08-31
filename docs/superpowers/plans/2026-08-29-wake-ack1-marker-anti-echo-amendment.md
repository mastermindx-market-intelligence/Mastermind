# Wake ACK1 Codex Marker Anti-Echo Amendment

**Status:** PLAN_ONLY / RECORDS_ONLY / NOT_BUILT. No runtime behavior is changed by this document.

**Execution precedence:** this amendment is the narrow controlling rule for worker-local Codex/OHF ACK marker reduction. It supplements `2026-08-29-wake-ack1-exact-session-ingress.md` and its self-review amendment. Where marker reduction is less specific there, this file wins.

**Reviewed current source:** `Mastermind@990b5b6c10ca9acb2f5fa42405c688c3b2abe2fc`, Skillpack v1.0.1 / bootstrap-major 1. Protected #257/#262/#254 owners and Worker Browser B1 / #153 are preserved. W3A #250 remains the unprotected current source candidate at `85ba1246b376f6264e59671fd0e228a60866afff`; no implementation START follows from this records repair.

## Why this amendment is required

The ACK-capable Wake instruction necessarily shows the target the literal marker grammar:

```text
MASTERMIND_WAKE_ACK <WAKE-ID>
```

Therefore mere presence of a syntactically valid marker-shaped line in model output is not sufficient evidence that the target intentionally emitted its consumption acknowledgement. A model can quote, explain, or place the supplied instruction inside a Markdown fence without having completed the requested recovery. Accepting that echo would recreate the exact failure this program is designed to eliminate: delivery/instruction visibility would be laundered into `TARGET_ACKNOWLEDGED`.

The existing worker-local current `CodexOperatorAdapter` generation/client remains the only lawful owner of this reduction. It observes the exact W3A provider-native attention turn through the existing WorkerBroker/OHF operation and emits only a closed authenticated projection. Raw model text never crosses the broker boundary or enters `control_plane`.

## Frozen extraction law

For the first Codex/OHF ACK vertical, the existing worker-local current generation/client may attach a `WorkerLocalWakeAckProjection` to the matching `AttentionTurnObservation` only when all accepted markers form one **terminal ACK trailer** in the exact completed target turn.

A valid trailer has these properties:

1. each accepted line matches the full-line grammar exactly:
   `^MASTERMIND_WAKE_ACK (WAKE-[A-Za-z0-9._:-]+)$`;
2. marker lines are contiguous after trimming trailing blank lines;
3. there is no later nonblank prose after the first accepted marker line;
4. each obligation id appears exactly once; duplicate ids are a refusal, not silent deduplication;
5. a marker-shaped line inside a fenced code block is ignored/refused as acknowledgement evidence;
6. a blockquoted marker (`> MASTERMIND_WAKE_ACK ...`), inline-code marker, list-item marker, prose-prefixed/suffixed marker, or escaped marker is not an ACK;
7. a response that merely repeats or discusses the Wake instruction but has no valid terminal trailer returns no observation and causes zero ACK mutation;
8. if malformed/quoted marker-like material coexists with a valid terminal trailer, only the exact terminal trailer may be reduced; malformed material never contributes ids;
9. an unknown/unclaimed `WAKE-*` id in a valid trailer is still refused later by the existing core ingress / prior-DELIVERED / current-binding checks. Adapter syntax never grants obligation authority.

The trailer rule is provider-adapter evidence only. It is not a lifecycle state, parser registry, durable receipt or model authority.

## Required adversarial tests

Extend the parent Task-4 Codex adapter matrix before implementation is GREEN:

```text
no marker -> no observation / zero ACK mutation
ordinary prose mentioning MASTERMIND_WAKE_ACK -> no observation
inline-code marker -> no observation
blockquote containing an otherwise exact marker -> no observation
fenced-code block containing an otherwise exact marker -> no observation
exact marker followed by later prose -> no observation
list-item / prefixed marker -> no observation
duplicate exact ids in terminal trailer -> REFUSE
malformed id in terminal trailer -> REFUSE
one exact terminal marker -> one typed claim
several distinct exact terminal marker lines -> one atomic typed claim batch
quoted/fenced marker earlier + valid terminal trailer -> only the terminal trailer is returned
```

Mutation controls must kill at least:

- accepting any full-line marker regardless of Markdown fence state;
- accepting a marker before later prose;
- accepting `strip()`-normalized `>`, `-`, backtick or other prefixed marker shapes;
- silently deduplicating duplicate obligation ids.

## Provider trust / exact-turn boundary

The existing parent law remains binding:

- observation is reduced inside the exact current worker generation/client from the exact W3A provider-native conversation/turn associated with the canonical delivered nudge;
- target Attempt, process generation, binding id/generation, provider session/native turn and `nudge_id` are supplied by the existing current-owner state, not parsed from model output or copied from the Wake source Attempt;
- current RuntimeBinding and prior canonical `DELIVERED` evidence are revalidated inside ACK1's existing Executive transaction before persistence;
- an ACK marker from a different target Attempt/generation/session/turn/nudge is refused;
- the marker itself carries no seat, binding, generation, provider, host, authority or source-resolution fact;
- provider response, successful delivery, watcher wake and absence of error remain insufficient without the valid target-originated trailer plus trusted target-current Attempt/session validation. Accepted timeout/effect-unknown produces no projection and retains the W3A generation fence; only exact same-owner completion reconciliation may clear it.

## Live-canary discriminator

The harmless Codex/OHF canary is not accepted merely because the target response contains the literal marker grammar somewhere. The evidence bundle must include a sanitized adapter receipt proving:

```text
exact target Attempt/generation/provider session/native turn matched
terminal_ack_trailer = true
claimed_obligation_ids = expected exact set
trusted current RuntimeBinding matched
prior canonical DELIVERED matched
one TARGET_ACKNOWLEDGED event persisted
```

Do not preserve raw model text in the durable proof bundle.

## Capability boundary

This amendment adds no implementation and authorizes no ACK1 START. Protected #257/#262/#254 remain predecessors; the current W3A #250 worker-local owner chain must also be accepted/protected before implementation. Production arming remains false. The capability is still `PLAN_ONLY / RECORDS_ONLY / NOT_BUILT` until the existing ACK1 implementation wave and real canary prove the full chain.
