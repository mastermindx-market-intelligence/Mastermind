"""Pure source-only compiler for one missing OS gateway publication generation.

This module owns no effect and issues no permission. It converts two exact
before-images (the installed Executive MCP configuration and its launchd plist)
plus already-qualified publication DATA into the exact candidate bytes for the
three fixed publication targets:

- ``/Library/Application Support/MastermindExecutive/config/executive-mcp.json``
- ``/Library/LaunchDaemons/com.mastermind.executive.mcp.plist``
- ``/Library/Application Support/MastermindExecutive/config/os-commission-publication.json``

Laws kept here (see docs/runbooks/mastermind-os-public-launch.md):

- Pure DATA compiler: no filesystem, network, subprocess or environment access
  at import or compile time. Imports are inert; every reused validator is the
  real shipped one and none of them performs IO on this path.
- The original root owner keeps provenance, held global-inflight, descriptor
  CAS and every genuine authorized input; the separately authorized
  AUTONOMY_TRANSACTION owner extension is commissioned LATER through its own
  sole writer. Compiling values grants nothing and dict/dataclass/bool/hash
  identity is never treated as authenticated origin.
- Helper digests are joined by equality only. This module never reads the
  installed release source and never claims that a supplied digest
  authenticates bytes.
- ``expected_bundle_digest`` binds the owner's already-qualified bundle; it is
  not, by itself, asset authentication.
- The publication configuration before-image is NOT an input of
  :func:`compile_gateway_candidates`. The owning transaction must explicitly
  qualify and bind it before durable intent; no absence receipt is fabricated
  here, and postimage classification never authorizes replay or rollback.

Existing owners reused verbatim: ``executive_mcp_entry.validate_document`` /
``load_app_policies`` / ``build_additional_policies``, the installed-peer
closed gateway plist profile with its strict bounded parsers, the canonical
five-tool submit law for grant templates, and the private Studio account and
port laws.
"""
from __future__ import annotations

import copy
import dataclasses
import hashlib
import json
import plistlib
import re

from control_plane import executive_installed_peer as installed
from integrations.executive_mcp.web_ceo_v3 import WEB_CEO_V3_PROFILE
from integrations.mastermind_executive_app.gateway import (
    READ_SCOPE,
    SUBMIT_SCOPE,
    load_app_policies,
)
from ops.executive_os import os_commission_auth_entry
from ops.executive_os.executive_mcp_entry import (
    OS_EXECUTIVE_RESOURCE,
    build_additional_policies,
    validate_document,
)

SCHEMA = "mastermind.os_gateway_publication.v1"
POSTIMAGE_SCHEMA = "mastermind.os_gateway_postimage.v1"
OPERATION = "OS_GATEWAY_PUBLICATION"

MCP_CONFIG_PATH = installed._GATEWAY_CONFIG_PATH
MCP_PLIST_PATH = installed._LAUNCHD_ROLES["gateway"].plist_path
MCP_PLIST_ENTRY_ARGUMENT = "/ops/executive_os/executive_mcp_entry.py"
GATEWAY_PLIST_PROFILE = installed._EXPECTED_PLIST_PROFILES["gateway"]
COMMISSION_CONFIG_PATH = str(os_commission_auth_entry.CONFIG)
AUDIT_DIRECTORY = str(os_commission_auth_entry.ROOT / "audit/os-commission-publication")
COMMISSION_SCHEMA = "mastermind.os_commission_publication.v1"
COMMISSION_KEYS = frozenset({
    "schema", "release_sha", "studio_uid", "studio_account", "studio_port",
    "policy", "grants", "base_sha", "audit_directory",
    "auth_helper_sha256", "file_helper_sha256",
})

# Closed configuration budgets: the existing commission/publication JSON
# budget, and the installed-peer strict plist budget.
MAX_CONFIG_BYTES = 65_536
MAX_PLIST_BYTES = 262_144

# Grant law owned by the incumbent Studio commission preparer
# (integrations/studio_direct_mcp/commission-prepare.mjs) and the sealed auth
# helper; the template values are validated under the canonical five-tool law.
MIN_GRANTS = 1
MAX_GRANTS = 16
GRANT_KEYS = frozenset({"principal_scope", "template"})
GRANT_TEMPLATE_REQUIRED = ("workstream", "department", "priority", "execution_profile")
GRANT_TEMPLATE_OPTIONAL = ("allowed_write_paths", "validation", "attempt_limit")
HEX40 = re.compile(r"[0-9a-f]{40}")
HEX64 = re.compile(r"[0-9a-f]{64}")

# Explicit harmless validation-only submit arguments. They exercise the real
# canonical tool law for each template and are never persisted, published or
# reported as an objective.
TEMPLATE_VALIDATION_ARGUMENTS = {
    "operation_key": "os-gateway-grant-template-validation",
    "objective": ("Canonical grant template validation only; not a real "
                  "objective and never persisted or published."),
}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def require(ok, message):
    if not ok:
        raise ValueError(message)


def _strict_json(raw, code):
    """Bounded duplicate-free nonfinite-free JSON via the installed peer."""
    require(type(raw) is bytes and 0 < len(raw) <= MAX_CONFIG_BYTES,
            "gateway publication JSON byte budget")
    from control_plane.executive_peer_identity import PeerIdentityError
    try:
        return installed._load_strict_json(raw, code=code)
    except PeerIdentityError:
        raise ValueError("gateway publication JSON refused") from None


def _strict_plist(raw):
    """Bounded XML plist without network via the installed peer."""
    require(type(raw) is bytes and 0 < len(raw) <= MAX_PLIST_BYTES,
            "gateway publication plist byte budget")
    from control_plane.executive_peer_identity import PeerIdentityError
    try:
        return installed._load_strict_plist(raw, code="GATEWAY_PUBLICATION_PLIST_MALFORMED")
    except PeerIdentityError:
        raise ValueError("gateway publication plist refused") from None


def _sha(value, pattern, message):
    require(type(value) is str and pattern.fullmatch(value) is not None, message)
    return value


def _json_value(value, *, depth=0):
    """One closed JSON value: no float, no foreign container, no exotic int."""
    require(depth <= 24, "gateway publication nesting budget")
    if value is None or type(value) is str or type(value) is bool:
        return
    if type(value) is int:
        require(-2 ** 63 <= value < 2 ** 63, "gateway publication integer budget")
        return
    if type(value) is list:
        for item in value:
            _json_value(item, depth=depth + 1)
        return
    if type(value) is dict:
        for key, item in value.items():
            require(type(key) is str, "gateway publication object keys are strings")
            _json_value(item, depth=depth + 1)
        return
    raise ValueError("gateway publication exact JSON types required")


def _qualified_inputs(qualified_publication_inputs):
    require(type(qualified_publication_inputs) is dict
            and set(qualified_publication_inputs)
            == {"publication_document", "auth_helper_sha256", "file_helper_sha256"},
            "closed qualified publication inputs required")
    document = qualified_publication_inputs["publication_document"]
    require(type(document) is dict, "publication document must be an object")
    _json_value(document)
    for key in ("auth_helper_sha256", "file_helper_sha256"):
        _sha(qualified_publication_inputs[key], HEX64, "qualified helper digest required")
    return document


def _account_label(label):
    """Exact private Studio account-label law (private_service._validate_account_label)."""
    from integrations.studio_direct_mcp import private_service
    try:
        private_service._validate_account_label(label)
    except SystemExit:
        raise ValueError("publication Studio account label refused") from None
    return label


def _grants(document):
    grants = document["grants"]
    require(type(grants) is list and MIN_GRANTS <= len(grants) <= MAX_GRANTS,
            "publication grants count refused")
    from integrations.executive_mcp.schemas import GatewayError, validate_tool_arguments
    scopes, seen = {}, []
    for grant in grants:
        require(type(grant) is dict and set(grant) == GRANT_KEYS,
                "publication grant keys are exactly principal_scope and template")
        _sha(grant["principal_scope"], HEX64, "publication grant principal_scope refused")
        template = grant["template"]
        require(type(template) is dict, "publication grant template must be an object")
        names = set(template)
        require(all(name in names for name in GRANT_TEMPLATE_REQUIRED)
                and names <= set(GRANT_TEMPLATE_REQUIRED) | set(GRANT_TEMPLATE_OPTIONAL),
                "publication grant template fields differ")
        # Canonical five-tool law for the exact template form; the harmless
        # arguments above exist only for this validation and are discarded.
        try:
            validate_tool_arguments("submit_ceo_intent",
                                    {**TEMPLATE_VALIDATION_ARGUMENTS, **template})
        except GatewayError:
            raise ValueError("publication grant template refused") from None
        encoded = canonical(grant)
        require(encoded not in seen, "publication grants must be unique")
        seen.append(encoded)
        scopes.setdefault(grant["principal_scope"], []).append(grant)
    for group in scopes.values():
        profiles = [grant["template"]["execution_profile"] for grant in group]
        if len(group) == 1:
            require(profiles != ["native_research_only"],
                    "native publication requires the exact READ-only pair")
            continue
        require(profiles == ["research_only", "native_research_only"],
                "same-scope publication requires the exact READ-only pair")
        first, second = group
        position = next(i for i, grant in enumerate(grants) if grant is first)
        require(grants[position + 1] is second,
                "same-scope publication pair must be adjacent")
        left = {key: value for key, value in first["template"].items()
                if key != "execution_profile"}
        right = {key: value for key, value in second["template"].items()
                 if key != "execution_profile"}
        require(canonical(left) == canonical(right)
                and type(right.get("attempt_limit")) is int
                and right["attempt_limit"] == 1
                and right.get("allowed_write_paths", []) == []
                and right.get("validation", {}) == {},
                "same-scope publication pair must have identical READ-only fields")
    return tuple(grants)


def _publication_policy(document, additional):
    """Join the document policy to the existing policy-derived OS submit policy."""
    pairs = [pair for pair in additional
             if pair.read.resource == OS_EXECUTIVE_RESOURCE
             and pair.submit.resource == OS_EXECUTIVE_RESOURCE]
    require(len(pairs) == 1, "one derived OS Executive policy variant required")
    expected = dataclasses.asdict(pairs[0].submit)
    require(expected["resource"] == OS_EXECUTIVE_RESOURCE
            and expected["allowed_algorithms"] == ("RS256",)
            and tuple(expected["required_scopes"])
            == tuple(sorted((READ_SCOPE, SUBMIT_SCOPE))),
            "derived OS submit policy is the fixed publication audience")
    from integrations.business_mcp_auth.contracts import AuthError, load_resource_policy
    try:
        policy = load_resource_policy(document["policy"])
    except AuthError:
        raise ValueError("publication policy differs from the derived OS submit "
                         "policy") from None
    require(canonical(document["policy"]) == canonical(expected)
            and canonical(document["policy"]) == canonical(dataclasses.asdict(policy)),
            "publication policy differs from the derived OS submit policy")
    return policy


def _qualify_document(document, *, expected_release_sha):
    require(set(document) == COMMISSION_KEYS, "publication document fields differ")
    require(document["schema"] == COMMISSION_SCHEMA, "publication schema differs")
    require(document["release_sha"] == _sha(expected_release_sha, HEX40,
                                            "expected release SHA required"),
            "publication release join differs")
    _sha(document["base_sha"], HEX40, "publication base SHA required")
    uid = document["studio_uid"]
    require(type(uid) is int and not type(uid) is bool and uid > 0,
            "publication Studio uid refused")
    _account_label(document["studio_account"])
    port = document["studio_port"]
    require(type(port) is int and not type(port) is bool
            and 1024 <= port <= 65535 and port != 8443,
            "publication Studio port refused")
    require(document["audit_directory"] == AUDIT_DIRECTORY,
            "publication audit directory refused")
    for key in ("auth_helper_sha256", "file_helper_sha256"):
        _sha(document[key], HEX64, "publication helper digest required")
    _grants(document)


def _proposed_mcp(prior, document, *, expected_release_sha):
    proposed = dict(prior)
    changed = {"release_sha", "os_executive_transport", "os_executive_resource",
               "os_commission_port"}
    for key in changed - {"release_sha"}:
        proposed.pop(key, None)
    proposed["release_sha"] = expected_release_sha
    proposed["os_executive_transport"] = True
    proposed["os_executive_resource"] = OS_EXECUTIVE_RESOURCE
    proposed["os_commission_port"] = document["studio_port"]
    require(set(prior) | changed >= set(proposed) and set(prior) <= set(proposed),
            "proposed MCP configuration fields differ")
    for key, value in prior.items():
        if key not in changed:
            require(proposed[key] == value, "proposed MCP configuration changed "
                    "an unrelated installed field")
    require(proposed["os_executive_transport"] is True
            and proposed["os_executive_resource"] == OS_EXECUTIVE_RESOURCE,
            "proposed OS transport is the exact enabled audience")
    validate_document(proposed)
    return proposed


def _proposed_plist(prior_plist, *, prior_release, expected_release_sha):
    releases = []
    require(installed._profile_matches(GATEWAY_PLIST_PROFILE, prior_plist, releases),
            "prior MCP plist is not the closed installed gateway profile")
    require(len(releases) == 1 and releases[0] == prior_release,
            "prior MCP plist release join differs")
    release_root = installed._SERVICE_RELEASES + "/" + expected_release_sha
    proposed = copy.deepcopy(prior_plist)
    proposed["WorkingDirectory"] = release_root
    argv = list(proposed["ProgramArguments"])
    require(len(argv) == 6, "prior MCP plist argv shape differs")
    argv[3] = release_root + MCP_PLIST_ENTRY_ARGUMENT
    proposed["ProgramArguments"] = argv
    require(set(proposed) == set(prior_plist), "proposed MCP plist fields differ")
    for key, value in prior_plist.items():
        if key == "WorkingDirectory":
            continue
        if key != "ProgramArguments":
            require(proposed[key] == value, "proposed MCP plist changed an "
                    "unrelated installed field")
    prior_argv = prior_plist["ProgramArguments"]
    require(len(prior_argv) == len(argv)
            and all(proposed_arg == prior_arg for index, (proposed_arg, prior_arg)
                    in enumerate(zip(argv, prior_argv)) if index != 3),
            "proposed MCP plist argv differs beyond the release entry")
    require(proposed["WorkingDirectory"] == release_root
            and proposed["ProgramArguments"][3] == release_root + MCP_PLIST_ENTRY_ARGUMENT,
            "proposed MCP plist release substitution differs")
    require(installed._profile_matches(GATEWAY_PLIST_PROFILE, proposed,
                                       [expected_release_sha]),
            "proposed MCP plist is not the closed installed gateway profile")
    return proposed


def compile_gateway_candidates(prior_mcp_bytes, prior_plist_bytes, *,
                               expected_release_sha, expected_bundle_digest,
                               qualified_publication_inputs):
    """Compile the three fixed candidate artifacts as immutable DATA.

    Every join above must hold or this refuses. The returned candidate carries
    exact before-bytes, proposed bytes, their SHA-256 digests, the expected
    release and bundle digests and the single fixed operation identity. It is
    inert DATA: installing, restarting, granting or publishing remains with the
    existing owners. The publication configuration before-image is absent from
    these inputs on purpose: the owning transaction must explicitly qualify and
    bind it before durable intent, and no absence receipt is fabricated here.
    """
    _sha(expected_release_sha, HEX40, "expected release SHA required")
    _sha(expected_bundle_digest, HEX64, "expected bundle digest required")
    document = _qualified_inputs(qualified_publication_inputs)
    prior_mcp = _strict_json(prior_mcp_bytes, code="GATEWAY_PUBLICATION_MCP_MALFORMED")
    prior_plist = _strict_plist(prior_plist_bytes)
    require(type(prior_mcp.get("executive_mcp_profile")) is str
            and prior_mcp["executive_mcp_profile"] == WEB_CEO_V3_PROFILE,
            "prior MCP profile must already be web_ceo_v3; no implicit upgrade")
    validate_document(prior_mcp)
    from integrations.business_mcp_auth.contracts import AuthError
    try:
        policies = load_app_policies(prior_mcp["policies"])
    except AuthError:
        raise ValueError("installed MCP policy envelope refused") from None
    _qualify_document(document, expected_release_sha=expected_release_sha)
    # Equality-only helper joins: supplied qualified digests must match the
    # document exactly; neither side is read from or checked against bytes.
    for key in ("auth_helper_sha256", "file_helper_sha256"):
        require(qualified_publication_inputs[key] == document[key],
                "qualified helper digest join differs")

    proposed_mcp = _proposed_mcp(prior_mcp, document,
                                 expected_release_sha=expected_release_sha)
    require(canonical(proposed_mcp["policies"]) == canonical(prior_mcp["policies"]),
            "proposed MCP policies are unchanged")
    additional = build_additional_policies(proposed_mcp, policies)
    _publication_policy(document, additional)

    proposed_plist = _proposed_plist(prior_plist, prior_release=prior_mcp["release_sha"],
                                     expected_release_sha=expected_release_sha)
    proposed_mcp_bytes = canonical(proposed_mcp) + b"\n"
    proposed_publication_bytes = canonical(document) + b"\n"
    proposed_plist_bytes = plistlib.dumps(proposed_plist)
    require(json.loads(proposed_mcp_bytes) == proposed_mcp
            and json.loads(proposed_publication_bytes) == document
            and plistlib.loads(proposed_plist_bytes) == proposed_plist,
            "proposed artifact serialization round-trip differs")
    require(len(proposed_mcp_bytes) <= MAX_CONFIG_BYTES
            and len(proposed_publication_bytes) <= MAX_CONFIG_BYTES,
            "proposed artifact byte budget")
    artifacts = tuple(
        GatewayArtifact(path=path, kind=kind, content=raw, sha256=digest(raw),
                        byte_count=len(raw))
        for path, kind, raw in (
            (MCP_CONFIG_PATH, "executive-mcp-config", proposed_mcp_bytes),
            (MCP_PLIST_PATH, "executive-mcp-plist", proposed_plist_bytes),
            (COMMISSION_CONFIG_PATH, "os-commission-publication", proposed_publication_bytes),
        ))
    return GatewayCandidate(
        schema=SCHEMA, operation=OPERATION,
        expected_release_sha=expected_release_sha,
        expected_bundle_digest=expected_bundle_digest,
        before_mcp_bytes=prior_mcp_bytes, before_plist_bytes=prior_plist_bytes,
        before_mcp_sha256=digest(prior_mcp_bytes),
        before_plist_sha256=digest(prior_plist_bytes),
        artifacts=artifacts,
    )


@dataclasses.dataclass(frozen=True)
class GatewayArtifact:
    """One fixed-target candidate artifact: exact bytes plus their digest."""

    path: str
    kind: str
    content: bytes
    sha256: str
    byte_count: int

    def __post_init__(self):
        require(type(self.path) is str and type(self.kind) is str
                and type(self.content) is bytes and 0 < len(self.content),
                "gateway artifact fields differ")
        require(self.byte_count == len(self.content)
                and self.sha256 == digest(self.content),
                "gateway artifact digest differs")


@dataclasses.dataclass(frozen=True)
class GatewayCandidate:
    """Immutable compiled DATA for one OS gateway publication generation.

    ``publication_before_sha256`` is always ``None`` here: the publication
    configuration before-image is deliberately absent from the compile inputs.
    The owning transaction must explicitly qualify and bind it before any
    durable intent; this class never fabricates an absence receipt.
    """

    schema: str
    operation: str
    expected_release_sha: str
    expected_bundle_digest: str
    before_mcp_bytes: bytes
    before_plist_bytes: bytes
    before_mcp_sha256: str
    before_plist_sha256: str
    artifacts: tuple
    publication_before_sha256: None = None

    def __post_init__(self):
        require(self.schema == SCHEMA and self.operation == OPERATION,
                "gateway candidate identity differs")
        require(type(self.expected_release_sha) is str
                and HEX40.fullmatch(self.expected_release_sha) is not None
                and type(self.expected_bundle_digest) is str
                and HEX64.fullmatch(self.expected_bundle_digest) is not None,
                "gateway candidate expected digests differ")
        require(type(self.before_mcp_bytes) is bytes and type(self.before_plist_bytes) is bytes
                and 0 < len(self.before_mcp_bytes) <= MAX_CONFIG_BYTES
                and 0 < len(self.before_plist_bytes) <= MAX_PLIST_BYTES,
                "gateway candidate before-images differ")
        require(self.before_mcp_sha256 == digest(self.before_mcp_bytes)
                and self.before_plist_sha256 == digest(self.before_plist_bytes),
                "gateway candidate before digests differ")
        require(self.publication_before_sha256 is None,
                "no publication before-image exists at compile time")
        require(type(self.artifacts) is tuple
                and [artifact.path for artifact in self.artifacts]
                == [MCP_CONFIG_PATH, MCP_PLIST_PATH, COMMISSION_CONFIG_PATH],
                "gateway candidate holds exactly the three fixed targets")

    def artifact(self, path):
        for candidate in self.artifacts:
            if candidate.path == path:
                return candidate
        raise ValueError("unknown gateway publication target")

    def publication_document(self):
        """Fresh publication document parsed from the candidate bytes."""
        return json.loads(self.artifact(COMMISSION_CONFIG_PATH).content)

    def mcp_document(self):
        """Fresh proposed MCP configuration parsed from the candidate bytes."""
        return json.loads(self.artifact(MCP_CONFIG_PATH).content)

    def operation_manifest(self):
        """Closed gateway-only manifest DATA for the existing typed owner.

        No store, dispatcher or registry is created. The manifest names the
        fixed targets and their digests only; it authorizes nothing and the
        unbound publication before-image stays explicitly required.
        """
        return {
            "schema": SCHEMA,
            "operation": self.operation,
            "expected_release_sha": self.expected_release_sha,
            "expected_bundle_digest": self.expected_bundle_digest,
            "targets": {artifact.path: {"kind": artifact.kind,
                                        "sha256": artifact.sha256,
                                        "byte_count": artifact.byte_count}
                        for artifact in self.artifacts},
            "before_images": {"executive-mcp-config": self.before_mcp_sha256,
                              "executive-mcp-plist": self.before_plist_sha256},
            "publication_grant_beforeimage": "REQUIRED_UNBOUND",
            "authority": "DATA_ONLY_compiled_values_grant_nothing",
        }


def classify_postimages(candidate, observed, *, publication_before_bytes=None):
    """Pure postimage comparison for the three fixed targets.

    ``observed`` must map exactly the three fixed paths to the observed bytes
    (or ``None`` when the target is absent). ``publication_before_bytes`` is
    only ever the owning transaction's explicitly qualified and bound
    publication configuration before-image; the compiler never supplies one.
    The classification is DATA: it never authorizes replay, rollback or any
    recovery effect, and any mixed, foreign or unbound observation stays
    UNKNOWN for external reconciliation by the existing owner.
    """
    require(type(candidate) is GatewayCandidate, "gateway candidate required")
    require(publication_before_bytes is None
            or type(publication_before_bytes) is bytes,
            "publication before-image must be the owner's exact bytes")
    paths = (MCP_CONFIG_PATH, MCP_PLIST_PATH, COMMISSION_CONFIG_PATH)
    require(type(observed) is dict and set(observed) == set(paths),
            "postimage observations cover exactly the three fixed targets")
    require(all(value is None or type(value) is bytes for value in observed.values()),
            "postimage observations are exact bytes or explicit absence")
    before = {MCP_CONFIG_PATH: candidate.before_mcp_bytes,
              MCP_PLIST_PATH: candidate.before_plist_bytes,
              COMMISSION_CONFIG_PATH: publication_before_bytes}
    labels = {}
    for path in paths:
        raw = observed[path]
        proposed = candidate.artifact(path).content
        if raw == proposed:
            labels[path] = "PROPOSED"
        elif publication_before_bytes is None and path == COMMISSION_CONFIG_PATH:
            labels[path] = "UNBOUND"
        elif raw is None:
            labels[path] = "ABSENT"
        elif raw == before[path]:
            labels[path] = "ORIGINAL"
        else:
            labels[path] = "FOREIGN"
    if all(labels[path] == "PROPOSED" for path in paths):
        state, reason = "MATCHED", None
    elif (labels[MCP_CONFIG_PATH] == "ORIGINAL" and labels[MCP_PLIST_PATH] == "ORIGINAL"
            and labels[COMMISSION_CONFIG_PATH] == "ORIGINAL"):
        state, reason = "ORIGINAL", None
    else:
        state = "UNKNOWN"
        reason = ("publication_beforeimage_unbound"
                  if labels[COMMISSION_CONFIG_PATH] == "UNBOUND" else "mixed_or_foreign")
    return {
        "schema": POSTIMAGE_SCHEMA,
        "operation": candidate.operation,
        "state": state,
        "reason": reason,
        "targets": {path: labels[path] for path in paths},
        "replay_authorized": False,
        "rollback_authorized": False,
    }
