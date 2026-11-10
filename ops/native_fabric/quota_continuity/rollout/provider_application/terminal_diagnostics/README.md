# Preserve native41 diagnostics in the APPLICATION transition

Use the existing APPLICATION builder and original Go transaction owners to
advance the complete terminal-diagnostics predecessor. This optional composition
retains both the accepted native41 diagnostics and the guard behavior already
bound by the frozen maintenance source cohort.

The frozen files in ../maintenance_guard are historical source inputs. Their
name does not establish that they match a currently selected native generation:
the actual native40 parent differs in five provider bindings, and native41 then
changes its worker to retain terminal diagnostics. The frozen records and their
accepted hashes remain unchanged.

## Exact sources and composition

The predecessor is the complete 116-member map authenticated by
ops/native_fabric/provider_plans/terminal_diagnostics/current40/profile.json,
introduced through protected source c34df5ac9a933c14971a7cf9055c505effef50ce.
Its canonical files-map SHA-256 is
5511104937c8bcf68a89558c510a88a7519de8b9958c7064fde20dfdf90c5f7a.
The original terminal component comes from
7efbbaa61abe9ec1efcde85dafcb70f7126646bd.

The joined worker retains the exact guard invoke function and every other byte
of the original terminal worker. The original terminal patch also transforms
the guard worker directly into the same joined file. composition.json commits
the two inputs, original component and patch, selected-predecessor profile,
new forward patch, exact byte count and complete before/after APPLICATION maps.

| Worker | SHA-256 |
| --- | --- |
| Actual native41 terminal parent | 2df8947c446e143d46bbf979e30dd11965080922839e2e37c3d8c0289ef2af7b |
| Frozen guard parent | 266c6dddb43e9abb669101504d6dc62a1936acd58628dd59927451deb8cc3f28 |
| Joined APPLICATION worker | 9e450c6aab4c4a82b8f78b5706c7eaa7236241dba030a762b6257d3b0f8d11dc |

## Build with the existing owner

```sh
python3 -B ops/native_fabric/quota_continuity/rollout/build_review_stage.py \
  --output /absolute/new/review-stage \
  --include-provider-plan-application \
  --include-provider-plan-remote-placement \
  --include-provider-plan-maintenance-guard \
  --include-provider-plan-terminal-diagnostics \
  --include-go-application --include-application-http --include-application-glm
```

The new flag requires the maintenance option and its existing APPLICATION and
remote-placement prerequisites. It changes only the worker within the complete
116-member core, before the existing GLM, Go and HTTP additions. The supported
outputs contain 116 core members, 118 with Go, 121 with HTTP and 123 with GLM.
Omitting the new flag preserves the existing frozen maintenance outputs.

The transition validator first requires equality of the whole native41
predecessor map and authenticates the entire joined target core. Only then does
it delegate to the existing maintenance/Go/HTTP validators. It retains the full
expanded namespace, external-component dependencies and original CURRENT
compare-and-swap. A partial source map, diagnostic rollback, guard rollback,
mixed provider cohort or foreign target is not a compatible transition.

The existing test_provider_application_transition module exercises the original
apply/reconcile transaction under both owner forms, including interrupted
selection/receipt recovery and stale CURRENT rejection. Its native41 source is
materialized through the existing protected composer chain. Those disposable
source descriptors are not installed selection or admission receipts.

This source composition does not select a generation or authorize service
admission. Publish, retained-account forwarding, one original Go selection,
service activation and attended Hermes proof retain their original owners.
