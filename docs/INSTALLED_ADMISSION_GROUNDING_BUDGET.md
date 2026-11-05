# Installed admission grounding budget

The selected App in `ops/executive_os/executive_mcp_entry.py` uses a 65-second
private response wait. Native foreground calls instead use their authenticated
remaining lifetime (maximum 300 seconds). Neither is the packet collector's
28-second budget. Fresh admission previously made two sequential full repository
observations twice, without a cumulative source deadline.

Fresh ingress now starts a 60-second request-local budget **after** the exact
command lookup finds no durable result. Both independent observations, the
intervening source reads, and pre-effect admission work share that deadline. A
nested installed observation cannot renew it. A standalone installed grounding
observation gets the same finite 60-second bound. The five-second difference from
the selected private response wait is a settlement/response reserve, not proof
that every repository pair fits. The default SDK's 10-second wait is not the
selected installed binding.

Each installed observation still uses `content_scope="all"` for both repositories,
with full object, inventory, raw worktree byte, ancestry, HEAD and applicable
source identity checks. It passes the same deadline into the existing proof
loops and children; the 10-second child ceilings remain. The source collector's
28-second ceiling, 24,000-object shards and two-worker proof implementation are
unchanged by this delta. No snapshot result is cached or shared across requests.

The async observer shields one physical thread and, if cancelled, waits for that
same bounded observation to settle before propagating cancellation. Repeated
cancellation cannot detach it. No subsequent observation or sink runs on that
cancelled path. This is not a `wait_for` around a live thread. Installed proof
workers join their children and use the existing owned-process cleanup. The
actual bounded-child cancellation test checks the child is gone before return.
Generic injected providers must still honor their own finite execution contract;
this change cannot forcibly terminate arbitrary Python business code.

The fresh path rechecks its budget before the existing sink. A principal guard
runs inside that sink, at its existing fresh-only position immediately before
Job creation; a wrapper checks the same copied deadline before and after that
guard. Its return verdict remains unchanged. A durable replay precedes the scope
and does not observe current sources or invoke the guard. Once the sink has been
entered, any original effect retains canonical reconciliation; this change never
reclassifies a committed or uncertain result as a safe retry.

Local evidence includes a five-case behavioral failing predecessor, a further
principal-guard expiry failure, repaired real Runtime admission/replay checks,
concurrent request isolation, and actual subprocess settlement on cancellation.
These are source tests, not installed throughput, connector fit, or production
acceptance. The incumbent #1465 owner retains release and real-host qualification.
