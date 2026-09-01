# Executive Attention Economics — F0D Cost-of-Delay Law

**Operation:** `mastermind-executive-attention-economics-20260830-sol-001`  
**Parents:** F0/F0A/F0B/F0C  
**Status:** `ARCHITECTURE FREEZE / SPEC_ONLY / RECORDS_ONLY`

## 1. Research ruling

Cost of Delay is a legitimate economic concept, but it does not justify a universal Mastermind executive-priority score.

Industry flow systems such as SAFe's WSJF estimate relative Cost of Delay and divide by relative job duration to sequence product-development work. Classical scheduling likewise models completion/tardiness objectives only after a cost function and service/processing-time assumptions are defined.

For Executive Attention Frontier, those assumptions often do not hold:

- the work item may be a **decision**, not the implementation job;
- implementation size is not executive cognition/service time;
- delay consequences may be discontinuous at a decision window rather than linear per hour;
- irreversible choices may have positive option value from waiting for information;
- dependencies and current autonomous progress change the consequence of delay;
- actual monetary/business loss may be unknown and must not be invented from labels.

Therefore EAF decomposes delay pressure into grounded factors unless a source owner supplies a real delay-cost function.

Primary references:

- SAFe WSJF/Cost of Delay definition: https://framework.scaledagile.com/wsjf/
- SAFe Cost of Delay glossary: https://framework.scaledagile.com/blog/glossary_term/cost-of-delay
- Scheduling literature commonly models linear/fixed tardiness/completion costs only under explicit cost/due-date assumptions; see e.g. DOI 10.1016/j.cie.2024.110060 and the scheduling references in F0.
- Real-options/value-of-information sources in F0 remain controlling for irreversible decisions under uncertainty.

## 2. Frozen law

### 2.1 Source-owned delay economics may be represented

If an accepted source explicitly supplies a time-dependent economic consequence, EAF may carry it as evidence, for example:

```text
delay_cost
  basis: monetary | relative | categorical
  value/function
  time_unit/window
  effective_at
  source_ref
  freshness
```

Exact wire names are A1 details.

The source must own the meaning. EAF may not estimate revenue loss, customer harm, opportunity value or legal/operational penalty from free text.

### 2.2 No universal executive WSJF

V1 may not compute a company-wide `cost_of_delay / job_size` or `cost_of_delay / decision_duration` score unless a later accepted architecture establishes that both numerator and denominator are source-backed and comparable for the specific bounded decision family.

In particular:

- PR size, lines changed, story points, worker token use and implementation duration are not proxies for Chairman/Sol cognition duration;
- worker runtime/resource burn is a pressure factor, not executive service time;
- model-estimated "minutes to decide" is not authority-grade scheduling data;
- relative business value workshops are not automatically comparable to live production-impact or authority windows.

### 2.3 Delay pressure is vector-valued by default

Without an explicit source-owned delay-cost function, EAF uses the existing grounded dimensions:

- decision/window timing;
- current actual impact;
- reversibility/irreversibility;
- exact downstream unblock;
- active resource burn;
- safe autonomous progress remaining;
- expected information / option value of waiting;
- evidence quality/freshness.

These dimensions may explain **why delay matters** without being summed into fake dollars or a fake relative score.

### 2.4 Sunk cost is not priority

Already-spent worker tokens, engineering effort or prior executive attention do not by themselves justify more attention. Only current/future resource burn, cost of delay, consequence, option value and other forward-looking source facts matter.

### 2.5 Delay cost cannot grant authority

A million-dollar delay estimate does not make a Sol-authorized decision Chairman-only. Authority remains a separate canonical partition.

## 3. Local use of ratio rules

A later bounded subdomain may lawfully use a ratio/WSJF-like rule only if all of these are true:

1. same authority partition;
2. same bounded decision/work family;
3. comparable accepted delay-cost basis;
4. comparable accepted service-duration basis for the scarce resource actually being scheduled;
5. no hard deadline/irreversibility/authority rule supersedes the ratio;
6. the rule is explicit, versioned, replayable and independently validated;
7. no missing optional evidence is silently encoded as zero.

Such a local rule would be a named policy plugin/input to EAF, not the architecture's universal ordering law.

## 4. Adversarial corpus additions

29. large implementation project with small/quick executive decision vs tiny patch with difficult executive tradeoff -> implementation size must not act as executive service-time denominator;
30. source-owned monetary delay function vs an item with only `user_facing` blast radius -> monetary evidence may be displayed/compared where lawful; blast radius must not be monetized;
31. high historical sunk cost but no current delay/resource/impact pressure -> sunk cost alone does not raise disposition;
32. high active resource burn waiting on a Sol decision -> burn increases pressure but does not estimate cognition duration or change authority;
33. irreversible choice with explicit evidence arriving before a safe review boundary -> option value can justify `VALID_WAIT` despite nominal business value;
34. two homogeneous bounded decisions with accepted comparable delay-cost and service-time facts -> a later explicitly configured local ratio policy may order them, with receipts, without creating a global score.

## 5. Freeze effect

Cost of Delay is now explicitly represented as **conditional source evidence**, not a universal score. F0's vector/partial-order architecture remains controlling.
