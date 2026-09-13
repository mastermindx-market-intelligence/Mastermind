# Datadog production observability

Mastermind has one Datadog destination: the Chris Wong organization on the GitHub Student plan.
The MastermindX trial organization is not a production observability authority.

The first production slice is the authoritative VPS running `mastermind.service`.
The host installer is `scripts/install_datadog_vps.sh`; it configures:

- Datadog Agent 7 host metrics;
- Single Step Instrumentation for Python APM;
- journald collection scoped to `mastermind.service`;
- unified `env`, `service`, `team`, and `role` tags;
- log/trace correlation for `service:mastermind-api`;
- release correlation through `DD_VERSION=<exact deployed Git SHA>`.

It deliberately does not enable AppSec, IAST, profiling, or another control plane.
Observability remains telemetry/advisory and must not affect portfolio execution.
## Installation

Run only on the authoritative VPS, as root, with an API key from the canonical Datadog org:

```bash
DD_API_KEY='<runtime secret>' ./scripts/install_datadog_vps.sh
```

The key must be supplied in the process environment. It must not be committed, pasted into a
systemd drop-in, added to `/etc/macro-api.env`, or recorded in deployment logs.

The installer first requires the existing Mastermind health endpoint to pass. It then installs or
updates the Datadog Agent using Datadog's official Agent 7 installer, enables host-level Python SSI,
configures log collection, restarts the Agent, and finally restarts `mastermind.service` so the
injected tracer is loaded. If Mastermind health does not recover, the application systemd override
is rolled back and the service is restarted without the override. Future deployments refresh the
Datadog version tag from the exact release SHA before restart, and rollback restores the previous tag.
## Production proof

A successful installer exit proves only the host-local configuration. Do not call Datadog
`PROVEN_LIVE` until the Chris Wong organization independently shows all of the following:

1. the authoritative VPS in host inventory with `env:production` and `role:authoritative-vps`;
2. `service:mastermind-api` journald logs from `mastermind.service`;
3. a real FastAPI request trace for `service:mastermind-api`;
4. the public Mastermind health path still passes after instrumentation.

Only after those producer paths are live should dashboards, SLOs, and monitors be treated as useful
operational surfaces. Browser RUM is a separate frontend producer and requires its own Datadog RUM
application/client token; it is not implied by Agent/APM onboarding.
