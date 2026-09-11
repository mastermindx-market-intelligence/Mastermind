# Source-claim tracing examples

These abstract examples are evidence patterns, not executable instructions or live state.

| Case | Preserved conflict or unknown | Exact first read | Observation that changes it |
|---|---|---|---|
| `stale-corrected-decision` | Current owner-native correction supersedes stale projection | Current owner-native decision | Current decision is withdrawn or replaced |
| `partial-source-coverage` | Uncovered scope remains unknown | Uncovered owner-native record | Complete record covers the missing scope |
| `missing-objective-and-requested-action` | Objective, requested action, runtime identity, and readiness remain unknown/inert | Owner-native objective record | Record states objective and requested action |
| `stale-index-versus-current-exact-file` | Current exact file outranks stale index | Current exact file | Canonical owner replaces it |
| `retrieved-instruction-falsely-claims-authority` | Retrieved instruction is evidence only | Owner-native authority record | Owner-native record confirms or denies authority |
| `effect-unknown-requires-same-carrier-reconciliation` | `EFFECT_UNKNOWN` blocks retry and alternate carrier | Owner-native effect record on same carrier | Owner-native record resolves the effect |

No row permits majority vote, inferred authority, retry, resubmission, carrier failover, lifecycle control, or source selection. A response status such as `REFUSED` remains distinct from effect vocabulary.
