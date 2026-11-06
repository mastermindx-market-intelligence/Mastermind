# Installed source binding for Capacity observations

The existing one-shot Wake observer can retain a point whose executing source and
Control configuration are joined to the actual installed release. This mode does
not start a campaign, service, worker, provider request, or recurring collection.
It does not attest a live Control peer or hold the Runtime namespace.

## Capture one installed point

Run as the normal root configuration owner on macOS, from the exact installed
release, using the installed pinned Python in isolated, no-site, no-bytecode
mode. The release must contain this producer. Use a unique receipt name in an
existing private root-owned directory with no group/other permissions or ACL.
An existing receipt, including an incomplete reservation, is never overwritten.

```sh
sudo /Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12 -I -S -B \
  "/Library/Application Support/MastermindExecutive/releases/${S}/scripts/executive_wake_reconcile.py" \
  --observe-only --installed-release-sha "${S}" \
  --observation-receipt "/absolute/private/evidence/unique-point.json" --json
```

`S` is the actual installed release SHA. The command refuses a source checkout,
an unpinned interpreter, a non-root/non-macOS process, a different installed
release, or an active autonomy transaction. It uses the existing Control owners
to qualify the complete release and manifest, Control launchd plist, signed PSF
Python, and the root-published Control observation receipt. It joins the current
Control bytes and physical identity before and after acquisition. Replacement
with identical bytes still invalidates the held observation.

The Runtime path comes only from that verified Control config and must match the
fixed installed Runtime root. Only the existing trusted `/var` alias
normalization is allowed. `--root` and `--boot-packet-file` are refused.
`--no-boot-packet` is allowed, but omitted source coverage stays explicit and
cannot become a complete company demand observation.

The existing installed owner's 25-second finite qualification budget is not
widened. It covers preflight, observation, and final owner rechecks. Real UTC
start/end labels and monotonic acquisition cost include qualification work;
separate monotonic phase costs retain preflight, observer, and final recheck
time. An expired budget or changed source/config/Python/plist produces no
completed installed receipt. The exclusive incomplete reservation remains for
reconciliation, with no automatic source-only fallback or replay.

## Report the retained explicit set

Use the same script and Python, as the root receipt owner, with only the exact
receipt paths to summarize. This path does not consult live Runtime or installed
source state. It checks the retained closed schemas, file custody, stream and
source digests, Control binding, and acquisition timing joins.

```sh
sudo /Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12 -I -S -B \
  "/Library/Application Support/MastermindExecutive/releases/${S}/scripts/executive_wake_reconcile.py" \
  --summarize-observations "/absolute/private/evidence/unique-point.json" --json
```

Installed captures use `mastermind.capacity_observation_receipt.v2`. Existing
source-only v1 receipts remain readable. The report retains each point's source
binding and timing, counts installed-source-bound points, and separately counts
those whose observer returned a healthy result. A source/config-bound point can
still contain a partial or unavailable Runtime result. Mixed source-only and
installed receipts, differing source/config/Runtime bindings, missing inputs,
or invalid receipts remain explicit collection failures.

The supplied set can prove `installed_source_and_config_custody_qualified`.
`installed_service_peer_attested`, `runtime_namespace_continuity_attested`,
`installed_coverage_claimed`, and `campaign_qualified` remain false. This source
join does not prove actual parent consumption, paid spend, accepted outcomes,
ordinary versus proof workload, or continuous seven-day observation. Those
requirements keep their separate unavailable/partial provenance; elapsed labels
or an empty Runtime cannot satisfy them.

## Qualification scope

The focused source tests execute the actual observer, Runtime rows, retained
Control projection contract, physical file replacement checks, exclusive receipt
custody, and offline report. Their macOS/root/install boundary is explicitly
modeled. They prove this composition's behavior, not a real installed campaign
or the host's signed Python/source custody. The production path always uses the
existing installed owners without a mutable trust manifest or caller authority.
