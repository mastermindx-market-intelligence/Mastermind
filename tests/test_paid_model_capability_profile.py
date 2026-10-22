"""Closed paid model-only sealed-input capability profile fence tests.

Covers the ``fabric.paid.glm.sealed-input.v1`` registry extension:

  (a) exact identity constants and the exact closed reviewed tuple on the
      default policy document, still V3, unarmed, under Executive OS
      lifecycle authority;
  (b) legacy preservation: every pre-existing profile keeps its exact frozen
      normalized profile digest and dataclass value, the old source document
      still loads to its frozen policy digest, and the legacy registry-level
      MCP/resource tables are unchanged;
  (c) the paid profile confers no capability at all: an empty required/ambient
      manifest, no Claude SDK projection, no Codex App Server projection or
      overrides -- no permission, token or authority is inferred;
  (d) adapter exclusivity: only ``canonical-paid-fabric`` maps
      ``glm-model-only``, the paid adapter maps no legacy surface, and the
      surface joins the sealed worker execution fence;
  (e) strict refusals: every profile field mutated off the closed tuple, plus
      mixed surface/realm/profile combinations, an alias profile, a renamed
      profile, and a V4-only key under the V3 document.

This module is registry policy only.  It never starts a process, transport or
provider admission, and never reads or writes anything outside ``tmp_path``.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from control_plane.executive_agent_capabilities import (
    CAPABILITY_POLICY_SCHEMA_V3,
    CapabilityPolicyError,
    ExecutionCapabilityRegistry,
    PAID_FABRIC_ADAPTER_ID,
    PAID_GLM_AUTH_REALM,
    PAID_GLM_EXECUTION_SURFACE,
    PAID_GLM_SEALED_PROFILE_ID,
    adapter_supports_execution_surface,
    is_sealed_worker_execution_surface,
)
from control_plane.operator_harness_contract import NativeHelperPolicy

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_POLICY_PATH = REPO_ROOT / "config" / "executive_agent_capabilities.json"

LEGACY_POLICY_DIGEST = "b4b281bfe934522f6ccb364657ccb25a9b9e47656943fcbb1d62197ff289fd95"
PAID_PROFILE_DIGEST = "ba1e883c749a1bd237b197141f9c4e83a206b70ea45cdee64ddbaf53f00739f7"
LEGACY_PROFILE_DIGESTS = {
    "fabric.attended.claude.bounded.v1": "351952f0608b7f2c3f5382d1c8028c20e3431a1f97d4f6a9271ecebe945493ba",
    "operator.appserver.interactive.company-mcp.v1": "19ea30bee5e609a70cae37c511cb519f8b6cbc535546aafa9b595729a5c59530",
    "operator.appserver.interactive.native-return.v1": "ef9460d90e76c9f3842f55bfd0625fddaf4764e0da9742f3993ebb347dbc1dd8",
    "operator.appserver.interactive.product-acceptance.v1": "80b3a3eaed8bc50475c3fa21aa45cb5043d3999a401d4df84f80782864e24b57",
    "operator.appserver.interactive.v1": "cd10fce1f53d01d1253e88fcf7850c0ab7928a2d9c7fc2340e3b8a1475fd324f",
    "operator.appserver.readonly.docs-mcp.native-helper.v1": "028fce73ff8c4cb8f8ada7b514e89b74fba64b92f29db3780004a360e0995d39",
    "operator.appserver.readonly.docs-mcp.v1": "13f077d50a2a5cecaa97ec29f5efdb32c8af9159374e16ef140f85556310544b",
    "operator.appserver.readonly.v1": "86d642f003c620a02ef9ffd3d1b49e2625d831e116995a5f9a32537ddf4a341c",
    "operator.browser.isolated.v1": "725fcb2372f72581e523a4c3db8ec3dd990da3323df913fb68c4d840dcf48779",
    "operator.browser.local-review.v1": "f0430198b3ba00e53b70583e547d12d3e471dd499b69ef4a495fc14ca2826199",
    "sealed.worker.claude.readonly.no-extensions.v1": "421b642a6a4ae978efffbe311023dd3495adc54cbc00e86bf5f6254be3dd5555",
    "sealed.worker.claude.write.no-extensions.v1": "74c4b0ebcb996b89a8607b71c3ed842fd87cd026d8b5fddd4947cbad0cf529a6",
    "sealed.worker.readonly.no-extensions.v1": "17893a6eff34b4cd7cbd764c396d5f10f66b83c2677a21bb97d42e2a4b023a03",
    "sealed.worker.write.no-extensions.v1": "bf4cf0fdd6b4a63def2b9410c0831cde1adfd0877689532c52c608d18477daa0",
}

LEGACY_ADAPTERS = ("codex-cli", "claude-code", "attended-fabric")
LEGACY_SURFACES = (
    "codex-exec",
    "codex-app-server",
    "claude-code",
    "claude-agent-sdk",
)

# The exact reviewed paid ceiling.  Any drift in any field refuses.
_PAID_HELPER_GRANT = {
    "mechanism": "codex-multi-agent-v2-inherit-parent",
    "default_model": "gpt-5.6-sol",
    "default_reasoning_effort": "xhigh",
    "inherit_parent_capabilities": True,
    "hide_spawn_agent_metadata": True,
    "max_concurrent_helpers": 1,
    "max_depth": 1,
    "max_runtime_seconds": 60,
}

_PAID_FIELD_MUTATIONS = (
    ("enabled", False),
    ("execution_surface", "codex-exec"),
    ("execution_surface", "codex-app-server"),
    ("execution_surface", "claude-code"),
    ("execution_surface", "claude-agent-sdk"),
    ("auth_realm", "dedicated-worker-account"),
    ("sandbox_policy", "workspace-write"),
    ("approval_policy", "on-request"),
    ("network_policy", "loopback-browser-only"),
    ("write_capable", True),
    ("native_helper_policy", "PARENT_READ_ONLY_CEILING"),
    ("native_helper_policy", "REQUIRES_SUBAGENT_CAPABILITY_CEILING"),
    ("native_helper", _PAID_HELPER_GRANT),
    ("skills", ["some-skill"]),
    ("mcp_servers", ["openai-developer-docs-v1"]),
    ("resources", ["worker-browser-b1-local"]),
    ("plugins", ["some-plugin"]),
    ("forbidden", ["some-capability"]),
    ("skill_capabilities", []),
)


def _raw_policy() -> dict:
    return json.loads(DEFAULT_POLICY_PATH.read_text(encoding="utf-8"))


def _write(tmp_path: Path, value: dict) -> Path:
    path = tmp_path / "capabilities-case.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def _refuse(tmp_path: Path, value: dict) -> None:
    with pytest.raises(CapabilityPolicyError):
        ExecutionCapabilityRegistry.load(_write(tmp_path, value))


@pytest.fixture(scope="module")
def legacy_registry(tmp_path_factory) -> ExecutionCapabilityRegistry:
    """The exact pre-extension source document, loaded through the current module."""

    path = tmp_path_factory.mktemp("legacy-source") / "old_capabilities.json"
    path.write_text(OLD_SOURCE, encoding="utf-8")
    return ExecutionCapabilityRegistry.load(path)


@pytest.fixture(scope="module")
def current_doc() -> dict:
    return _raw_policy()


@pytest.fixture(scope="module")
def current_registry() -> ExecutionCapabilityRegistry:
    return ExecutionCapabilityRegistry.load(DEFAULT_POLICY_PATH)


# ---------------------------------------------------------------------------
# (a) exact identity and the closed reviewed tuple
# ---------------------------------------------------------------------------


def test_exact_paid_identity_constants():
    assert PAID_GLM_SEALED_PROFILE_ID == "fabric.paid.glm.sealed-input.v1"
    assert PAID_GLM_EXECUTION_SURFACE == "glm-model-only"
    assert PAID_GLM_AUTH_REALM == "paid-lease-bound-account"
    assert PAID_FABRIC_ADAPTER_ID == "canonical-paid-fabric"


def test_default_policy_stays_v3_unarmed_with_unchanged_legacy_fields(current_registry):
    assert current_registry.schema_version == CAPABILITY_POLICY_SCHEMA_V3
    assert current_registry.policy_version == "2026-10-14.attended-qualification"
    assert current_registry.lifecycle_authority == "executive_os"
    assert current_registry.production_armed is False
    assert current_registry.capability_packages == {}
    assert set(current_registry.profiles) == (
        set(LEGACY_PROFILE_DIGESTS) | {PAID_GLM_SEALED_PROFILE_ID}
    )


def test_paid_profile_resolves_to_the_exact_closed_tuple(current_registry):
    profile = current_registry.resolve(PAID_GLM_SEALED_PROFILE_ID)
    assert profile.profile_id == PAID_GLM_SEALED_PROFILE_ID
    assert profile.enabled is True
    assert profile.execution_surface == PAID_GLM_EXECUTION_SURFACE
    assert profile.auth_realm == PAID_GLM_AUTH_REALM
    assert profile.sandbox_policy == "read-only"
    assert profile.approval_policy == "never"
    assert profile.network_policy == "disabled"
    assert profile.write_capable is False
    assert profile.native_helper_policy is NativeHelperPolicy.DISABLED
    assert profile.native_helper is None
    assert profile.skills == ()
    assert profile.skill_grants == ()
    assert profile.mcp_server_grants == ()
    assert profile.mcp_servers == ()
    assert profile.resource_grants == ()
    assert profile.plugins == ()
    assert profile.forbidden == ()
    assert profile.required_capability_names == ()
    assert profile.profile_digest == PAID_PROFILE_DIGEST


def test_paid_profile_confers_no_capability_or_projection(current_registry):
    profile = current_registry.resolve(PAID_GLM_SEALED_PROFILE_ID)
    manifest = profile.capability_manifest(harness_binary_digest="a" * 64)
    assert manifest.required == ()
    assert manifest.allowed_ambient == ()
    assert manifest.forbidden == ()
    assert manifest.unclassified_policy == "fail_closed_on_write"
    # The model-only surface is not a Codex App Server profile and not a
    # Claude operator profile: neither launch projection may be produced.
    with pytest.raises(CapabilityPolicyError):
        profile.app_server_config_overrides()
    with pytest.raises(CapabilityPolicyError):
        profile.claude_sdk_config_projection()
    # The generic closed config projection carries no server, helper, plugin,
    # skill or writable-sandbox field.
    assert profile.app_server_config_projection() == {
        "agents": {"enabled": False},
        "features": {
            "apps": False,
            "auth_elicitation": False,
            "enable_mcp_apps": False,
            "mcp_2026_07_28": False,
            "multi_agent": False,
            "multi_agent_v2": False,
            "plugins": False,
            "remote_plugin": False,
            "tool_call_mcp_elicitation": False,
        },
        "mcp_servers": {},
        "plugins": {},
        "skills": {"config": None},
    }


# ---------------------------------------------------------------------------
# (b) legacy preservation against frozen values
# ---------------------------------------------------------------------------


def test_legacy_profile_digests_are_preserved_exactly(current_registry):
    for profile_id, expected in LEGACY_PROFILE_DIGESTS.items():
        profile = current_registry.profiles[profile_id]
        assert profile.profile_digest == expected, profile_id


def test_old_source_document_still_loads_to_its_frozen_policy(legacy_registry):
    assert legacy_registry.policy_digest == LEGACY_POLICY_DIGEST
    assert legacy_registry.schema_version == CAPABILITY_POLICY_SCHEMA_V3
    assert legacy_registry.production_armed is False
    assert set(legacy_registry.profiles) == set(LEGACY_PROFILE_DIGESTS)
    with pytest.raises(CapabilityPolicyError):
        legacy_registry.resolve(PAID_GLM_SEALED_PROFILE_ID)


def test_legacy_profile_values_are_identical_across_extension(
    legacy_registry, current_registry
):
    for profile_id, legacy in legacy_registry.profiles.items():
        assert current_registry.profiles[profile_id] == legacy, profile_id
    assert current_registry.mcp_servers == legacy_registry.mcp_servers
    assert current_registry.resources == legacy_registry.resources
    assert current_registry.policy_version == legacy_registry.policy_version
    assert current_registry.lifecycle_authority == legacy_registry.lifecycle_authority
    assert current_registry.production_armed == legacy_registry.production_armed


def test_policy_digest_covers_the_paid_profile(legacy_registry, current_registry):
    assert current_registry.policy_digest != LEGACY_POLICY_DIGEST
    assert current_registry.resolve(PAID_GLM_SEALED_PROFILE_ID).enabled is True


def test_legacy_profiles_keep_their_resolve_behavior(current_registry):
    profile = current_registry.resolve("operator.appserver.readonly.v1")
    assert profile.execution_surface == "codex-app-server"
    with pytest.raises(CapabilityPolicyError, match="disabled"):
        current_registry.resolve("operator.appserver.interactive.company-mcp.v1")
    with pytest.raises(CapabilityPolicyError, match="unknown execution capability profile"):
        current_registry.resolve("fabric.paid.glm.sealed-input.v2")


# ---------------------------------------------------------------------------
# (c)/(d) sealed-worker fence and adapter exclusivity
# ---------------------------------------------------------------------------


def test_paid_surface_is_a_sealed_worker_surface():
    assert is_sealed_worker_execution_surface(PAID_GLM_EXECUTION_SURFACE) is True
    assert is_sealed_worker_execution_surface("GLM-Model-Only") is True
    assert is_sealed_worker_execution_surface("codex-exec") is True
    assert is_sealed_worker_execution_surface("codex-app-server") is False


@pytest.mark.parametrize("adapter_id", (*LEGACY_ADAPTERS, "unknown-adapter", "claude"))
def test_only_the_canonical_paid_adapter_maps_the_paid_surface(adapter_id):
    assert adapter_supports_execution_surface(adapter_id, PAID_GLM_EXECUTION_SURFACE) is False


@pytest.mark.parametrize("surface", LEGACY_SURFACES)
def test_paid_adapter_maps_no_legacy_surface(surface):
    assert adapter_supports_execution_surface(PAID_FABRIC_ADAPTER_ID, surface) is False


def test_canonical_paid_adapter_maps_exactly_the_paid_surface():
    assert adapter_supports_execution_surface(
        PAID_FABRIC_ADAPTER_ID, PAID_GLM_EXECUTION_SURFACE
    ) is True


# ---------------------------------------------------------------------------
# (e) strict refusals
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("field", "value"), _PAID_FIELD_MUTATIONS)
def test_paid_profile_field_mutations_refuse(tmp_path, current_doc, field, value):
    doc = copy.deepcopy(current_doc)
    doc["profiles"][PAID_GLM_SEALED_PROFILE_ID][field] = value
    _refuse(tmp_path, doc)


def test_paid_surface_rejected_on_legacy_profile(tmp_path, current_doc):
    doc = copy.deepcopy(current_doc)
    doc["profiles"]["operator.appserver.readonly.v1"][
        "execution_surface"
    ] = PAID_GLM_EXECUTION_SURFACE
    _refuse(tmp_path, doc)


def test_paid_realm_rejected_on_legacy_profile(tmp_path, current_doc):
    doc = copy.deepcopy(current_doc)
    doc["profiles"]["operator.appserver.readonly.v1"][
        "auth_realm"
    ] = PAID_GLM_AUTH_REALM
    _refuse(tmp_path, doc)


def test_renamed_paid_profile_refuses(tmp_path, current_doc):
    doc = copy.deepcopy(current_doc)
    profile = doc["profiles"].pop(PAID_GLM_SEALED_PROFILE_ID)
    doc["profiles"]["fabric.paid.glm.sealed-input.v2"] = profile
    _refuse(tmp_path, doc)


def test_alias_profile_with_the_exact_paid_tuple_refuses(tmp_path, current_doc):
    doc = copy.deepcopy(current_doc)
    doc["profiles"]["fabric.paid.glm.alias.v1"] = copy.deepcopy(
        doc["profiles"][PAID_GLM_SEALED_PROFILE_ID]
    )
    _refuse(tmp_path, doc)


def test_paid_profile_rejects_v4_only_key_under_v3_document(tmp_path, current_doc):
    doc = copy.deepcopy(current_doc)
    doc["profiles"][PAID_GLM_SEALED_PROFILE_ID]["skill_capabilities"] = []
    _refuse(tmp_path, doc)


def test_legacy_document_with_paid_profile_absent_stays_valid(tmp_path, legacy_registry):
    # The old source document is unchanged legacy policy, not a refusal case:
    # the paid profile is simply absent there.
    assert PAID_GLM_SEALED_PROFILE_ID not in legacy_registry.profiles


OLD_SOURCE = r"""{
  "schema_version": "mastermind.executive_agent_capabilities/v3",
  "policy_version": "2026-10-14.attended-qualification",
  "lifecycle_authority": "executive_os",
  "production_armed": false,
  "mcp_servers": {
    "company-consultation-mcp-v1": {
      "config_name": "company-consultation-v1",
      "transport": "stdio",
      "command": "/usr/bin/python3",
      "args": [
        "-I",
        "-S",
        "-B",
        "-c",
        "import hashlib,json,os,pathlib,re,stat,subprocess\nR=pathlib.Path(\"/Library/Application Support/MastermindExecutive\")\nC=R/\"config/company-consultation-edge.json\"\nE={\"PATH\":\"/usr/bin:/bin\",\"LANG\":\"en_US.UTF-8\"}\ndef sealed(p,d=False):\n for n in (p,*p.parents):\n  i=n.lstat(); D=d or n!=p\n  if i.st_uid!=0 or ((n==p or n==R or R in n.parents) and i.st_gid!=0) or i.st_mode&0o022 or stat.S_ISLNK(i.st_mode) or not (stat.S_ISDIR(i.st_mode) if D else stat.S_ISREG(i.st_mode)) or (not D and i.st_nlink!=1): raise ValueError()\n  if b\"+\" in subprocess.check_output([\"/usr/bin/stat\",\"-f\",\"%Sp\",str(n)],env=E): raise ValueError()\ntry:\n sealed(C)\n if stat.S_IMODE(C.stat().st_mode)!=0o444: raise ValueError()\n v=json.loads(C.read_bytes()); S=v[\"release_sha\"]\n if set(v)!={\"schema\",\"release_sha\",\"control_uid\",\"worker_uid\",\"entry_sha256\",\"receipt_sha256\"} or v[\"schema\"]!=\"mastermind.company_mcp_edge/v1\" or type(S)!=str or re.fullmatch(\"[0-9a-f]{40}\",S) is None or type(v[\"worker_uid\"])!=int or v[\"worker_uid\"]<=0 or os.geteuid()!=v[\"worker_uid\"]: raise ValueError()\n P=R/\"releases\"/S/\"ops/executive_os/company_mcp_edge.py\"; sealed(P)\n if hashlib.sha256(P.read_bytes()).hexdigest()!=v[\"entry_sha256\"]: raise ValueError()\n B=pathlib.Path(\"/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12\"); sealed(B)\n os.execve(B,[str(B),\"-I\",\"-S\",\"-B\",str(P),\"stdio\"],E)\nexcept (KeyError,OSError,TypeError,ValueError):\n raise SystemExit(\"Company edge bootstrap refused\")\n"
      ],
      "required": true,
      "auth_status": "unsupported",
      "server_identity": "mastermind-company-consultation-mcp",
      "server_version": "1.0.0",
      "enabled_tools": [
        "company.peers",
        "company.consult",
        "company.reply",
        "company.consultation"
      ],
      "default_tools_approval_mode": "approve",
      "tool_schema_digest": "f9463e714240c5ac347bb029788b88d5556ad9d77c69eabcec1b7038e210a722"
    },
    "openai-developer-docs-v1": {
      "config_name": "openaiDeveloperDocs",
      "transport": "streamable-http",
      "url": "https://developers.openai.com/mcp",
      "required": true,
      "auth_status": "unsupported",
      "server_identity": "openai-docs-mcp",
      "server_version": "1.0.0",
      "enabled_tools": [
        "fetch_openai_doc",
        "search_openai_docs"
      ],
      "default_tools_approval_mode": "approve",
      "tool_schema_digest": "9c6e56942336e507f7fb8e3cb781288c40028b2284c2b2d629e262521d66f8e7"
    },
    "playwright-worker-browser-b1": {
      "config_name": "playwrightWorkerBrowser",
      "transport": "stdio",
      "command": "/usr/bin/python3",
      "args": [
        "-I",
        "-S",
        "-c",
        "import hashlib,json,os,stat\nK=(\"MASTERMIND_BROWSER_ARTIFACT_DIR\",\"MASTERMIND_BROWSER_FIXTURE_A_URL\",\"MASTERMIND_BROWSER_FIXTURE_B_URL\",\"MASTERMIND_BROWSER_FIXTURE_NONCE\",\"MASTERMIND_BROWSER_ORIGIN\",\"MASTERMIND_BROWSER_PROXY_URL\",\"MASTERMIND_BROWSER_RUNTIME_MANIFEST_PATH\",\"MASTERMIND_BROWSER_RUNTIME_MANIFEST_SHA256\",\"MASTERMIND_BROWSER_RUNTIME_ROOT\",\"MASTERMIND_BROWSER_WORKSPACE_PATH\",\"PLAYWRIGHT_BROWSERS_PATH\")\nF=\"MASTERMIND_BROWSER_RUNTIME_CONTAINER_FD\"\nN=\"worker-browser-b1-install-manifest.json\"\nd=-1; D=-1\ntry:\n e={k:os.environ[k] for k in K}\n r=e[\"MASTERMIND_BROWSER_RUNTIME_ROOT\"]\n m=e[\"MASTERMIND_BROWSER_RUNTIME_MANIFEST_PATH\"]\n if not os.path.isabs(r) or os.path.basename(r)!=\"runtime\" or m!=os.path.join(r,N): raise ValueError()\n c=os.path.dirname(r)\n q=getattr(os,\"O_NOFOLLOW\",0); z=getattr(os,\"O_DIRECTORY\",0)\n if not q or not z: raise OSError()\n d=os.open(c,os.O_RDONLY|q|z); i=os.fstat(d)\n x=os.open(\"runtime/\"+N,os.O_RDONLY|q,dir_fd=d)\n try:\n  a=os.fstat(x)\n  if not stat.S_ISREG(a.st_mode) or a.st_nlink!=1 or a.st_uid!=os.geteuid() or stat.S_IMODE(a.st_mode)!=0o400 or not 0<a.st_size<=4194304: raise OSError()\n  b=b\"\"\n  while len(b)<=4194304:\n   h=os.read(x,65536)\n   if not h: break\n   b+=h\n  j=os.fstat(x)\n finally: os.close(x)\n if len(b)>4194304 or (a.st_dev,a.st_ino,a.st_size,a.st_mtime_ns)!=(j.st_dev,j.st_ino,j.st_size,j.st_mtime_ns) or hashlib.sha256(b).hexdigest()!=e[\"MASTERMIND_BROWSER_RUNTIME_MANIFEST_SHA256\"]: raise ValueError()\n v=json.loads(b.decode(\"utf-8\")); w=v[\"runtime_container\"]\n if b!=json.dumps(v,sort_keys=True,separators=(\",\",\":\"),ensure_ascii=False).encode()+b\"\\n\" or set(w)!={\"device\",\"gid\",\"inode\",\"mode\",\"uid\"} or any(type(w[k]) is not int for k in w) or w!={\"device\":i.st_dev,\"gid\":i.st_gid,\"inode\":i.st_ino,\"mode\":stat.S_IMODE(i.st_mode),\"uid\":i.st_uid} or i.st_uid!=os.geteuid() or stat.S_IMODE(i.st_mode)!=0o500: raise ValueError()\n D=os.dup(d)\n for C in (\"runtime\",\"bin\"):\n  Y=os.open(C,os.O_RDONLY|q|z,dir_fd=D); os.close(D); D=Y; U=os.fstat(D)\n  if not stat.S_ISDIR(U.st_mode) or U.st_uid!=os.geteuid() or stat.S_IMODE(U.st_mode)!=0o500: raise OSError()\n l=v[\"launcher\"]; y=os.open(\"worker-browser-b1-launcher\",os.O_RDONLY|q,dir_fd=D)\n try:\n  s=os.fstat(y); g=hashlib.sha256(); n=0\n  while n<=4194304:\n   h=os.read(y,65536)\n   if not h: break\n   n+=len(h); g.update(h)\n  t=os.fstat(y); k=os.stat(\"worker-browser-b1-launcher\",dir_fd=D,follow_symlinks=False)\n finally: os.close(y)\n P=lambda o:(o.st_dev,o.st_ino,o.st_mode,o.st_nlink,o.st_uid,o.st_gid,o.st_size,o.st_mtime_ns,o.st_ctime_ns)\n if set(l)!={\"gid\",\"mode\",\"path\",\"sha256\",\"uid\"} or l[\"path\"]!=os.path.join(r,\"bin\",\"worker-browser-b1-launcher\") or not stat.S_ISREG(s.st_mode) or s.st_nlink!=1 or s.st_uid!=os.geteuid() or stat.S_IMODE(s.st_mode)!=0o500 or n!=s.st_size or n>4194304 or P(s)!=P(t) or P(s)!=P(k) or l!={\"gid\":s.st_gid,\"mode\":0o500,\"path\":l[\"path\"],\"sha256\":g.hexdigest(),\"uid\":s.st_uid}: raise ValueError()\n os.close(D); D=-1\n os.set_inheritable(d,True); e[F]=str(d); os.fchdir(d)\n os.execve(\"runtime/bin/worker-browser-b1-launcher\",[\"runtime/bin/worker-browser-b1-launcher\"],e)\nexcept (KeyError,OSError,TypeError,UnicodeError,ValueError):\n if D>=0:\n  try: os.close(D)\n  except OSError: pass\n if d>=0:\n  try: os.close(d)\n  except OSError: pass\n raise SystemExit(\"runtime container bootstrap refused\")\n"
      ],
      "required": true,
      "auth_status": "unsupported",
      "server_identity": "playwright",
      "server_version": "1.63.0-alpha-2026-08-05",
      "enabled_tools": [
        "browser_click",
        "browser_close",
        "browser_console_messages",
        "browser_fill_form",
        "browser_hover",
        "browser_navigate",
        "browser_network_requests",
        "browser_resize",
        "browser_snapshot",
        "browser_tabs",
        "browser_take_screenshot",
        "browser_wait_for"
      ],
      "default_tools_approval_mode": "approve",
      "tool_schema_digest": "859063beb705b4ed15b0defc2c42533d6bce1a3f18bf02c38f28f2422598fc0b"
    },
    "native-return-mcp-v1": {
      "config_name": "mastermind-native-return",
      "transport": "stdio",
      "command": "/usr/bin/python3",
      "args": [
        "-I",
        "-S",
        "-B",
        "-c",
        "import hashlib,json,os,pathlib,re,stat,subprocess\nR=pathlib.Path(\"/Library/Application Support/MastermindExecutive\")\nC=R/\"config/company-consultation-edge.json\"\nE={\"PATH\":\"/usr/bin:/bin\",\"LANG\":\"en_US.UTF-8\"}\ndef sealed(p,d=False):\n for n in (p,*p.parents):\n  i=n.lstat(); D=d or n!=p\n  if i.st_uid!=0 or ((n==p or n==R or R in n.parents) and i.st_gid!=0) or i.st_mode&0o022 or stat.S_ISLNK(i.st_mode) or not (stat.S_ISDIR(i.st_mode) if D else stat.S_ISREG(i.st_mode)) or (not D and i.st_nlink!=1): raise ValueError()\n  if b\"+\" in subprocess.check_output([\"/usr/bin/stat\",\"-f\",\"%Sp\",str(n)],env=E): raise ValueError()\ntry:\n sealed(C)\n if stat.S_IMODE(C.stat().st_mode)!=0o444: raise ValueError()\n v=json.loads(C.read_bytes()); S=v[\"release_sha\"]\n if set(v)!={\"schema\",\"release_sha\",\"control_uid\",\"worker_uid\",\"entry_sha256\",\"receipt_sha256\"} or v[\"schema\"]!=\"mastermind.company_mcp_edge/v1\" or type(S)!=str or re.fullmatch(\"[0-9a-f]{40}\",S) is None or type(v[\"worker_uid\"])!=int or v[\"worker_uid\"]<=0 or os.geteuid()!=v[\"worker_uid\"]: raise ValueError()\n P=R/\"releases\"/S/\"ops/executive_os/company_mcp_edge.py\"; sealed(P)\n if hashlib.sha256(P.read_bytes()).hexdigest()!=v[\"entry_sha256\"]: raise ValueError()\n B=pathlib.Path(\"/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12\"); sealed(B)\n os.execve(B,[str(B),\"-I\",\"-S\",\"-B\",str(P),\"native-stdio\"],E)\nexcept (KeyError,OSError,TypeError,ValueError):\n raise SystemExit(\"Company edge bootstrap refused\")\n"
      ],
      "required": true,
      "auth_status": "unsupported",
      "server_identity": "mastermind-native-return-mcp",
      "server_version": "1.0.0",
      "enabled_tools": [
        "native.reply"
      ],
      "default_tools_approval_mode": "approve",
      "tool_schema_digest": "b2ed6841f5693bd3f2fcd91b036ba1bae529ea9a8472e524b61648c1ced8fb40"
    },
    "product-acceptance-mcp-v1": {
      "config_name": "mastermind-product-acceptance",
      "transport": "stdio",
      "command": "/usr/bin/python3",
      "args": [
        "-I",
        "-S",
        "-B",
        "-c",
        "import hashlib,json,os,pathlib,re,stat,subprocess\nR=pathlib.Path(\"/Library/Application Support/MastermindExecutive\")\nC=R/\"config/company-consultation-edge.json\"\nE={\"PATH\":\"/usr/bin:/bin\",\"LANG\":\"en_US.UTF-8\"}\ndef sealed(p,d=False):\n for n in (p,*p.parents):\n  i=n.lstat(); D=d or n!=p\n  if i.st_uid!=0 or ((n==p or n==R or R in n.parents) and i.st_gid!=0) or i.st_mode&0o022 or stat.S_ISLNK(i.st_mode) or not (stat.S_ISDIR(i.st_mode) if D else stat.S_ISREG(i.st_mode)) or (not D and i.st_nlink!=1): raise ValueError()\n  if b\"+\" in subprocess.check_output([\"/usr/bin/stat\",\"-f\",\"%Sp\",str(n)],env=E): raise ValueError()\ntry:\n sealed(C)\n if stat.S_IMODE(C.stat().st_mode)!=0o444: raise ValueError()\n v=json.loads(C.read_bytes()); S=v[\"release_sha\"]\n if set(v)!={\"schema\",\"release_sha\",\"control_uid\",\"worker_uid\",\"entry_sha256\",\"receipt_sha256\"} or v[\"schema\"]!=\"mastermind.company_mcp_edge/v1\" or type(S)!=str or re.fullmatch(\"[0-9a-f]{40}\",S) is None or type(v[\"worker_uid\"])!=int or v[\"worker_uid\"]<=0 or os.geteuid()!=v[\"worker_uid\"]: raise ValueError()\n P=R/\"releases\"/S/\"ops/executive_os/company_mcp_edge.py\"; sealed(P)\n if hashlib.sha256(P.read_bytes()).hexdigest()!=v[\"entry_sha256\"]: raise ValueError()\n B=pathlib.Path(\"/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12\"); sealed(B)\n os.execve(B,[str(B),\"-I\",\"-S\",\"-B\",str(P),\"acceptance-stdio\"],E)\nexcept (KeyError,OSError,TypeError,ValueError):\n raise SystemExit(\"Company edge bootstrap refused\")\n"
      ],
      "required": true,
      "auth_status": "unsupported",
      "server_identity": "mastermind-product-acceptance-mcp",
      "server_version": "1.0.0",
      "enabled_tools": [
        "request_decision"
      ],
      "default_tools_approval_mode": "approve",
      "tool_schema_digest": "a8a86ebfc59820efafe0810e08f3897583ab104817596c2d4e94f8f80c93e84d"
    }
  },
  "resources": {
    "worker-browser-b1-local": {
      "kind": "browser-devserver",
      "manifest_path": "config/worker_browser_b1_control_room_devserver.json",
      "manifest_digest": "de100f6c8cfbf1a77fb1c2e4c8a17193c4a51eb78d8eaf59fbed942e7d2e9e71",
      "runtime_root": "/Volumes/Mastermind/worker-browser-b1/runtime",
      "runtime_manifest_path": "/Volumes/Mastermind/worker-browser-b1/runtime/worker-browser-b1-install-manifest.json",
      "runtime_manifest_digest": "c4b15f3ba4d5c20e869b63af86109ed57d2da929d525d1d8a0a2c65625209e9f",
      "artifact_root": "/Volumes/Mastermind/worker-browser-b1/artifacts",
      "browser": "chromium",
      "browser_revision": "1237"
    },
    "worker-browser-isolated": {
      "kind": "browser-fabric-pending",
      "mode": "isolated",
      "transport": "stdio",
      "admission": "required"
    }
  },
  "plugins": {},
  "profiles": {
    "operator.appserver.interactive.company-mcp.v1": {
      "enabled": false,
      "execution_surface": "codex-app-server",
      "auth_realm": "dedicated-worker-account",
      "sandbox_policy": "read-only",
      "approval_policy": "never",
      "network_policy": "disabled",
      "write_capable": false,
      "native_helper_policy": "disabled",
      "native_helper": null,
      "skills": [],
      "mcp_servers": [
        "company-consultation-mcp-v1"
      ],
      "resources": [],
      "plugins": [],
      "forbidden": []
    },
    "operator.appserver.readonly.v1": {
      "enabled": true,
      "execution_surface": "codex-app-server",
      "auth_realm": "dedicated-worker-account",
      "sandbox_policy": "read-only",
      "approval_policy": "never",
      "network_policy": "disabled",
      "write_capable": false,
      "native_helper_policy": "disabled",
      "native_helper": null,
      "skills": [],
      "mcp_servers": [],
      "resources": [],
      "plugins": [],
      "forbidden": []
    },
    "operator.appserver.readonly.docs-mcp.v1": {
      "enabled": true,
      "execution_surface": "codex-app-server",
      "auth_realm": "dedicated-worker-account",
      "sandbox_policy": "read-only",
      "approval_policy": "never",
      "network_policy": "disabled",
      "write_capable": false,
      "native_helper_policy": "disabled",
      "native_helper": null,
      "skills": [],
      "mcp_servers": [
        "openai-developer-docs-v1"
      ],
      "resources": [],
      "plugins": [],
      "forbidden": []
    },
    "operator.appserver.readonly.docs-mcp.native-helper.v1": {
      "enabled": true,
      "execution_surface": "codex-app-server",
      "auth_realm": "dedicated-worker-account",
      "sandbox_policy": "read-only",
      "approval_policy": "never",
      "network_policy": "disabled",
      "write_capable": false,
      "native_helper_policy": "parent_read_only_ceiling",
      "native_helper": {
        "mechanism": "codex-multi-agent-v2-inherit-parent",
        "default_model": "gpt-5.6-sol",
        "default_reasoning_effort": "xhigh",
        "inherit_parent_capabilities": true,
        "hide_spawn_agent_metadata": true,
        "max_concurrent_helpers": 1,
        "max_depth": 1,
        "max_runtime_seconds": 60
      },
      "skills": [],
      "mcp_servers": [
        "openai-developer-docs-v1"
      ],
      "resources": [],
      "plugins": [],
      "forbidden": []
    },
    "operator.appserver.interactive.v1": {
      "enabled": true,
      "execution_surface": "codex-app-server",
      "auth_realm": "dedicated-worker-account",
      "sandbox_policy": "read-only",
      "approval_policy": "never",
      "network_policy": "disabled",
      "write_capable": false,
      "native_helper_policy": "disabled",
      "native_helper": null,
      "skills": [],
      "mcp_servers": [],
      "resources": [],
      "plugins": [],
      "forbidden": []
    },
    "sealed.worker.readonly.no-extensions.v1": {
      "enabled": true,
      "execution_surface": "codex-exec",
      "auth_realm": "dedicated-worker-account",
      "sandbox_policy": "read-only",
      "approval_policy": "never",
      "network_policy": "disabled",
      "write_capable": false,
      "native_helper_policy": "disabled",
      "native_helper": null,
      "skills": [],
      "mcp_servers": [],
      "resources": [],
      "plugins": [],
      "forbidden": []
    },
    "sealed.worker.write.no-extensions.v1": {
      "enabled": true,
      "execution_surface": "codex-exec",
      "auth_realm": "dedicated-worker-account",
      "sandbox_policy": "workspace-write",
      "approval_policy": "never",
      "network_policy": "disabled",
      "write_capable": true,
      "native_helper_policy": "disabled",
      "native_helper": null,
      "skills": [],
      "mcp_servers": [],
      "resources": [],
      "plugins": [],
      "forbidden": []
    },
    "sealed.worker.claude.readonly.no-extensions.v1": {
      "enabled": true,
      "execution_surface": "claude-code",
      "auth_realm": "dedicated-worker-account",
      "sandbox_policy": "read-only",
      "approval_policy": "never",
      "network_policy": "disabled",
      "write_capable": false,
      "native_helper_policy": "disabled",
      "native_helper": null,
      "skills": [],
      "mcp_servers": [],
      "resources": [],
      "plugins": [],
      "forbidden": []
    },
    "sealed.worker.claude.write.no-extensions.v1": {
      "enabled": true,
      "execution_surface": "claude-code",
      "auth_realm": "dedicated-worker-account",
      "sandbox_policy": "workspace-write",
      "approval_policy": "never",
      "network_policy": "disabled",
      "write_capable": true,
      "native_helper_policy": "disabled",
      "native_helper": null,
      "skills": [],
      "mcp_servers": [],
      "resources": [],
      "plugins": [],
      "forbidden": []
    },
    "operator.browser.local-review.v1": {
      "enabled": true,
      "execution_surface": "codex-app-server",
      "auth_realm": "dedicated-worker-account",
      "sandbox_policy": "read-only",
      "approval_policy": "never",
      "network_policy": "loopback-browser-only",
      "write_capable": false,
      "native_helper_policy": "disabled",
      "native_helper": null,
      "skills": [],
      "mcp_servers": [
        "openai-developer-docs-v1",
        "playwright-worker-browser-b1"
      ],
      "resources": [
        "worker-browser-b1-local"
      ],
      "plugins": [],
      "forbidden": []
    },
    "operator.browser.isolated.v1": {
      "enabled": false,
      "execution_surface": "codex-app-server",
      "auth_realm": "dedicated-worker-account",
      "sandbox_policy": "read-only",
      "approval_policy": "never",
      "network_policy": "disabled",
      "write_capable": false,
      "native_helper_policy": "disabled",
      "native_helper": null,
      "skills": [],
      "mcp_servers": [],
      "resources": [
        "worker-browser-isolated"
      ],
      "plugins": [],
      "forbidden": []
    },
    "operator.appserver.interactive.native-return.v1": {
      "enabled": true,
      "execution_surface": "codex-app-server",
      "auth_realm": "dedicated-worker-account",
      "sandbox_policy": "read-only",
      "approval_policy": "never",
      "network_policy": "disabled",
      "write_capable": false,
      "native_helper_policy": "disabled",
      "native_helper": null,
      "skills": [],
      "mcp_servers": [
        "native-return-mcp-v1"
      ],
      "resources": [],
      "plugins": [],
      "forbidden": []
    },
    "fabric.attended.claude.bounded.v1": {
      "enabled": true,
      "execution_surface": "claude-code",
      "auth_realm": "dedicated-worker-account",
      "sandbox_policy": "read-only",
      "approval_policy": "never",
      "network_policy": "disabled",
      "write_capable": false,
      "native_helper_policy": "disabled",
      "native_helper": null,
      "skills": [],
      "mcp_servers": [],
      "resources": [],
      "plugins": [],
      "forbidden": []
    },
    "operator.appserver.interactive.product-acceptance.v1": {
      "enabled": true,
      "execution_surface": "codex-app-server",
      "auth_realm": "dedicated-worker-account",
      "sandbox_policy": "read-only",
      "approval_policy": "never",
      "network_policy": "disabled",
      "write_capable": false,
      "native_helper_policy": "disabled",
      "native_helper": null,
      "skills": [],
      "mcp_servers": [
        "product-acceptance-mcp-v1"
      ],
      "resources": [],
      "plugins": [],
      "forbidden": []
    }
  }
}
"""
