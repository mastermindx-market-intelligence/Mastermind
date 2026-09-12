# Trading Lab v3 backend schematics

2026-09-12. Read-only preflight is implemented as a research candidate. Authentication, database transactions, persistent execution and new Macro integrations are proposed and not live. Exact DOT/SVG renderings accompany the conversation package.

## One owner per fact

```mermaid
flowchart TD
 UI[Today / Plan / Portfolio / Learn] --> P[Implemented read-only preflight]
 A[Proposed trusted owner adapter] --> P
 S[Existing Self-Directed account owner] --> A
 G[Existing Macro brain gateway and run owner] --> A
 M[Existing Macro market and risk owners] --> A
 J[Existing private trade episode owner] --> A
 P -. preview is not permission .-> E[Future existing-owner paper execution transaction]
```

User input supplies intent only. Account, quote, review, policy and source generations come from trusted owner reads. The synthetic adapter in the candidate is a fixture, not that production trust boundary.

## Two speeds

```mermaid
flowchart LR
 T[Thesis / horizon / evidence changes] --> R[Refresh scoped thesis review]
 Q[Price / size / reservations change] --> D[Recompute deterministic economics]
 R --> B[Bind latest preview]
 D --> B
 B --> C[Explicit exact-action confirmation]
 C -. future integration .-> X[Execution owner rechecks under lock]
```

A current thesis review cannot approve an unaffordable quantity. A quote update must not require a new expensive thesis review. Content hashes are change detectors, never authorization credentials.

## Proposed domain structure

```mermaid
erDiagram
 EXISTING_USER ||--o{ PAPER_ACCOUNT : owns
 PAPER_ACCOUNT ||--o{ PAPER_ORDER : contains
 PAPER_ORDER ||--o{ ORDER_EVENT : records
 PAPER_ORDER ||--o{ PAPER_FILL : produces
 PAPER_FILL ||--o{ CASH_ENTRY : explains
 PAPER_FILL ||--o{ LOT_DISPOSAL : reconciles
 PAPER_ACCOUNT ||--o{ EXISTING_TRADE_EPISODE : contextualizes
 EXISTING_TRADE_EPISODE ||--o{ THESIS_REVIEW_REVISION : preserves
 PAPER_ACCOUNT ||--o{ NAV_PROJECTION : reports
```

Physical extensions are conditional on actual schema/owner inspection. Composite account/mode references prevent cross-user joins. Unique account/request identity stops duplicate orders. Fills, cash and lot facts commit inside one economic transaction; positions, balances and NAV are projections. Existing trade episodes, conversations, identity and publication owners are not replaced.

## Separate Macro program

```mermaid
flowchart TD
 R[Existing causal regime and transition owners] --> F[Point-in-time study and shared lineage]
 D[Existing dispersion / breadth / price owners] --> F
 H[Existing risk / market-state owners] --> F
 F -. empirical and source gates .-> C[One shared market-context contract]
 C -.-> U[Macro dashboard]
 C -.-> N[Neural Web]
 C -.-> P[Prophet]
 C -.-> S[Risk Radar and each market/risk score owner]
 C -.-> T[Terminal and Trading Lab]
```

The conditional edges are not activated by this document. Descriptive context, forecast conditioning and policy effects have different proof gates. No circular independent-confirmation loop and no Trading Lab-local substitute model. See `MACRO_HANDOFF.md` for the multi-turn research-to-production sequence and consumer matrix.
