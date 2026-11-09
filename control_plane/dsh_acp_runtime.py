"""Rev 5 DSH lane: the ``dsh-acp`` runtime descriptor (D5 + D2-DSH).

This module owns the company-side truth about running DeepSeek Harness (DSH)
as a native ACP agent beneath T3 Code, per the Revision 5 master plan §6
("Native DSH beneath T3", "Descendant policy") and the Wave 3 change order §3C.

Three facts this descriptor pins, each from observed evidence on M2
(2026-11-08, dsh 0.2.2-rc.1, npm-global ``@deepseek-ai/dsh``):

1.  Runtime identity.  ``runtime=dsh`` is a HARNESS identity, distinct from
    ``model=deepseek``: selecting a DeepSeek model on another route is not
    this harness.  The ACP serving profile composes its own agent loop,
    tools, subagent fan-out and credential custody; the model is chosen per
    session through ACP config options.

2.  ACP provider config for T3.  T3 adds DSH as a *Local ACP command*
    (Settings → Providers → Add provider → Show more → Local ACP command):
    executable ``dsh`` plus ONE LITERAL ARGUMENT PER ROW, no shell
    expansion, persisted as a ``ProviderInstanceConfig`` in the server's
    ``userdata/settings.json``.  The acp-app profile takes ZERO app
    arguments, so the argument rows are exactly the launcher flags:
    ``--profile`` and the profile NAME.  Two verified shapes:

    * company profile (qualified lane): ``--profile`` / ``mmx-acp`` —
      created from the shipped ``acp`` template via the documented
      ``dsh --profile mmx-acp --from-default-profile acp`` seam
      (``dsh --help``: "Create or reset another profile at a non-shipped
      name with --from-default-profile").
    * shipped profile: ``--profile`` / ``acp`` — which is exactly the T3
      documentation's two-row example ("use ``dsh`` with arguments
      ``--profile`` and ``acp``", docs/user/providers-acp.md:35): ``acp``
      is the PROFILE NAME, not an app argument.

    A three-row ``--profile``/``<name>``/``acp`` shape (profile name plus
    ``acp`` as an app argument) FAILS to boot: dsh exits with
    ``error: too many arguments. Expected 0 arguments but got 1: acp``
    (live receipt ``dsh_acp_probe_receipt_profile_mmxacp_acp.jsonl`` — the
    failed-variant receipt retained on M2).  The shipped ``desktop`` and
    ``web`` profiles do refuse CLI/ACP boot ("managed exclusively by the
    Electron application"), which does NOT extend to the CLI-bootable
    ``acp``/``mmx-acp`` profiles.

3.  Descendant policy, chosen by evidence and enforced here:
    ``bounded_native_fanout``.  A live ACP session on ``mmx-acp`` called
    the native ``subagent`` tool, started child session
    ``fe1d0c8f-82d2-45f5-ba27-3e9c7770593a`` inside the same dsh process,
    listed it with ``list_agents(scope=children)``, and the ACP prompt
    settled only after the child completed.  The child-spawn seam
    (``@deepseek-ai/dsh-subagent`` + in-process spawn/fork backends)
    enforces a REAL bounded envelope — ``maxActiveSubagents`` (default 8,
    sampled before every activation, ``ACTIVATION_LIMIT_REACHED`` at
    capacity, process-local slots) and ``maxDepth`` (default 1, enforced
    per delegation attempt) — and children share the parent's process, so
    they cannot take a separate host placement.  No native hook in the
    shipped composition obtains per-child Executive admission, so
    ``fabric_per_child`` would be a configuration promise without a real
    enforcement mechanism (forbidden by the plan); the envelope is the one
    reservation, reconciled against observed children, never envelope AND
    per-child.

This module is a descriptor + policy + lineage surface, not a launcher: it
selects nothing and starts nothing.  Registering the ``dsh-acp`` row in
``ADAPTER_DESCRIPTORS`` names the route; the lane stays
``implemented=False`` until the full T3→DSH composition and confinement
profile are reviewed (the same discipline as the WO-18 ``opencode-free-cli``
row).
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
from typing import Any, Mapping

__all__ = [
    "DSH_ACP_RUNTIME_ID",
    "DSH_RUNTIME_KIND",
    "AcpCapabilityStatus",
    "DshAcpCapability",
    "DshAcpProviderConfig",
    "NativeFanoutEnvelope",
    "DshDescendantPolicy",
    "DescendantPolicyViolation",
    "DESCENDANT_POLICIES",
    "DshExecutiveToolsBridge",
    "DshRuntimeDescriptor",
    "DSH_ACP_RUNTIME",
    "descendant_policy",
]

#: The runtime descriptor id registered in ``ADAPTER_DESCRIPTORS``.
DSH_ACP_RUNTIME_ID = "dsh-acp"

#: The harness/runtime kind.  Deliberately NOT a model identity: a
#: ``model=deepseek`` selection on any other route is a different lane.
DSH_RUNTIME_KIND = "dsh"

# --- Capability discovery ----------------------------------------------------

SUPPORTED = "SUPPORTED"
UNSUPPORTED = "UNSUPPORTED"
UNKNOWN = "UNKNOWN"

#: The three lawful statuses for a discovered capability (Rev 5 l.368-369).
AcpCapabilityStatus = (SUPPORTED, UNSUPPORTED, UNKNOWN)


@dataclasses.dataclass(frozen=True)
class DshAcpCapability:
    """One discovered ACP capability with the evidence that observed it.

    ``status`` is one of SUPPORTED / UNSUPPORTED / UNKNOWN.  Evidence lines
    cite live receipts (M2 probe, 2026-11-08) or the pinned dsh source
    contract; a status without evidence is not recorded here.
    """

    status: str
    scope: str = ""
    evidence: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.status not in AcpCapabilityStatus:
            raise ValueError(f"capability status must be one of {AcpCapabilityStatus}")


#: Capability discovery for the dsh ACP lane, from real M2 probes on the
#: qualified ``mmx-acp`` profile (dsh 0.2.2-rc.1).  Receipts:
#: ``dsh_acp_probe_receipt_profile_mmxacp.jsonl`` (working session),
#: ``dsh_acp_probe_receipt_profile_mmxacp_acp.jsonl`` (three-row refusal).
DSH_ACP_CAPABILITIES: dict[str, DshAcpCapability] = {
    # initialize -> agentCapabilities.sessionCapabilities = {close, list,
    # resume}; session/resume method present in @deepseek-ai/dsh-acp.
    "resume": DshAcpCapability(
        status=SUPPORTED,
        scope="persistent root sessions; jsonl persistence under $DSH_HOME/sessions",
        evidence=(
            "live initialize: sessionCapabilities {close:{}, list:{}, resume:{}}",
            "dsh-acp README: session/resume restores a persisted inactive session "
            "without replaying old updates; ordinary forks admitted, "
            "origin: subagent sessions excluded",
        ),
    ),
    # session/list returned 24 persisted sessions live; T3 imports a native
    # session as a deterministic thread (providers-acp.md "Native sessions").
    "import": DshAcpCapability(
        status=SUPPORTED,
        scope="ACP session listing/import into T3 threads",
        evidence=(
            "live session/list: 24 persisted sessions, newest-first pages",
            "providers-acp.md: importing an agent session creates a deterministic "
            "T3 thread; re-import returns the existing thread",
        ),
    ),
    # session/new advertised a model select (deepseek-account / zai groups)
    # plus reasoning_effort; session/set_config_option updates them.
    "models": DshAcpCapability(
        status=SUPPORTED,
        scope="per-session model + reasoning effort over ACP config options",
        evidence=(
            "live session/new configOptions: model select currentValue "
            '[\"zai\",\"glm-5.3-flash\"] with deepseek-account/zai groups; '
            "reasoning_effort select present",
            "dsh-acp README: session/set_config_option serialized update of the "
            "advertised model or reasoning_effort",
        ),
    ),
    # ACP request_permission + dsh permission presets.
    "permissions": DshAcpCapability(
        status=SUPPORTED,
        scope="ACP session/request_permission one-shot allow/reject; DSH_PERMISSION_MODE presets",
        evidence=(
            "dsh-acp README: session/request_permission with one-shot choices",
            "composed profile dump: dsh-permission-presets "
            "(read-only / workspace-write / danger-full-access) and "
            "dsh-user-approval policy ask/never",
        ),
    ),
    # usage_update events carry context-window usage only; per-model-call
    # token/cost granularity is NOT exposed over ACP.
    "usage": DshAcpCapability(
        status=SUPPORTED,
        scope="context-window usage only (used/size); per-model-call usage unknown",
        evidence=(
            "live session/update usage_update: {used: 10344, size: 1000000} "
            "across both prompts",
        ),
    ),
    # Explicitly NOT supported, preserved as limitations (plan l.369).
    "usage_per_model_call": DshAcpCapability(
        status=UNKNOWN,
        scope="ACP exposes no per-call token/cost event; reserve conservatively "
        "per managed turn plus the declared descendant envelope",
        evidence=(
            "dsh-acp README protocol contract exposes usage only via "
            "session/update context usage",
        ),
    ),
    "acp_workspace_rollback_rewinds_conversation": DshAcpCapability(
        status=UNSUPPORTED,
        scope="ACP checkpoint rollback does not rewind native conversation history",
        evidence=(
            "providers-acp.md:130-132 — the next turn after a rollback starts a "
            "fresh agent session",
        ),
    ),
    "session_transcript_replay": DshAcpCapability(
        status=UNSUPPORTED,
        evidence=(
            "dsh-acp README: deletion, forks, transcript replay and additional "
            "directories are unsupported",
        ),
    ),
}


# --- T3 provider config ------------------------------------------------------

@dataclasses.dataclass(frozen=True)
class DshAcpProviderConfig:
    """The exact T3 Local-ACP-command provider configuration for DSH.

    T3 persists provider instances in ``<T3 home>/userdata/settings.json``
    (``ProviderInstanceConfig``: driver-decoded config + ``environment``
    array of ``{name, value}`` overrides).  Local commands are launched
    directly with one literal argument per row and NO shell expansion.
    """

    executable: str = "dsh"
    #: One literal argument per row, exactly as T3 launches them.  The
    #: acp-app profile takes zero app arguments, so these rows are the
    #: launcher flags only.
    argument_rows: tuple[str, ...] = ("--profile", "mmx-acp")
    #: The T3-doc two-row shape against the SHIPPED profile (also verified
    #: live): ``acp`` is the profile name.
    shipped_profile_argument_rows: tuple[str, ...] = ("--profile", "acp")
    display_name: str = "DeepSeek Harness (mmx-acp)"
    #: Recommended: pin an absolute executable override (e.g.
    #: /Users/<user>/.local/bin/dsh) so the instance cannot drift with PATH.
    executable_override_recommended: str = (
        "~/.local/bin/dsh -> ~/.local/lib/node_modules/@deepseek-ai/dsh/lib/bin.js"
    )
    #: Environment overrides live in the provider instance.  DSH credentials
    #: stay with DSH (its credential store / its own launching environment);
    #: they are never copied into Mastermind code, config or ledgers.  The
    #: qualified M2 profile routes at the zai provider via the llm-pi-ai
    #: ``apiKeyEnv`` seam (key consumed from the process environment, as the
    #: shipped desktop profile does).
    environment_overrides_note: str = (
        "optional; e.g. DSH_PERMISSION_MODE. Provider API keys, when a "
        "non-account route is qualified, are consumed by dsh from its own "
        "configured apiKeyEnv — never embedded here"
    )
    t3_persistence: str = "<T3 home>/userdata/settings.json (ProviderInstanceConfig)"
    t3_ui_path: str = (
        "Settings → Providers → Add provider → Show more → Local ACP command"
    )

    def launch_argv(self, executable: str | None = None) -> tuple[str, ...]:
        return (executable or self.executable, *self.argument_rows)


# --- Descendant policy -------------------------------------------------------

FABRIC_PER_CHILD = "fabric_per_child"
BOUNDED_NATIVE_FANOUT = "bounded_native_fanout"
NATIVE_FANOUT_DISABLED = "native_fanout_disabled"

#: Exactly one policy per runtime descriptor (Rev 5 "Descendant policy").
DESCENDANT_POLICIES = (FABRIC_PER_CHILD, BOUNDED_NATIVE_FANOUT, NATIVE_FANOUT_DISABLED)


class DescendantPolicyViolation(ValueError):
    """A descendant observation or reservation attempt violates the policy."""


@dataclasses.dataclass(frozen=True)
class NativeFanoutEnvelope:
    """The native descendant envelope a dsh profile really enforces.

    ``max_active_subagents`` and ``max_depth`` are the composed profile's
    actual values (sampled by dsh before every activation / delegation
    attempt).  ``host_scope`` records where the envelope physically lives:
    the dsh process's own host — the envelope is reserved THERE, never as
    fleet-wide capacity.
    """

    max_active_subagents: int
    max_depth: int
    host_scope: str = "process-local"
    enforced_by: str = (
        "@deepseek-ai/dsh-subagent: maxActiveSubagents sampled before every "
        "new or cold-resumed activation (ACTIVATION_LIMIT_REACHED at "
        "capacity, process-local slots); maxDepth enforced per delegation "
        "attempt"
    )

    def __post_init__(self) -> None:
        if self.max_active_subagents < 1:
            raise ValueError("max_active_subagents must be >= 1")
        if self.max_depth < 0:
            raise ValueError("max_depth must be >= 0")


@dataclasses.dataclass(frozen=True)
class DshDescendantPolicy:
    """One enforceable descendant policy for the dsh-acp runtime.

    Construction rules (fail closed, at __post_init__):

    * ``fabric_per_child`` REQUIRES ``admission_hook_evidence`` naming the
      real native hook where each child obtains its own root-carrying
      placement.  None exists in the shipped composition (children are
      in-process), so this policy cannot be constructed for dsh-acp today —
      claiming it would be a configuration promise without enforcement.
    * ``bounded_native_fanout`` REQUIRES a ``NativeFanoutEnvelope`` and
      REFUSES per-child slot reservations (no envelope-AND-per-child double
      counting; exactly one reservation model).
    * ``native_fanout_disabled`` requires neither and refuses every native
      child.
    """

    policy: str
    envelope: NativeFanoutEnvelope | None = None
    admission_hook_evidence: str = ""
    evidence: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.policy not in DESCENDANT_POLICIES:
            raise ValueError(f"policy must be one of {DESCENDANT_POLICIES}")
        if self.policy == FABRIC_PER_CHILD:
            if not self.admission_hook_evidence.strip():
                raise DescendantPolicyViolation(
                    "fabric_per_child requires a real native admission hook "
                    "(evidence required); a configuration promise without "
                    "enforcement is forbidden (Rev 5 descendant policy)")
            if self.envelope is not None:
                raise DescendantPolicyViolation(
                    "fabric_per_child admits children individually and must "
                    "not also carry a native fan-out envelope (double "
                    "reservation is forbidden)")
        elif self.policy == BOUNDED_NATIVE_FANOUT:
            if not isinstance(self.envelope, NativeFanoutEnvelope):
                raise DescendantPolicyViolation(
                    "bounded_native_fanout requires the actual enforced "
                    "envelope (max_active_subagents, max_depth)")
        elif self.policy == NATIVE_FANOUT_DISABLED:
            if self.envelope is not None:
                raise DescendantPolicyViolation(
                    "native_fanout_disabled carries no envelope")

    # -- enforcement ---------------------------------------------------------

    def validate_profile_observation(
        self, observed_active: int, observed_depth: int,
    ) -> None:
        """Refuse admission when the live profile envelope is not the
        reserved one (silent drift would make the reservation a lie)."""
        if self.policy != BOUNDED_NATIVE_FANOUT or self.envelope is None:
            return
        if (observed_active != self.envelope.max_active_subagents
                or observed_depth != self.envelope.max_depth):
            raise DescendantPolicyViolation(
                "profile envelope drifted from the reserved envelope: "
                f"observed (active={observed_active}, depth={observed_depth}) "
                f"vs reserved (active={self.envelope.max_active_subagents}, "
                f"depth={self.envelope.max_depth}); re-reserve or re-qualify "
                "the profile before admitting")

    def reserve_descendant_slot(self, child_key: str) -> None:
        """Per-child reservation attempt — the double-count guard.

        Under ``bounded_native_fanout`` the ONE reservation is the envelope
        at the dsh process's host; reserving slots per child on top of it
        would charge the same children twice (forbidden by Rev 5).
        """
        if self.policy == BOUNDED_NATIVE_FANOUT:
            raise DescendantPolicyViolation(
                "bounded_native_fanout reserves ONE native envelope at the "
                "dsh process's host; per-child slot reservations on the same "
                "lane are double counting (child_key="
                f"{child_key!r})")
        if self.policy == NATIVE_FANOUT_DISABLED:
            raise DescendantPolicyViolation(
                "native_fanout_disabled: no native descendant may be "
                f"reserved (child_key={child_key!r})")

    def account_observed_child(
        self, observed_active_children: int, *, observed_depth: int = 1,
    ) -> int:
        """Account observed native children against the policy.

        Returns the accounted count (the number reconciled INTO the
        envelope).  Under ``bounded_native_fanout`` children beyond the
        envelope are a policy violation: dsh should have refused them
        (ACTIVATION_LIMIT_REACHED); observing more than the envelope means
        the profile was altered without re-qualification — the lane must be
        refused until reconciled, and the violation is raised here so no
        caller can silently absorb it.
        """
        if self.policy == NATIVE_FANOUT_DISABLED:
            raise DescendantPolicyViolation(
                "native_fanout_disabled: a native child was observed "
                f"({observed_active_children}); the lane must be refused")
        if self.policy == FABRIC_PER_CHILD:
            # Each observed child is admitted through the fabric hook with
            # its own placement; accounting belongs to that admission.
            return observed_active_children
        assert self.envelope is not None  # bounded (constructed with one)
        if observed_active_children > self.envelope.max_active_subagents:
            raise DescendantPolicyViolation(
                f"observed {observed_active_children} active native children "
                f"exceed the reserved envelope "
                f"({self.envelope.max_active_subagents}); hidden fan-out "
                "beyond the reservation is refused")
        if observed_depth > self.envelope.max_depth:
            raise DescendantPolicyViolation(
                f"observed descendant depth {observed_depth} exceeds the "
                f"reserved envelope depth {self.envelope.max_depth}")
        return observed_active_children


# --- Executive tools bridge (Rev 5 §6 l.371) ---------------------------------

@dataclasses.dataclass(frozen=True)
class DshExecutiveToolsBridge:
    """The narrow Executive-tools bridge for DSH under T3 ACP.

    T3 injects its OWN MCP bridge into ACP agents and does NOT forward the
    agent's arbitrary external MCP configuration (confirmed at the pinned
    source: ``packages/provider-acp/src/server/mcpOverAcpBridge.ts`` wired
    from ``adapter.ts``).  Executive tools therefore reach DSH through the
    QUALIFIED NATIVE SEAM — ``@deepseek-ai/dsh-mcp-client`` entries in the
    profile's own ``cordis.patch.yml`` user layer — which is exactly how the
    shipped desktop profile already mounts company bridges on M2:

    * ``mcp-mmx-browser`` — pinned-closure stdio server
      (``~/.dsh/mcp/mmx-browser/server.js``) mirroring the native Hermes
      plugin 0.5.0 contract: hash-verified source closure, per-call pinned
      subprocess, identity-checked receipts.
    * ``mcp-subagent-fabric`` — loopback Streamable HTTP to the M2
      subagent-fabric private gateway (127.0.0.1:45119) exposing the eight
      ``fabric_*`` tools: DSH-side delegation THROUGH the company fabric,
      each such child admitted by the fabric on its own binding.

    This bridge record documents WHICH seam and WHY; the operator-owned
    patch fragment below is the shape applied to the qualified profile's
    ``cordis.patch.yml``.  It contains no credentials: stdio/loopback
    transports and dsh-side env consumption only.
    """

    seam: str = "dsh-mcp-client entries in the profile cordis.patch.yml user layer"
    why: str = (
        "T3 injects its own MCP bridge into ACP agents and does not forward "
        "arbitrary agent MCP configuration (mcpOverAcpBridge.ts at the "
        "pinned T3 source); Executive tools must ride dsh's own qualified "
        "plugin seam or an explicit narrow bridge — this is the native seam, "
        "with the pinned-closure/loopback discipline the desktop profile "
        "already uses on M2"
    )
    exemplars_on_m2: tuple[str, ...] = (
        "~/.dsh/mcp/mmx-browser/server.js (pinned source closure, receipts)",
        "subagent-fabric private gateway 127.0.0.1:45119/mcp (fabric_* tools)",
    )

    def patch_layer_fragment(self) -> str:
        """The operator-owned YAML fragment (no credentials) applied to the
        qualified profile's ``cordis.patch.yml``."""
        return (
            "# Narrow Executive-tools bridge — dsh-mcp-client entries\n"
            "# (loopback / pinned-stdio only; no credentials in this layer)\n"
            "- insert:\n"
            "    - id: mcp-subagent-fabric\n"
            "      name: \"@deepseek-ai/dsh-mcp-client\"\n"
            "      config:\n"
            "        serverName: subagent_fabric\n"
            "        transport: streamable-http\n"
            "        url: http://127.0.0.1:45119/mcp\n"
            "        toolCallTimeoutMs: 300000\n"
            "        reconnect:\n"
            "          enabled: true\n"
            "          initialDelayMs: 500\n"
            "          maxDelayMs: 30000\n"
            "          maxAttempts: 10\n"
        )


# --- The descriptor ----------------------------------------------------------

@dataclasses.dataclass(frozen=True)
class DshRuntimeDescriptor:
    """The ``dsh-acp`` runtime descriptor (runtime=dsh, NOT model=deepseek).

    Source-complete descriptor with probe-backed facts; the lane itself
    stays unimplemented in ``ADAPTER_DESCRIPTORS`` until the full T3→DSH
    composition and confinement profile are reviewed (naming the route
    selects nothing and launches nothing).
    """

    runtime_id: str = DSH_ACP_RUNTIME_ID
    runtime_kind: str = DSH_RUNTIME_KIND
    #: Explicit: this is a harness identity. ``model=deepseek`` selections
    #: elsewhere are different lanes.
    distinct_from_model: str = "deepseek"
    provider_config: DshAcpProviderConfig = dataclasses.field(
        default_factory=DshAcpProviderConfig)
    capabilities: Mapping[str, DshAcpCapability] = dataclasses.field(
        default_factory=lambda: dict(DSH_ACP_CAPABILITIES))
    descendant_policy: DshDescendantPolicy = None  # type: ignore[assignment]
    executive_tools_bridge: DshExecutiveToolsBridge = dataclasses.field(
        default_factory=DshExecutiveToolsBridge)
    #: A placement child on this lane never starts without the broker-issued
    #: ExecutionBinding.v1 (WO-13/WO-14/WO-16 discipline).
    binding_required: bool = True
    #: Provenance of every fact above.
    provenance: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.runtime_kind == self.distinct_from_model:
            raise ValueError("runtime kind must not collapse into a model identity")
        if not isinstance(self.descendant_policy, DshDescendantPolicy):
            raise ValueError("a runtime descriptor requires a descendant policy")

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "runtime_id": self.runtime_id,
            "runtime_kind": self.runtime_kind,
            "distinct_from_model": self.distinct_from_model,
            "binding_required": self.binding_required,
            "provider_config": {
                "executable": self.provider_config.executable,
                "argument_rows": list(self.provider_config.argument_rows),
                "shipped_profile_argument_rows": list(
                    self.provider_config.shipped_profile_argument_rows),
                "launch_argv": list(self.provider_config.launch_argv()),
            },
            "capabilities": {
                name: {"status": cap.status, "scope": cap.scope,
                       "evidence": list(cap.evidence)}
                for name, cap in self.capabilities.items()
            },
            "descendant_policy": {
                "policy": self.descendant_policy.policy,
                "envelope": (None if self.descendant_policy.envelope is None else {
                    "max_active_subagents":
                        self.descendant_policy.envelope.max_active_subagents,
                    "max_depth": self.descendant_policy.envelope.max_depth,
                    "host_scope": self.descendant_policy.envelope.host_scope,
                }),
                "evidence": list(self.descendant_policy.evidence),
            },
            "executive_tools_bridge": {
                "seam": self.executive_tools_bridge.seam,
                "why": self.executive_tools_bridge.why,
            },
            "provenance": list(self.provenance),
        }
        return payload

    def digest(self) -> str:
        return hashlib.sha256(
            json.dumps(self.to_dict(), sort_keys=True,
                       separators=(",", ":")).encode()).hexdigest()


def descendant_policy() -> DshDescendantPolicy:
    """The evidence-chosen descendant policy for the dsh-acp runtime.

    ``bounded_native_fanout`` — chosen because the child-spawn seam really
    enforces a fixed envelope and its children are in-process (no per-child
    placement surface exists to hook).
    """
    return DshDescendantPolicy(
        policy=BOUNDED_NATIVE_FANOUT,
        envelope=NativeFanoutEnvelope(
            max_active_subagents=8,
            max_depth=1,
        ),
        evidence=(
            "LIVE (mmx-acp, 2026-11-08): ACP session 21b294b3 called the "
            "native subagent tool, started in-process child "
            "fe1d0c8f-82d2-45f5-ba27-3e9c7770593a (persisted session dir on "
            "disk), listed it via list_agents(scope=children), and the ACP "
            "prompt settled only after the child completed "
            "(receipt dsh_acp_probe_receipt_profile_mmxacp.jsonl)",
            "SOURCE: @deepseek-ai/dsh-subagent contract — maxActiveSubagents "
            "(default 8) sampled before every new or cold-resumed activation, "
            "ACTIVATION_LIMIT_REACHED at capacity, process-local slots; "
            "maxDepth (default 1) enforced per delegation attempt",
            "SOURCE: the acp-app profile composes ONLY in-process backends "
            "(dsh-subagent-spawn-in-process / dsh-subagent-fork-in-process): "
            "children share the parent's process, agent factory, LLM and "
            "tools — they cannot take a separate host placement",
            "mmx-acp composed profile dump (sha256 "
            "145935ae427082c5ae8238dfc91ac0cd3e7b7c38300be0385b2588f5b9de84b2): "
            "subagent entry carries no override, so shipped defaults 8/1 apply",
            "fabric_per_child rejected: no native admission hook exists in "
            "the shipped composition — claiming it would be a configuration "
            "promise without a real enforcement mechanism (forbidden)",
        ),
    )


#: The one descriptor for the dsh-acp runtime lane.
DSH_ACP_RUNTIME = DshRuntimeDescriptor(
    descendant_policy=descendant_policy(),
    provenance=(
        "dsh 0.2.2-rc.1 (npm-global @deepseek-ai/dsh, "
        "~/.local/lib/node_modules/@deepseek-ai/dsh) on M2, 2026-11-08",
        "live ACP session receipts: "
        "~/.hermes/profiles/engineering/cache/scratch/dsh-acp-probe/"
        "dsh_acp_probe_receipt_profile_mmxacp.jsonl (mmx-acp, two-row shape) "
        "and dsh_acp_probe_receipt.jsonl (shipped acp profile, T3-doc shape); "
        "three-row refusal receipt: "
        "dsh_acp_probe_receipt_profile_mmxacp_acp.jsonl",
        "profile qualification: dsh --profile mmx-acp --from-default-profile "
        "acp (documented creation seam); zai route via the llm-pi-ai apiKeyEnv "
        "seam in the profile's cordis.patch.yml user layer (dsh-side credential "
        "custody; no credentials copied)",
    ),
)
