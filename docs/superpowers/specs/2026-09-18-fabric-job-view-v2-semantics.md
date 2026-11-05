# Fabric Job View v2 semantic correction

Operation: `fabric-job-view-g7-acceptance-20260918-sol-001`.
Parent consumer freeze: PR #704. Dependent Web-CEO profile: PR #779.

## Ruling

`mastermind.fabric_job_view.v1` is historical and remains behavior-compatible.
It aliases Runtime `COMPLETED` to `result.state=ACCEPTED`; that literal must
not be exposed to a Web CEO as product acceptance.

`mastermind.fabric_job_view.v2` corrects the semantics without creating an
acceptance service or store:

- raw Job `status` remains the Executive Runtime status;
- `result.state` is execution/result lifecycle only; `COMPLETED` stays
  `COMPLETED` and never becomes `ACCEPTED`;
- each rendered Job carries an `acceptance` facet;
- until an accepted product-acceptance owner exists, that facet is exactly
  `NOT_PROJECTED` with `producer_owner=null`;
- a `MISSING_PRODUCER` fact names `acceptance.state`;
- result text, artifacts, review verdicts, transport outcomes, and model output
  have zero authority to manufacture product acceptance;
- `ceo_submit_armed=false` means new submission is unavailable. It does not
  imply that an earlier admitted Job cannot exist.

V2 reuses the v1 gather path and Runtime registries. It adds no database,
lifecycle, decision ledger, acceptance table, queue, auth plane, or retry path.

## Capability boundary

This closes G7 semantic truth only. G8 remains independently held: the current
Runtime producer still performs unbounded Job/Attempt acquisition before the
Fabric projector can truncate. V2 must not be exposed over the network until an
owner-issued bounded Runtime seam closes G8.

## Acceptance

A completed Job with review pending or absent acceptance renders:

```text
status=COMPLETED
result.state=COMPLETED
acceptance.state=NOT_PROJECTED
```

An acceptance-looking result payload does not change that facet. Disarming new
submissions preserves already admitted roots and reports only submission
unavailability. V1 regressions must remain green.
