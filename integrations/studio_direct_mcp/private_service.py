#!/usr/bin/env python3
"""First-install lifecycle helper for per-account private Studio Direct gateways.

Manages only the private launchd label com.mastermind.studio-direct-private.<account>,
its LaunchAgent plist, and ~/.local/share/studio-direct-mcp/private/<account>.
Never touches the public service, the tailnet-only service, or other accounts.

Subprocess calls go through _run so tests can mock them.
"""
from __future__ import annotations

# The existing CLI remains the bootstrap trust boundary. Re-exec before any
# path-searchable import; source library imports retain their existing behavior.
import sys as _bootstrap_sys
if __name__ == "__main__" and not (
        _bootstrap_sys.flags.isolated and _bootstrap_sys.flags.no_site
        and _bootstrap_sys.dont_write_bytecode):
    import posix as _bootstrap_os
    _bootstrap_os.execv(
        _bootstrap_sys.executable,
        [_bootstrap_sys.executable, "-I", "-S", "-B", __file__, *_bootstrap_sys.argv[1:]],
    )

import argparse
import fcntl
import hashlib
import json
import os
import plistlib
import re
import stat
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from contextlib import contextmanager
from functools import wraps
from pathlib import Path

DIR_MODE = 0o700
FILE_MODE = 0o600

# Funnel/OAuth listener. A private job must never take it.
RESERVED_FUNNEL_PORT = 45017

# Preserve the proven private-seat runtime timeouts: 30 minutes idle and 5 minutes per request.
# These values match the currently deployed Business-seat configuration and avoid restage regressions.
IDLE_TIMEOUT_MS = 1_800_000
REQUEST_TIMEOUT_MS = 300_000

# Shared private-seat gateways can serve many short-lived ChatGPT frontend MCP
# sessions while retaining one bounded backend owner per principal. 64 proved too
# small under multi-session C2 use and caused capacity 503s despite healthy backend
# execution. The gateway validates up to 1024; keep a bounded 256 installed default.
MAX_SESSIONS = 256

# Bounded typed-Git publication policy. These are host-owned values, not CLI
# inputs, so a ChatGPT caller cannot select another repository, remote, lane,
# credential, Git binary, or workspace authority.
TYPED_GIT_WORKSPACE_CLI_REL = Path(".local/bin/mmx-workspace")
TYPED_GIT_SOURCE_REPOSITORY_REL = Path("Documents/GitHub/Mastermind")
TYPED_GIT_BINARY = "/usr/bin/git"
TYPED_GIT_REMOTE_URL = "https://github.com/mastermindx-market-intelligence/Mastermind.git"
FABRIC_RELEASE_PUBLIC_PROVENANCE = "github_public_protected_v1"
FABRIC_RELEASE_LOCAL_PROVENANCE = "local_git_v1"
FABRIC_PUBLIC_REPOSITORY = "mastermindx-market-intelligence/Mastermind"
FABRIC_PUBLIC_REF = "refs/heads/master"
FABRIC_PUBLIC_API_ROOT = "https://api.github.com/repos/" + FABRIC_PUBLIC_REPOSITORY
FABRIC_PUBLIC_JSON_LIMIT = 1024 * 1024
FABRIC_PUBLIC_TIMEOUT_SECONDS = 10
FABRIC_PUBLIC_METADATA_URL_RE = re.compile(
    re.escape(FABRIC_PUBLIC_API_ROOT)
    + r"(?:/git/ref/heads/master|/git/(?:commits|trees)/[0-9a-f]{40})\Z"
)


def _fabric_git_sha(value) -> bool:
    return type(value) is str and re.fullmatch(r"[0-9a-f]{40}", value) is not None
# Host-owned identities; these match the existing mmx-workspace repository catalog.
# No caller-supplied path, remote, repository or credential is admitted.
TYPED_GIT_CLOSED_PROFILES = (
    ("mastermind", TYPED_GIT_SOURCE_REPOSITORY_REL, TYPED_GIT_REMOTE_URL),
    ("macro", Path("Documents/Cluade/macro-main"),
     "https://github.com/mastermindx-market-intelligence/macro.git"),
    ("terminal", Path("Documents/Cluade/charting-app"),
     "https://github.com/mastermindx-market-intelligence/mastermind-terminal.git"),
)


# Paper Desktop capability is a gateway-local consumer of the separately reviewed
# guarded adapter in PR #585. The private gateway never accepts these paths or
# hashes from ChatGPT.
# Runtime generations are immutable from the perspective of installed seats. A new
# bridge SHA gets a new directory so one-seat canaries cannot invalidate another
# seat that still pins the previous bridge bytes.
PAPER_RUNTIME_REL = Path(".local/share/mastermind-paper/runtime/v12")
PAPER_RUNTIME_SCHEMA = "mastermind.paper_runtime.v1"
PAPER_BRIDGE_SHA256 = "82bc7f2d75aec423711922198b68f317618a83de177bf4934b73d7b418a6ecfb"
PAPER_COMMAND_TIMEOUT_MS = 70_000
# Exact existing M1 Chris Admin legacy Paper gateway: no new account or tunnel.
# These pins are single-use predecessor CAs; any changed installed state requires
# a new independent review rather than choosing a nearby runtime generation.
M1_PAPER_V20_ACCOUNT = "chrisadmin"
M1_PAPER_V5_RUNTIME_REL = Path(".local/share/mastermind-paper/runtime/v5")
M1_PAPER_V20_RUNTIME_REL = Path(".local/share/mastermind-paper/runtime/v20")
M1_PAPER_V5_BRIDGE_SHA256 = "d3301a1466d46ae081ded963f438c019fabf39c9bccfc8c669f16562a52bf7f6"
M1_PAPER_V20_BRIDGE_SHA256 = "1a73ab002e89c87b489e8cee9f5c821530929a5b701eb0aaac7eed03a5a22ced"
M1_PAPER_V20_MERGE = "e3ee36e297140539e05a0524f3446e086f40c5d1"
M1_PAPER_V5_MANIFEST_SHA256 = "a97c67c52e334d624f9c3266177ed5a430323fa5310fbd52611942504b4e3457"
M1_PAPER_V5_CONFIG_SHA256 = "99686765df4296917a6762e379dc34daec7d6750315377d5a043eaa04edc441f"
M1_PAPER_V5_NONPAPER_SHA256 = "11a66a9b085108e4a645d7b24513b8a392492c17ad1abd09e060bfa978dceb02"
M1_PAPER_V5_PLIST_SHA256 = "72ab2c78f5a06efe254a47293f36a5770fa95f90311cefd390ea37317d04f677"

PAPER_APP_REL = Path("Applications/Paper.app")

# The accepted immutable v20 target generation. The global selection above
# intentionally stays v12; this pin only names the staged generation that the
# one reviewed C2 Personal v12 cohort may select through the dedicated
# transaction below. runtime_stage.py remains the owner that stages and never
# rewrites the v20 directory.
PAPER_RUNTIME_V20_REL = Path(".local/share/mastermind-paper/runtime/v20")
PAPER_V20_BRIDGE_SHA256 = "1a73ab002e89c87b489e8cee9f5c821530929a5b701eb0aaac7eed03a5a22ced"
PAPER_RUNTIME_V10_REL = Path(".local/share/mastermind-paper/runtime/v10")
PAPER_V10_BRIDGE_SHA256 = "7d810c458a53e00e21014fd7375ac338dc9c1421b30f823feb4d34184f9d08fc"
FLEET_V20_COHORT_SOURCE_SHA256 = "101c958e389ab4077edf54be70e6e894cedf3bba77e2daa9ab291361b192ca8a"
# One closed admission set shared by the dispatcher and real lifecycle-lock gate.
FLEET_V20_ENROLLED_ACCOUNTS = frozenset((
    "admin-business", "chatgpt1", "chatgpt2-business", "chatgpt3",
    "chatgpt3-w570f6f34", "chatgpt3-wa2a9e6f9",
    "chatgpt4", "mastermind-os-publication",
))

# Optional read-only fleet-status consumer. It delegates to the installed
# Studio Direct control owner instead of letting a model compose shell probes.
FLEET_STATUS_LAUNCHER_REL = Path(".local/bin/studio-direct")
FLEET_STATUS_TIMEOUT_MS = 15_000

# CLI adapter. gateway.mjs is still staged as the engine import, never argv[1].
PRIVATE_GATEWAY_NAME = "private-tunnel-gateway.mjs"

ACCOUNT_LABEL_MAX = 64
ACCOUNT_LABEL_RE = re.compile(r"^[a-z0-9](?:[a-z0-9._-]{0,63})?$")
RESERVED_ACCOUNT_LABELS = frozenset(
    ("public", "shared", "default", "state", "config", "logs", "manifest")
)

# Files staged from source directory. gateway.mjs is the engine library.
STAGE_FILES = (
    "gateway.mjs",
    "original-delivery.mjs",
    "t3-control.mjs",
    "t3-dot-tools.json",
    "modern-fabric-http.mjs",
    "output-budget.mjs",
    "git-publish.mjs",
    "workspace-access.mjs",
    "commission-prepare.mjs",
    "commission-service.mjs",
    "paper-design.mjs",
    "fleet-status.mjs",
    "private-tunnel-auth.mjs",
    "private-tunnel-gateway.mjs",
    "package.json",
    "package-lock.json",
)

# Historical installs are admitted only through exact known file sets. The
# immediately preceding v0.1.6 install has every current file except the new
# read-only fleet-status consumer; earlier generations also predate Paper,
# output paging, and typed Git.
LEGACY_STAGE_FILES_V9 = tuple(name for name in STAGE_FILES if name not in {"t3-control.mjs", "t3-dot-tools.json"})
LEGACY_STAGE_FILES_V8 = tuple(name for name in LEGACY_STAGE_FILES_V9 if name != "original-delivery.mjs")
LEGACY_STAGE_FILES_V7 = tuple(name for name in LEGACY_STAGE_FILES_V8 if name != "modern-fabric-http.mjs")
LEGACY_STAGE_FILES_V6 = tuple(name for name in LEGACY_STAGE_FILES_V7 if name not in {"commission-prepare.mjs", "commission-service.mjs"})
LEGACY_STAGE_FILES_V5 = tuple(name for name in LEGACY_STAGE_FILES_V6 if name != "workspace-access.mjs")
LEGACY_STAGE_FILES_V4 = tuple(name for name in LEGACY_STAGE_FILES_V5 if name != "fleet-status.mjs")
LEGACY_STAGE_FILES_V3 = tuple(name for name in LEGACY_STAGE_FILES_V4 if name != "paper-design.mjs")
LEGACY_STAGE_FILES_V2 = tuple(name for name in LEGACY_STAGE_FILES_V3 if name != "output-budget.mjs")
LEGACY_STAGE_FILES_V1 = tuple(name for name in LEGACY_STAGE_FILES_V2 if name != "git-publish.mjs")
# The approved 2026-10-14 ChatGPT1 Studio 0.1.10 install had exactly this
# reviewed predecessor generation (see #1333 and the source lineage of #1477).
# Unlike general historical generations, its two fleet/tailnet modules came
# from a branch not in current protected STAGE_FILES. Recognize ONLY this
# exact 12-file set on a V2 manifest. No file, config, binary, plist or
# dependency hash verification is relaxed, and no repository grant is implied.
V2_CHATGPT1_FLEET_TAILNET_PREDECESSOR = frozenset((
    "gateway.mjs", "output-budget.mjs", "git-publish.mjs",
    "workspace-access.mjs", "paper-design.mjs", "fleet-status.mjs",
    "fleet-routing.mjs", "private-tunnel-auth.mjs",
    "private-tunnel-gateway.mjs", "tailnet-gateway.mjs",
    "package.json", "package-lock.json",
))

# Exact 0.1.10 ChatGPT1 fleet bundle signed into the existing V2 manifest.
# This is an owner-bound compatibility update, NOT a generic legacy bundle
# upgrade or permission grant. Unchanged modules retain their original bytes.
FLEET_V10_PRESERVED_GIT_BLOBS = {
    "gateway.mjs": "f87ac012339e82fe46bce5ddc70d1d04183d1b6e",
    "output-budget.mjs": "6d4680a357dc5780e1b09ae32c9ebc908c94353b",
    "paper-design.mjs": "82b35d150433f5128b83a089b581873ad5d73daa",
    "fleet-status.mjs": "ef7ab489ca5134fc6f5d825977ab43a21aab3078",
    "fleet-routing.mjs": "63c47d73ae7b73a61c95cee1803c549ecd6df9c8",
    "private-tunnel-auth.mjs": "cd7ec9fc38ae10cefe8e472246aaf9c6221b0281",
    "private-tunnel-gateway.mjs": "6ea4b75a0ce76995cde4c7f090ad4e28a183f3db",
    "tailnet-gateway.mjs": "d654200a417d5a4dadfcc4e0f6141ef9adda6a04",
    "package.json": "e983917ada1a9da715cedd1acce7559f26a2a932",
    "package-lock.json": "d119580040b0edc59cf0e239922b54a023f899c5",
}
# The already-installed C2 Business fleet v0.1.10 predecessor is a DISTINCT
# 11-file owner, with NO repository-workspace enrollment. Recognizing its
# exact V2 manifest does not grant a new Git repository or change its live
# gateway, tenant or tool catalog. A separate closed migration may later
# upgrade the bounded source generation with explicit original-manifest CAS.
V2_C2_BUSINESS_FLEET_PREDECESSOR = frozenset((
    "gateway.mjs", "git-publish.mjs", "output-budget.mjs",
    "package.json", "package-lock.json", "paper-design.mjs",
    "fleet-status.mjs", "fleet-routing.mjs", "tailnet-gateway.mjs",
    "private-tunnel-auth.mjs", "private-tunnel-gateway.mjs",
))

# Exact 2026-10-21 predecessor seals only. These do not admit later
# unreconciled installations or authorize a compatibility upgrade.
V2_FABRIC_DESIGN_TAILNET_FILES = frozenset((
    "fleet-status.mjs", "gateway.mjs", "git-publish.mjs",
    "output-budget.mjs", "package-lock.json", "package.json",
    "paper-design.mjs", "private-tunnel-auth.mjs",
    "private-tunnel-gateway.mjs", "tailnet-gateway.mjs",
))

V2_FABRIC_READ_OPERATOR_FILES = V2_FABRIC_DESIGN_TAILNET_FILES | frozenset((
    "fabric-operator.mjs",
))

SEALED_V2_FLEET_GATEWAY_PREDECESSORS = {
    "admin-business": (
        "68792c832344c61a7f0ca3462d85c85eba0e586877ee68934153c2bc18e55ebd",
        "5dc83dd6aa840b3d321502045db1c4dcaf6fa9d09d5cca8422d5717c84191b1a",
        V2_C2_BUSINESS_FLEET_PREDECESSOR,
    ),
    "chatgpt3-w570f6f34": (
        "35246e482e79f3203b3e1cd28e76c77cfbef8681c1157a9a5add4e232a7820e5",
        "5462b46a30a5d67fbc3dcee368bfe2675eb409b3bacecbeddc70e9a5a3d9a123",
        V2_C2_BUSINESS_FLEET_PREDECESSOR,
    ),
    "chatgpt3-wa2a9e6f9": (
        "0a248967072622afa375c6e6ab749d025150b7805fe288c2de83da381c66e0b4",
        "39c6bbe7ddfb69b8ac837be37f7b9fed06f10645967dc1675221dad4b5040879",
        V2_C2_BUSINESS_FLEET_PREDECESSOR,
    ),
    "chatgpt4": (
        "2252819766e266ac0be6b30c94694b503aad4634d8de184f62611542fb581bd0",
        "5b7e4ea4b83d1cff6f371dc1ccb3862762222336ba9bb24c0444ad42d3d959c9",
        V2_C2_BUSINESS_FLEET_PREDECESSOR,
    ),
    "fabric-design": (
        "87de91f4fd0d51571c2350cf4fe53704ad035eba8f095c13b09352732307671c",
        "0481da04b267ea610a917e78203ac7829c1799a2a83e226502978c6d8bc7d2f9",
        V2_FABRIC_DESIGN_TAILNET_FILES,
    ),
    "fabric-read": (
        "f39e118cb770d4f793dd92c31e9f17f7153e7daef4e9703be7408fde702d40bb",
        "c0fda20241050072ccdecc4cfa5e31d4322a3e0a645404666e7116db372954d3",
        V2_FABRIC_READ_OPERATOR_FILES,
    ),
}

# Exact historical installed C2 Business 0.1.10 generation. All pinned file
# hashes are provenance checks, NOT a repository access grant. The Gateway
# target source is the independently reviewed fleet v0.1.10 generation; the
# Git publisher/workspace layer is pinned to the reviewed #1535 source.
C2_BUSINESS_V10_ORIGINAL_BLOBS = {
    "fleet-routing.mjs": "7a1d770bf59d9198f1b29f94f56c2e845c4e1b55",
    "fleet-status.mjs": "f04630857f75d712f701360f18e84d42ac8ae8ba",
    "gateway.mjs": "b4fd9aa277403d42e532ed9ecb0a9ff50adb5fe9",
    "git-publish.mjs": "f187b291cbb21782abfdb460a67b557ef1d29638",
    "output-budget.mjs": "6d4680a357dc5780e1b09ae32c9ebc908c94353b",
    "package-lock.json": "d119580040b0edc59cf0e239922b54a023f899c5",
    "package.json": "e983917ada1a9da715cedd1acce7559f26a2a932",
    "paper-design.mjs": "82b35d150433f5128b83a089b581873ad5d73daa",
    "private-tunnel-auth.mjs": "cd7ec9fc38ae10cefe8e472246aaf9c6221b0281",
    "private-tunnel-gateway.mjs": "6ea4b75a0ce76995cde4c7f090ad4e28a183f3db",
    "tailnet-gateway.mjs": "d654200a417d5a4dadfcc4e0f6141ef9adda6a04",
}
C2_PERSONAL_CURRENT_MANIFEST_SHA256 = "c5744dcc7a96d0bc0b019f3c153e8acc8761320ff11541340df753fb493c5460"
# Exact live C2 Personal post-#1604 sealed generation. A dedicated stopped-
# service, manifest-CAS migration changes ONLY the Git command budget.
# Repository enrollment, Git source, fleet, Paper and all module hashes stay fixed.
C2_PERSONAL_TIMEOUT_PREDECESSOR_SHA256 = "4bb0b40cbc7849487c0d886b30261f70fd6e1828d1d217643a56e3fa6aea40fb"
C2_PERSONAL_TIMEOUT_COMMAND_MS = 45000
C2_PERSONAL_TARGET_PATCH_SHA256 = {
    "gateway.mjs": "17157fa5f8739dbe17aae767a335e97dd713a978dde9b192feb1b41a7b036b30",
    "git-publish.mjs": "d8f7f7712129094ce0ffac2eaeb66d15dd3f063a3ade9fa354de7af0d412477a",
    "workspace-access.mjs": "9c4c20dd4edbc426c8561801708ee205e19bb47b48134ec8f5654a10f1cb7cf3",
}
C2_BUSINESS_TARGET_PATCH_SHA256 = {
    "gateway.mjs": "17157fa5f8739dbe17aae767a335e97dd713a978dde9b192feb1b41a7b036b30",
    "git-publish.mjs": "d8f7f7712129094ce0ffac2eaeb66d15dd3f063a3ade9fa354de7af0d412477a",
    "workspace-access.mjs": "9c4c20dd4edbc426c8561801708ee205e19bb47b48134ec8f5654a10f1cb7cf3",
}

# Only existing reviewed, closed-profile enrolled fleet-v0.1.10 seats.
# Other installed gateways differ in bundle/permissions and are NOT eligible.
FLEET_V10_ENROLLED_ACCOUNTS = frozenset(("chatgpt1", "chatgpt3"))

FLEET_V10_PUBLISHER_PATCH_SHA256 = {
    "git-publish.mjs": "d8f7f7712129094ce0ffac2eaeb66d15dd3f063a3ade9fa354de7af0d412477a",
    "workspace-access.mjs": "9c4c20dd4edbc426c8561801708ee205e19bb47b48134ec8f5654a10f1cb7cf3",
}
# PR #1535's exact, already-installed closed publisher is the ONLY eligible
# second-stage predecessor. No arbitrary closed publisher may be overwritten.
FLEET_V10_PREVIOUS_CLOSED_PUBLISHER_SHA256 = "72faf293d9c0a90c45ab442821e26f199f5ea406a091a7aed7ebce3519e55f69"

# Exact sealed index-sync predecessor observed on enrolled fleet seats. Keep
# this pair independent from both historical targets and the merge target.
FLEET_V10_MERGE_PUBLISHER_PREDECESSOR_SHA256 = {
    "git-publish.mjs": "d8f7f7712129094ce0ffac2eaeb66d15dd3f063a3ade9fa354de7af0d412477a",
    "workspace-access.mjs": "9c4c20dd4edbc426c8561801708ee205e19bb47b48134ec8f5654a10f1cb7cf3",
}
# The merge-capable publisher's previously sealed target is a valid *incoming
# predecessor* for the narrow rejection-diagnostics update. Do not accept
# arbitrary live publisher bytes, widen the account allowlist, or change
# inherited config/credential/manifest requirements.
FLEET_V10_POST_MERGE_PUBLISHER_PREDECESSOR_SHA256 = {
    "git-publish.mjs": "badd8a554ae8230808d18a1943aa49edb7ced51391ed2cbadb358cd015d62c3a",
    "workspace-access.mjs": "e4f74c201d177e6af1c3e113cc180430542cfd08a25591b81fb6d04c8a575db5",
}
# Previously accepted rejection-diagnostics publisher is an exact incoming
# predecessor only. The next target embeds the recovery journal in the single
# already-staged git-publish.mjs, avoiding a new unsealed runtime import.
FLEET_V10_REJECTION_PUBLISHER_PREDECESSOR_SHA256 = {
    "git-publish.mjs": "10574812f428114314a1529df2d969e52b19d2db8d4f971564a98970d93adc67",
    "workspace-access.mjs": "e4f74c201d177e6af1c3e113cc180430542cfd08a25591b81fb6d04c8a575db5",
}
FLEET_V10_MERGE_PUBLISHER_PATCH_SHA256 = {
    "git-publish.mjs": "abc3b4dc6f3c9574ebb116e28a44f42136f8d8df3f2b0ec1504668daaf46b6bc",
    "workspace-access.mjs": "e4f74c201d177e6af1c3e113cc180430542cfd08a25591b81fb6d04c8a575db5",
}

# One closed C1 fleet-gateway Git-failure correction. This adds a gateway-only
# successor route to the incumbent owner for the single already-enrolled
# chatgpt1 seat. It creates no seat, installer, publisher, registry, queue,
# service or account, and it changes no publisher module, configuration byte,
# fleet route, scheduling cap, dependency, launcher, credential or grant.
#
# The predecessor is the exact installed fleet gateway (public Git object
# f87ac012...). The successor is the deterministic compile of that exact
# predecessor by integrations/studio_direct_mcp/fleet_git_failure_compat.py,
# which pins one fixed complete successor hash. The classifier and the
# typed-Git catch are byte-exact copies of the current protected gateway's own
# regions, so the truthfulness of the classification is inherited rather than
# re-invented here.
C1_GIT_FAILURE_COMPAT_ACCOUNT = "chatgpt1"
C1_GIT_FAILURE_COMPAT_GATEWAY = "gateway.mjs"
C1_GIT_FAILURE_COMPAT_PREDECESSOR_SHA256 = (
    "17157fa5f8739dbe17aae767a335e97dd713a978dde9b192feb1b41a7b036b30")
C1_GIT_FAILURE_COMPAT_PREDECESSOR_GIT_BLOB = (
    "f87ac012339e82fe46bce5ddc70d1d04183d1b6e")
C1_GIT_FAILURE_COMPAT_SUCCESSOR_SHA256 = (
    "336de8ed10e7da483d46e93bd98439fd00c3e277111b39b5baa9cf0e68074674")
C1_GIT_FAILURE_COMPAT_SUCCESSOR_GIT_BLOB = (
    "c02bcdada5217bbc987099e90ebdce236f023b86")
# Closed internal artifact-verification purpose for the chatgpt1 gateway
# formatter. Not a CLI flag, config permission, registry, or native operation.
# The literal is repeated in the native proof script below; both must match.
C1_GATEWAY_RETAINED_PROOF_PURPOSE = "c1-gateway-preserving-formatter"

# Exact sealed C2 predecessor observed for the one-seat Paper v10 -> v12 repair.
# These are reviewed installation identity pins, never caller-selectable source or runtime paths.
# The fleet bundle remains installed byte-for-byte; only Paper configuration moves.
C2_PAPER_ACCOUNT = "chatgpt2-personal"
C2_PAPER_ORIGINAL_MANIFEST_SHA256 = "10658ddba662cac2c0a321dfdc48b9b009199187e9709f8f7d63a30bf2406337"
C2_PAPER_MANIFEST_CANONICAL_SHA256 = frozenset((
    "821e37a4e10011f3335984416edaac92899c6bc27526c0f017b3d75130950d84",
    "d477cd952b86d76c07a2554a94a1ce5dc8c5e42bda544a5603caf0f54e17c9b7",
))
C2_LIFECYCLE_LOCK_NAME = "private-service.lifecycle.lock"
# These are the two already enrolled restricted Fabric seats, not a caller-selectable
# account family. Their backends may advance independently of their sealed gateways.
FABRIC_BACKEND_ACCOUNT = "subagent-fabric-c3"
FABRIC_BACKEND_MODERN_ACCOUNT = "fabric-c3-570f6f34"
FABRIC_BACKEND_MODERN_PORT = 45280
FABRIC_BACKEND_ACCOUNTS = frozenset((FABRIC_BACKEND_ACCOUNT, FABRIC_BACKEND_MODERN_ACCOUNT))
FABRIC_BACKEND_SOURCE = "integrations/studio_direct_mcp/fabric-backend.mjs"
FABRIC_BACKEND_RELEASES_REL = Path(".local/share/studio-direct-mcp/releases")
FABRIC_BACKEND_RELEASE_SCHEMA = "mastermind.fabric_backend_release.v1"
C2_PAPER_NON_PAPER_CONFIG_SHA256 = "adc1c3367236b8a3a49b30169c2fb0a5dc3e85ecb415ab1b7d4d799fdf075b38"
C2_PAPER_ORIGINAL_BRIDGE_SHA256 = "7d810c458a53e00e21014fd7375ac338dc9c1421b30f823feb4d34184f9d08fc"
C2_PAPER_FILES_SHA256 = {
    "fleet-routing.mjs": "dc98537e5ade635f5c9fa3a89ab99ae9ea57f549d2856832d01f90c1e61c1533",
    "fleet-status.mjs": "a7ba88b02d7099d99d0e6d1e702b2faee6b7a05e7e6e6a49c86c567184e5c780",
    "gateway.mjs": "92e7f38f9eb53a5b140d0f3809b3381a4d35cea86bbb2e20229f108792ec30c8",
    "git-publish.mjs": "9d50cd828e51d0c08a7be0ca7b18c89bfd8fb767a548bb1e4deaddaf185225ae",
    "output-budget.mjs": "5fb464cdb531adf944561ddda760b77856530bcc08f7ba48ef774d6750f5a071",
    "package-lock.json": "9a4e7398ddb45f44d6910fc05118bac425397f4b9869f33229da81f76ae262d0",
    "package.json": "25ab096e21ac6e8c3761ee896e69d175ba628c1fe5751bcfab452c304a4bb634",
    "paper-design.mjs": "e2162584ceab9941e7bcce51b73120c9a9aeb13c128cd5b217077c005f0f1c7e",
    "private-tunnel-auth.mjs": "fe8c9e5ba14fd7750fc26bbfe45ed3f77d4b96fa8ff639c6b5efdf653740e1c0",
    "private-tunnel-gateway.mjs": "fd4eb541590cafc3c92a0b0ac1f7080baa76193704a2219e58b02462ef4d5540",
    "tailnet-gateway.mjs": "9dd75992ba0b5c658582779ebeb71a06f13ec0a3475aa83d62753e22832b906b",
}
C2_PAPER_RUNTIME_IDENTITY = {
    "host": "127.0.0.1",
    "port": 45026,
    "nodeHash": "3fbe98203f8f4a86ce5b0b573a1a30aa4253064c4c2a0299c436d259b68e54b0",
    "backendHash": "a4145198dc75cd34e7c7452c2054b4cc0d29e199ae1459961a17e4da25a13500",
    "dependencyTreeHash": "91ce96dc69159edcabb3eee472e6ebafb18450b93a03addd6adf0df6dca47e29",
}

# Distinct sealed, already-enrolled C2 Business Paper v10 installation. This is
# an independent per-seat transaction, never permission to rewrite another
# account's config, fleet modules, workspace grants, or immutable runtime.
C2_PAPER_BUSINESS_ACCOUNT = "chatgpt2-business"
C2_PAPER_UPGRADE_ACCOUNTS = frozenset((C2_PAPER_ACCOUNT, C2_PAPER_BUSINESS_ACCOUNT))
C2_PAPER_BUSINESS_ORIGINAL_MANIFEST_SHA256 = "504c22af839e154bb1a5314134240b9eb7064f043e1003a357922e1103c21b06"
C2_PAPER_BUSINESS_NON_PAPER_CONFIG_SHA256 = "ed2dc2b9f7f812406c7ef7e9297b3ad5b54c8c15c11903463e61a1d628b0fdf0"
C2_PAPER_BUSINESS_RUNTIME_IDENTITY = {**C2_PAPER_RUNTIME_IDENTITY, "port": 45028}

# Independently verified C4 installation, observed 2026-10-18. Its eleven module
# bytes equal C2_PAPER_FILES_SHA256, but its account, manifests, configuration and
# dependency seal are distinct. This admits only its original and planned Paper
# configuration; it does not enroll a new workspace or change installed grants.
C4_PAPER_ACCOUNT = "chatgpt4"
C4_PAPER_ORIGINAL_MANIFEST_SHA256 = "849e0af6b498408eba843bcbf2c9c500e199c218db06f00db9cb13b54303b071"
C4_PAPER_MANIFEST_CANONICAL_SHA256 = frozenset((
    "e0e7865965285af6372fdf27ee70ae27f494b37fe19e1f5af763406295a96ec2",
    "2252819766e266ac0be6b30c94694b503aad4634d8de184f62611542fb581bd0",
    # Exact native-pool pin postimage; all other C4 profile fields stay sealed.
    "e10730454cd343b8774929b9c6d39f5dfbf1c9b7e83bfdc82636b8e54d0437a0",
    # Exact v20 Paper-only successor of that native-pin postimage, with the
    # original 11 module seals, plist, port and non-Paper config unchanged.
    "f46f1aeec2c5b0baa98f7c655723bbdfbb0a4765f87a98aacb29381750382b1e",
))
C4_PAPER_NON_PAPER_CONFIG_SHA256 = "94a480d9db9c59e2d76b6d3fdd9f9b1a448bcd77c26fbe30f430f79357e36894"
C4_PAPER_RUNTIME_IDENTITY = {
    "host": "127.0.0.1",
    "port": 45024,
    "nodeHash": "3fbe98203f8f4a86ce5b0b573a1a30aa4253064c4c2a0299c436d259b68e54b0",
    "backendHash": "a4145198dc75cd34e7c7452c2054b4cc0d29e199ae1459961a17e4da25a13500",
    "dependencyTreeHash": "639c904d1d5832baa832eac8519cf2304073d3d72fdacc03fd879281068e6211",
}
PAPER_RUNTIME_UPGRADE_ACCOUNTS = C2_PAPER_UPGRADE_ACCOUNTS | frozenset((C4_PAPER_ACCOUNT,))

# Fresh read-only observed C2 Personal M2 cohort, 2026-11-02. This seat already
# received the reviewed closed-publisher generation and selects exact v12, so
# the historical v10 -> v12 admission above can never fire for it again. Its
# one-seat v12 -> v20 selection reuses the identical single-use manifest-CAS
# transaction with this pinned predecessor. The installed 12-file cohort is the
# sealed publisher patch plus the unchanged fleet modules; no byte identity is
# invented here. The node/backend/dependency identity is inherited from the
# seat's sealed C2 predecessor because the publisher patch changed only module
# bytes; a live manifest that disagrees refuses closed and requires fresh
# observation of the exact differing identity fields.
C2_PAPER_V12_MANIFEST_SHA256 = (
    "c5cdba867972f547aaefa7dbfc5840467d2961c7f4d346e8de1f1ba575686ef6")
C2_PAPER_V12_NON_PAPER_CONFIG_SHA256 = (
    "201288e64eadeb25e16306e737831fb828ce638a54b0e41c16945bd1c737eb08")
C2_PAPER_V12_FILES_SHA256 = {
    **{name: digest for name, digest in C2_PAPER_FILES_SHA256.items()
       if name not in C2_PERSONAL_TARGET_PATCH_SHA256},
    **C2_PERSONAL_TARGET_PATCH_SHA256,
}


KNOWN_MANIFEST_FILESETS = frozenset(
    (
        frozenset(STAGE_FILES),
        frozenset(LEGACY_STAGE_FILES_V9),
        frozenset(LEGACY_STAGE_FILES_V8),
        frozenset(LEGACY_STAGE_FILES_V7),
        frozenset(LEGACY_STAGE_FILES_V6),
        frozenset(LEGACY_STAGE_FILES_V5),
        frozenset(LEGACY_STAGE_FILES_V4),
        frozenset(LEGACY_STAGE_FILES_V3),
        frozenset(LEGACY_STAGE_FILES_V2),
        frozenset(LEGACY_STAGE_FILES_V1),
    )
)

MANIFEST_VERSION = 2
MANIFEST_KEYS_V1 = (
    "version",
    "account",
    "label",
    "files",
    "configHash",
    "plistHash",
    "source",
    "node",
    "backend",
    "host",
    "port",
)
MANIFEST_KEYS_V2 = MANIFEST_KEYS_V1 + (
    "nodeHash",
    "backendHash",
    "dependencyTreeHash",
)
LEGACY_PROVISIONED_MANIFEST_KEYS = MANIFEST_KEYS_V1 + (
    "provisioned_from",
    "installation_state",
)
LEGACY_PROVISIONED_STATE = "LOCAL_GATEWAY_PREPARED_TUNNEL_NOT_CREATED"


class CmdResult:
    __slots__ = ("returncode", "stdout", "stderr")

    def __init__(self, returncode: int = 0, stdout: str = "", stderr: str = ""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _run(cmd, *, check: bool = True, timeout: float = 30.0) -> CmdResult:
    res = subprocess.run(
        list(cmd),
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    out = CmdResult(res.returncode, res.stdout or "", res.stderr or "")
    if check and out.returncode != 0:
        raise RuntimeError(
            f"command failed: {cmd!r} rc={out.returncode} stderr={out.stderr.strip()}"
        )
    return out


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _canonical_json_sha256(value: object) -> str:
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")).hexdigest()


def _sealed_v2_fleet_gateway_predecessor(data: dict, account: str) -> bool:
    """Recognize only one exact already-installed historical V2 gateway seal."""
    entry = SEALED_V2_FLEET_GATEWAY_PREDECESSORS.get(account)
    if (entry is None or not isinstance(data, dict)
            or data.get("version") != MANIFEST_VERSION
            or data.get("account") != account):
        return False
    files = data.get("files")
    return (isinstance(files, dict)
            and frozenset(files) == entry[2]
            and _canonical_json_sha256(data) == entry[0])


def _sha256_hex(value: str) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(
        c in "0123456789abcdef" for c in value
    )


def _stable_regular_file_hash(path: Path, *, label: str) -> str:
    """Hash one exact regular file and refuse identity drift while reading it."""

    try:
        before = path.lstat()
    except OSError:
        raise SystemExit(f"{label} missing") from None
    if path.is_symlink() or not stat.S_ISREG(before.st_mode):
        raise SystemExit(f"{label} must be a regular non-symlink file")
    digest = _sha256_file(path)
    try:
        after = path.lstat()
    except OSError:
        raise SystemExit(f"{label} changed while hashing") from None
    identity = lambda info: (
        info.st_dev,
        info.st_ino,
        info.st_mode,
        info.st_size,
        info.st_mtime_ns,
        info.st_ctime_ns,
    )
    if identity(before) != identity(after):
        raise SystemExit(f"{label} changed while hashing")
    return digest


def _dependency_tree_hash_once(root: Path) -> str:
    """Return one host-path-independent digest of the installed dependency tree."""

    if root.is_symlink() or not root.is_dir():
        raise SystemExit(
            "not staged: node_modules missing; "
            "parent must run npm ci --omit=dev --ignore-scripts"
        )
    try:
        resolved_root = root.resolve(strict=True)
        root_info = root.lstat()
    except OSError:
        raise SystemExit("not staged: node_modules unavailable") from None
    entries: list[tuple[object, ...]] = [
        (".", "directory", stat.S_IMODE(root_info.st_mode))
    ]
    stack = [root]
    while stack:
        directory = stack.pop()
        try:
            children = sorted(os.scandir(directory), key=lambda item: item.name)
        except OSError:
            raise SystemExit("not staged: dependency tree unreadable") from None
        for child in children:
            path = Path(child.path)
            rel = path.relative_to(root).as_posix()
            try:
                info = path.lstat()
            except OSError:
                raise SystemExit("not staged: dependency tree changed while hashing") from None
            mode = stat.S_IMODE(info.st_mode)
            if stat.S_ISLNK(info.st_mode):
                try:
                    target = os.readlink(path)
                except OSError:
                    raise SystemExit("not staged: dependency symlink unreadable") from None
                if os.path.isabs(target):
                    raise SystemExit("not staged: dependency symlink escapes node_modules")
                try:
                    resolved_target = (path.parent / target).resolve(strict=True)
                    resolved_target.relative_to(resolved_root)
                except (OSError, ValueError):
                    raise SystemExit("not staged: dependency symlink escapes node_modules") from None
                entries.append((rel, "symlink", mode, target))
            elif stat.S_ISDIR(info.st_mode):
                entries.append((rel, "directory", mode))
                stack.append(path)
            elif stat.S_ISREG(info.st_mode):
                digest = _stable_regular_file_hash(path, label="dependency file")
                entries.append((rel, "file", mode, info.st_size, digest))
            else:
                raise SystemExit("not staged: unsupported dependency entry")
    payload = json.dumps(
        sorted(entries, key=lambda item: str(item[0])),
        sort_keys=False,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _dependency_tree_hash(root: Path) -> str:
    """Require two identical dependency observations so concurrent drift refuses."""

    first = _dependency_tree_hash_once(root)
    second = _dependency_tree_hash_once(root)
    if first != second:
        raise SystemExit("not staged: dependency tree changed while hashing")
    return first


def _user_root() -> Path:
    return Path(os.environ.get("HOME") or str(Path.home()))


def _fsync_dir(directory: Path) -> None:
    try:
        dfd = os.open(str(directory), os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(dfd)
    finally:
        os.close(dfd)


def _under_home(path: Path, home: Path) -> bool:
    path_s = os.path.normpath(str(path))
    home_s = os.path.normpath(str(home))
    return path_s == home_s or path_s.startswith(home_s + os.sep)


def _assert_no_symlink_ancestors(path: Path) -> None:
    """Refuse symlink components between dest and HOME.

    Path.mkdir(parents=True) follows parent symlinks. Walk stops at HOME so
    platform links above the test/user root (e.g. /var -> /private/var) are
    not treated as hostile.
    """
    home = _user_root()
    if not path.is_absolute():
        raise SystemExit(f"path must be absolute: {path}")
    if not _under_home(path, home):
        raise SystemExit(f"refusing path outside HOME: {path}")
    cur = path
    while cur != home:
        if os.path.islink(cur):
            raise SystemExit(f"refusing symlink ancestor: {cur}")
        parent = cur.parent
        if parent == cur:
            break
        cur = parent


def _atomic_write_bytes(path: Path, data: bytes, mode: int = FILE_MODE) -> None:
    _assert_no_symlink_ancestors(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if os.path.islink(path.parent) or (path.parent.exists() and not path.parent.is_dir()):
        raise SystemExit(f"refusing non-directory or symlink path: {path.parent}")
    fd, tmp = tempfile.mkstemp(
        dir=str(path.parent), prefix=path.name + ".", suffix=".tmp"
    )
    try:
        os.fchmod(fd, mode)
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
        _fsync_dir(path.parent)
    except BaseException:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise


def _atomic_write_text(path: Path, data: str, mode: int = FILE_MODE) -> None:
    _atomic_write_bytes(path, data.encode("utf-8"), mode)


def _is_owned_by_us(path: Path) -> bool:
    return os.lstat(path).st_uid == os.getuid()


def _assert_dest_safe(path: Path) -> None:
    _assert_no_symlink_ancestors(path)
    if path.is_symlink():
        raise SystemExit(f"refusing destination symlink: {path}")
    if path.exists() and not _is_owned_by_us(path):
        raise SystemExit(f"refusing non-owned destination: {path}")


def _ensure_secure_dir(path: Path) -> None:
    if path.is_symlink():
        raise SystemExit(f"refusing symlink path: {path}")
    _assert_no_symlink_ancestors(path)
    if path.exists():
        if not path.is_dir():
            raise SystemExit(f"refusing non-directory path: {path}")
        st = os.lstat(path)
        if st.st_uid != os.getuid():
            raise SystemExit(f"refusing non-owned directory: {path}")
        os.chmod(path, DIR_MODE)
        return
    path.mkdir(parents=True, mode=DIR_MODE)
    if path.is_symlink() or not path.is_dir():
        raise SystemExit(f"refusing non-directory or symlink path: {path}")
    st = os.lstat(path)
    if st.st_uid != os.getuid():
        raise SystemExit(f"refusing non-owned directory: {path}")
    os.chmod(path, DIR_MODE)


def _copy_secure(src: Path, dst: Path) -> None:
    if src.is_symlink() or not src.is_file():
        raise SystemExit(f"source invalid: {src}")
    _assert_dest_safe(dst)
    _ensure_secure_dir(dst.parent)
    _atomic_write_bytes(dst, src.read_bytes(), FILE_MODE)


def _check_source_files(source: Path) -> list[Path]:
    if source.is_symlink() or not source.is_dir():
        raise SystemExit(f"source dir invalid: {source}")
    found: list[Path] = []
    for name in STAGE_FILES:
        p = source / name
        if p.is_symlink() or not p.is_file():
            raise SystemExit(f"missing or symlink source file: {p}")
        found.append(p)
    return found


def _resolve_abs(name: str, value: str) -> Path:
    if not os.path.isabs(value):
        raise SystemExit(f"{name} must be absolute: {value}")
    p = Path(value)
    if p.is_symlink():
        raise SystemExit(f"{name} must not be a symlink: {value}")
    if not p.is_file():
        raise SystemExit(f"{name} not found: {value}")
    return p


def _validate_account_label(label: str) -> None:
    if not label:
        raise SystemExit("account label must not be empty")
    if not label.isascii():
        raise SystemExit("account label must be ASCII")
    if label != label.lower():
        raise SystemExit("account label must be lowercase")
    if len(label) > ACCOUNT_LABEL_MAX:
        raise SystemExit("account label must be at most 64 characters")
    if not ACCOUNT_LABEL_RE.fullmatch(label):
        raise SystemExit(
            "account label must match "
            f"{ACCOUNT_LABEL_RE.pattern} (got {label!r})"
        )
    if label in RESERVED_ACCOUNT_LABELS:
        raise SystemExit(f"account label {label!r} is reserved")


def _build_runtime_roots(account: str) -> dict:
    """Build per-account paths using the real HOME environment variable."""
    user_root = _user_root()
    base = user_root / ".local" / "share" / "studio-direct-mcp" / "private" / account
    return {
        "base": base,
        "state": base / "state",
        "logs": base / "logs",
        "config": base / "config.json",
        "manifest": base / "manifest.json",
        "plist": user_root / "Library" / "LaunchAgents" / f"com.mastermind.studio-direct-private.{account}.plist",
        "gateway": base / PRIVATE_GATEWAY_NAME,
        "node_modules": base / "node_modules",
    }



# Exact existing cohort: pin compatibility preserves installed capabilities.
NATIVE_POOL_PIN_ACCOUNTS = frozenset(('admin-business', 'chatgpt1', 'chatgpt2-business', 'chatgpt2-personal', 'chatgpt3', 'chatgpt3-w570f6f34', 'chatgpt3-wa2a9e6f9', 'chatgpt4', 'fabric-design', 'fabric-read'))
# The already enrolled public seats that may move from their preserved original
# successor pins to a qualified retained-Go application ingress. This is the
# same cohort the incumbent native forward-selection proof already admits; it
# is not a new roster, seat set or enrollment.
NATIVE_POOL_PIN_FORWARD_ACCOUNTS = frozenset(('admin-business', 'chatgpt1', 'chatgpt2-business', 'chatgpt2-personal', 'chatgpt3', 'chatgpt3-w570f6f34', 'chatgpt3-wa2a9e6f9', 'chatgpt4', 'fabric-design', 'fabric-read'))
NATIVE_POOL_PIN_PREDECESSORS = {'admin-business': {'fleet-routing.mjs': 'dc98537e5ade635f5c9fa3a89ab99ae9ea57f549d2856832d01f90c1e61c1533',
                    'fleet-status.mjs': 'a7ba88b02d7099d99d0e6d1e702b2faee6b7a05e7e6e6a49c86c567184e5c780',
                    'gateway.mjs': '92e7f38f9eb53a5b140d0f3809b3381a4d35cea86bbb2e20229f108792ec30c8',
                    'git-publish.mjs': '9d50cd828e51d0c08a7be0ca7b18c89bfd8fb767a548bb1e4deaddaf185225ae',
                    'output-budget.mjs': '5fb464cdb531adf944561ddda760b77856530bcc08f7ba48ef774d6750f5a071',
                    'package-lock.json': '9a4e7398ddb45f44d6910fc05118bac425397f4b9869f33229da81f76ae262d0',
                    'package.json': '25ab096e21ac6e8c3761ee896e69d175ba628c1fe5751bcfab452c304a4bb634',
                    'paper-design.mjs': 'e2162584ceab9941e7bcce51b73120c9a9aeb13c128cd5b217077c005f0f1c7e',
                    'private-tunnel-auth.mjs': 'fe8c9e5ba14fd7750fc26bbfe45ed3f77d4b96fa8ff639c6b5efdf653740e1c0',
                    'private-tunnel-gateway.mjs': 'fd4eb541590cafc3c92a0b0ac1f7080baa76193704a2219e58b02462ef4d5540',
                    'tailnet-gateway.mjs': '9dd75992ba0b5c658582779ebeb71a06f13ec0a3475aa83d62753e22832b906b'},
 'chatgpt3-w570f6f34': {'fleet-routing.mjs': 'dc98537e5ade635f5c9fa3a89ab99ae9ea57f549d2856832d01f90c1e61c1533',
                        'fleet-status.mjs': 'a7ba88b02d7099d99d0e6d1e702b2faee6b7a05e7e6e6a49c86c567184e5c780',
                        'gateway.mjs': '92e7f38f9eb53a5b140d0f3809b3381a4d35cea86bbb2e20229f108792ec30c8',
                        'git-publish.mjs': '9d50cd828e51d0c08a7be0ca7b18c89bfd8fb767a548bb1e4deaddaf185225ae',
                        'output-budget.mjs': '5fb464cdb531adf944561ddda760b77856530bcc08f7ba48ef774d6750f5a071',
                        'package-lock.json': '9a4e7398ddb45f44d6910fc05118bac425397f4b9869f33229da81f76ae262d0',
                        'package.json': '25ab096e21ac6e8c3761ee896e69d175ba628c1fe5751bcfab452c304a4bb634',
                        'paper-design.mjs': 'e2162584ceab9941e7bcce51b73120c9a9aeb13c128cd5b217077c005f0f1c7e',
                        'private-tunnel-auth.mjs': 'fe8c9e5ba14fd7750fc26bbfe45ed3f77d4b96fa8ff639c6b5efdf653740e1c0',
                        'private-tunnel-gateway.mjs': 'fd4eb541590cafc3c92a0b0ac1f7080baa76193704a2219e58b02462ef4d5540',
                        'tailnet-gateway.mjs': '9dd75992ba0b5c658582779ebeb71a06f13ec0a3475aa83d62753e22832b906b'},
 'chatgpt3-wa2a9e6f9': {'fleet-routing.mjs': 'dc98537e5ade635f5c9fa3a89ab99ae9ea57f549d2856832d01f90c1e61c1533',
                        'fleet-status.mjs': 'a7ba88b02d7099d99d0e6d1e702b2faee6b7a05e7e6e6a49c86c567184e5c780',
                        'gateway.mjs': '92e7f38f9eb53a5b140d0f3809b3381a4d35cea86bbb2e20229f108792ec30c8',
                        'git-publish.mjs': '9d50cd828e51d0c08a7be0ca7b18c89bfd8fb767a548bb1e4deaddaf185225ae',
                        'output-budget.mjs': '5fb464cdb531adf944561ddda760b77856530bcc08f7ba48ef774d6750f5a071',
                        'package-lock.json': '9a4e7398ddb45f44d6910fc05118bac425397f4b9869f33229da81f76ae262d0',
                        'package.json': '25ab096e21ac6e8c3761ee896e69d175ba628c1fe5751bcfab452c304a4bb634',
                        'paper-design.mjs': 'e2162584ceab9941e7bcce51b73120c9a9aeb13c128cd5b217077c005f0f1c7e',
                        'private-tunnel-auth.mjs': 'fe8c9e5ba14fd7750fc26bbfe45ed3f77d4b96fa8ff639c6b5efdf653740e1c0',
                        'private-tunnel-gateway.mjs': 'fd4eb541590cafc3c92a0b0ac1f7080baa76193704a2219e58b02462ef4d5540',
                        'tailnet-gateway.mjs': '9dd75992ba0b5c658582779ebeb71a06f13ec0a3475aa83d62753e22832b906b'},
 'fabric-design': {'fleet-status.mjs': 'a7ba88b02d7099d99d0e6d1e702b2faee6b7a05e7e6e6a49c86c567184e5c780',
                   'gateway.mjs': '970b47f1c6a15bc3f1175f1043c5dd4a59ad748c2374b586e384bbd6ba40ce5e',
                   'git-publish.mjs': '9d50cd828e51d0c08a7be0ca7b18c89bfd8fb767a548bb1e4deaddaf185225ae',
                   'output-budget.mjs': '5fb464cdb531adf944561ddda760b77856530bcc08f7ba48ef774d6750f5a071',
                   'package-lock.json': '9a4e7398ddb45f44d6910fc05118bac425397f4b9869f33229da81f76ae262d0',
                   'package.json': '25ab096e21ac6e8c3761ee896e69d175ba628c1fe5751bcfab452c304a4bb634',
                   'paper-design.mjs': 'e2162584ceab9941e7bcce51b73120c9a9aeb13c128cd5b217077c005f0f1c7e',
                   'private-tunnel-auth.mjs': 'fe8c9e5ba14fd7750fc26bbfe45ed3f77d4b96fa8ff639c6b5efdf653740e1c0',
                   'private-tunnel-gateway.mjs': '225b1a592f5486c688efc6f5fc37184877a7e3e8022c2e831858c8989c6cca00',
                   'tailnet-gateway.mjs': 'bd46b40cfd5f2744f9b07be38ff2656676939707e753f6e846f4a2c578944d25'},
 'fabric-read': {'fabric-operator.mjs': '2ed7578ced90da1e17a95faa4df2e43c164ade42e832d307efbb3902aed42a00',
                 'fleet-status.mjs': 'a7ba88b02d7099d99d0e6d1e702b2faee6b7a05e7e6e6a49c86c567184e5c780',
                 'gateway.mjs': '2a9038d802cdefeea3af4a3fbe45d2326fb894a42c72f3f4f946603419b93446',
                 'git-publish.mjs': '9d50cd828e51d0c08a7be0ca7b18c89bfd8fb767a548bb1e4deaddaf185225ae',
                 'output-budget.mjs': '5fb464cdb531adf944561ddda760b77856530bcc08f7ba48ef774d6750f5a071',
                 'package-lock.json': '9a4e7398ddb45f44d6910fc05118bac425397f4b9869f33229da81f76ae262d0',
                 'package.json': '25ab096e21ac6e8c3761ee896e69d175ba628c1fe5751bcfab452c304a4bb634',
                 'paper-design.mjs': 'e2162584ceab9941e7bcce51b73120c9a9aeb13c128cd5b217077c005f0f1c7e',
                 'private-tunnel-auth.mjs': 'fe8c9e5ba14fd7750fc26bbfe45ed3f77d4b96fa8ff639c6b5efdf653740e1c0',
                 'private-tunnel-gateway.mjs': '225b1a592f5486c688efc6f5fc37184877a7e3e8022c2e831858c8989c6cca00',
                 'tailnet-gateway.mjs': '89a3d1c972a31ab62f19205439d6f09bc24f4d51783ebc2e1bea788bcd9d817c'}}

# Retained sealed Tailnet seats, each with only its original and exact native
# pool-pin postimage. These are profile selectors, never an argv fallback.
_NATIVE_POOL_PIN_TAILNET_CANONICAL = {
    "fabric-design": frozenset((
        "87de91f4fd0d51571c2350cf4fe53704ad035eba8f095c13b09352732307671c",
        "a1c9117bfd3d210072b16aacd8f4b32e0c23ecf08eb28406d6218f7cf590a25c",
        "b08c021b6c3c9cd9a1acdd57957fbf5e88b6d63daa11b963b7476d993b1a8b46",
        "070cebf2c4b4bbd41eb7fd687347292e40e13519a98a303bafca13202e971e8c",
    )),
    "fabric-read": frozenset((
        "328c25399daf9ab16c994ea30bd4a628ef40483e5f9af89fe34f191ac4f48819",
        "6738294cefcca0be4d2696d51ebd41eb937e25a8515ca556f72c4b52d3f2f20c",
        "f39e118cb770d4f793dd92c31e9f17f7153e7daef4e9703be7408fde702d40bb",
        "32f76d5282f1187a3c355835bd5b34bb73f4e00fe05b9de9a84c958780ef9836",
    )),
}



# Fixed consumer contract of the existing control_bundle owner. This does not
# install, repair or select a bundle; source-worktree execution remains separate.
# The interpreter-selected bootstrap is trusted. This authenticates the retained
# dependency snapshot, not the already-loaded bootstrap generation.
CONTROL_BUNDLE_SCHEMA = "mastermind.studio_direct_control_bundle.v1"
CONTROL_BUNDLE_FILES = (
    "private_service.py",
    "private_tunnel_service.py",
    "studio_direct_control.py",
    "private_service_status_successor.py",
    "private_service_pin.py",
    "private_service_pin_enrollment.py",
    "paper_v20_fleet_cohorts.py",
    "ops/native_fabric/quota_continuity/rollout/native_install.py",
    "ops/native_fabric/quota_continuity/rollout/native_generation.py",
    "ops/fabric_launch/install.py",
    "fleet_git_failure_compat.py",
    "ops/native_fabric/quota_continuity/rollout/build_review_stage.py",
    "ops/native_fabric/quota_continuity/rollout/preimages/native_generation_75330d.py",
    "control_plane/provider_protocols.py",
    "ops/native_fabric/paid_canonical_glm/candidate/glm_shim.py",
    "ops/native_fabric/provider_plans/maintenance_guard/lease_broker.py.patch",
    "ops/native_fabric/provider_plans/maintenance_guard/remote_sub_exec.py.patch",
    "ops/native_fabric/provider_plans/memory118/fabric_memory_view.py",
    "ops/native_fabric/provider_plans/memory118/lease_broker.after-maintenance.py.patch",
    "ops/native_fabric/provider_plans/memory118/native_owner/fabric_operator_contract.py",
    "ops/native_fabric/provider_plans/memory118/native_owner/fabric_operator_owner.py",
    "ops/native_fabric/provider_plans/memory118/native_owner/protected_memory_economic.py",
    "ops/native_fabric/provider_plans/memory118/native_owner/provider_outcome.py",
    "ops/native_fabric/provider_plans/memory118/native_owner/run_observation_delivery.py",
    "ops/native_fabric/provider_plans/memory118_support_status/after_terminal_diagnostics/profile.json",
    "ops/native_fabric/provider_plans/memory118_support_status/artifact_delivery.py.patch",
    "ops/native_fabric/provider_plans/memory118_support_status/fabric_task.py.patch",
    "ops/native_fabric/provider_plans/patches/pick_remote_plan_modes.forward.patch",
    "ops/native_fabric/provider_plans/profile.json",
    "ops/native_fabric/provider_plans/remote_placement/profile.json",
    "ops/native_fabric/provider_plans/router_admission.json",
    "ops/native_fabric/provider_plans/terminal_diagnostics/component.json",
    "ops/native_fabric/provider_plans/terminal_diagnostics/current40/profile.json",
    "ops/native_fabric/provider_plans/terminal_diagnostics/native_plan_worker.py.forward.patch",
    "ops/native_fabric/quota_continuity/candidate/application_http_transports.py",
    "ops/native_fabric/quota_continuity/candidate/go_lease_capability.py",
    "ops/native_fabric/quota_continuity/candidate/go_lease_gateway.py",
    "ops/native_fabric/quota_continuity/candidate/go_shim.py",
    "ops/native_fabric/quota_continuity/candidate/lease_broker.py",
    "ops/native_fabric/quota_continuity/candidate/native_go_entry.py",
    "ops/native_fabric/quota_continuity/rollout/application_http_realm_projection.py",
    "ops/native_fabric/quota_continuity/rollout/preimages/glm_application_core_5c3d/go_lease_capability.py",
    "ops/native_fabric/quota_continuity/rollout/preimages/glm_application_core_5c3d/go_lease_gateway.py",
    "ops/native_fabric/quota_continuity/rollout/preimages/glm_application_core_5c3d/lease_broker.py",
    "ops/native_fabric/quota_continuity/rollout/provider_application/composition.json",
    "ops/native_fabric/quota_continuity/rollout/provider_application/maintenance_guard/experiential_bridge.py",
    "ops/native_fabric/quota_continuity/rollout/provider_application/maintenance_guard/experiential_host_context.py",
    "ops/native_fabric/quota_continuity/rollout/provider_application/maintenance_guard/experiential_plan_policy.py",
    "ops/native_fabric/quota_continuity/rollout/provider_application/maintenance_guard/experiential_transport.py",
    "ops/native_fabric/quota_continuity/rollout/provider_application/maintenance_guard/native40-profile.json",
    "ops/native_fabric/quota_continuity/rollout/provider_application/maintenance_guard/native40-provenance.json",
    "ops/native_fabric/quota_continuity/rollout/provider_application/maintenance_guard/native_plan_worker.py",
    "ops/native_fabric/quota_continuity/rollout/provider_application/memory_support/composition.json",
    "ops/native_fabric/quota_continuity/rollout/provider_application/memory_support/fabric_task.py.forward.patch",
    "ops/native_fabric/quota_continuity/rollout/provider_application/memory_support/lease_broker.py.forward.patch",
    "ops/native_fabric/quota_continuity/rollout/provider_application/remote-placement.json",
    "ops/native_fabric/quota_continuity/rollout/provider_application/terminal_diagnostics/composition.json",
    "ops/native_fabric/quota_continuity/rollout/provider_application/terminal_diagnostics/native_plan_worker.py.forward.patch",
    "ops/native_fabric/quota_continuity/source/application_http_transports.py.preimage",
    "ops/native_fabric/quota_continuity/source/codex_provider_realm.py.preimage",
    "ops/native_fabric/quota_continuity/source/glm_keys.py",
    "ops/native_fabric/quota_continuity/source/go_shim.py",
    "ops/native_fabric/support_policy_status/reader.py",
    "ops/native_fabric/provider_plans/fleet_launch_repair/profile.json",
    "ops/native_fabric/provider_plans/fleet_launch_repair/fabric_task.py.patch",
    "ops/native_fabric/provider_plans/fleet_launch_repair/lease_broker.py.patch",
    "ops/native_fabric/provider_plans/fleet_launch_repair/remote_sub.sh.patch",
    "ops/native_fabric/provider_plans/fleet_launch_repair/support_bundle.py.patch",
    "ops/native_fabric/quota_continuity/rollout/provider_application/fleet_launch_repair/composition.json",
    "ops/native_fabric/quota_continuity/rollout/provider_application/fleet_launch_repair/fabric_task.py.forward.patch",
    "ops/native_fabric/quota_continuity/rollout/provider_application/fleet_launch_repair/lease_broker.py.forward.patch",
    "ops/native_fabric/quota_continuity/rollout/provider_application/fleet_launch_repair/remote_sub.sh.forward.patch",
    "ops/native_fabric/quota_continuity/rollout/provider_application/fleet_launch_repair/support_bundle.py.forward.patch",
    "ops/native_fabric/quota_continuity/rollout/preimages/glm_application_core_5c3d/lease_broker_provider_memory.py",
)
# Exact inert pre-control-bundle snapshots observed on the original M2 host.
# These are NOT executable/source dependencies and confer no runtime authority.
# Preserve them without admission of arbitrary pre-* names or changed content.
HISTORICAL_CONTROL_BACKUPS = {
    'private_service.py.pre-exact-legacy-manifests-20261022': 'a184ca7f3408e20454adf4f1e5986add845b5742908efd9ed4e0f552755820bb',
    'private_service.py.pre-sealed-byte-validation-20261022': 'e636a728dbde6ca43b2248456aaabddbab8d78693066df7717030d07e757ebe4',
    'private_tunnel_service.py.pre-concurrency8-20261022': '4a7d425a2345eaf30b56ed1ca148e0afa2f8e474bd03e2453d4e0a9a4ef85467',
    'private_tunnel_service.py.pre-exact-sealed-roster-20261022': 'c3753a0c4167560a7980c366e707ce41153d93b8a8710ba4365ba9a45ff8d81f',
    'private_tunnel_service.py.pre-sealed-argv-20261022': 'b0449df0252159dbebed084ccc3d4520690ff811f0e30125d37ca8effb3e68fa',
    'studio_direct_control.py.pre-public-projection-20261022': '6fca63efd82132f3063d065d9757e10c22e7d4cef4b6549b24068b407bce912d',
}

_INSTALLED_CONTROL_CONTEXT = None


def _installed_control_layout(root):
    directories = {Path("."): {"manifest.json", ".control-bundle.lock"}}
    for name in CONTROL_BUNDLE_FILES:
        parts = Path(name).parts
        for index, part in enumerate(parts):
            parent = Path(*parts[:index])
            directories.setdefault(parent, set()).add(part)
            if index < len(parts) - 1:
                directories.setdefault(parent / part, set())
    for relative, expected in directories.items():
        directory = root / relative
        _assert_dest_safe(directory)
        info = directory.lstat()
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) != DIR_MODE):
            raise ValueError("unsafe installed control directory")
        observed = {path.name for path in directory.iterdir()}
        if relative == Path("."):
            for backup, expected_hash in HISTORICAL_CONTROL_BACKUPS.items():
                if backup not in observed:
                    continue
                historical = directory / backup
                info = historical.lstat()
                if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                        or info.st_nlink != 1 or stat.S_IMODE(info.st_mode) != FILE_MODE
                        or hashlib.sha256(_fabric_release_bytes(historical)).hexdigest() != expected_hash):
                    raise ValueError("unsealed installed historical backup")
                observed.remove(backup)
        if observed != expected:
            raise ValueError("unsealed installed control path")


def _installed_control_context():
    root = Path.home() / ".local/share/studio-direct-mcp/control"
    source = Path(os.path.abspath(__file__))
    invocation = Path(os.path.abspath(sys.argv[0])) if sys.argv else None
    def installed_origin(path):
        return tuple(part.casefold() for part in path.parent.parts[-4:]) == (
            ".local", "share", "studio-direct-mcp", "control")
    # Recognize installed-shaped origins independently of the current HOME,
    # including external aliases and case variants. They must never become a
    # source-worktree fallback. Genuine disjoint source execution is unchanged.
    origins = [source, source.resolve()]
    if invocation is not None:
        origins.extend((invocation, invocation.resolve()))
    if not any(installed_origin(path) for path in origins):
        return None
    fd = None
    try:
        if source != root / "private_service.py":
            raise ValueError("installed bootstrap origin differs")
        _assert_dest_safe(source)
        lock_path = root / ".control-bundle.lock"
        _assert_dest_safe(lock_path)
        fd = os.open(lock_path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK)
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                or info.st_nlink != 1 or stat.S_IMODE(info.st_mode) != FILE_MODE):
            raise ValueError("unsafe existing bundle lock")
        fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
        named = lock_path.lstat()
        if (info.st_dev, info.st_ino) != (named.st_dev, named.st_ino):
            raise ValueError("existing bundle lock changed")
        _installed_control_layout(root)

        def unique(pairs):
            value = {}
            for key, item in pairs:
                if key in value:
                    raise ValueError("duplicate control manifest key")
                value[key] = item
            return value

        manifest_path = root / "manifest.json"
        raw = _fabric_release_bytes(manifest_path, limit=64 * 1024)
        if stat.S_IMODE(manifest_path.lstat().st_mode) != FILE_MODE:
            raise ValueError("unsafe control manifest mode")
        manifest = json.loads(raw.decode("utf-8"), object_pairs_hook=unique)
        if (type(manifest) is not dict
                or set(manifest) != {"schema", "files", "launcher", "launcherHash",
                                     "bundleDigest", "source"}
                or manifest["schema"] != CONTROL_BUNDLE_SCHEMA):
            raise ValueError("control manifest differs")
        files = manifest["files"]
        if (type(files) is not dict or set(files) != set(CONTROL_BUNDLE_FILES)
                or not all(_sha256_hex(value) for value in files.values())):
            raise ValueError("incomplete control closure")
        launcher = Path.home() / ".local/bin/studio-direct"
        if (manifest["launcher"] != str(launcher)
                or not _sha256_hex(manifest["launcherHash"])
                or not _sha256_hex(manifest["bundleDigest"])
                or not isinstance(manifest["source"], str)
                or not Path(manifest["source"]).is_absolute()):
            raise ValueError("control provenance differs")
        launcher_bytes = _fabric_release_bytes(launcher, limit=64 * 1024)
        if (not launcher.lstat().st_mode & stat.S_IXUSR
                or hashlib.sha256(launcher_bytes).hexdigest() != manifest["launcherHash"]
                or _canonical_json_sha256({
                    "files": files, "launcherHash": manifest["launcherHash"],
                }) != manifest["bundleDigest"]):
            raise ValueError("control bundle digest differs")
        payloads = {}
        for name in CONTROL_BUNDLE_FILES:
            path = root / name
            payloads[name] = _fabric_release_bytes(path)
            if (stat.S_IMODE(path.lstat().st_mode) != FILE_MODE
                    or hashlib.sha256(payloads[name]).hexdigest() != files[name]):
                raise ValueError("control code differs")
        # Keep the original owner's shared lock for the entire helper process.
        # Its existing installer cannot replace files during native imports.
        return {"root": root, "files": payloads, "lock_fd": fd}
    except (OSError, ValueError, TypeError, SystemExit):
        if fd is not None:
            os.close(fd)
        raise SystemExit("CONTROL_BUNDLE_CLOSURE_REFUSED") from None
    except BaseException:
        if fd is not None:
            os.close(fd)
        raise


def _installed_control_module(name, relative, *, register=False):
    import importlib.util
    context = _INSTALLED_CONTROL_CONTEXT
    if context is None or relative not in CONTROL_BUNDLE_FILES:
        raise SystemExit("CONTROL_BUNDLE_CLOSURE_REFUSED")
    path = context["root"] / relative
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    previous = sys.modules.get(name)
    if register:
        sys.modules[name] = module
    try:
        exec(compile(context["files"][relative], str(path), "exec"), module.__dict__)
    except BaseException:
        if register:
            if previous is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = previous
        raise
    return module


def _pin_owner_module():
    if _INSTALLED_CONTROL_CONTEXT is not None:
        return _installed_control_module("_studio_pin_owner", "private_service_pin.py")
    import importlib.util
    path = Path(__file__).resolve().with_name("private_service_pin.py")
    spec = importlib.util.spec_from_file_location("_studio_pin_owner", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _fleet_status_successor_owner_module():
    if _INSTALLED_CONTROL_CONTEXT is not None:
        return _installed_control_module("_studio_status_successor_owner", "private_service_status_successor.py", register=True)
    import importlib.util
    path = Path(__file__).resolve().with_name("private_service_status_successor.py")
    spec = importlib.util.spec_from_file_location("_studio_status_successor_owner", path)
    owner = importlib.util.module_from_spec(spec)
    # Frozen dataclasses introspect their live defining module during import.
    sys.modules[spec.name] = owner
    spec.loader.exec_module(owner)
    return owner


def cmd_fleet_status_module_upgrade(args):
    owner = _fleet_status_successor_owner_module()
    value = owner.run(sys.modules[__name__], args)
    print(json.dumps(value, sort_keys=True))
    return 0


def _pin_enrollment_owner_module():
    if _INSTALLED_CONTROL_CONTEXT is not None:
        return _installed_control_module("_studio_pin_enrollment_owner", "private_service_pin_enrollment.py")
    import importlib.util
    path = Path(__file__).resolve().with_name("private_service_pin_enrollment.py")
    spec = importlib.util.spec_from_file_location("_studio_pin_enrollment_owner", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _fleet_git_failure_compat_module():
    """Load the deterministic source compiler for the one C1 gateway successor.

    The compiler is pure source code: it decides whether a byte sequence is
    exactly the reviewed predecessor and returns the exact accepted successor
    bytes. It never touches a host, an installed directory or a live effect.
    """
    if _INSTALLED_CONTROL_CONTEXT is not None:
        return _installed_control_module(
            "_studio_fleet_git_failure_compat", "fleet_git_failure_compat.py")
    import importlib.util
    path = Path(__file__).resolve().with_name("fleet_git_failure_compat.py")
    spec = importlib.util.spec_from_file_location("_studio_fleet_git_failure_compat", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def cmd_native_pool_pin_enrollment(args):
    owner = _pin_enrollment_owner_module()
    try:
        value = owner.run(sys.modules[__name__], args)
    except SystemExit as error:
        if type(error.code) is str and error.code in {
            "NATIVE_PIN_ENROLLMENT_" + code for code in owner.REFUSAL_CODES
        }:
            raise
        raise SystemExit("NATIVE_PIN_ENROLLMENT_OWNER_REFUSED") from None
    except (OSError, ValueError, KeyError, TypeError, RecursionError):
        raise SystemExit("NATIVE_PIN_ENROLLMENT_OWNER_REFUSED") from None
    print(json.dumps(value, sort_keys=True))
    return 0


def cmd_native_pool_pin(args):
    pin = _pin_owner_module()
    try:
        value = pin.run(sys.modules[__name__], args)
    except SystemExit as error:
        allowed = {"NATIVE_POOL_PIN_" + code for code in pin.REFUSAL_CODES}
        allowed.update(("NATIVE_POOL_PIN_SUCCESSOR_REFUSED", "NATIVE_POOL_PIN_SUCCESSOR_CHANGED"))
        if type(error.code) is str and error.code in allowed:
            raise
        raise SystemExit("NATIVE_POOL_PIN_OWNER_REFUSED") from None
    except (OSError, ValueError, KeyError, TypeError, RecursionError):
        raise SystemExit("NATIVE_POOL_PIN_OWNER_REFUSED") from None
    print(json.dumps(value, sort_keys=True))
    return 0


def cmd_native_pool_pin_forward(args):
    """Dispatch the one closed forward Go bridge pin transaction.

    The incumbent original pin owner keeps its own command, plan, receipt and
    artifact set. This companion adds no second transaction to that record and
    no new lifecycle, registry or credential path.
    """
    pin = _pin_owner_module()
    try:
        value = pin.run_forward(sys.modules[__name__], args)
    except SystemExit as error:
        allowed = {"NATIVE_POOL_PIN_FORWARD_" + code for code in pin.FORWARD_REFUSAL_CODES}
        if type(error.code) is str and error.code in allowed:
            raise
        raise SystemExit("NATIVE_POOL_PIN_FORWARD_OWNER_REFUSED") from None
    except (OSError, ValueError, KeyError, TypeError, RecursionError):
        raise SystemExit("NATIVE_POOL_PIN_FORWARD_OWNER_REFUSED") from None
    print(json.dumps(value, sort_keys=True))
    return 0


@contextmanager
def _native_selected_publication_lock_for_publisher(account):
    """Hold the existing selected native-generation lock throughout a publisher CAS.

    Retained bootstrap evidence may have been pruned. The incumbent read-only
    status verifier already authenticates those selected bytes; use its exact
    store to acquire the SAME existing publication lock, then verify again.
    Never create a second lock, install a generation or change a pool pointer.
    """
    if account != "chatgpt2-personal":
        raise SystemExit("NATIVE_POOL_PIN_ACCOUNT_REFUSED")
    from types import SimpleNamespace
    pin = _pin_owner_module()
    roots = _build_runtime_roots(account)
    plan = pin.decode(_fabric_release_bytes(
        roots["state"] / "native-pool-pin" / "plan.json"))
    args = SimpleNamespace(
        account=account, operation="status",
        successor_bundle=plan["successor_bundle"],
        successor_plan_sha256=plan["successor_digest"],
        retained_proof_purpose="")
    with _pin_native_context(args) as before:
        if before["phase"] != "SELECTED":
            raise SystemExit("NATIVE_POOL_PIN_SUCCESSOR_REFUSED")
    import importlib.util
    if _INSTALLED_CONTROL_CONTEXT is not None:
        native = _installed_control_module(
            "_studio_pin_pub_generation",
            "ops/native_fabric/quota_continuity/rollout/native_generation.py")
    else:
        path = (Path(__file__).resolve().parents[2] /
                "ops/native_fabric/quota_continuity/rollout/native_generation.py")
        spec = importlib.util.spec_from_file_location("_studio_pin_pub_generation", path)
        native = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(native)
    with native.publication_lock(Path(before["store"])):
        with _pin_native_context(args) as after:
            if after != before:
                raise SystemExit("NATIVE_POOL_PIN_SUCCESSOR_CHANGED")
        yield


def cmd_native_pool_pin_publisher(args):
    """Use only the existing selected-pin owner for a sealed C2 publisher update."""
    pin = _pin_owner_module()
    try:
        value = pin.run_publisher(sys.modules[__name__], args)
    except SystemExit as error:
        if type(error.code) is str and error.code in {
            "NATIVE_POOL_PIN_" + code for code in pin.REFUSAL_CODES
        }:
            raise
        raise SystemExit("NATIVE_POOL_PIN_PUBLISHER_OWNER_REFUSED") from None
    except (OSError, ValueError, KeyError, TypeError, RecursionError):
        raise SystemExit("NATIVE_POOL_PIN_PUBLISHER_OWNER_REFUSED") from None
    print(json.dumps(value, sort_keys=True))
    return 0


@contextmanager
def _pin_native_context(args):
    """Use the existing successor verifier and publication lock, never a hash-only claim."""
    import importlib.util
    context = _INSTALLED_CONTROL_CONTEXT
    code_root = context["root"] if context is not None else Path(__file__).resolve().parents[2]
    rollout = code_root / "ops/native_fabric/quota_continuity/rollout"
    python_flags = ["-I", "-S", "-B"] if context is not None else ["-I", "-B"]
    for name in ("native_install.py", "native_generation.py"):
        source = rollout / name
        if source.is_symlink() or not source.is_file():
            raise SystemExit("NATIVE_POOL_PIN_SUCCESSOR_REFUSED")
    code = r"""
import json,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
import native_install as i
import native_generation as g
try:
 p,payload=i.read_successor(Path(sys.argv[2]))
except FileNotFoundError:
 # Status may read one completed historical pin after its bootstrap artifact
 # was pruned. The same retained reader is the artifact check for the closed
 # chatgpt1 gateway formatter, on both preview and apply. Generic native
 # apply/reconcile stay on the strict reader and remain refused.
 purpose=sys.argv[6] if len(sys.argv)>6 else ''
 closed=(purpose=='c1-gateway-preserving-formatter' and sys.argv[4]=='chatgpt1' and sys.argv[5] in ('preview','apply'))
 if purpose and not closed:raise
 if sys.argv[5]!='status' and not closed:raise
 p,payload=i.read_retained_successor_after_bootstrap_prune(Path(sys.argv[2]))
assert p['digest']==sys.argv[3]
store=Path(p['store']);current=g.current(store);old=p['expected_selection']
new={'schema':g.POINTER_SCHEMA,'generation':p['target_generation'],'previous':old['generation'],'sequence':old['sequence']+1}
e=p['entries']['pool']
if current==old:
 i._upgrade_entries(p);phase='PREVIOUS'
elif current==new:
 i._upgrade_entries(p,complete=True);phase='SELECTED'
elif (sys.argv[4] in (
        'admin-business', 'chatgpt1', 'chatgpt2-business', 'chatgpt2-personal',
        'chatgpt3', 'chatgpt3-w570f6f34', 'chatgpt3-wa2a9e6f9', 'chatgpt4')
      and p['digest']=='77c2c136852a783a1e2572c145af7536ee6cd0d7f443daa4c09795c333fd3dc7'
      and new['generation']=='28faaf101463bcabef578ab1acabdcd270e301c7ed9cedf294e82fd459ccfcce'
      and new['sequence']==24
      and isinstance(current,dict)
      and current.get('schema')==g.POINTER_SCHEMA
      and type(current.get('sequence')) is int
      and current['sequence']>new['sequence']
      and current.get('previous') not in (None,current.get('generation'))):
 # All eight reviewed public-seat native pins share this completed immutable
 # sequence-24 successor (including the non-Paper-v20 personal profile).
 # Later native releases do not invalidate historical ingress, but only
 # these eight exact accounts admit verified forward selection.
 g.verify(store,new['generation'])
 g.verify(store,current['generation'])
 g.verify(store,current['previous'])
 i._upgrade_entries(p,complete=True)
 phase='SELECTED'
else:raise ValueError('selection_refused')
# Include the exact selected pointer in both lock-bound proofs. Without it,
# a sequence-26 -> sequence-27 change could masquerade as identical SELECTED.
print(json.dumps({'successor_digest':p['digest'],'target_generation':p['target_generation'],'expected_selection':old,'pool_target':e['target'],'pool_previous':e['previous'],'pool_bridge':e['bridge'],'store':p['store'],'phase':phase,'selection':current},sort_keys=True))
"""
    if (C1_GATEWAY_RETAINED_PROOF_PURPOSE not in code
            or C1_GIT_FAILURE_COMPAT_ACCOUNT not in code):
        raise SystemExit("NATIVE_POOL_PIN_SUCCESSOR_REFUSED")
    purpose = getattr(args, "retained_proof_purpose", None) or ""
    if purpose and (
            purpose != C1_GATEWAY_RETAINED_PROOF_PURPOSE
            or args.account != C1_GIT_FAILURE_COMPAT_ACCOUNT
            or args.operation not in ("preview", "apply")):
        raise SystemExit("NATIVE_POOL_PIN_SUCCESSOR_REFUSED")
    def proof():
        try:
            r = subprocess.run([sys.executable, *python_flags, "-c", code, str(rollout),
                str(args.successor_bundle), args.successor_plan_sha256, args.account,
                args.operation, purpose],
                capture_output=True, timeout=30)
        except (OSError, subprocess.SubprocessError):
            raise SystemExit("NATIVE_POOL_PIN_SUCCESSOR_REFUSED") from None
        if r.returncode != 0 or len(r.stdout) > 16384:
            raise SystemExit("NATIVE_POOL_PIN_SUCCESSOR_REFUSED")
        value = _pin_owner_module().decode(r.stdout)
        if set(value) != {"successor_digest", "target_generation", "expected_selection",
                "pool_target", "pool_previous", "pool_bridge", "store", "phase", "selection"}:
            raise SystemExit("NATIVE_POOL_PIN_SUCCESSOR_REFUSED")
        return value
    first = proof()
    if context is not None:
        generation = _installed_control_module(
            "_studio_pin_native_generation",
            "ops/native_fabric/quota_continuity/rollout/native_generation.py")
    else:
        spec = importlib.util.spec_from_file_location("_studio_pin_native_generation", rollout / "native_generation.py")
        generation = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(generation)
    from contextlib import nullcontext
    lock = (generation.publication_lock(Path(first["store"]))
            if args.operation in ("apply", "reconcile") else nullcontext())
    with lock:
        checked = proof()
        if checked != first:
            raise SystemExit("NATIVE_POOL_PIN_SUCCESSOR_CHANGED")
        yield checked


@contextmanager
def _pin_forward_native_context(args):
    """Bind the forward transition to the authentic retained-Go artifact.

    This is the same isolated proof shape as the incumbent successor proof: it
    imports the actual native owners, authenticates the retained Go artifact
    with the strict reader and observes the committed phase. It never applies,
    repairs, retries or relabels a native transition, and it never trusts a
    caller supplied digest, path or pointer.
    """
    import importlib.util
    context = _INSTALLED_CONTROL_CONTEXT
    code_root = context["root"] if context is not None else Path(__file__).resolve().parents[2]
    rollout = code_root / "ops/native_fabric/quota_continuity/rollout"
    python_flags = ["-I", "-S", "-B"] if context is not None else ["-I", "-B"]
    for name in ("native_install.py", "native_generation.py"):
        source = rollout / name
        if source.is_symlink() or not source.is_file():
            raise SystemExit("NATIVE_POOL_PIN_FORWARD_GO_REFUSED")
    code = r"""
import json,os,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
import native_install as i
import native_generation as g
bundle=Path(sys.argv[2])
# The strict reader authenticates the artifact identity exactly once. It is
# never used as an inspection channel and never falls back to another chain.
envelope=i._successor_json(bundle/'PLAN.json')
schema=envelope.get('schema') if type(envelope) is dict else None
if schema==i.GO_SCHEMA:
    plan,payloads=i.read_go(bundle)
    prior_bundle,prior,_,_,_=i._completed_successor(plan['prior_successor_bundle'])
elif schema==i.GO_RETAINED_SCHEMA:
    plan,payloads=i.read_retained_go(bundle)
    historical=i._retained_successor_evidence(plan['prior_successor_bundle'],
        original_absent=True,current_bridges=False)
    prior_bundle,prior=historical['bundle'],historical['plan']
else:
    raise ValueError('unsupported Go ingress schema')
if (prior['digest']!=plan['prior_successor_digest'] or
    Path(prior_bundle).resolve()!=Path(plan['prior_successor_bundle']).resolve()):
    raise ValueError('Go predecessor differs')
prior_entry=prior['entries']['pool']
original_successor={
 'successor_bundle':str(prior_bundle),'successor_digest':prior['digest'],
 'target_generation':prior['target_generation'],
 'expected_selection':prior['expected_selection'],
 'pool_target':prior_entry['target'],'pool_previous':prior_entry['previous'],
 'pool_bridge':prior_entry['bridge'],
}
store=Path(plan['store'])
entry=plan['entries']['pool']
previous=plan['expected_selection']
selected={'schema':g.POINTER_SCHEMA,'generation':plan['target_generation'],
          'previous':previous['generation'],'sequence':previous['sequence']+1}
# The completed Go ingress proof is authoritative for the committed phase.
completed=False
try:
    i._completed_go_for_service(bundle)
    completed=True
except (ValueError,OSError,KeyError,TypeError):
    completed=False
if completed:
    phase='SELECTED'
    if g.current(store)!=selected:
        raise ValueError('selection differs from the completed Go ingress')
else:
    # An unresolved or unacknowledged Go transaction is not absence and can
    # never authorize a new forward preparation.
    receipts=store/'bootstrap'
    if os.path.lexists(receipts/'.go-application-ingress-v1.json'):
        raise ValueError('unresolved Go transaction')
    if os.path.lexists(receipts/(plan['digest']+'.go.json')):
        raise ValueError('unacknowledged Go transaction')
    if g.current(store)!=previous:
        raise ValueError('selection compare-and-swap refused')
    # The old Go ingress bytes must still be the exact preimages.
    i._upgrade_entries(plan)
    phase='PREVIOUS'
print(json.dumps({
 'original_successor':original_successor,
 'go_digest':plan['digest'],'go_schema':plan['schema'],
 'go_generation':plan['target_generation'],
 'go_expected_selection':plan['expected_selection'],
 'go_bootstrap_digest':plan['bootstrap_digest'],
 'go_prior_successor_digest':plan['prior_successor_digest'],
 'go_component_sha256':plan['component_sha256'],
 'go_manifest_sha256':plan['manifest_sha256'],
 'pool_target':entry['target'],'pool_previous':entry['previous'],
 'pool_bridge':entry['bridge'],'store':plan['store'],'phase':phase,
},sort_keys=True))
"""
    def proof():
        try:
            r = subprocess.run([sys.executable, *python_flags, "-c", code, str(rollout),
                str(args.forward_go_bundle)], capture_output=True, timeout=60)
        except (OSError, subprocess.SubprocessError):
            raise SystemExit("NATIVE_POOL_PIN_FORWARD_GO_REFUSED") from None
        if r.returncode != 0 or len(r.stdout) > 16384:
            raise SystemExit("NATIVE_POOL_PIN_FORWARD_GO_REFUSED")
        value = _pin_owner_module().decode(r.stdout)
        if set(value) != {
            "original_successor",
            "go_digest", "go_schema", "go_generation", "go_expected_selection",
            "go_bootstrap_digest", "go_prior_successor_digest",
            "go_component_sha256", "go_manifest_sha256", "pool_target",
            "pool_previous", "pool_bridge", "store", "phase",
        }:
            raise SystemExit("NATIVE_POOL_PIN_FORWARD_GO_REFUSED")
        if value["phase"] not in ("PREVIOUS", "SELECTED"):
            raise SystemExit("NATIVE_POOL_PIN_FORWARD_GO_REFUSED")
        return value
    first = proof()
    if context is not None:
        generation = _installed_control_module(
            "_studio_pin_forward_native_generation",
            "ops/native_fabric/quota_continuity/rollout/native_generation.py")
    else:
        spec = importlib.util.spec_from_file_location(
            "_studio_pin_forward_native_generation", rollout / "native_generation.py")
        generation = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(generation)
    from contextlib import nullcontext
    lock = (generation.publication_lock(Path(first["store"]))
            if args.operation in ("apply", "reconcile") else nullcontext())
    with lock:
        checked = proof()
        if checked != first:
            raise SystemExit("NATIVE_POOL_PIN_FORWARD_GO_CHANGED")
        yield checked


def _pin_reject_generic_restage(account):
    # The newly recognized cohort receives only preserving lifecycle/pin support.
    # It does not silently acquire the generic capability-rebuilding upgrade path.
    if account not in NATIVE_POOL_PIN_ACCOUNTS:
        return
    _validate_account_label(account)
    roots = _build_runtime_roots(account)
    if os.path.lexists(roots["state"] / "native-pool-pin"):
        raise SystemExit("NATIVE_POOL_PIN_PROFILE_REQUIRES_PIN_OWNER")
    if account not in NATIVE_POOL_PIN_PREDECESSORS:
        return
    if not os.path.lexists(roots["manifest"]):
        return
    prior = _read_manifest(roots["manifest"], account,
        "com.mastermind.studio-direct-private." + account, required=True)
    if prior["files"] == NATIVE_POOL_PIN_PREDECESSORS[account]:
        raise SystemExit("NATIVE_POOL_PIN_PROFILE_REQUIRES_PIN_OWNER")


def _pin_require_start(account, roots):
    if account not in NATIVE_POOL_PIN_ACCOUNTS:
        return
    if os.path.lexists(roots["state"] / "native-pool-pin-forward"):
        # The forward owner authenticates every incumbent predecessor against
        # its retained before bytes, then the exact live after pair and Go.
        _pin_owner_module().require_start(sys.modules[__name__], account, roots)
        return
    if os.path.lexists(roots["state"] / "fleet-status-module-successor"):
        owner = _fleet_status_successor_owner_module()
        if owner.require_start(sys.modules[__name__], account, roots):
            return
        raise SystemExit("FLEET_STATUS_SUCCESSOR_START_REFUSED")
    if account in ("chatgpt4", "admin-business", "chatgpt3-w570f6f34", "chatgpt3-wa2a9e6f9") and os.path.lexists(roots["state"] / "native-pool-pin-enrollment"):
        _pin_enrollment_owner_module().require_start(sys.modules[__name__], account, roots)
        return
    _pin_owner_module().require_start(sys.modules[__name__], account, roots)


@contextmanager
def _c2_lifecycle_mutex(account: str):
    """Serialize enrolled Paper and Fabric mutations on persistent private lock inodes.

    Never unlink this file: replacement would let another invocation lock a new
    inode while the previous one is still held. Closing the descriptor (including
    process exit) releases the lock, and CLOEXEC prevents launchctl inheriting it.
    """
    if account not in (PAPER_RUNTIME_UPGRADE_ACCOUNTS | FABRIC_BACKEND_ACCOUNTS
                       | {"chatgpt2-business", M1_PAPER_V20_ACCOUNT, "mastermind-os-publication"}
                       | NATIVE_POOL_PIN_ACCOUNTS):
        raise SystemExit("C2 lifecycle mutex cannot select another account")
    subject = ("Fabric" if account in FABRIC_BACKEND_ACCOUNTS
               else "M1 Paper" if account == M1_PAPER_V20_ACCOUNT else "C2")
    lock_path = _build_runtime_roots(account)["state"] / C2_LIFECYCLE_LOCK_NAME
    _assert_dest_safe(lock_path)
    current = lock_path.parent
    home = _user_root()
    while True:
        try:
            info = current.lstat()
        except OSError as exc:
            raise SystemExit(f"{subject} lifecycle lock parent is unavailable") from exc
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) & 0o022
                or (current == lock_path.parent and stat.S_IMODE(info.st_mode) & 0o077)):
            raise SystemExit(f"{subject} lifecycle lock parent is unsafe")
        if current == home:
            break
        current = current.parent
    try:
        fd = os.open(lock_path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC, FILE_MODE)
    except OSError as exc:
        raise SystemExit(f"{subject} lifecycle lock is unavailable") from exc
    try:
        def verify_inode():
            held = os.fstat(fd)
            _assert_dest_safe(lock_path)
            named = lock_path.lstat()
            if (not stat.S_ISREG(held.st_mode) or held.st_uid != os.getuid()
                    or stat.S_IMODE(held.st_mode) != FILE_MODE or held.st_nlink != 1
                    or held.st_size != 0 or (held.st_dev, held.st_ino) != (named.st_dev, named.st_ino)):
                raise SystemExit(f"{subject} lifecycle lock inode is unsafe or changed")
        verify_inode()
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise SystemExit(f"{subject} lifecycle mutation already in progress; refusing concurrent operation") from exc
        except OSError as exc:
            raise SystemExit(f"{subject} lifecycle lock could not be acquired") from exc
        verify_inode()
        yield
    finally:
        os.close(fd)


def _c2_lifecycle_serialized(*, readonly_preflight: bool = False):
    def decorate(function):
        @wraps(function)
        def guarded(args):
            fleet_selection = getattr(args, "fleet_v20", False) is True
            if fleet_selection and args.account not in FLEET_V20_ENROLLED_ACCOUNTS:
                # Let the source owner issue the normal typed refusal before
                # any unrelated account lifecycle lock inode can be created.
                return function(args)
            if ((args.account not in PAPER_RUNTIME_UPGRADE_ACCOUNTS and not fleet_selection)
                    or (readonly_preflight and getattr(args, "preflight_only", False) is True)):
                return function(args)
            with _c2_lifecycle_mutex(args.account):
                return function(args)
        return guarded
    return decorate


def _fabric_lifecycle_serialized(*, readonly_preflight: bool = False):
    """Only the two enrolled Fabric seats share their release locks with lifecycle calls."""
    def decorate(function):
        @wraps(function)
        def guarded(args):
            if (args.account not in FABRIC_BACKEND_ACCOUNTS
                    or (readonly_preflight and getattr(args, "preflight_only", False) is True)):
                return function(args)
            # First-install staging predates a runtime/state directory. There can
            # be no backend release until that first manifest exists.
            if (function.__name__ == "cmd_stage"
                    and not _build_runtime_roots(args.account)["state"].exists()):
                return function(args)
            with _c2_lifecycle_mutex(args.account):
                return function(args)
        return guarded
    return decorate


def _pin_lifecycle_serialized(function):
    """Extend only normal lifecycle calls, without changing Paper eligibility gates."""
    @wraps(function)
    def guarded(args):
        covered = PAPER_RUNTIME_UPGRADE_ACCOUNTS | FABRIC_BACKEND_ACCOUNTS
        if args.account not in NATIVE_POOL_PIN_ACCOUNTS or args.account in covered:
            return function(args)
        with _c2_lifecycle_mutex(args.account):
            return function(args)
    return guarded


def _pin_install_serialized(function):
    """The existing installer mutates under the same pin/lifecycle lock."""
    @wraps(function)
    def guarded(source, node_abs, backend_abs, account, label, host, port, roots, **kwargs):
        if account not in NATIVE_POOL_PIN_ACCOUNTS or not os.path.lexists(roots["manifest"]):
            return function(source, node_abs, backend_abs, account, label, host, port, roots, **kwargs)
        before = _fabric_release_bytes(roots["manifest"])
        with _c2_lifecycle_mutex(account):
            if _fabric_release_bytes(roots["manifest"]) != before:
                raise SystemExit("NATIVE_POOL_PIN_INSTALL_CAS_REFUSED")
            _pin_reject_generic_restage(account)
            return function(source, node_abs, backend_abs, account, label, host, port, roots, **kwargs)
    return guarded


def _typed_git_config(user_root: Path, *, closed_repositories: bool = False) -> dict:
    common = {
        "enabled": True,
        "workspaceCli": str(user_root / TYPED_GIT_WORKSPACE_CLI_REL),
        "gitBinary": TYPED_GIT_BINARY,
        "commandTimeoutMs": 15_000,
        "pushTimeoutMs": 60_000,
    }
    if closed_repositories:
        return {
            **common,
            "repositories": [
                {
                    "repository": alias,
                    "sourceRepository": str(user_root / source),
                    "allowedRemoteUrls": [remote],
                }
                for alias, source, remote in TYPED_GIT_CLOSED_PROFILES
            ],
        }
    return {
        **common,
        "sourceRepository": str(user_root / TYPED_GIT_SOURCE_REPOSITORY_REL),
        "allowedRemoteUrls": [TYPED_GIT_REMOTE_URL],
    }


PAPER_RUNTIME_V22_REL = Path(".local/share/mastermind-paper/runtime/v22")
PAPER_RUNTIME_V22_BRIDGE_SHA256 = "af03759abbb493155ba32802a769b27699c672be716c1d29b1cab5b3b68a778b"


def _verify_paper_runtime(
    user_root: Path, *, expected_sha: str | None = None,
    runtime_rel: Path | None = None, rel: Path | None = None,
) -> dict:
    # One owner, two reviewed callers: M1 uses runtime_rel; C2 uses rel.
    if runtime_rel == PAPER_RUNTIME_V22_REL or rel == PAPER_RUNTIME_V22_REL:
        if (runtime_rel != PAPER_RUNTIME_V22_REL or rel != PAPER_RUNTIME_V22_REL
                or expected_sha != PAPER_RUNTIME_V22_BRIDGE_SHA256):
            raise SystemExit("Paper v22 requires the exact reviewed runtime and bridge")

    if runtime_rel is not None and rel is not None and runtime_rel != rel:
        raise SystemExit("Paper runtime conflicting generation selectors")
    runtime_rel = runtime_rel or rel or PAPER_RUNTIME_REL
    if runtime_rel not in (PAPER_RUNTIME_REL, M1_PAPER_V5_RUNTIME_REL, M1_PAPER_V20_RUNTIME_REL, PAPER_RUNTIME_V20_REL, PAPER_RUNTIME_V10_REL, PAPER_RUNTIME_V22_REL):
        raise SystemExit("paper runtime generation is not an admitted target")
    if runtime_rel == M1_PAPER_V5_RUNTIME_REL:
        fixed_sha = M1_PAPER_V5_BRIDGE_SHA256
    elif runtime_rel == PAPER_RUNTIME_V10_REL:
        fixed_sha = PAPER_V10_BRIDGE_SHA256
    elif runtime_rel in (M1_PAPER_V20_RUNTIME_REL, PAPER_RUNTIME_V20_REL):
        # These constants are the same approved bridge in source, but individual
        # hermetic tests deliberately mock their owner's expected bridge bytes.
        allowed_sha = (M1_PAPER_V20_BRIDGE_SHA256, PAPER_V20_BRIDGE_SHA256)
        if expected_sha is None:
            expected_sha = M1_PAPER_V20_BRIDGE_SHA256
        if expected_sha not in allowed_sha:
            raise SystemExit("Paper exact runtime bridge SHA mismatch")
        fixed_sha = expected_sha
    else:
        fixed_sha = None
    if runtime_rel in (M1_PAPER_V5_RUNTIME_REL, PAPER_RUNTIME_V10_REL):
        if expected_sha not in (None, fixed_sha):
            raise SystemExit("Paper exact runtime bridge SHA mismatch")
        expected_sha = fixed_sha
    elif fixed_sha is None:
        expected_sha = PAPER_BRIDGE_SHA256 if expected_sha is None else expected_sha
    runtime = user_root / runtime_rel
    source = runtime / "source"
    bridge = source / "bridge.py"
    receipt_path = runtime / "RUNTIME.json"
    python = runtime / "venv" / "bin" / "python"

    for path, label in ((runtime, "runtime"), (source, "source")):
        if path.is_symlink() or not path.is_dir():
            raise SystemExit(f"paper {label} missing or unsafe: {path}")
        info = path.stat()
        if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077:
            raise SystemExit(f"paper {label} permissions/owner are unsafe: {path}")

    for path, label in ((bridge, "bridge"), (receipt_path, "receipt")):
        if path.is_symlink() or not path.is_file():
            raise SystemExit(f"paper {label} missing or unsafe: {path}")
        info = path.stat()
        if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077:
            raise SystemExit(f"paper {label} permissions/owner are unsafe: {path}")

    if python.is_symlink() or not python.is_file() or not os.access(python, os.X_OK):
        raise SystemExit(f"paper runtime python missing or unsafe: {python}")
    if _sha256_file(bridge) != expected_sha:
        raise SystemExit("paper bridge hash mismatch")

    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit("paper runtime receipt invalid") from exc
    expected_sources = {"bridge.py": expected_sha}
    if (
        not isinstance(receipt, dict)
        or receipt.get("schema") != PAPER_RUNTIME_SCHEMA
        or receipt.get("generation") != runtime_rel.name
        or receipt.get("bridge_sha256") != expected_sha
        or receipt.get("source_sha256") != expected_sources
        or receipt.get("network_install_performed") is not False
        or receipt.get("production_acceptance") is not False
    ):
        raise SystemExit("paper runtime receipt does not match the required generation")
    return receipt


def _paper_design_config(
    user_root: Path, *,
    rel: Path | None = None, bridge_sha256: str | None = None,
) -> dict:
    runtime = user_root / (PAPER_RUNTIME_REL if rel is None else rel)
    bridge_sha256 = PAPER_BRIDGE_SHA256 if bridge_sha256 is None else bridge_sha256
    return {
        "enabled": True,
        "pythonPath": str(runtime / "venv" / "bin" / "python"),
        "bridgePath": str(runtime / "source" / "bridge.py"),
        "bridgeSha256": bridge_sha256,
        "appPath": str(user_root / PAPER_APP_REL),
        "commandTimeoutMs": PAPER_COMMAND_TIMEOUT_MS,
    }


def _publication_upgrade_paper_config(
    account: str, previous_config: dict, user_root: Path,
) -> dict | None:
    """Retain the fixed publication seat's qualified, already selected v20."""
    if account != "mastermind-os-publication" or "paperDesign" not in previous_config:
        return None
    paper = previous_config["paperDesign"]
    if (type(paper) is not dict or paper.get("enabled") is not True
            or type(paper.get("commandTimeoutMs")) is not int):
        raise SystemExit("publication Paper predecessor is not an admitted profile")
    if paper == _paper_design_config(user_root):
        return None
    expected = _paper_design_config(
        user_root, rel=PAPER_RUNTIME_V20_REL, bridge_sha256=PAPER_V20_BRIDGE_SHA256,
    )
    if paper != expected:
        raise SystemExit("publication Paper predecessor is not an admitted profile")
    _verify_paper_runtime(
        user_root, runtime_rel=PAPER_RUNTIME_V20_REL, expected_sha=PAPER_V20_BRIDGE_SHA256,
    )
    return expected


def _fleet_status_config(user_root: Path) -> dict | None:
    launcher = user_root / FLEET_STATUS_LAUNCHER_REL
    if not launcher.exists():
        return None
    return {
        "enabled": True,
        "launcherPath": str(launcher),
        "launcherSha256": _stable_regular_file_hash(
            launcher, label="Studio Direct control launcher"
        ),
        "timeoutMs": FLEET_STATUS_TIMEOUT_MS,
    }


ORIGINAL_COLLECTION_ACCOUNT = "fabric-c3-570f6f34"
ORIGINAL_COLLECTION_PRINCIPAL = "p:tunnel:" + ORIGINAL_COLLECTION_ACCOUNT
ORIGINAL_COLLECTION_SCHEMA = "mastermind.fabric_original_collection.v2"
ORIGINAL_COLLECTION_LEGACY_SCHEMA = "mastermind.fabric_original_collection.v1"
ORIGINAL_COLLECTION_RUNS = frozenset((
    "fabric-app-native-drivers-j-20261105-01",
    "fabric-app-application-process-carrier-20261105-01",
))
ORIGINAL_COLLECTION_FIELDS = frozenset((
    "enabled", "schema", "pythonPath", "pythonSha256", "controlPath",
    "controlSha256", "controlBundleDigest", "nativeStore", "nativeGeneration",
    "predecessor",
))
ORIGINAL_COLLECTION_LEGACY_FIELDS = frozenset(ORIGINAL_COLLECTION_FIELDS - {"predecessor"})

# The sealed predecessor import. The machine owner builds and seals it; the
# gateway owner only consumes the sealed result. A caller-selected object,
# matching labels or a digest the caller computed over its own bytes are not
# authentication.
ORIGINAL_PREDECESSOR_SCHEMA = "mastermind.fabric_original_predecessor.v1"
ORIGINAL_PREDECESSOR_KEYS = frozenset(("prior", "receipt_sha256", "runs", "schema", "seal"))
ORIGINAL_PREDECESSOR_PRIOR_KEYS = frozenset((
    "account", "bundleDigest", "configHash", "controlSha256", "host",
    "nativeGeneration", "parent", "principal", "root",
))
ORIGINAL_PREDECESSOR_RUN_KEYS = frozenset(("destination", "observation"))
ORIGINAL_PREDECESSOR_ROOT = "fabric-application-integration-20261104-sol"
ORIGINAL_PREDECESSOR_MAX_RECEIPT = 1024 * 1024
# Exactly one reconciliation selection exists, for the preserved J identity.
ORIGINAL_RECONCILE_RUN = "fabric-app-native-drivers-j-20261105-01"

# The original status contract emitted by the incumbent collector. The retry
# flag is accepted under either spelling; exactly one must be present.
ORIGINAL_OBSERVATION_STATUS_KEYS = frozenset((
    "acceptance", "controller_state", "destination_reserved", "effect_state",
    "lease_settlement", "original_operation_mutated", "reason", "run_id", "state",
))
ORIGINAL_OBSERVATION_RECEIPT_KEYS = frozenset((
    "acceptance", "controller_state", "delivery_verified", "destination_reserved",
    "lease_settlement", "original_operation_mutated", "receipt_sha256", "run_id", "state",
))
ORIGINAL_OBSERVATION_RETRY_KEYS = ("retry_authorized", "retry_allowed")

# Durable one-use subordinate ownership for the single reconciliation.
ORIGINAL_RECONCILIATION_SCHEMA = "mastermind.fabric_original_reconciliation.v1"
ORIGINAL_RECONCILIATION_PREFIX = "original-reconciliation-"
ORIGINAL_RECONCILIATION_SUFFIX = ".json"
# Evidence that an original helper was still in flight during the transition.
ORIGINAL_HELPER_PENDING_PREFIX = "original-helper-"
ORIGINAL_HELPER_PENDING_SUFFIX = ".pending"


def _original_collection_profile(account, host, port, fabric_only, modern_fabric):
    if (account != ORIGINAL_COLLECTION_ACCOUNT or host != "127.0.0.1" or port != 45280
            or fabric_only is not True or modern_fabric is not True):
        raise ValueError("original collection requires its existing private C3 service")


def _canonical_json(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _original_predecessor_body(document: dict) -> str:
    """Flat canonical body: sorted ``path=value`` lines.

    The machine owner and the gateway owner must agree byte for byte without
    sharing a JSON canonicaliser, so the body is deliberately flat ASCII.
    """
    pairs = [("schema", document["schema"]),
             ("receipt_sha256", document["receipt_sha256"])]
    for key in sorted(document["prior"]):
        pairs.append(("prior." + key, str(document["prior"][key])))
    for run_id in sorted(document["runs"]):
        entry = document["runs"][run_id]
        pairs.append(("runs." + run_id + ".destination", entry["destination"]))
        pairs.append(("runs." + run_id + ".observation",
                      "null" if entry["observation"] is None else entry["observation"]))
    lines = []
    for path, value in sorted(pairs, key=lambda item: item[0]):
        if "\n" in value or "=" in path or not path:
            raise ValueError("original predecessor body refused")
        lines.append(path + "=" + value)
    return "\n".join(lines)


def _original_predecessor_seal(document: dict) -> str:
    return hashlib.sha256(_original_predecessor_body(document).encode("utf-8")).hexdigest()


def _original_observation_shape(value) -> str | None:
    """Return the contract shape of one original status observation, or None."""
    if type(value) is not dict:
        return None
    keys = set(value)
    retry = keys & set(ORIGINAL_OBSERVATION_RETRY_KEYS)
    if len(retry) != 1:
        return None
    rest = keys - set(ORIGINAL_OBSERVATION_RETRY_KEYS)
    if rest == set(ORIGINAL_OBSERVATION_STATUS_KEYS):
        return "status"
    if rest == set(ORIGINAL_OBSERVATION_RECEIPT_KEYS):
        return "receipt"
    # The incumbent's unqualified-evidence response did not always include
    # reservation/effect fields. Retain that exact observation as held; never
    # manufacture the missing facts or make it eligible for reconciliation.
    optional = {"destination_reserved", "effect_state"}
    if (value.get("state") == "UNKNOWN"
            and set(ORIGINAL_OBSERVATION_STATUS_KEYS) - optional <= rest
            and rest < set(ORIGINAL_OBSERVATION_STATUS_KEYS)):
        return "held_status"
    return None


def _original_json(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate original observation field")
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=unique,
        parse_constant=lambda value: (_ for _ in ()).throw(
            ValueError("nonfinite original observation field")))


def _original_observation_find(document):
    """Find the unique original status observation in a retained receipt.

    Decode the retained JSON/MCP text envelopes without treating prose as an
    observation. Every branch must fit the bounds before uniqueness is known.
    """
    found = []
    stack = [(document, 0, True)]
    visited = 0
    decoded_bytes = 0
    while stack:
        value, depth, encoded = stack.pop()
        visited += 1
        if visited > 4096 or depth > 16:
            raise ValueError("original observation envelope exceeds its bound")
        if _original_observation_shape(value) is not None:
            found.append(value)
            if len(found) > 1:
                raise ValueError("original observation envelope is ambiguous")
            continue
        if type(value) is dict:
            stack.extend((item, depth + 1, key in
                {"text", "response", "result", "output", "content"})
                for key, item in value.items())
        elif type(value) is list:
            stack.extend((item, depth + 1, encoded) for item in value)
        elif encoded and type(value) is str and value.lstrip().startswith(("{", "[")):
            decoded_bytes += len(value.encode("utf-8"))
            if decoded_bytes > 4 * ORIGINAL_PREDECESSOR_MAX_RECEIPT:
                raise ValueError("original observation text exceeds its bound")
            stack.append((_original_json(value), depth + 1, True))
    if len(found) != 1:
        return None
    return found[0]


def _original_observation_qualify(observation, run_id) -> str:
    """Qualify one retained observation against the original source contract."""
    shape = _original_observation_shape(observation)
    if shape is None:
        raise ValueError("original predecessor observation is not the original contract")
    if observation.get("run_id") != run_id:
        raise ValueError("original predecessor observation names another run")
    retry = next(key for key in ORIGINAL_OBSERVATION_RETRY_KEYS if key in observation)
    if observation[retry] is not False:
        raise ValueError("original predecessor observation authorizes a retry")
    if observation.get("acceptance") != "NOT_RECORDED":
        raise ValueError("original predecessor observation recorded acceptance")
    if observation.get("original_operation_mutated") is not False:
        raise ValueError("original predecessor observation mutated the original operation")
    if (observation.get("lease_settlement") != "UNKNOWN"
            or observation.get("controller_state") != "UNKNOWN"):
        raise ValueError("original predecessor observation settled a lease or controller")
    state = observation.get("state")
    if shape in ("status", "held_status"):
        if state not in ("ABSENT", "UNKNOWN"):
            raise ValueError("original predecessor observation is not absent or unknown")
        if ("effect_state" in observation and observation["effect_state"] != "UNKNOWN"):
            raise ValueError("original predecessor observation effect is not unknown")
        if ("destination_reserved" in observation
                and type(observation["destination_reserved"]) is not bool):
            raise ValueError("original predecessor observation reservation is not a fact")
        if state == "ABSENT" and observation.get("destination_reserved") is not False:
            raise ValueError("original predecessor observation claims a reservation it never made")
    else:
        if state not in ("PENDING", "COMPLETE"):
            raise ValueError("original predecessor observation is not a retained return")
        if observation.get("destination_reserved") is not True:
            raise ValueError("original predecessor observation lost its reservation")
        if type(observation.get("delivery_verified")) is not bool:
            raise ValueError("original predecessor observation verification is not a fact")
        if observation["delivery_verified"] != (state == "COMPLETE"):
            raise ValueError("original predecessor observation verification differs from state")
        if not _sha256_hex(observation.get("receipt_sha256")):
            raise ValueError("original predecessor observation receipt digest is not qualified")
    return shape


def _original_predecessor_verify(document) -> dict:
    """Machine-owner verification of an installed predecessor binding."""
    if type(document) is not dict or set(document) != set(ORIGINAL_PREDECESSOR_KEYS):
        raise ValueError("original predecessor binding is not installed")
    if document["schema"] != ORIGINAL_PREDECESSOR_SCHEMA:
        raise ValueError("original predecessor schema refused")
    if not _sha256_hex(document["receipt_sha256"]):
        raise ValueError("original predecessor digest refused")
    prior = document["prior"]
    if type(prior) is not dict or set(prior) != set(ORIGINAL_PREDECESSOR_PRIOR_KEYS):
        raise ValueError("original predecessor prior commitments refused")
    if (prior["account"] != ORIGINAL_COLLECTION_ACCOUNT
            or prior["principal"] != ORIGINAL_COLLECTION_PRINCIPAL):
        raise ValueError("original predecessor owner refused")
    if (prior["root"] != ORIGINAL_PREDECESSOR_ROOT or prior["parent"] != ORIGINAL_PREDECESSOR_ROOT
            or prior["host"] != "ubuntu1"):
        raise ValueError("original predecessor root refused")
    for key in ("bundleDigest", "configHash", "controlSha256", "nativeGeneration"):
        if not _sha256_hex(prior[key]):
            raise ValueError("original predecessor commitment refused")
    runs = document["runs"]
    if type(runs) is not dict or set(runs) != set(ORIGINAL_COLLECTION_RUNS):
        raise ValueError("original predecessor runs refused")
    for run_id, entry in runs.items():
        if run_id not in ORIGINAL_COLLECTION_RUNS:
            raise ValueError("original predecessor run refused")
        if type(entry) is not dict or set(entry) != set(ORIGINAL_PREDECESSOR_RUN_KEYS):
            raise ValueError("original predecessor entry refused")
        if (type(entry["destination"]) is not str or not entry["destination"].startswith("/")
                or "\n" in entry["destination"]):
            raise ValueError("original predecessor destination refused")
        destination = Path(entry["destination"])
        if (str(destination) != entry["destination"] or ".." in destination.parts or "\x00" in entry["destination"]
                or ORIGINAL_PREDECESSOR_ROOT not in destination.parts
                or destination.name != run_id + "-collection-v1"):
            raise ValueError("original predecessor destination refused")
        if entry["observation"] is None:
            continue  # Explicit held slot, not an unattempted operation.
        if type(entry["observation"]) is not str or not entry["observation"]:
            raise ValueError("original predecessor observation refused")
        try:
            observation = _original_json(entry["observation"])
        except ValueError:
            raise ValueError("original predecessor observation is not decodable")
        _original_observation_qualify(observation, run_id)
    if _original_predecessor_seal(document) != document["seal"]:
        raise ValueError("original predecessor seal refused")
    return document


def _original_collection_scope(collector) -> dict:
    """The installed machine-owned scope for the two fixed original runs."""
    scope = {}
    for run_id in sorted(ORIGINAL_COLLECTION_RUNS):
        plain = collector.PLAIN_SCOPES.get(run_id)
        if type(plain) is not dict:
            raise ValueError("original collection scope is missing")
        scope[run_id] = {key: plain[key]
            for key in ("root", "parent", "host", "destination")}
    return scope


def _original_predecessor_build(receipt_path, expected_digest, prior_descriptor,
                                prior_config_hash, scope, retained_observations=None) -> dict:
    """Qualify the retained original receipt and seal the machine-owner import."""
    path = Path(receipt_path)
    if not path.is_absolute():
        raise SystemExit("original predecessor receipt path must be absolute")
    try:
        # Retained caller evidence can live on the existing evidence volume,
        # outside HOME. Capture one bounded, stable regular file; the complete
        # caller-supplied digest remains the authority for these exact bytes.
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
        with os.fdopen(fd, "rb") as stream:
            before = os.fstat(stream.fileno())
            if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
                    or before.st_size > ORIGINAL_PREDECESSOR_MAX_RECEIPT):
                raise ValueError("original receipt is not a bounded regular file")
            raw = stream.read(ORIGINAL_PREDECESSOR_MAX_RECEIPT + 1)
            identity = lambda info: (info.st_dev, info.st_ino, info.st_mode,
                info.st_size, info.st_mtime_ns, info.st_ctime_ns)
            if (len(raw) != before.st_size
                    or identity(before) != identity(os.fstat(stream.fileno()))
                    or identity(before) != identity(path.lstat())):
                raise ValueError("original receipt changed during capture")
    except (OSError, ValueError, SystemExit) as error:
        raise SystemExit("original predecessor receipt unavailable or unstable") from error
    # The whole-file digest is the only accepted expectation. An inner
    # response digest is never a substitute for it.
    digest = hashlib.sha256(raw).hexdigest()
    if digest != expected_digest:
        raise SystemExit("original predecessor receipt digest mismatch")
    try:
        document = _original_json(raw.decode("utf-8"))
        observation = _original_observation_find(document)
    except (UnicodeDecodeError, ValueError, RecursionError):
        raise SystemExit("original predecessor receipt is not decodable JSON")
    if observation is None:
        raise SystemExit(
            "original predecessor receipt carries no unique original status observation; "
            "supply the retained first call receipt in the original status contract")
    run_id = observation.get("run_id")
    if run_id not in ORIGINAL_COLLECTION_RUNS:
        raise SystemExit("original predecessor receipt names an unenrolled run")
    try:
        _original_observation_qualify(observation, run_id)
    except ValueError as error:
        raise SystemExit("original predecessor receipt refused: " + str(error))
    run_scope = scope.get(run_id)
    if run_scope is None:
        raise SystemExit("original predecessor receipt names an unscoped run")
    canonical = _canonical_json(observation)
    predecessor = {
        "schema": ORIGINAL_PREDECESSOR_SCHEMA,
        "receipt_sha256": digest,
        "prior": {
            "account": ORIGINAL_COLLECTION_ACCOUNT,
            "principal": ORIGINAL_COLLECTION_PRINCIPAL,
            "root": run_scope["root"],
            "parent": run_scope["parent"],
            "host": run_scope["host"],
            "controlSha256": prior_descriptor["controlSha256"],
            "nativeGeneration": prior_descriptor["nativeGeneration"],
            "configHash": prior_config_hash,
            "bundleDigest": prior_descriptor["controlBundleDigest"],
        },
        "runs": {run: {"destination": scope[run]["destination"], "observation": None}
                 for run in sorted(ORIGINAL_COLLECTION_RUNS)},
    }
    predecessor["runs"][run_id]["observation"] = canonical
    for retained_run, retained in (retained_observations or {}).items():
        if retained_run not in ORIGINAL_COLLECTION_RUNS or retained_run == run_id:
            raise ValueError("original predecessor retained slot conflicts")
        _original_observation_qualify(retained, retained_run)
        predecessor["runs"][retained_run]["observation"] = _canonical_json(retained)
    predecessor["seal"] = _original_predecessor_seal(predecessor)
    return predecessor



def _original_collection_native(configuration=None, *, require_current=True):
    """Use the incumbent sealed control and native-generation owners."""
    context = _INSTALLED_CONTROL_CONTEXT
    if context is None:
        raise ValueError("original collection requires installed control closure")
    native = _installed_control_module("_studio_original_native_generation",
        "ops/native_fabric/quota_continuity/rollout/native_generation.py")
    stable = Path.home() / (".claude/projects/-Users-chriswong-Documents-Cluade-Macro-Dashboard/"
        "handoff_kits/meta-ceo-b-2026-09-08/ext")
    store = stable.parent / "native-code-releases"
    selected = native.current(store) if configuration is None or require_current else None
    digest = selected["generation"] if configuration is None else configuration.get("nativeGeneration")
    if require_current and digest != selected["generation"]:
        raise ValueError("original collection native selection changed")
    root, metadata = native.verify(store, digest)
    required = {"ext/original_delivery_collector.py", "ext/artifact_delivery.py",
        "ext/artifact_reader.py", "ext/artifact_production.py", "ext/native_runtime_bindings.py"}
    if metadata["stable_ext"] != str(stable) or not required.issubset(metadata["files"]):
        raise ValueError("original collection native closure missing")
    control = context["root"] / "private_service.py"
    interpreter = Path(sys.executable).resolve(strict=True)
    manifest = json.loads(_fabric_release_bytes(context["root"] / "manifest.json"))
    expected = {"enabled": True, "schema": ORIGINAL_COLLECTION_SCHEMA,
        "pythonPath": str(interpreter),
        "pythonSha256": _stable_regular_file_hash(interpreter, label="original collection interpreter"),
        "controlPath": str(control), "controlSha256": hashlib.sha256(context["files"]["private_service.py"]).hexdigest(),
        "controlBundleDigest": manifest["bundleDigest"],
        "nativeStore": str(store), "nativeGeneration": digest}
    # The predecessor binding is machine-owner sealed and carried beside the
    # installed descriptor. It is verified here and never chosen by a caller.
    predecessor = None
    if configuration is not None:
        provided = dict(configuration)
        if "predecessor" in provided:
            predecessor = provided.pop("predecessor")
        if provided != expected:
            raise ValueError("original collection installed descriptor changed")
        if predecessor is not None:
            _original_predecessor_verify(predecessor)
    expected["predecessor"] = predecessor
    return expected, native, root, metadata


def _original_collection_descriptor_validate(descriptor) -> None:
    """Validate one retained original collection descriptor.

    The v1 descriptor predates the predecessor binding and is still accepted
    as the incumbent's own commitment; the v2 descriptor carries it.
    """
    if type(descriptor) is not dict:
        raise SystemExit("invalid retained original collection selection")
    fields = set(descriptor)
    if fields == set(ORIGINAL_COLLECTION_LEGACY_FIELDS):
        schema = ORIGINAL_COLLECTION_LEGACY_SCHEMA
    elif fields == set(ORIGINAL_COLLECTION_FIELDS):
        schema = ORIGINAL_COLLECTION_SCHEMA
    else:
        raise SystemExit("invalid retained original collection selection")
    if (descriptor.get("enabled") is not True
            or descriptor.get("schema") != schema
            or any(not _sha256_hex(descriptor.get(key)) for key in
                   ("pythonSha256", "controlSha256", "controlBundleDigest", "nativeGeneration"))
            or any(type(descriptor.get(key)) is not str or not Path(descriptor[key]).is_absolute()
                   or str(Path(descriptor[key])) != descriptor[key] or ".." in Path(descriptor[key]).parts
                   for key in ("pythonPath", "controlPath", "nativeStore"))):
        raise SystemExit("invalid retained original collection selection")
    predecessor = descriptor.get("predecessor")
    if predecessor is not None:
        try:
            _original_predecessor_verify(predecessor)
        except ValueError as error:
            raise SystemExit(str(error))


def _original_predecessor_setting(args, roots, prior, previous, previous_predecessor,
                                  descriptor) -> dict | None:
    """Carry the sealed predecessor forward or seal a new one.

    One sealed import per installation. A clean empty owner is never
    constructed over an already sealed predecessor.
    """
    receipt = getattr(args, "original_predecessor_receipt", None)
    expected = getattr(args, "original_predecessor_sha256", None)
    # Legacy call sites carry mock objects with no new CLI attributes. Only
    # actual explicit option values are read.
    if type(receipt) is not str:
        receipt = None
    if type(expected) is not str:
        expected = None
    if (receipt is None) != (expected is None):
        raise SystemExit("original predecessor receipt and sha256 must be supplied together")
    if expected is not None and not _sha256_hex(expected):
        raise SystemExit("original predecessor sha256 must be a sha256 digest")
    if receipt is None:
        if previous_predecessor is None:
            if previous is not None:
                raise SystemExit("refusing upgrade: retained original receipt is required before replacing an unsealed owner")
            return None
        try:
            _original_predecessor_verify(previous_predecessor)
        except ValueError as error:
            raise SystemExit(str(error))
        return previous_predecessor
    if previous_predecessor is not None:
        # A repeated identical request is idempotent; a different receipt is
        # refused. One sealed import per installation.
        if previous_predecessor.get("receipt_sha256") == expected:
            return previous_predecessor
        raise SystemExit(
            "refusing upgrade: the installed original predecessor binding is already sealed")
    if previous is None:
        raise SystemExit(
            "refusing upgrade: an original predecessor import requires an existing "
            "original collection installation")
    collector = _original_collection_collector(descriptor, require_current=True)
    scope = _original_collection_scope(collector)
    # Read the companion's existing local receipt; this is not a collection or
    # remote observation. An unreadable companion remains explicitly held.
    retained = {}
    for run in ORIGINAL_COLLECTION_RUNS - {ORIGINAL_RECONCILE_RUN}:
        observed = collector._gateway_collection_status(run)
        if observed.get("state") in ("COMPLETE", "PENDING"):
            _original_observation_qualify(observed, run)
            retained[run] = observed
    predecessor = _original_predecessor_build(
        receipt, expected, previous, prior.get("configHash"), scope, retained)
    _original_predecessor_verify(predecessor)
    return predecessor


def _original_collection_setting(args, roots, prior, fabric_only, modern_fabric):
    requested = getattr(args, "original_collection", None)
    if requested is not None and type(requested) is not bool:
        raise SystemExit("invalid original collection selection")
    previous = None
    if prior is not None:
        if _sha256_file(roots["config"]) != prior.get("configHash"):
            raise SystemExit("original collection configuration changed")
        config = json.loads(roots["config"].read_text(encoding="utf-8"))
        previous = config.get("originalCollection")
        if previous is not None:
            if (config.get("backendMode") != "shared-account"
                    or config.get("gitPublish") is not False or config.get("paperDesign") is not False
                    or any(key in config for key in ("repositoryWorkspaces", "commissionPublication", "fleetStatus", "publicUrl"))):
                raise SystemExit("invalid retained original collection selection")
            _original_collection_descriptor_validate(previous)
            _original_collection_profile(config.get("accountLabel"), config.get("host"),
                config.get("port"), config.get("fabricOnly"), config.get("modernFabricProtocol"))
    enabled = previous is not None if requested is None else requested
    if not enabled:
        return None
    _original_collection_profile(args.account, "127.0.0.1", args.port, fabric_only, modern_fabric)
    # Explicit opt-in is needed initially. Upgrades rebuild a fully verified
    # descriptor under the same enrolled service; no client chooses a path.
    descriptor, _, _, _ = _original_collection_native()
    previous_predecessor = previous.get("predecessor") if previous is not None else None
    predecessor = _original_predecessor_setting(
        args, roots, prior, previous, previous_predecessor, descriptor)
    return dict(descriptor, predecessor=predecessor)



def _original_collection_collector(configuration=None, *, require_current=True):
    """Load the sealed installed collector module.

    The installed native generation owns these bytes. Nothing outside the
    sealed closure is imported, and the collector is never written to disk.
    """
    _, native, root, metadata = _original_collection_native(
        configuration, require_current=require_current)
    import importlib.util
    ext = root / "ext"
    target = ext / "original_delivery_collector.py"
    source = native.regular_bytes(target)
    if native.digest(source) != metadata["files"]["ext/original_delivery_collector.py"]:
        raise ValueError("original collector changed")
    sys.path.insert(0, str(ext))
    sys.dont_write_bytecode = True
    spec = importlib.util.spec_from_file_location("original_delivery_collector", target)
    collector = importlib.util.module_from_spec(spec)
    if "original_delivery_collector" in sys.modules:
        raise ValueError("original collector module conflict")
    sys.modules["original_delivery_collector"] = collector
    exec(compile(source, str(target), "exec"), collector.__dict__)
    return collector


def _original_state_root(account: str) -> Path:
    return _build_runtime_roots(account)["state"]


# The existing private-service installer owns these immutable recovery records.
# They authorize only completion of one frozen installation, never a new run.
_ORIGINAL_INSTALL_SCHEMA = "mastermind.studio_original_preserving_install.v1"
_ORIGINAL_INSTALL_PREFIX = "original-preserving-upgrade-"
_ORIGINAL_INSTALL_LIMIT = 16 * 1024 * 1024


def _original_install_encode(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def _original_install_paths(roots):
    return {**{name: roots["base"] / name for name in STAGE_FILES},
            "@config": roots["config"], "@plist": roots["plist"], "@manifest": roots["manifest"]}


def _original_install_executor():
    context = _INSTALLED_CONTROL_CONTEXT
    interpreter = Path(sys.executable).resolve(strict=True)
    control = Path(__file__).resolve(strict=True)
    closure = None
    if context is not None:
        closure = {}
        for name, expected in context["files"].items():
            current = _fabric_release_bytes(context["root"] / name)
            if current != expected:
                raise SystemExit("original preserving upgrade control closure changed")
            closure[name] = hashlib.sha256(current).hexdigest()
    return {"python": str(interpreter),
            "pythonHash": _stable_regular_file_hash(interpreter, label="original upgrade interpreter"),
            "control": str(control),
            "controlHash": _stable_regular_file_hash(control, label="original upgrade control"),
            "installedRoot": str(context["root"]) if context is not None else None,
            "installedClosure": closure}


def _original_install_fsync_parent(directory):
    # Custody evidence requires a positive directory durability fence.
    _assert_dest_safe(directory)
    before = directory.lstat()
    fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        held = os.fstat(fd)
        identity = lambda value: (value.st_dev, value.st_ino, value.st_uid, value.st_mode)
        if (not stat.S_ISDIR(held.st_mode) or held.st_uid != os.getuid()
                or held.st_mode & 0o022 or identity(before) != identity(held)):
            raise SystemExit("original preserving upgrade parent changed or unsafe")
        os.fsync(fd)
        if identity(directory.lstat()) != identity(held):
            raise SystemExit("original preserving upgrade parent changed during sync")
    finally:
        os.close(fd)


def _original_install_sync(path, expected):
    # A visible file is not an acknowledged fsync. Re-establish durability of
    # this exact inode and its parent before using it as an installation proof.
    limit = max(2 * 1024 * 1024, len(expected))
    if _fabric_release_bytes(path, limit=limit) != expected:
        raise SystemExit("original preserving upgrade durable bytes changed")
    before = path.lstat()
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK)
    try:
        opened = os.fstat(fd)
        if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
            raise SystemExit("original preserving upgrade durable inode changed")
        os.fsync(fd)
        named = path.lstat()
        if (named.st_dev, named.st_ino) != (opened.st_dev, opened.st_ino):
            raise SystemExit("original preserving upgrade durable inode changed")
    finally:
        os.close(fd)
    _original_install_fsync_parent(path.parent)
    if _fabric_release_bytes(path, limit=limit) != expected:
        raise SystemExit("original preserving upgrade durable readback changed")


def _original_install_decode(plan, roots):
    import base64
    fields = {"schema", "uid", "account", "label", "source", "node", "backend",
              "host", "port", "executor", "request", "entries"}
    if (type(plan) is not dict or set(plan) != fields
            or plan["schema"] != _ORIGINAL_INSTALL_SCHEMA
            or type(plan["uid"]) is not int or plan["uid"] != os.getuid()
            or plan["account"] != ORIGINAL_COLLECTION_ACCOUNT
            or plan["label"] != "com.mastermind.studio-direct-private." + ORIGINAL_COLLECTION_ACCOUNT
            or plan["host"] != "127.0.0.1" or type(plan["port"]) is not int or plan["port"] != 45280
            or any(type(plan[k]) is not str or not Path(plan[k]).is_absolute()
                   for k in ("source", "node", "backend"))
            or type(plan["executor"]) is not dict or type(plan["request"]) is not dict
            or type(plan["entries"]) is not list):
        raise SystemExit("original preserving upgrade plan identity refused")
    targets = _original_install_paths(roots)
    if [row.get("key") for row in plan["entries"] if type(row) is dict] != list(targets):
        raise SystemExit("original preserving upgrade plan members refused")
    decoded = {}
    for row in plan["entries"]:
        if type(row) is not dict or set(row) != {"key", "before", "beforeMode", "after"}:
            raise SystemExit("original preserving upgrade plan row refused")
        values = {}
        for phase in ("before", "after"):
            value = row[phase]
            if phase == "before" and value is None:
                values[phase] = None
                continue
            if type(value) is not str:
                raise SystemExit("original preserving upgrade plan payload refused")
            try:
                raw = base64.b64decode(value, validate=True)
            except (ValueError, TypeError):
                raise SystemExit("original preserving upgrade plan payload refused") from None
            if len(raw) > 2 * 1024 * 1024 or base64.b64encode(raw).decode("ascii") != value:
                raise SystemExit("original preserving upgrade plan payload refused")
            values[phase] = raw
        mode = row["beforeMode"]
        if ((values["before"] is None and mode is not None)
                or (values["before"] is not None
                    and (type(mode) is not int or mode & 0o022 or not 0 <= mode <= 0o777))):
            raise SystemExit("original preserving upgrade plan mode refused")
        decoded[row["key"]] = (values["before"], values["after"], mode)
    try:
        old = _original_json(decoded["@manifest"][0].decode("utf-8"))
        new = _original_json(decoded["@manifest"][1].decode("utf-8"))
        before = _original_json(decoded["@config"][0].decode("utf-8"))
        after = _original_json(decoded["@config"][1].decode("utf-8"))
        prior = before["originalCollection"]
        selected = after["originalCollection"]
        _original_collection_descriptor_validate(prior)
        _original_collection_descriptor_validate(selected)
        _original_collection_profile(before.get("accountLabel"), before.get("host"),
            before.get("port"), before.get("fabricOnly"), before.get("modernFabricProtocol"))
        _original_collection_profile(after.get("accountLabel"), after.get("host"),
            after.get("port"), after.get("fabricOnly"), after.get("modernFabricProtocol"))
        predecessor = selected["predecessor"]
        _original_predecessor_verify(predecessor)
        if {k: v for k, v in before.items() if k != "originalCollection"} != {
                k: v for k, v in after.items() if k != "originalCollection"}:
            raise ValueError("configuration changed outside original selection")
        if prior.get("predecessor") is not None:
            if predecessor != prior["predecessor"]:
                raise ValueError("sealed predecessor changed")
        else:
            commitments = {"controlSha256": prior["controlSha256"],
                "nativeGeneration": prior["nativeGeneration"],
                "configHash": hashlib.sha256(decoded["@config"][0]).hexdigest(),
                "bundleDigest": prior["controlBundleDigest"]}
            if any(predecessor["prior"].get(k) != v for k, v in commitments.items()):
                raise ValueError("predecessor does not bind original install")
        expected = {"version": MANIFEST_VERSION, "account": plan["account"],
            "label": plan["label"], "files": {
                name: hashlib.sha256(decoded[name][1]).hexdigest() for name in STAGE_FILES},
            "source": plan["source"], "node": plan["node"], "backend": plan["backend"],
            "nodeHash": old["nodeHash"], "backendHash": old["backendHash"],
            "dependencyTreeHash": old["dependencyTreeHash"], "host": plan["host"],
            "port": plan["port"], "configHash": hashlib.sha256(decoded["@config"][1]).hexdigest(),
            "plistHash": hashlib.sha256(decoded["@plist"][1]).hexdigest()}
        if new != expected:
            raise ValueError("target manifest differs")
        for key in ("account", "label", "node", "backend", "host", "port"):
            if old[key] != expected[key]:
                raise ValueError("original install identity differs")
        if (old["configHash"] != hashlib.sha256(decoded["@config"][0]).hexdigest()
                or old["plistHash"] != hashlib.sha256(decoded["@plist"][0]).hexdigest()
                or not set(old["files"]).issubset(set(STAGE_FILES))):
            raise ValueError("original manifest closure differs")
        for name in STAGE_FILES:
            previous = decoded[name][0]
            if name in old["files"]:
                if previous is None or hashlib.sha256(previous).hexdigest() != old["files"][name]:
                    raise ValueError("original source preimage differs")
            elif previous is not None:
                raise ValueError("unowned source preimage")
        expected_plist = plistlib.dumps(_build_plist(Path(plan["node"]), roots["gateway"],
            roots["config"], _user_root(), plan["label"]), fmt=plistlib.FMT_XML)
        if decoded["@plist"][1] != expected_plist:
            raise ValueError("target plist differs")
    except (KeyError, ValueError, TypeError, AttributeError, UnicodeError) as error:
        raise SystemExit("original preserving upgrade plan closure refused") from error
    return decoded, old, new, selected


def _original_install_records(roots):
    state = roots["state"]
    _assert_dest_safe(state)
    info = state.lstat()
    if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) != DIR_MODE):
        raise SystemExit("original preserving upgrade state refused")
    names = sorted(p.name for p in state.iterdir() if p.name.startswith(_ORIGINAL_INSTALL_PREFIX))
    if len(names) > 128:
        raise SystemExit("original preserving upgrade history exceeds bound")
    plans, completions = {}, {}
    for name in names:
        suffix = name[len(_ORIGINAL_INSTALL_PREFIX):]
        complete = suffix.endswith(".complete.json")
        digest = suffix[:-14] if complete else suffix[:-5] if suffix.endswith(".json") else ""
        if not _sha256_hex(digest):
            raise SystemExit("original preserving upgrade record name refused")
        path = state / name
        raw = _fabric_release_bytes(path, limit=_ORIGINAL_INSTALL_LIMIT)
        if stat.S_IMODE(path.lstat().st_mode) != FILE_MODE:
            raise SystemExit("original preserving upgrade record mode refused")
        try:
            value = _original_json(raw.decode("utf-8"))
        except (ValueError, UnicodeError) as error:
            raise SystemExit("original preserving upgrade record malformed") from error
        if raw != _original_install_encode(value):
            raise SystemExit("original preserving upgrade record is not canonical")
        if complete:
            completions[digest] = (path, raw, value)
        else:
            if hashlib.sha256(raw).hexdigest() != digest:
                raise SystemExit("original preserving upgrade record digest differs")
            decoded = _original_install_decode(value, roots)
            plans[digest] = (path, raw, value, decoded)
    if set(completions) - set(plans):
        raise SystemExit("original preserving upgrade orphan completion")
    records = []
    for digest, (path, raw, plan, decoded) in plans.items():
        complete = completions.get(digest)
        if complete is not None:
            expected = {"schema": _ORIGINAL_INSTALL_SCHEMA, "planSha256": digest,
                        "targetManifestSha256": hashlib.sha256(decoded[0]["@manifest"][1]).hexdigest(),
                        "state": "COMPLETE"}
            if complete[2] != expected:
                raise SystemExit("original preserving upgrade completion differs")
            _original_install_sync(path, raw)
            _original_install_sync(complete[0], complete[1])
        records.append((digest, path, raw, plan, decoded, complete))
    if sum(record[5] is None for record in records) > 1:
        raise SystemExit("original preserving upgrade has multiple unresolved plans")
    return records


def _original_install_pending(roots):
    return any(record[5] is None for record in _original_install_records(roots))


def _original_install_request(args):
    # Capture the existing upgrade parser's explicit/default CLI fields, not
    # incidental attributes on legacy call-site objects.
    defaults = build_parser().parse_args(["upgrade", "--account", args.account,
        "--source", str(args.source), "--node", str(args.node),
        "--backend", str(args.backend), "--port", str(args.port)])
    provided = vars(args)
    result = {}
    for name, default in vars(defaults).items():
        if name == "func":
            continue
        value = provided.get(name, default)
        if isinstance(value, Path):
            value = str(value)
        if type(value) not in (str, int, float, bool, type(None)):
            raise SystemExit("original preserving upgrade request field refused")
        result[name] = value
    _original_install_encode(result)
    return result


def _original_install_matches(plan, args, source, node, backend, port):
    return (plan["source"] == str(source) and plan["node"] == str(node)
        and plan["backend"] == str(backend) and plan["port"] == port
        and plan["account"] == args.account
        and _original_install_encode(plan["request"]) == _original_install_encode(_original_install_request(args)))


def _original_install_observe(roots, decoded):
    states = {}
    for key, path in _original_install_paths(roots).items():
        before, after, mode = decoded[key]
        if not os.path.lexists(path):
            if before is not None:
                raise SystemExit("original preserving upgrade target missing")
            states[key] = "OLD"
            continue
        actual = _fabric_release_bytes(path)
        actual_mode = stat.S_IMODE(path.lstat().st_mode)
        if actual == after and actual_mode == FILE_MODE:
            states[key] = "TARGET"
        elif before is not None and actual == before and actual_mode == mode:
            states[key] = "OLD"
        else:
            raise SystemExit("original preserving upgrade foreign target bytes")
    return states


def _original_install_output(plan, roots, old):
    print(json.dumps({"upgraded": True, "account": plan["account"], "label": plan["label"],
        "runtime": str(roots["base"]), "plist": str(roots["plist"]), "manifest": str(roots["manifest"]),
        "gateway": str(roots["gateway"]), "port": plan["port"], "source": plan["source"],
        "previousSource": str(old.get("source") or "")}))
    return 0


def _original_install_finish(record, roots, *, completed=False):
    digest, path, raw, plan, decoded_owner, receipt = record
    decoded, old, new, selected = decoded_owner
    if _original_install_executor() != plan["executor"]:
        raise SystemExit("original preserving upgrade executing closure changed")
    incoming = {src.name: _sha256_file(src) for src in _check_source_files(Path(plan["source"]))}
    if incoming != new["files"]:
        raise SystemExit("original preserving upgrade incoming source changed")
    if (_stable_regular_file_hash(Path(plan["node"]), label="original upgrade node") != new["nodeHash"]
            or _stable_regular_file_hash(Path(plan["backend"]), label="original upgrade backend") != new["backendHash"]
            or (new["dependencyTreeHash"] is not None
                and _dependency_tree_hash(roots["node_modules"]) != new["dependencyTreeHash"])):
        raise SystemExit("original preserving upgrade runtime closure changed")
    # Validate the frozen descriptor, never construct a replacement from CURRENT
    # or collect/rebuild either original predecessor slot.
    _original_collection_native(selected, require_current=not completed)
    observed = _original_install_observe(roots, decoded)
    if completed and any(value != "TARGET" for value in observed.values()):
        raise SystemExit("original preserving upgrade completed install changed")
    _original_install_sync(path, raw)
    targets = _original_install_paths(roots)
    for key, target in targets.items():
        before, after, mode = decoded[key]
        # Recheck the whole old/target relation before every replacement.
        observed = _original_install_observe(roots, decoded)
        if observed[key] == "OLD":
            if completed:
                raise SystemExit("original preserving upgrade cannot roll back completion")
            _atomic_write_bytes(target, after, FILE_MODE)
        _original_install_sync(target, after)
    _verify_staged_install(plan["account"], plan["label"], roots,
                           require_runtime_seal=new["dependencyTreeHash"] is not None)
    if any(value != "TARGET" for value in _original_install_observe(roots, decoded).values()):
        raise SystemExit("original preserving upgrade final closure changed")
    result = {"schema": _ORIGINAL_INSTALL_SCHEMA, "planSha256": digest,
              "targetManifestSha256": hashlib.sha256(decoded["@manifest"][1]).hexdigest(),
              "state": "COMPLETE"}
    completion = roots["state"] / (_ORIGINAL_INSTALL_PREFIX + digest + ".complete.json")
    expected = _original_install_encode(result)
    if not os.path.lexists(completion):
        _fabric_release_new(completion, expected)
    _original_install_sync(completion, expected)
    return _original_install_output(plan, roots, old)


def _original_install_resume(args, source, node, backend, port, roots):
    if args.account != ORIGINAL_COLLECTION_ACCOUNT:
        return None
    records = _original_install_records(roots)
    pending = [record for record in records if record[5] is None]
    if pending:
        record = pending[0]
        if not _original_install_matches(record[3], args, source, node, backend, port):
            raise SystemExit("original preserving upgrade requires its original request")
        return _original_install_finish(record, roots)
    # Historical completion is never permission to restore an old installation.
    for record in reversed(records):
        if not _original_install_matches(record[3], args, source, node, backend, port):
            continue
        if _original_install_executor() != record[3]["executor"]:
            continue
        try:
            observed = _original_install_observe(roots, record[4][0])
        except SystemExit:
            continue
        incoming = {src.name: _sha256_file(src) for src in _check_source_files(source)}
        if all(value == "TARGET" for value in observed.values()) and incoming == record[4][2]["files"]:
            return _original_install_finish(record, roots, completed=True)
    return None


def _original_install_begin(source, node, backend, account, label, host, port, roots,
                            original_collection, retained_config, dependency_tree_hash, original_request):
    import base64
    if _original_install_pending(roots):
        raise SystemExit("original preserving upgrade requires reconciliation")
    source_payloads = {src.name: src.read_bytes() for src in _check_source_files(source)}
    if retained_config is None:
        raise SystemExit("original preserving upgrade requires retained configuration")
    config = json.dumps(retained_config, indent=2, sort_keys=True).encode("utf-8")
    plist = plistlib.dumps(_build_plist(node, roots["gateway"], roots["config"], _user_root(), label),
                          fmt=plistlib.FMT_XML)
    manifest = {"version": MANIFEST_VERSION, "account": account, "label": label,
        "files": {name: hashlib.sha256(raw).hexdigest() for name, raw in source_payloads.items()},
        "source": str(source), "node": str(node), "backend": str(backend),
        "nodeHash": _stable_regular_file_hash(node, label="node"),
        "backendHash": _stable_regular_file_hash(backend, label="backend"),
        "dependencyTreeHash": dependency_tree_hash, "host": host, "port": port,
        "configHash": hashlib.sha256(config).hexdigest(), "plistHash": hashlib.sha256(plist).hexdigest()}
    payloads = {**source_payloads, "@config": config, "@plist": plist,
                "@manifest": json.dumps(manifest, indent=2, sort_keys=True).encode("utf-8")}
    entries = []
    for key, target in _original_install_paths(roots).items():
        exists = os.path.lexists(target)
        before = _fabric_release_bytes(target) if exists else None
        entries.append({"key": key,
            "before": base64.b64encode(before).decode("ascii") if before is not None else None,
            "beforeMode": stat.S_IMODE(target.lstat().st_mode) if exists else None,
            "after": base64.b64encode(payloads[key]).decode("ascii")})
    plan = {"schema": _ORIGINAL_INSTALL_SCHEMA, "uid": os.getuid(), "account": account,
        "label": label, "source": str(source), "node": str(node), "backend": str(backend),
        "host": host, "port": port, "executor": _original_install_executor(),
        "request": original_request, "entries": entries}
    decoded = _original_install_decode(plan, roots)
    raw = _original_install_encode(plan)
    if len(raw) > _ORIGINAL_INSTALL_LIMIT:
        raise SystemExit("original preserving upgrade plan exceeds bound")
    digest = hashlib.sha256(raw).hexdigest()
    path = roots["state"] / (_ORIGINAL_INSTALL_PREFIX + digest + ".json")
    # No target is changed until this complete original plan is durable.
    _fabric_release_new(path, raw)
    return _original_install_finish((digest, path, raw, plan, decoded, None), roots)


def _original_installed_descriptor(configuration=None):
    """Bind the whole descriptor, including its predecessor, to the live seal."""
    account = ORIGINAL_COLLECTION_ACCOUNT
    roots = _build_runtime_roots(account)
    if _original_install_pending(roots):
        raise ValueError("original preserving upgrade requires reconciliation")
    manifest = _verify_staged_install(account,
        f"com.mastermind.studio-direct-private.{account}", roots)
    raw = _fabric_release_bytes(roots["config"])
    if hashlib.sha256(raw).hexdigest() != manifest["configHash"]:
        raise ValueError("original collection installed configuration changed")
    config = _original_json(raw.decode("utf-8"))
    _original_collection_profile(config.get("accountLabel"), config.get("host"),
        config.get("port"), config.get("fabricOnly"), config.get("modernFabricProtocol"))
    descriptor = config.get("originalCollection")
    _original_collection_descriptor_validate(descriptor)
    if configuration is not None and configuration != descriptor:
        raise ValueError("original collection descriptor is not the installed selection")
    return descriptor, manifest


@contextmanager
def _original_control_quiescence():
    """Use the incumbent control lock, including for helpers predating markers."""
    context = _INSTALLED_CONTROL_CONTEXT
    lock = _user_root() / ".local/share/studio-direct-mcp/control/.control-bundle.lock"
    _assert_dest_safe(lock)
    owned = context is None
    fd = (os.open(lock, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK)
          if owned else context["lock_fd"])
    try:
        held, named = os.fstat(fd), lock.lstat()
        if (not stat.S_ISREG(held.st_mode) or held.st_uid != os.getuid()
                or held.st_nlink != 1 or stat.S_IMODE(held.st_mode) != FILE_MODE
                or (held.st_dev, held.st_ino) != (named.st_dev, named.st_ino)):
            raise SystemExit("original helper control lock is unqualified")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            raise SystemExit("original helper quiescence is not proven") from error
        yield
    finally:
        if owned:
            os.close(fd)
        else:
            fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)


def _original_upgrade_serialized(function):
    @wraps(function)
    def guarded(args):
        if args.account != ORIGINAL_COLLECTION_ACCOUNT:
            return function(args)
        roots = _build_runtime_roots(args.account)
        if _original_install_pending(roots):
            with _original_control_quiescence():
                return function(args)
        raw = _fabric_release_bytes(roots["config"])
        if _original_json(raw.decode("utf-8")).get("originalCollection") is None:
            return function(args)
        with _original_control_quiescence():
            return function(args)
    return guarded


def _original_fsync_dir(directory):
    """A failed durability fence prevents transport; it is never best effort."""
    _assert_dest_safe(directory)
    fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        held = os.fstat(fd)
        if (held.st_uid != os.getuid() or stat.S_IMODE(held.st_mode) != DIR_MODE):
            raise OSError("original state directory is unsafe")
        os.fsync(fd)
    finally:
        os.close(fd)


def _original_helper_pending(account: str) -> list[str]:
    """Names of original helper markers still present in the owner state."""
    state = _original_state_root(account)
    if account != ORIGINAL_COLLECTION_ACCOUNT:
        return []
    _assert_dest_safe(state)
    if not state.is_dir():
        raise SystemExit("original helper state is unavailable; quiescence is unproven")
    try:
        names = sorted(path.name for path in state.iterdir()
            if path.name.startswith(ORIGINAL_HELPER_PENDING_PREFIX)
            and path.name.endswith(ORIGINAL_HELPER_PENDING_SUFFIX))
    except OSError as error:
        raise SystemExit("original helper markers are unreadable; quiescence is unproven") from error
    return names


def _original_helper_marker(account: str) -> Path:
    return _original_state_root(account) / (
        ORIGINAL_HELPER_PENDING_PREFIX + str(os.getpid()) + ORIGINAL_HELPER_PENDING_SUFFIX)


def _original_helper_marker_take():
    """Record that this helper is in flight. The marker is evidence only."""
    marker = _original_helper_marker(ORIGINAL_COLLECTION_ACCOUNT)
    _ensure_secure_dir(marker.parent)
    handle = os.open(str(marker), os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(handle, "wb") as stream:
        payload = str(os.getpid()).encode("ascii")
        if stream.write(payload) != len(payload):
            raise OSError("short original helper marker write")
        stream.flush()
        os.fsync(stream.fileno())
    _original_fsync_dir(marker.parent)
    return marker


def _original_helper_marker_drop(marker) -> None:
    if marker is None:
        return
    try:
        marker.unlink()
        _original_fsync_dir(marker.parent)
    except OSError:
        pass


def _original_reconciliation_record(account: str, run_id: str) -> Path:
    return _original_state_root(account) / (
        ORIGINAL_RECONCILIATION_PREFIX + run_id + ORIGINAL_RECONCILIATION_SUFFIX)


def _original_reconcile_claim(configuration, run_id, predecessor_sha256, collector):
    """Take the durable one-use subordinate ownership before any transport.

    The record's existence is the fence. A crash, a lost helper outcome or an
    absent leaf never makes the observation eligible again.
    """
    document = _original_predecessor_verify(configuration.get("predecessor"))
    entry = document["runs"].get(run_id)
    if entry is None or run_id != ORIGINAL_RECONCILE_RUN:
        raise ValueError("original reconciliation is not enrolled for this run")
    if document["receipt_sha256"] != predecessor_sha256:
        raise ValueError("original predecessor digest refused")
    scope = _original_collection_scope(collector)
    if run_id not in scope or scope[run_id]["destination"] != entry["destination"]:
        raise ValueError("original reconciliation destination changed")
    observation = _original_json(entry["observation"]) if entry["observation"] is not None else None
    if (_original_observation_shape(observation) != "status"
            or observation.get("state") not in ("ABSENT", "UNKNOWN")):
        raise ValueError("original reconciliation is not eligible")
    path = _original_reconciliation_record(ORIGINAL_COLLECTION_ACCOUNT, run_id)
    _ensure_secure_dir(path.parent)
    payload = _canonical_json({
        "schema": ORIGINAL_RECONCILIATION_SCHEMA,
        "run_id": run_id,
        "predecessor_sha256": predecessor_sha256,
        "destination": entry["destination"],
        "state": "INTENT",
    }).encode("utf-8")
    handle = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(handle, "wb") as stream:
        if stream.write(payload) != len(payload):
            raise OSError("short_local_write")
        stream.flush()
        os.fsync(stream.fileno())
    _original_fsync_dir(path.parent)
    return path, entry["destination"]


def _original_reconcile_settle(path: Path, result, run_id, predecessor_sha256,
                               destination) -> None:
    """Record the settled outcome without ever releasing the one-use fence."""
    state = "COMPLETE" if result.get("state") == "COMPLETE" else "UNKNOWN"
    payload = _canonical_json({
        "schema": ORIGINAL_RECONCILIATION_SCHEMA,
        "run_id": run_id,
        "predecessor_sha256": predecessor_sha256,
        "destination": destination,
        "state": state,
        "receipt_sha256": result.get("receipt_sha256"),
    }).encode("utf-8")
    _atomic_write_bytes(path, payload, 0o600)
    _original_fsync_dir(path.parent)


def cmd_original_collection_helper(args):
    """Fixed installed helper for the already-authorized gateway operation.

    Its stdin contains correlation/selectors, never an identity assertion.
    The gateway checks its actual private-channel principal before spawning.
    Same-UID machine-owner access remains the existing trust model.
    """
    started = False
    selected_run = None
    operation = None
    try:
        raw = sys.stdin.buffer.read(16385)
        if len(raw) > 16384:
            raise ValueError("original collection input bound")
        def unique(pairs):
            value = {}
            for key, item in pairs:
                if key in value:
                    raise ValueError("duplicate original collection field")
                value[key] = item
            return value
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=unique)
        required = {"configuration", "operation", "run_id"}
        if (type(value) is not dict or not required.issubset(value)
                or set(value) - required - {"receipt_sha256", "predecessor_sha256"}
                or value["operation"] not in ("collect", "status", "result", "reconcile")
                or type(value["run_id"]) is not str or value["run_id"] not in ORIGINAL_COLLECTION_RUNS
                or (value["operation"] == "result" and not _sha256_hex(value.get("receipt_sha256")))
                or (value["operation"] != "result" and "receipt_sha256" in value)
                or (value["operation"] == "reconcile" and not _sha256_hex(value.get("predecessor_sha256")))
                or (value["operation"] != "reconcile" and "predecessor_sha256" in value)
                or type(value["configuration"]) is not dict
                or set(value["configuration"]) != ORIGINAL_COLLECTION_FIELDS):
            raise ValueError("original collection selector refused")
        selected_run = value["run_id"]
        operation = value["operation"]
        # Evidence that this helper was in flight. A stale marker is preserved
        # as evidence of an interrupted dispatch and is never deleted blindly.
        with _c2_lifecycle_mutex(ORIGINAL_COLLECTION_ACCOUNT):
            _original_installed_descriptor(value["configuration"])
            if operation == "collect":
                raise ValueError("original collect must consume its retained owner slot")
            return _original_collection_dispatch(value)
    except (OSError,ValueError,TypeError,KeyError,AttributeError,RecursionError,SystemExit):
        print(json.dumps({"run_id": selected_run, "state": "REFUSED",
            "effect_state": "NOT_APPLIED", "reason": "original_collection_unconfirmed",
            "retry_authorized": False}))
        return 75


def _original_collection_dispatch(value):
    """Invoked only while the installed descriptor and lifecycle lock are held."""
    operation, selected_run = value["operation"], value["run_id"]
    started = completed = False
    marker = None
    try:
        marker = _original_helper_marker_take()
        try:
            collector = _original_collection_collector(
                value["configuration"], require_current=operation in ("collect", "reconcile"))
            if collector.GATEWAY_ORIGINAL_RUNS != ORIGINAL_COLLECTION_RUNS:
                raise ValueError("original collector scope differs")
            record = None
            if operation == "reconcile":
                # Machine-owner verification of the sealed predecessor and the
                # durable one-use fence both precede any remote transport.
                record, destination = _original_reconcile_claim(value["configuration"],
                    value["run_id"], value["predecessor_sha256"], collector)
            started = True
            result = collector._gateway_original_delivery(value["operation"], value["run_id"],
                value.get("receipt_sha256"))
            if record is not None:
                _original_reconcile_settle(record, result, selected_run,
                    value["predecessor_sha256"], destination)
            encoded = json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
            if len(encoded) > 16 * 1024 * 1024:
                raise ValueError("original collection output bound")
            sys.stdout.buffer.write(encoded + b"\n")
            completed = True
            return 0
        finally:
            if completed or not started:
                _original_helper_marker_drop(marker)
    except (OSError,ValueError,TypeError,KeyError,AttributeError,RecursionError,SystemExit):
        effect_possible = started and operation in ("collect", "reconcile")
        print(json.dumps({"run_id": selected_run,
            "state": "UNKNOWN" if effect_possible else "REFUSED",
            "effect_state": "EFFECT_UNKNOWN" if effect_possible else "NOT_APPLIED",
            "reason": "original_collection_unconfirmed", "retry_authorized": False}))
        return 75


def cmd_original_predecessor_readback(args) -> int:
    """Read back the installed predecessor import and the one-use fence.

    This is a read-only owner readback. It performs no collection, no
    transport and no install, and it never rewrites the sealed binding.
    """
    account = args.account
    if account != ORIGINAL_COLLECTION_ACCOUNT:
        raise SystemExit("original predecessor readback account refused")
    roots = _build_runtime_roots(account)
    descriptor, installed = _original_installed_descriptor()
    predecessor = descriptor.get("predecessor") if isinstance(descriptor, dict) else None
    if predecessor is None:
        print(json.dumps({"account": account, "predecessor": None, "sealed": False,
            "reason": "no_sealed_predecessor_binding",
            "reconciliation": {}, "pending_helpers": _original_helper_pending(account),
            "configHash": installed["configHash"]}, sort_keys=True, indent=2))
        return 0
    try:
        _original_predecessor_verify(predecessor)
        sealed, reason = True, "sealed_predecessor_verified"
    except ValueError as error:
        sealed, reason = False, str(error)
    records = {}
    for run_id in sorted(predecessor.get("runs") or {}):
        path = _original_reconciliation_record(account, run_id)
        records[run_id] = (json.loads(path.read_text(encoding="utf-8"))
            if path.is_file() and not path.is_symlink() else None)
    print(json.dumps({"account": account, "predecessor": predecessor,
        "sealed": sealed, "reason": reason, "reconciliation": records,
        "pending_helpers": _original_helper_pending(account),
        "configHash": installed["configHash"]}, sort_keys=True, indent=2))
    return 0


def _build_config(
    account: str,
    host: str,
    port: int,
    node_abs: Path,
    backend_abs: Path,
    state_dir: Path,
    user_root: Path,
    *,
    repository_workspaces: bool = False,
    commission_digest: str | None = None,
    fabric_only: bool = False,
    modern_fabric: bool = False,
    original_collection: dict | None = None,
) -> dict:
    if type(modern_fabric) is not bool or (modern_fabric and (not fabric_only or host != "127.0.0.1")):
        raise ValueError("modern Fabric requires the closed private Fabric-only profile")
    if type(fabric_only) is not bool or (fabric_only and (repository_workspaces or commission_digest is not None)):
        raise ValueError("Fabric-only profile cannot enable unrelated capabilities")
    if type(repository_workspaces) is not bool:
        raise ValueError("repository workspace setting must be boolean")
    # publicUrl is omitted: the private adapter rejects a public origin.
    config = {
        "accountLabel": account,
        "host": host,
        "testMode": False,
        "port": port,
        "command": str(node_abs),
        "args": [str(backend_abs), "--no-onboarding"],
        "cwd": str(user_root),
        "childEnv": {"NODE_OPTIONS": ""},
        "stateDir": str(state_dir),
        "maxSessions": MAX_SESSIONS,
        "requestTimeoutMs": REQUEST_TIMEOUT_MS,
        "idleTimeoutMs": IDLE_TIMEOUT_MS,
        "reclaimIdleGraceMs": 30_000,
        "gitPublish": False if fabric_only else _typed_git_config(
            user_root, closed_repositories=repository_workspaces),
        "paperDesign": False if fabric_only else _paper_design_config(user_root),
    }
    if fabric_only:
        config["fabricOnly"] = True
        config["childEnv"]["MMX_FABRIC_SDK_PACKAGE"] = str(state_dir.parent / "package.json")
    if modern_fabric:
        config["modernFabricProtocol"] = True
        config["backendMode"] = "shared-account"
    if original_collection is not None:
        _original_collection_profile(account, host, port, fabric_only, modern_fabric)
        if (type(original_collection) is not dict or set(original_collection) != ORIGINAL_COLLECTION_FIELDS
                or original_collection.get("enabled") is not True
                or original_collection.get("schema") != ORIGINAL_COLLECTION_SCHEMA):
            raise ValueError("invalid original collection descriptor")
        config["originalCollection"] = dict(original_collection)
    if repository_workspaces:
        config["repositoryWorkspaces"] = {
            "enabled": True, "allowedRepositories": ["mastermind", "macro", "terminal"]
        }
    if commission_digest is not None:
        if (not repository_workspaces or host != "127.0.0.1" or port in (8443, RESERVED_FUNNEL_PORT)
                or type(commission_digest) is not str or not re.fullmatch(r"[0-9a-f]{64}", commission_digest)):
            raise ValueError("commission publication requires closed private workspace profile")
        config["commissionPublication"] = {"enabled": True, "configurationDigest": commission_digest}
    # An attended Fabric-only channel exposes no unrelated host telemetry.
    if not fabric_only:
        fleet_status = _fleet_status_config(user_root)
        if fleet_status is not None:
            config["fleetStatus"] = fleet_status
    return config


def _build_plist(
    node_abs: Path,
    gateway_path: Path,
    config_path: Path,
    user_root: Path,
    label: str,
) -> dict:
    return {
        "Label": label,
        "ProgramArguments": [
            str(node_abs),
            str(gateway_path),
            str(config_path),
        ],
        "EnvironmentVariables": {
            "NODE_OPTIONS": "",
            "PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin",
            "HOME": str(user_root),
            "UV_THREADPOOL_SIZE": "16",
        },
        "ProcessType": "Interactive",
        "Umask": 0o077,
        "ExitTimeOut": 25,
        "WorkingDirectory": str(user_root),
        "RunAtLoad": True,
        "KeepAlive": {"SuccessfulExit": False},
        "ThrottleInterval": 10,
        "StandardOutPath": str(gateway_path.parent / "logs" / "out.log"),
        "StandardErrorPath": str(gateway_path.parent / "logs" / "err.log"),
        "StandardInPath": "/dev/null",
    }


def _write_plist(plist_path: Path, payload: dict) -> None:
    _assert_dest_safe(plist_path)
    data = plistlib.dumps(payload, fmt=plistlib.FMT_XML)
    _atomic_write_bytes(plist_path, data, FILE_MODE)


def _valid_manifest(data, account: str, label: str) -> bool:
    if not isinstance(data, dict):
        return False
    version = data.get("version")
    keys = frozenset(data)
    legacy_provisioned = (
        version == 1 and keys == frozenset(LEGACY_PROVISIONED_MANIFEST_KEYS)
    )
    expected_keys = (
        frozenset(MANIFEST_KEYS_V1)
        if version == 1 and not legacy_provisioned
        else frozenset(MANIFEST_KEYS_V2)
        if version == MANIFEST_VERSION
        else frozenset(LEGACY_PROVISIONED_MANIFEST_KEYS)
        if legacy_provisioned
        else None
    )
    if expected_keys is None or keys != expected_keys:
        return False
    if data.get("account") != account or data.get("label") != label:
        return False
    if legacy_provisioned:
        if data.get("installation_state") != LEGACY_PROVISIONED_STATE:
            return False
        provisioned_from = data.get("provisioned_from")
        if not isinstance(provisioned_from, str) or not provisioned_from:
            return False
        source_account = Path(provisioned_from)
        expected_parent = (
            _user_root() / ".local" / "share" / "studio-direct-mcp" / "private"
        )
        if (
            not source_account.is_absolute()
            or source_account.parent != expected_parent
            or source_account.name == account
            or ACCOUNT_LABEL_RE.fullmatch(source_account.name) is None
        ):
            return False
    files = data.get("files")
    if not isinstance(files, dict):
        return False
    fileset = frozenset(files)
    # Only eight exact, originally enrolled installed successor manifests.
    # The general validator and the original pin/start proof remain binding.
    status_owner = _fleet_status_successor_owner_module()
    qualified_status_successor = (
        version == MANIFEST_VERSION
        and account in status_owner.POST_MANIFEST_CANONICAL_SHA256
        and files.get(status_owner.MODULE) == status_owner.TARGET_SOURCE_SHA256
        and _canonical_json_sha256(data)
            == status_owner.POST_MANIFEST_CANONICAL_SHA256.get(account)
    )
    c2_paper_predecessor = (
        version == MANIFEST_VERSION and account == C2_PAPER_ACCOUNT
        and files == C2_PAPER_FILES_SHA256
        and all(data.get(key) == value for key, value in C2_PAPER_RUNTIME_IDENTITY.items())
        and _canonical_json_sha256(data) in C2_PAPER_MANIFEST_CANONICAL_SHA256
    )
    c4_paper_cohort = (
        version == MANIFEST_VERSION and account == C4_PAPER_ACCOUNT
        and files == C2_PAPER_FILES_SHA256
        and all(data.get(key) == value for key, value in C4_PAPER_RUNTIME_IDENTITY.items())
        and _canonical_json_sha256(data) in C4_PAPER_MANIFEST_CANONICAL_SHA256
    )
    if (fileset not in KNOWN_MANIFEST_FILESETS
            and not (version == MANIFEST_VERSION and (
                fileset == V2_CHATGPT1_FLEET_TAILNET_PREDECESSOR
                or (account == "chatgpt2-business"
                    and fileset == V2_C2_BUSINESS_FLEET_PREDECESSOR)
            ))
            and not c2_paper_predecessor and not c4_paper_cohort
            and not qualified_status_successor
            and not _sealed_v2_fleet_gateway_predecessor(data, account)
            and not (version == MANIFEST_VERSION and account in NATIVE_POOL_PIN_PREDECESSORS
                     and files == NATIVE_POOL_PIN_PREDECESSORS[account])):
        return False
    if any(not _sha256_hex(digest) for digest in files.values()):
        return False
    if not _sha256_hex(data.get("configHash")) or not _sha256_hex(data.get("plistHash")):
        return False
    if version == MANIFEST_VERSION:
        if not _sha256_hex(data.get("nodeHash")) or not _sha256_hex(data.get("backendHash")):
            return False
        dependency_hash = data.get("dependencyTreeHash")
        if dependency_hash is not None and not _sha256_hex(dependency_hash):
            return False
    return True


def _read_manifest(
    manifest_path: Path,
    account: str,
    label: str,
    *,
    required: bool = False,
) -> dict | None:
    if manifest_path.is_symlink():
        raise SystemExit("refusing symlink manifest")
    try:
        fd = os.open(
            manifest_path,
            os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK,
        )
    except FileNotFoundError:
        if required:
            raise SystemExit("not staged: manifest missing")
        return None
    except OSError as exc:
        raise SystemExit("corrupt manifest") from exc
    try:
        before = os.fstat(fd)
        # Match the bounded regular-file contract of the existing tunnel reader.
        limit = 65536
        if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= limit:
            raise SystemExit("corrupt manifest")
        raw = bytearray()
        while len(raw) <= limit:
            part = os.read(fd, min(65536, limit + 1 - len(raw)))
            if not part:
                break
            raw.extend(part)
        after = os.fstat(fd)
        named = manifest_path.lstat()
        identity = lambda info: (
            info.st_dev, info.st_ino, info.st_mode, info.st_size,
            info.st_mtime_ns, info.st_ctime_ns,
        )
        if (len(raw) != before.st_size or len(raw) > limit
                or identity(before) != identity(after)
                or identity(after) != identity(named)):
            raise SystemExit("corrupt manifest")
        captured = bytes(raw)
    except OSError as exc:
        raise SystemExit("corrupt manifest") from exc
    finally:
        os.close(fd)
    try:
        data = json.loads(captured.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SystemExit("corrupt manifest") from exc
    if not _valid_manifest(data, account, label):
        raise SystemExit("corrupt manifest")
    if _sealed_v2_fleet_gateway_predecessor(data, account):
        expected_bytes_sha = SEALED_V2_FLEET_GATEWAY_PREDECESSORS[account][1]
        # Authenticate the same immutable bytes that produced data. A later
        # pathname replacement must never supply a different accepted seal.
        if hashlib.sha256(captured).hexdigest() != expected_bytes_sha:
            raise SystemExit("corrupt manifest")
    return data


def _installed_file_hashes(
    base: Path, names: tuple[str, ...] = STAGE_FILES
) -> dict[str, str] | None:
    hashes: dict[str, str] = {}
    for name in names:
        dest = base / name
        if dest.is_symlink() or not dest.is_file():
            return None
        hashes[name] = _sha256_file(dest)
    return hashes


def _load_plist(plist_path: Path) -> dict | None:
    if plist_path.is_symlink() or not plist_path.is_file():
        return None
    try:
        with plist_path.open("rb") as fh:
            data = plistlib.load(fh)
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def _launchd_domain() -> str:
    return f"gui/{os.getuid()}"


def _launchd_target(label: str) -> str:
    return f"{_launchd_domain()}/{label}"


def _parse_launchd_print(text: str) -> dict:
    state = None
    pid = None
    path = None
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("state = "):
            state = stripped.split("=", 1)[1].strip()
        elif stripped.startswith("pid = "):
            raw = stripped.split("=", 1)[1].strip()
            if raw.isdigit():
                pid = int(raw)
        elif stripped.startswith("path = "):
            path = stripped.split("=", 1)[1].strip()
    return {"state": state, "pid": pid, "path": path}


def _launchd_inspect(label: str) -> dict | None:
    res = _run(["launchctl", "print", _launchd_target(label)], check=False)
    if res.returncode != 0:
        return None
    parsed = _parse_launchd_print(res.stdout)
    if parsed["state"] is None and parsed["pid"] is None:
        return None
    return parsed


def _lifecycle_inspect(account: str, label: str, roots: dict, *,
                       require_positive: bool = False) -> dict | None:
    """Enrolled lifecycle owners require positive identity or exact absence.

    Preserve generic C2 Business lifecycle inspection semantics; its dedicated
    Paper cutover explicitly opts into stricter absence proof.
    """
    if (account not in (C2_PAPER_ACCOUNT, C4_PAPER_ACCOUNT)
            and account not in _NATIVE_POOL_PIN_TAILNET_CANONICAL
            and account not in FABRIC_BACKEND_ACCOUNTS and not require_positive):
        return _launchd_inspect(label)
    subject = "Fabric" if account in FABRIC_BACKEND_ACCOUNTS else "C2"
    target = _launchd_target(label)
    absent = (f'Bad request.\nCould not find service "{label}" '
              f'in domain for user gui: {os.getuid()}\n')
    try:
        result = _run(["launchctl", "print", target], check=False)
    except Exception as exc:
        raise SystemExit(f"{subject} launchctl state is indeterminate; refusing lifecycle effect") from exc
    if result.returncode == 113 and result.stdout == "" and result.stderr == absent:
        return None
    lines = result.stdout.splitlines()
    # launchctl indents target fields by one tab; nested coalition states use
    # additional tabs and must not replace the service's own state or identity.
    fields = {key: [line for line in lines[1:-1] if line.startswith(f"\t{key} = ")]
              for key in ("path", "state", "pid")}
    parsed = _parse_launchd_print("\n".join(line for values in fields.values() for line in values))
    if (result.returncode != 0 or result.stderr != ""
            or not lines or lines[0] != f"{target} = {{" or lines[-1] != "}"
            or len(fields["path"]) != 1 or len(fields["state"]) != 1 or len(fields["pid"]) > 1
            or parsed["path"] != str(roots["plist"])
            or parsed["state"] not in ("running", "waiting")
            or (fields["pid"] and (not isinstance(parsed["pid"], int) or parsed["pid"] <= 0))
            or (parsed["state"] == "running" and parsed["pid"] is None)):
        raise SystemExit(f"{subject} launchctl state is indeterminate; refusing lifecycle effect")
    return parsed


def _info_is_running(info: dict) -> bool:
    pid = info.get("pid")
    if isinstance(pid, int) and pid > 0:
        return True
    return info.get("state") == "running"


def _expected_argv(
    node_abs: Path,
    gateway_path: Path,
    config_path: Path,
) -> list[str]:
    return [str(node_abs), str(gateway_path), str(config_path)]


def _stage_dest_files(roots: dict) -> list[Path]:
    return [
        *(roots["base"] / name for name in STAGE_FILES),
        roots["config"],
        roots["manifest"],
        roots["plist"],
    ]


def _assert_first_install_clean(roots: dict) -> None:
    for path in _stage_dest_files(roots):
        if path.exists() or path.is_symlink():
            raise SystemExit(f"refusing overwrite of unmanifested destination: {path}")


def _verify_prior_install(
    prior: dict,
    source: Path,
    node_abs: Path,
    backend_abs: Path,
    account: str,
    label: str,
    host: str,
    port: int,
    roots: dict,
) -> None:
    if (
        prior.get("source") != str(source)
        or prior.get("node") != str(node_abs)
        or prior.get("backend") != str(backend_abs)
        or prior.get("account") != account
        or prior.get("label") != label
        or prior.get("host") != host
        or prior.get("port") != port
    ):
        raise SystemExit(
            "refusing restage: existing manifest diverges; "
            "stop the service first and pass the exact same "
            "--account, --source, --node, --backend, --port"
        )
    if prior.get("version") == MANIFEST_VERSION:
        if _stable_regular_file_hash(node_abs, label="node") != prior.get("nodeHash"):
            raise SystemExit("refusing restage: node hash diverges")
        if _stable_regular_file_hash(backend_abs, label="backend") != prior.get("backendHash"):
            raise SystemExit("refusing restage: backend hash diverges")
        sealed_dependencies = prior.get("dependencyTreeHash")
        if sealed_dependencies is not None:
            if _dependency_tree_hash(roots["node_modules"]) != sealed_dependencies:
                raise SystemExit("refusing restage: dependency tree hash diverges")
    incoming = {src.name: _sha256_file(src) for src in _check_source_files(source)}
    prior_names = tuple(prior["files"].keys())
    installed = _installed_file_hashes(roots["base"], prior_names)
    if installed != prior.get("files"):
        raise SystemExit(
            "refusing restage: existing file hashes diverge; "
            "stop the service first and pass the exact same --source"
        )
    if incoming != installed:
        raise SystemExit(
            "refusing restage: incoming source hashes diverge; "
            "stop the service first and pass the exact same --source"
        )
    if roots["config"].is_symlink() or not roots["config"].is_file():
        raise SystemExit(
            "refusing restage: existing config missing; stop the service first"
        )
    if _sha256_file(roots["config"]) != prior.get("configHash"):
        raise SystemExit(
            "refusing restage: existing config hash diverges; "
            "stop the service first"
        )
    if roots["plist"].is_symlink() or not roots["plist"].is_file():
        raise SystemExit(
            "refusing restage: existing plist missing; stop the service first"
        )
    if _sha256_file(roots["plist"]) != prior.get("plistHash"):
        raise SystemExit(
            "refusing restage: existing plist hash diverges; "
            "stop the service first"
        )
    plist = _load_plist(roots["plist"])
    if plist is None or plist.get("Label") != label:
        raise SystemExit(
            "refusing restage: existing plist diverges; "
            "stop the service first"
        )
    argv = list(plist.get("ProgramArguments") or [])
    expected = _expected_argv(node_abs, roots["gateway"], roots["config"])
    if argv != expected:
        raise SystemExit(
            "refusing restage: existing argv diverges; "
            "stop the service first"
        )


def _preflight_stage(
    source: Path,
    node_abs: Path,
    backend_abs: Path,
    account: str,
    label: str,
    host: str,
    port: int,
    roots: dict,
) -> None:
    _check_source_files(source)
    _assert_no_symlink_ancestors(roots["base"])
    _assert_no_symlink_ancestors(roots["plist"])
    manifest_path = roots["manifest"]
    prior = _read_manifest(manifest_path, account, label)
    if prior is not None:
        _verify_prior_install(
            prior, source, node_abs, backend_abs,
            account, label, host, port, roots,
        )
    else:
        _assert_first_install_clean(roots)
    info = _launchd_inspect(label)
    if info is not None:
        raise SystemExit(
            "refusing restage while service is running; stop first"
        )
    for path in _stage_dest_files(roots):
        _assert_dest_safe(path)
    return prior


def _validate_port(port: int) -> None:
    if port == RESERVED_FUNNEL_PORT:
        raise SystemExit(
            f"--port must not be {RESERVED_FUNNEL_PORT}: "
            "reserved for the public OAuth/Funnel service"
        )
    if not (1024 <= port <= 65535):
        raise SystemExit("--port must be between 1024 and 65535")


@_pin_install_serialized
def _write_install(
    source: Path,
    node_abs: Path,
    backend_abs: Path,
    account: str,
    label: str,
    host: str,
    port: int,
    roots: dict,
    *,
    result_key: str,
    previous_source: str | None = None,
    dependency_tree_hash: str | None = None,
    repository_workspaces: bool = False,
    commission_digest: str | None = None,
    fabric_only: bool = False,
    modern_fabric: bool = False,
    original_collection: dict | None = None,
    retained_config: dict | None = None,
    original_request: dict | None = None,
) -> int:
    if (account == ORIGINAL_COLLECTION_ACCOUNT and previous_source is not None
            and original_collection is not None and original_collection.get("predecessor") is not None):
        return _original_install_begin(source, node_abs, backend_abs, account, label, host, port,
            roots, original_collection, retained_config, dependency_tree_hash, original_request)
    user_root = _user_root()
    _ensure_secure_dir(roots["base"])
    _ensure_secure_dir(roots["state"])
    _ensure_secure_dir(roots["logs"])

    files: dict[str, str] = {}
    for src in _check_source_files(source):
        dst = roots["base"] / src.name
        _copy_secure(src, dst)
        files[src.name] = _sha256_file(dst)

    _atomic_write_text(
        roots["config"],
        json.dumps(
            retained_config if retained_config is not None else _build_config(
                account,
                host,
                port,
                node_abs,
                backend_abs,
                roots["state"],
                user_root,
                repository_workspaces=repository_workspaces,
                commission_digest=commission_digest,
                fabric_only=fabric_only,
                modern_fabric=modern_fabric,
                original_collection=original_collection,
            ),
            indent=2,
            sort_keys=True,
        ),
    )
    plist = _build_plist(
        node_abs, roots["gateway"], roots["config"], user_root, label
    )
    _write_plist(roots["plist"], plist)

    manifest = {
        "version": MANIFEST_VERSION,
        "account": account,
        "label": label,
        "files": files,
        "source": str(source),
        "node": str(node_abs),
        "backend": str(backend_abs),
        "nodeHash": _stable_regular_file_hash(node_abs, label="node"),
        "backendHash": _stable_regular_file_hash(backend_abs, label="backend"),
        "dependencyTreeHash": dependency_tree_hash,
        "host": host,
        "port": port,
        "configHash": _sha256_file(roots["config"]),
        "plistHash": _sha256_file(roots["plist"]),
    }
    _atomic_write_text(
        roots["manifest"],
        json.dumps(manifest, indent=2, sort_keys=True),
    )

    result = {
        result_key: True,
        "account": account,
        "label": label,
        "runtime": str(roots["base"]),
        "plist": str(roots["plist"]),
        "manifest": str(roots["manifest"]),
        "gateway": str(roots["gateway"]),
        "port": port,
        "source": str(source),
    }
    if previous_source is not None:
        result["previousSource"] = previous_source
    print(json.dumps(result))
    return 0




def _repository_workspace_setting(args, roots: dict, prior: dict | None) -> bool:
    """Preserve the manifest-verified setting; only explicit opt-in can enable it."""
    requested = getattr(args, "enable_repository_workspaces", False)
    if type(requested) is not bool:
        raise SystemExit("invalid repository workspace setting")
    previous = False
    if prior is not None:
        config_path = roots["config"]
        if _sha256_file(config_path) != prior.get("configHash"):
            raise SystemExit("repository workspace config changed during preflight")
        value = json.loads(config_path.read_text(encoding="utf-8")).get("repositoryWorkspaces")
        if value is not None:
            if (type(value) is not dict or value.get("enabled") is not True
                    or value != {"enabled": True, "allowedRepositories": ["mastermind", "macro", "terminal"]}):
                raise SystemExit("existing repository workspace setting is not the installed closed profile")
            previous = True
    return requested or previous


def _fabric_profile_setting(args, roots: dict, prior: dict | None) -> bool:
    """Retain the manifest-verified restricted profile; never repurpose Studio."""
    requested = getattr(args, "fabric_only", False)
    if type(requested) is not bool:
        raise SystemExit("invalid Fabric profile setting")
    previous = False
    if prior is not None:
        if _sha256_file(roots["config"]) != prior.get("configHash"):
            raise SystemExit("Fabric profile changed during preflight")
        config = json.loads(roots["config"].read_text(encoding="utf-8"))
        if "fabricOnly" in config:
            if (config["fabricOnly"] is not True or config.get("gitPublish") is not False
                    or config.get("paperDesign") is not False
                    or "repositoryWorkspaces" in config or "commissionPublication" in config
                    or "fleetStatus" in config):
                raise SystemExit("invalid retained Fabric-only profile")
            previous = True
        if requested and not previous:
            raise SystemExit("create a separate Fabric installation; do not repurpose Studio")
    enabled = requested or previous
    if enabled and (getattr(args, "enable_repository_workspaces", False)
                    or getattr(args, "os_commission_config_sha256", None) is not None):
        raise SystemExit("Fabric-only profile cannot enable unrelated capabilities")
    return enabled


def _modern_fabric_setting(args, roots: dict, prior: dict | None, fabric_only: bool) -> bool:
    """Explicit opt-in or verified retention in the same restricted installation."""
    requested = getattr(args, "modern_fabric_protocol", None)
    if requested is not None and type(requested) is not bool:
        raise SystemExit("invalid modern Fabric protocol setting")
    previous = False
    if prior is not None:
        if _sha256_file(roots["config"]) != prior.get("configHash"):
            raise SystemExit("modern Fabric configuration changed during preflight")
        config = json.loads(roots["config"].read_text(encoding="utf-8"))
        value = config.get("modernFabricProtocol", False)
        if type(value) is not bool:
            raise SystemExit("invalid retained modern Fabric protocol setting")
        if value:
            if (not fabric_only or config.get("fabricOnly") is not True
                    or config.get("backendMode") != "shared-account"
                    or config.get("host") != "127.0.0.1"
                    or config.get("gitPublish") is not False
                    or config.get("paperDesign") is not False
                    or any(key in config for key in ("repositoryWorkspaces", "commissionPublication", "fleetStatus", "publicUrl"))):
                raise SystemExit("invalid retained modern Fabric-only profile")
            previous = True
    enabled = previous if requested is None else requested
    if enabled and not fabric_only:
        raise SystemExit("modern protocol requires the existing Fabric-only profile")
    return enabled


OS_COMMISSION_CONFIG = Path("/Library/Application Support/MastermindExecutive/config/os-commission-publication.json")


def _commission_setting(args, roots: dict, prior: dict | None) -> str | None:
    """Preserve only verified opt-in; never accept a caller-selected config path."""
    requested = getattr(args, "os_commission_config_sha256", None)
    if requested is not None and (type(requested) is not str or not re.fullmatch(r"[0-9a-f]{64}", requested)):
        raise SystemExit("invalid commission configuration digest")
    previous = None
    if prior is not None:
        if _sha256_file(roots["config"]) != prior.get("configHash"):
            raise SystemExit("commission configuration changed during preflight")
        value = json.loads(roots["config"].read_text(encoding="utf-8")).get("commissionPublication")
        if value is not None:
            if (type(value) is not dict or set(value) != {"enabled", "configurationDigest"}
                    or value["enabled"] is not True or type(value["configurationDigest"]) is not str
                    or not re.fullmatch(r"[0-9a-f]{64}", value["configurationDigest"])):
                raise SystemExit("existing commission publication profile is invalid")
            previous = value["configurationDigest"]
    digest = requested or previous
    if digest is None:
        return None
    if (os.getuid() != os.geteuid() or not _repository_workspace_setting(args, roots, prior)
            or args.port == 8443):
        raise SystemExit("commission publication requires private repository workspace profile")
    current = OS_COMMISSION_CONFIG
    first = True
    while True:
        info = current.lstat()
        if (info.st_uid != 0 or info.st_mode & 0o022 or stat.S_ISLNK(info.st_mode)
                or (first and (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1))
                or (not first and not stat.S_ISDIR(info.st_mode))):
            raise SystemExit("commission configuration is not root sealed")
        if current == current.parent:
            break
        current, first = current.parent, False
    raw = OS_COMMISSION_CONFIG.read_bytes()
    if len(raw) > 65536 or hashlib.sha256(raw).hexdigest() != digest:
        raise SystemExit("commission configuration digest changed")
    value = json.loads(raw)
    keys = {"schema", "release_sha", "studio_uid", "studio_account", "studio_port",
            "policy", "grants", "base_sha", "audit_directory", "auth_helper_sha256", "file_helper_sha256"}
    if (type(value) is not dict or set(value) != keys
            or value["schema"] != "mastermind.os_commission_publication.v1"
            or type(value["studio_uid"]) is not int or value["studio_uid"] != os.getuid()
            or value["studio_account"] != args.account or type(value["studio_port"]) is not int
            or value["studio_port"] != args.port):
        raise SystemExit("commission configuration does not match this installed Studio owner")
    return digest


@_fabric_lifecycle_serialized()
def cmd_stage(args) -> int:
    account = args.account
    _pin_reject_generic_restage(account)
    _validate_account_label(account)
    label = f"com.mastermind.studio-direct-private.{account}"
    host = "127.0.0.1"

    if not os.path.isabs(args.source):
        raise SystemExit("--source must be absolute")
    source = Path(args.source)
    if source.is_symlink() or not source.is_dir():
        raise SystemExit(f"source dir invalid: {source}")
    node_abs = _resolve_abs("--node", args.node)
    backend_abs = _resolve_abs("--backend", args.backend)
    port = int(args.port)
    _validate_port(port)

    roots = _build_runtime_roots(account)
    prior = _preflight_stage(
        source, node_abs, backend_abs, account, label, host, port, roots
    )
    fabric_only = _fabric_profile_setting(args, roots, prior)
    modern_fabric = _modern_fabric_setting(args, roots, prior, fabric_only)
    original_collection = _original_collection_setting(args, roots, prior, fabric_only, modern_fabric)
    # Paper remains mandatory only for a profile that actually exposes Paper.
    if not fabric_only:
        _verify_paper_runtime(_user_root())
    retained_dependency_hash = (
        prior.get("dependencyTreeHash")
        if isinstance(prior, dict) and prior.get("version") == MANIFEST_VERSION
        else None
    )

    return _write_install(
        source, node_abs, backend_abs, account, label, host, port, roots,
        result_key="staged",
        dependency_tree_hash=retained_dependency_hash,
        repository_workspaces=_repository_workspace_setting(args, roots, prior),
        commission_digest=_commission_setting(args, roots, prior),
        fabric_only=fabric_only,
        modern_fabric=modern_fabric,
        original_collection=original_collection,
    )

def _sealed_historical_tailnet_launch_argv(
    account: str, manifest: dict, roots: dict,
    expected_argv: list[str], actual_argv: list[str],
) -> bool:
    """Allow only the two byte-pinned historical Fabric tailnet launchers.

    The caller has already verified every module hash, the immutable original
    manifest bytes, the plist SHA256, and the account/label. This helper does
    not permit re-staging or changing the original launch agent.
    """
    if account not in {"fabric-design", "fabric-read"}:
        return False
    if not _sealed_v2_fleet_gateway_predecessor(manifest, account):
        return False
    if "tailnet-gateway.mjs" not in manifest.get("files", {}):
        return False
    if len(expected_argv) != 3 or len(actual_argv) != 3:
        return False
    historical_argv = [
        expected_argv[0],
        str(roots["base"] / "tailnet-gateway.mjs"),
        expected_argv[2],
    ]
    return actual_argv == historical_argv


def _verify_staged_install(
    account: str,
    label: str,
    roots: dict,
    *,
    require_runtime_seal: bool = True,
) -> dict:
    manifest_path = roots["manifest"]
    manifest = _read_manifest(manifest_path, account, label, required=True)

    for name, expected_hash in manifest["files"].items():
        path = roots["base"] / name
        if path.is_symlink() or not path.is_file():
            raise SystemExit(f"not staged: {name} missing")
        if _sha256_file(path) != expected_hash:
            raise SystemExit(f"not staged: {name} hash mismatch")

    deps = roots["node_modules"]
    if deps.is_symlink() or not deps.is_dir():
        raise SystemExit(
            "not staged: node_modules missing; "
            "parent must run npm ci --omit=dev --ignore-scripts"
        )

    if roots["config"].is_symlink() or not roots["config"].is_file():
        raise SystemExit("not staged: config missing")
    stored_config_hash = manifest.get("configHash")
    if stored_config_hash is None:
        raise SystemExit("not staged: config hash missing from manifest")
    if _sha256_file(roots["config"]) != stored_config_hash:
        raise SystemExit("not staged: config hash mismatch")

    if roots["plist"].is_symlink() or not roots["plist"].is_file():
        raise SystemExit("not staged: plist missing")
    stored_plist_hash = manifest.get("plistHash")
    if stored_plist_hash is None:
        raise SystemExit("not staged: plist hash missing from manifest")
    if _sha256_file(roots["plist"]) != stored_plist_hash:
        raise SystemExit("not staged: plist hash mismatch")

    node = Path(manifest["node"])
    backend = Path(manifest["backend"])
    if node.is_symlink() or not node.is_file():
        raise SystemExit("not staged: node missing")
    if backend.is_symlink() or not backend.is_file():
        raise SystemExit("not staged: backend missing")
    if require_runtime_seal:
        if manifest.get("version") != MANIFEST_VERSION:
            raise SystemExit("not staged: legacy manifest must be upgraded and runtime sealed")
        if _stable_regular_file_hash(node, label="node") != manifest.get("nodeHash"):
            raise SystemExit("not staged: node hash mismatch")
        if _stable_regular_file_hash(backend, label="backend") != manifest.get("backendHash"):
            raise SystemExit("not staged: backend hash mismatch")
        sealed_dependencies = manifest.get("dependencyTreeHash")
        if sealed_dependencies is None:
            raise SystemExit("not staged: runtime dependencies are not sealed")
        if _dependency_tree_hash(deps) != sealed_dependencies:
            raise SystemExit("not staged: dependency tree hash mismatch")

    plist = _load_plist(roots["plist"])
    if plist is None:
        raise SystemExit("not staged: plist missing")
    if plist.get("Label") != label:
        raise SystemExit("plist is not our exact install")

    expected_argv = _expected_argv(node, roots["gateway"], roots["config"])
    actual_argv = list(plist.get("ProgramArguments") or [])
    historical_tailnet = _sealed_historical_tailnet_launch_argv(
        account, manifest, roots, expected_argv, actual_argv,
    )
    if actual_argv != expected_argv and not historical_tailnet:
        raise SystemExit("plist is not our exact install")
    if (Path(actual_argv[1]).name != PRIVATE_GATEWAY_NAME
            and not historical_tailnet):
        raise SystemExit("plist is not our exact install")

    return manifest


def _native_pin_manifest_valid(data, account: str, label: str) -> bool:
    """Keep the private profile rules and close the two Tailnet state sets."""
    if not _valid_manifest(data, account, label):
        return False
    if account not in _NATIVE_POOL_PIN_TAILNET_CANONICAL:
        return True
    return (data["files"] == NATIVE_POOL_PIN_PREDECESSORS[account]
            and _canonical_json_sha256(data)
            in _NATIVE_POOL_PIN_TAILNET_CANONICAL[account])


def _verify_native_pin_tailnet_install(account: str, label: str, roots: dict) -> dict:
    """Read the complete existing seal for one exact preserved Tailnet seat.

    The private verifier remains private-only. No argument, path or caller
    selector can opt an arbitrary profile into this transport. Even stop/seal
    callers must retain the complete reviewed runtime seal for these states.
    """
    manifest = _pin_owner_module().decode(_fabric_release_bytes(roots["manifest"]))
    if (account not in _NATIVE_POOL_PIN_TAILNET_CANONICAL
            or not _native_pin_manifest_valid(manifest, account, label)):
        raise SystemExit("not staged: preserved Tailnet profile differs")
    for name, expected_hash in manifest["files"].items():
        if hashlib.sha256(_fabric_release_bytes(roots["base"] / name)).hexdigest() != expected_hash:
            raise SystemExit("not staged: preserved Tailnet module differs")
    if hashlib.sha256(_fabric_release_bytes(roots["config"])).hexdigest() != manifest["configHash"]:
        raise SystemExit("not staged: preserved Tailnet config differs")
    plist_raw = _fabric_release_bytes(roots["plist"])
    if hashlib.sha256(plist_raw).hexdigest() != manifest["plistHash"]:
        raise SystemExit("not staged: preserved Tailnet plist differs")
    node, backend = Path(manifest["node"]), Path(manifest["backend"])
    if (_stable_regular_file_hash(node, label="Tailnet node") != manifest["nodeHash"]
            or _stable_regular_file_hash(backend, label="Tailnet backend") != manifest["backendHash"]
            or manifest["dependencyTreeHash"] is None
            or _dependency_tree_hash(roots["node_modules"]) != manifest["dependencyTreeHash"]):
        raise SystemExit("not staged: preserved Tailnet runtime differs")
    plist = plistlib.loads(plist_raw)
    gateway = roots["base"] / "tailnet-gateway.mjs"
    expected_argv = _expected_argv(node, gateway, roots["config"])
    if (not isinstance(plist, dict) or plist.get("Label") != label
            or list(plist.get("ProgramArguments") or []) != expected_argv):
        raise SystemExit("plist is not the exact preserved Tailnet install")
    return manifest


def _verify_native_pin_install(account: str, label: str, roots: dict, *,
                               require_runtime_seal: bool = True) -> dict:
    """Select only the two closed Tailnet owners; preserve private admission."""
    if account in _NATIVE_POOL_PIN_TAILNET_CANONICAL:
        return _verify_native_pin_tailnet_install(account, label, roots)
    if require_runtime_seal:
        return _verify_staged_install(account, label, roots)
    return _verify_staged_install(account, label, roots, require_runtime_seal=False)



def _verify_upgrade_preserves_installed_fleet_capabilities(
    prior: dict, roots: dict, projected: dict,
) -> None:
    """Fail closed before any writes when an enrolled v0.1.10 fleet seat would lose service.

    This is an explicit migration guard, NOT permission to broaden historical
    filesets or treat an approved old manifest as permission to downgrade it.
    A separately reviewed compatibility source must retain both fleet modules
    and every configured fleet route, scheduling cap and fleet-status binding.
    """
    if frozenset(prior["files"]) not in (
        V2_CHATGPT1_FLEET_TAILNET_PREDECESSOR,
        frozenset(C2_PAPER_FILES_SHA256),
        V2_C2_BUSINESS_FLEET_PREDECESSOR,
    ):
        return
    required = frozenset(("fleet-routing.mjs", "tailnet-gateway.mjs"))
    if not required.issubset(STAGE_FILES):
        raise SystemExit(
            "refusing upgrade: installed fleet/tailnet capability modules absent "
            "from target release; reviewed compatibility migration required"
        )
    config_path = roots["config"]
    if config_path.is_symlink() or not config_path.is_file():
        raise SystemExit("refusing upgrade: existing fleet config unavailable")
    before_hash = _stable_regular_file_hash(config_path, label="existing config")
    if before_hash != prior["configHash"]:
        raise SystemExit("refusing upgrade: existing fleet config hash changed")
    try:
        existing = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SystemExit("refusing upgrade: existing fleet config invalid") from exc
    if (_stable_regular_file_hash(config_path, label="existing config") != before_hash
            or not isinstance(existing, dict)):
        raise SystemExit("refusing upgrade: existing fleet config changed")
    routes = existing.get("fleetRouting")
    if (not isinstance(routes, dict) or routes.get("enabled") is not True
            or not isinstance(routes.get("routes"), list)
            or len(routes["routes"]) < 1):
        raise SystemExit("refusing upgrade: historical fleet routes unverified")
    for key in (
        "fleetRouting", "maxPerSessionConcurrency", "maxQueuedPerSession",
        "fleetStatus",
    ):
        if existing.get(key) != projected.get(key):
            raise SystemExit(
                f"refusing upgrade: fleet capability {key} would change; "
                "reviewed compatibility migration required"
            )


def _upgrade_fleet_v10_publisher_only(
    args, source: Path, node_abs: Path, backend_abs: Path,
    account: str, label: str, port: int, roots: dict,
) -> int:
    """Replace only the two reviewed publisher modules on the sealed fleet 0.1.10.

    The canonical private_service installer owns this transaction. Never
    replace a live gateway with protected-master's different runtime bundle.
    The administrator supplies the exact observed manifest digest (CAS).
    """
    expected = getattr(args, "publisher_expected_manifest_sha256", None)
    preview = getattr(args, "publisher_preflight_only", False)
    if (account not in FLEET_V10_ENROLLED_ACCOUNTS or type(preview) is not bool
            or not _sha256_hex(expected)
            or getattr(args, "fabric_only", False)
            or getattr(args, "enable_repository_workspaces", False)
            or getattr(args, "os_commission_config_sha256", None)):
        raise SystemExit("fleet publisher compatibility requires an existing enrolled fleet owner and exact manifest CAS")
    path = roots["manifest"]
    if _stable_regular_file_hash(path, label="installed manifest") != expected:
        raise SystemExit("fleet publisher compatibility: installed manifest CAS mismatch")
    prior = _verify_staged_install(account, label, roots, require_runtime_seal=True)
    if (prior.get("version") != MANIFEST_VERSION
            or frozenset(prior["files"]) != V2_CHATGPT1_FLEET_TAILNET_PREDECESSOR
            or not prior.get("dependencyTreeHash")
            or prior.get("node") != str(node_abs)
            or prior.get("backend") != str(backend_abs)
            or prior.get("host") != "127.0.0.1"
            or prior.get("port") != port):
        raise SystemExit("fleet publisher compatibility: original sealed identity does not match")
    for name, expected_blob in FLEET_V10_PRESERVED_GIT_BLOBS.items():
        candidate = roots["base"] / name
        _assert_dest_safe(candidate)
        data = candidate.read_bytes()
        actual = hashlib.sha1(
            b"blob " + str(len(data)).encode("ascii") + b"\0" + data
        ).hexdigest()
        if name == C1_GIT_FAILURE_COMPAT_GATEWAY:
            # The reviewed C1 gateway-only successor is an accepted installed
            # generation for this one seat only. No other account and no
            # arbitrary gateway bytes are admitted.
            accepted = {expected_blob}
            if account == C1_GIT_FAILURE_COMPAT_ACCOUNT:
                accepted.add(C1_GIT_FAILURE_COMPAT_SUCCESSOR_GIT_BLOB)
            if actual not in accepted:
                raise SystemExit("fleet publisher compatibility: preserved fleet generation changed")
            continue
        if actual != expected_blob:
            raise SystemExit("fleet publisher compatibility: preserved fleet generation changed")
    config_path = roots["config"]
    manifest_path = roots["manifest"]
    for candidate in (config_path, manifest_path):
        _assert_dest_safe(candidate)
    old_config_bytes = config_path.read_bytes()
    old_manifest_bytes = manifest_path.read_bytes()
    if (hashlib.sha256(old_config_bytes).hexdigest() != prior["configHash"]
            or hashlib.sha256(old_manifest_bytes).hexdigest() != expected):
        raise SystemExit("fleet publisher compatibility: verified snapshot changed during preflight")
    try:
        old_config = json.loads(old_config_bytes)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise SystemExit("fleet publisher compatibility: original config invalid") from exc
    user_root = _user_root()
    if (type(old_config) is not dict
            or old_config.get("repositoryWorkspaces") != {
                "enabled": True, "allowedRepositories": ["mastermind", "macro", "terminal"]}
            or old_config.get("fleetRouting", {}).get("enabled") is not True
            or len(old_config["fleetRouting"].get("routes", [])) != 2
            or old_config.get("maxPerSessionConcurrency") != 8
            or old_config.get("maxQueuedPerSession") != 16
            or type(old_config.get("fleetStatus")) is not dict
            or old_config.get("fabricOnly") is True
            or "commissionPublication" in old_config
            or "modernFabricProtocol" in old_config):
        raise SystemExit("fleet publisher compatibility: original scoped capabilities changed")
    # Preserve historical legacy/index-sync transition constraints. Only
    # three exact sealed closed-profile predecessor pairs are eligible:
    # original index-sync, merge-capable publisher and reviewed rejection-
    # diagnostics generation. No wildcard source hashes or account expansion.
    # The sealed manifest, not the caller, chooses the transition.
    original_publisher = old_config.get("gitPublish")
    expected_closed = _typed_git_config(user_root, closed_repositories=True)
    patch_hashes = FLEET_V10_PUBLISHER_PATCH_SHA256
    preserve_config_bytes = False
    if (original_publisher == expected_closed and any(
            all(prior["files"].get(name) == digest for name, digest in exact_pair.items())
            for exact_pair in (
                FLEET_V10_MERGE_PUBLISHER_PREDECESSOR_SHA256,
                FLEET_V10_POST_MERGE_PUBLISHER_PREDECESSOR_SHA256,
                FLEET_V10_REJECTION_PUBLISHER_PREDECESSOR_SHA256,
            ))):
        patch_hashes = FLEET_V10_MERGE_PUBLISHER_PATCH_SHA256
        preserve_config_bytes = True
    elif original_publisher == _typed_git_config(user_root):
        pass  # existing legacy-to-closed upgrade
    elif (original_publisher == expected_closed
            and prior["files"].get("git-publish.mjs") ==
                FLEET_V10_PREVIOUS_CLOSED_PUBLISHER_SHA256
            and prior["files"].get("workspace-access.mjs") ==
                FLEET_V10_PUBLISHER_PATCH_SHA256["workspace-access.mjs"]):
        pass  # exact reviewed closed-to-closed module update
    else:
        raise SystemExit("fleet publisher compatibility: unrecognized prior publisher identity")
    new_config = dict(old_config)
    new_config["gitPublish"] = expected_closed
    if ({k: v for k, v in new_config.items() if k != "gitPublish"}
            != {k: v for k, v in old_config.items() if k != "gitPublish"}):
        raise SystemExit("fleet publisher compatibility: unrelated config change")
    config_bytes = (old_config_bytes if preserve_config_bytes else
                    json.dumps(new_config, indent=2, sort_keys=True).encode("utf-8"))
    names = tuple(patch_hashes)
    old_files = {}
    new_files = {}
    for name in names:
        installed = roots["base"] / name
        incoming = source / name
        _assert_dest_safe(installed)
        if incoming.is_symlink() or not incoming.is_file():
            raise SystemExit("fleet publisher compatibility: source module unavailable")
        original = installed.read_bytes()
        modified = incoming.read_bytes()
        if (hashlib.sha256(original).hexdigest() != prior["files"][name]
                or hashlib.sha256(modified).hexdigest() != patch_hashes[name]):
            raise SystemExit("fleet publisher compatibility: source or installed module hash mismatch")
        old_files[name] = original
        new_files[name] = modified
    future = dict(prior)
    future["files"] = dict(prior["files"])
    for name in names:
        future["files"][name] = hashlib.sha256(new_files[name]).hexdigest()
    future["configHash"] = hashlib.sha256(config_bytes).hexdigest()
    if not _valid_manifest(future, account, label):
        raise SystemExit("fleet publisher compatibility: prospective manifest invalid")
    if _stable_regular_file_hash(manifest_path, label="installed manifest") != expected:
        raise SystemExit("fleet publisher compatibility: installed state changed during planning")
    if preview:
        print(json.dumps({
            "preflight": True, "effect": "NOT_APPLIED", "account": account,
            "originalManifestSha256": expected,
            "publisherModules": list(names),
            "fleetRoutesPreserved": len(old_config["fleetRouting"]["routes"]),
            "concurrencyPreserved": [8, 16],
            "existingBundleRetained": True,
        }, sort_keys=True))
        return 0
    if _launchd_inspect(label) is not None:
        raise SystemExit("refusing fleet publisher upgrade while service is loaded; stop first")
    # Reconfirm all observed bytes immediately before the first effect.
    if (_stable_regular_file_hash(manifest_path, label="installed manifest") != expected
            or _stable_regular_file_hash(config_path, label="installed config") != prior["configHash"]
            or any(_sha256_file(roots["base"] / n) != prior["files"][n] for n in names)):
        raise SystemExit("fleet publisher compatibility: original installation changed")
    # All new source was hash-pinned before entry. Manifest is written LAST:
    # interrupted installation fails the existing manifest/hash gate closed.
    old_bytes = {**{roots["base"] / n: old_files[n] for n in names},
                 config_path: old_config_bytes, manifest_path: old_manifest_bytes}
    planned = {**{roots["base"] / n: new_files[n] for n in names},
               config_path: config_bytes,
               manifest_path: json.dumps(future, indent=2, sort_keys=True).encode("utf-8")}
    committed = False
    try:
        for target, payload in planned.items():
            _atomic_write_bytes(target, payload)
        committed = True
        _verify_staged_install(account, label, roots, require_runtime_seal=True)
    except BaseException as exc:
        if committed:
            raise SystemExit(
                "fleet publisher compatibility: EFFECT_UNKNOWN after manifest commit; "
                "inspect original service before attempting recovery"
            ) from exc
        try:
            # os.replace may have succeeded even when a later fsync failed.
            # Thus a return-code ledger cannot prove which files changed.
            # Reconcile *every* planned path by bytes before safe rollback.
            if _launchd_inspect(label) is not None:
                raise RuntimeError("service became loaded during transaction")
            observed = {target: target.read_bytes() for target in planned}
            if any(observed[t] not in (old_bytes[t], planned[t]) for t in planned):
                raise RuntimeError("non-owned concurrent mutation while recovering")
            for target in reversed(tuple(planned)):
                if observed[target] != old_bytes[target]:
                    _atomic_write_bytes(target, old_bytes[target])
            if (any(target.read_bytes() != old_bytes[target] for target in planned)
                    or _stable_regular_file_hash(manifest_path, label="installed manifest") != expected):
                raise RuntimeError("rollback byte identity differs")
            _verify_staged_install(
                account, label, roots, require_runtime_seal=True)
        except BaseException as rollback_exc:
            raise SystemExit(
                "fleet publisher compatibility: EFFECT_UNKNOWN during rollback; "
                "do not restart or replay until original state is reconciled"
            ) from rollback_exc
        raise SystemExit("fleet publisher compatibility: NOT_APPLIED; original state restored") from exc
    print(json.dumps({
        "publisherFleetCompatibility": True, "account": account, "effect": "APPLIED",
        "manifestSha256": _sha256_file(manifest_path),
        "gatewayAndFleetModulesPreserved": True,
        "repositoryWorkspacesPreserved": True,
        "serviceStarted": False,
    }, sort_keys=True))
    return 0


@contextmanager
def _c1_retained_pin_state(account: str, roots: dict, *, operation="preview"):
    """Keep the incumbent selected-pin proof through this closed transition.

    The native pin owner verifies its own intent, transformation, result,
    selected phase and bridge. Preview and apply share one retained-proof
    purpose. Apply keeps the publication lock; preview does not. No pin
    operation is replayed and the formatter is not relabeled as status.
    """
    # The incumbent fleet-status transaction owns startup while its record
    # exists. This formatter has no authority to rewrite or replay that plan.
    if os.path.lexists(roots["state"] / "fleet-status-module-successor"):
        raise SystemExit("C1_FLEET_STATUS_SUCCESSOR_REQUIRES_OWNER")
    pin = _pin_owner_module()
    path = roots["state"] / "native-pool-pin"
    if not os.path.lexists(path):
        yield {"present": False, "state": "ABSENT", "applicable": False}
        return
    pin.directory(sys.modules[__name__], path)
    if not os.path.lexists(path / "result.json"):
        raise SystemExit(
            "C1 fleet gateway compatibility: retained native-pool pin is pending")
    with pin.selected_applied_context(
            sys.modules[__name__], account, roots, operation=operation,
            retained_proof_purpose=C1_GATEWAY_RETAINED_PROOF_PURPOSE) as (plan, raw):
        current = _fabric_release_bytes(roots["config"])
        manifest = _fabric_release_bytes(roots["manifest"])
        original = (current == raw["config.after.json"]
                    and manifest == raw["manifest.after.json"])
        paper = (not original and pin._fleet_paper_v20_postpin_start(
            sys.modules[__name__], account, roots, plan, raw, current, manifest))
        if not (original or paper):
            raise SystemExit(
                "C1 fleet gateway compatibility: retained native-pool pin is not the current installed state")
        yield {"present": True, "state": "COMPLETE", "applicable": True,
               "planSha256": pin.plan_sha(sys.modules[__name__], plan),
               "paperSuccessor": bool(paper)}


def _cmd_c1_fleet_git_failure_compat(args, account: str) -> int:
    """Dispatch the one closed chatgpt1 gateway-only transition.

    The successor is compiled from the exact installed predecessor bytes, so
    no caller-supplied source bundle reaches the installation. A read-only
    preflight works while the service still runs; a modifying transaction
    holds the incumbent persistent lifecycle lock inode through apply and
    reconciliation.
    """
    _validate_account_label(account)
    if account != C1_GIT_FAILURE_COMPAT_ACCOUNT:
        raise SystemExit(
            "C1 fleet gateway compatibility requires the enrolled chatgpt1 "
            "owner and an exact manifest CAS")
    label = f"com.mastermind.studio-direct-private.{account}"
    if not os.path.isabs(args.source):
        raise SystemExit("--source must be absolute")
    source = Path(args.source)
    if source.is_symlink() or not source.is_dir():
        raise SystemExit(f"source dir invalid: {source}")
    node_abs = _resolve_abs("--node", args.node)
    backend_abs = _resolve_abs("--backend", args.backend)
    port = int(args.port)
    _validate_port(port)
    roots = _build_runtime_roots(account)
    if getattr(args, "publisher_preflight_only", False) is True:
        with _c1_retained_pin_state(account, roots) as pin_state:
            return _upgrade_c1_fleet_git_failure_compat(
                args, source, node_abs, backend_abs, account, label, port, roots,
                pin_state=pin_state)
    with _c2_lifecycle_mutex(account):
        with _c1_retained_pin_state(account, roots, operation="apply") as pin_state:
            return _upgrade_c1_fleet_git_failure_compat(
                args, source, node_abs, backend_abs, account, label, port, roots,
                pin_state=pin_state)


def _upgrade_c1_fleet_git_failure_compat(
    args, source: Path, node_abs: Path, backend_abs: Path,
    account: str, label: str, port: int, roots: dict, *, pin_state: dict,
) -> int:
    """Replace ONLY the installed C1 fleet gateway with the reviewed successor.

    One closed, gateway-only transaction for the single already-enrolled
    ``chatgpt1`` seat. The incumbent owner keeps owning installation, the
    manifest/seal and the launchd lifecycle. This route replaces one module
    and its manifest digest; it changes no publisher module, configuration
    byte, fleet route, scheduling cap, dependency, package file, launcher,
    credential or grant, and it never creates a seat, installer, publisher,
    registry, queue or service.

    The administrator supplies the exact observed manifest digest (CAS). The
    gateway hash alone never qualifies an installation: the complete existing
    file map, manifest/config/plist hashes, dependency seal, Node/backend
    identity, account, port and the actual permitted publisher pair are all
    verified first.
    """
    expected = getattr(args, "publisher_expected_manifest_sha256", None)
    preview = getattr(args, "publisher_preflight_only", False)
    if (account != C1_GIT_FAILURE_COMPAT_ACCOUNT or type(preview) is not bool
            or not _sha256_hex(expected)
            or getattr(args, "fabric_only", False)
            or getattr(args, "enable_repository_workspaces", False)
            or getattr(args, "os_commission_config_sha256", None)):
        raise SystemExit(
            "C1 fleet gateway compatibility requires the enrolled chatgpt1 "
            "owner and an exact manifest CAS")
    manifest_path = roots["manifest"]
    config_path = roots["config"]
    gateway_path = roots["base"] / C1_GIT_FAILURE_COMPAT_GATEWAY
    for candidate in (manifest_path, config_path, gateway_path):
        _assert_dest_safe(candidate)
    if _stable_regular_file_hash(manifest_path, label="installed manifest") != expected:
        raise SystemExit("C1 fleet gateway compatibility: installed manifest CAS mismatch")
    prior = _verify_staged_install(account, label, roots, require_runtime_seal=True)
    if (prior.get("version") != MANIFEST_VERSION
            or frozenset(prior["files"]) != V2_CHATGPT1_FLEET_TAILNET_PREDECESSOR
            or not prior.get("dependencyTreeHash")
            or prior.get("node") != str(node_abs)
            or prior.get("backend") != str(backend_abs)
            or prior.get("host") != "127.0.0.1"
            or prior.get("port") != port):
        raise SystemExit("C1 fleet gateway compatibility: original sealed identity does not match")
    # Every preserved fleet module must still be the incumbent's exact
    # reviewed generation. Only the gateway itself is replaced.
    for name, expected_blob in FLEET_V10_PRESERVED_GIT_BLOBS.items():
        if name == C1_GIT_FAILURE_COMPAT_GATEWAY:
            continue
        candidate = roots["base"] / name
        _assert_dest_safe(candidate)
        data = candidate.read_bytes()
        actual = hashlib.sha1(
            b"blob " + str(len(data)).encode("ascii") + b"\0" + data
        ).hexdigest()
        if actual != expected_blob:
            raise SystemExit("C1 fleet gateway compatibility: preserved fleet generation changed")
    # The installed publisher pair must be one the incumbent already accepts.
    installed_pair = {name: prior["files"].get(name)
                      for name in ("git-publish.mjs", "workspace-access.mjs")}
    accepted_pairs = (
        dict(FLEET_V10_PUBLISHER_PATCH_SHA256),
        dict(FLEET_V10_MERGE_PUBLISHER_PREDECESSOR_SHA256),
        dict(FLEET_V10_POST_MERGE_PUBLISHER_PREDECESSOR_SHA256),
        dict(FLEET_V10_MERGE_PUBLISHER_PATCH_SHA256),
        {"git-publish.mjs": FLEET_V10_PREVIOUS_CLOSED_PUBLISHER_SHA256,
         "workspace-access.mjs": FLEET_V10_PUBLISHER_PATCH_SHA256["workspace-access.mjs"]},
    )
    if installed_pair not in accepted_pairs:
        raise SystemExit("C1 fleet gateway compatibility: unrecognized prior publisher identity")
    old_config_bytes = config_path.read_bytes()
    old_manifest_bytes = manifest_path.read_bytes()
    if (hashlib.sha256(old_config_bytes).hexdigest() != prior["configHash"]
            or hashlib.sha256(old_manifest_bytes).hexdigest() != expected):
        raise SystemExit("C1 fleet gateway compatibility: verified snapshot changed during preflight")
    try:
        old_config = json.loads(old_config_bytes)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise SystemExit("C1 fleet gateway compatibility: original config invalid") from exc
    routes = old_config.get("fleetRouting") if type(old_config) is dict else None
    if (type(old_config) is not dict
            or type(routes) is not dict or routes.get("enabled") is not True
            or not isinstance(routes.get("routes"), list) or len(routes["routes"]) < 1
            or type(old_config.get("fleetStatus")) is not dict
            or old_config.get("fabricOnly") is True
            or "commissionPublication" in old_config
            or "modernFabricProtocol" in old_config):
        raise SystemExit("C1 fleet gateway compatibility: original scoped capabilities changed")
    # The installed gateway must be exactly the reviewed predecessor. The
    # compiler refuses anything else, including a preimage with one changed
    # byte, several anchors or a preimage that is already patched.
    installed_gateway = gateway_path.read_bytes()
    compat = _fleet_git_failure_compat_module()
    try:
        compat.verify_preimage(installed_gateway)
        successor = compat.compile_successor(installed_gateway)
    except compat.CompatError as exc:
        raise SystemExit(
            "C1 fleet gateway compatibility: installed gateway is not the reviewed "
            f"predecessor ({exc.code})") from None
    if (hashlib.sha256(successor).hexdigest() != C1_GIT_FAILURE_COMPAT_SUCCESSOR_SHA256
            or compat.git_blob_sha1(successor) != C1_GIT_FAILURE_COMPAT_SUCCESSOR_GIT_BLOB):
        raise SystemExit("C1 fleet gateway compatibility: compiled successor is not the pinned successor")
    # A retained native-pool pin is qualified before anything is written. A
    # pending, unknown or foreign pin refuses; an applied pin keeps its own
    # records, plan, result and native phase untouched.
    if pin_state.get("present") and not pin_state.get("applicable"):
        raise SystemExit(
            "C1 fleet gateway compatibility: retained native-pool pin is "
            f"{pin_state.get('state')} and cannot be advanced")
    future = dict(prior)
    future["files"] = dict(prior["files"])
    future["files"][C1_GIT_FAILURE_COMPAT_GATEWAY] = hashlib.sha256(successor).hexdigest()
    if not _valid_manifest(future, account, label):
        raise SystemExit("C1 fleet gateway compatibility: prospective manifest invalid")
    target_manifest_bytes = json.dumps(future, indent=2, sort_keys=True).encode("utf-8")
    if _stable_regular_file_hash(manifest_path, label="installed manifest") != expected:
        raise SystemExit("C1 fleet gateway compatibility: installed state changed during planning")
    diff = compat.diff_report(installed_gateway, successor)
    guard = compat.guard_report(successor)
    if preview:
        try:
            stopped = _lifecycle_inspect(account, label, roots, require_positive=True) is None
            blocker = None
        except SystemExit as exc:
            stopped = False
            blocker = str(exc)
        print(json.dumps({
            "preflight": True, "effect": "NOT_APPLIED", "account": account,
            "label": label, "port": port,
            "originalManifestSha256": expected,
            "targetManifestSha256": hashlib.sha256(target_manifest_bytes).hexdigest(),
            "gatewayModule": C1_GIT_FAILURE_COMPAT_GATEWAY,
            "preimageGatewaySha256": C1_GIT_FAILURE_COMPAT_PREDECESSOR_SHA256,
            "preimageGatewayGitBlob": C1_GIT_FAILURE_COMPAT_PREDECESSOR_GIT_BLOB,
            "targetGatewaySha256": C1_GIT_FAILURE_COMPAT_SUCCESSOR_SHA256,
            "targetGatewayGitBlob": C1_GIT_FAILURE_COMPAT_SUCCESSOR_GIT_BLOB,
            "targetGatewaySize": len(successor),
            "sourceDiff": {"hunks": diff["hunks"], "addedLines": diff["addedLines"],
                           "removedLines": diff["removedLines"]},
            "preservedGuard": guard,
            "preservedFiles": sorted(prior["files"]),
            "publisherPairPreserved": installed_pair,
            "fleetRoutesPreserved": len(routes["routes"]),
            "concurrencyPreserved": [old_config.get("maxPerSessionConcurrency"),
                                     old_config.get("maxQueuedPerSession")],
            "configBytesPreserved": True,
            "nativePoolPin": pin_state,
            "serviceStopped": stopped,
            "blocker": blocker,
            "serviceStarted": False,
        }, sort_keys=True))
        return 0
    # A stopped-service prerequisite needs a positive stop proof. The generic
    # launchd probe treats every nonzero launchctl result as absence, which is
    # not proof that the service stopped.
    if _lifecycle_inspect(account, label, roots, require_positive=True) is not None:
        raise SystemExit("refusing C1 fleet gateway upgrade while service is loaded; stop first")
    # Reconfirm every observed byte immediately before the first effect.
    if (_stable_regular_file_hash(manifest_path, label="installed manifest") != expected
            or _stable_regular_file_hash(config_path, label="installed config") != prior["configHash"]
            or hashlib.sha256(gateway_path.read_bytes()).hexdigest()
            != C1_GIT_FAILURE_COMPAT_PREDECESSOR_SHA256):
        raise SystemExit("C1 fleet gateway compatibility: original installation changed")
    old_bytes = {gateway_path: installed_gateway, manifest_path: old_manifest_bytes}
    planned = {gateway_path: successor, manifest_path: target_manifest_bytes}
    committed = False
    try:
        for target, payload in planned.items():
            _atomic_write_bytes(target, payload)
        committed = True
        _verify_staged_install(account, label, roots, require_runtime_seal=True)
    except BaseException as exc:
        if committed:
            raise SystemExit(
                "C1 fleet gateway compatibility: EFFECT_UNKNOWN after manifest commit; "
                "inspect the original service before attempting recovery"
            ) from exc
        try:
            # os.replace may have succeeded even when a later fsync failed, so
            # a return-code ledger cannot prove which file changed. Reconcile
            # every planned path by bytes and distinguish the exact original,
            # the exact target and any foreign or mixed bytes.
            if _lifecycle_inspect(account, label, roots, require_positive=True) is not None:
                raise RuntimeError("service became loaded during transaction")
            observed = {target: target.read_bytes() for target in planned}
            if any(observed[target] not in (old_bytes[target], planned[target])
                   for target in planned):
                raise RuntimeError("foreign or mixed bytes while recovering")
            for target in reversed(tuple(planned)):
                if observed[target] != old_bytes[target]:
                    _atomic_write_bytes(target, old_bytes[target])
            if (any(target.read_bytes() != old_bytes[target] for target in planned)
                    or _stable_regular_file_hash(manifest_path, label="installed manifest") != expected):
                raise RuntimeError("rollback byte identity differs")
            _verify_staged_install(account, label, roots, require_runtime_seal=True)
        except BaseException as rollback_exc:
            raise SystemExit(
                "C1 fleet gateway compatibility: EFFECT_UNKNOWN during rollback; "
                "do not restart or replay until the original state is reconciled"
            ) from rollback_exc
        raise SystemExit(
            "C1 fleet gateway compatibility: NOT_APPLIED; original state restored") from exc
    print(json.dumps({
        "c1FleetGitFailureCompatibility": True, "account": account, "effect": "APPLIED",
        "label": label, "port": port,
        "manifestSha256": _sha256_file(manifest_path),
        "gatewayModule": C1_GIT_FAILURE_COMPAT_GATEWAY,
        "targetGatewaySha256": C1_GIT_FAILURE_COMPAT_SUCCESSOR_SHA256,
        "targetGatewayGitBlob": C1_GIT_FAILURE_COMPAT_SUCCESSOR_GIT_BLOB,
        "otherFleetModulesPreserved": True,
        "publisherPairPreserved": True,
        "configBytesPreserved": True,
        "nativePoolPin": pin_state,
        "serviceStarted": False,
    }, sort_keys=True))
    return 0


def _upgrade_c2_business_original_fleet_mastermind_only(
    args, source: Path, node_abs: Path, backend_abs: Path,
    account: str, label: str, port: int, roots: dict,
) -> int:
    """One original installer transaction: C2's exact 11-file -> 12-file source.

    Preserves every configured capability and original Mastermind-only Git
    boundary. No auto-enrollment of Macro/Terminal, no service restart, and no
    cross-seat copying of secrets/config. Source bytes are pinned independently
    of the supplied directory and must be reviewed before any live release.
    """
    expected = getattr(args, "publisher_expected_manifest_sha256", None)
    preview = getattr(args, "publisher_preflight_only", False)
    if (account not in ("chatgpt2-business", C2_PAPER_ACCOUNT) or type(preview) is not bool
            or not _sha256_hex(expected)
            or getattr(args, "enable_repository_workspaces", False) is True
            or getattr(args, "fabric_only", False) is True
            or type(getattr(args, "os_commission_config_sha256", None)) is str):
        raise SystemExit("C2 compatibility requires original Business owner, sealed manifest CAS and no new repository grants")
    personal = account == C2_PAPER_ACCOUNT
    if ((getattr(args, "c2_business_fleet_compat", False) is True)
            == (getattr(args, "c2_personal_closed_publisher", False) is True)):
        raise SystemExit("C2 compatibility: select one original owner operation")
    if personal != (getattr(args, "c2_personal_closed_publisher", False) is True):
        raise SystemExit("C2 compatibility: operation/account mismatch")
    target_patch = C2_PERSONAL_TARGET_PATCH_SHA256 if personal else C2_BUSINESS_TARGET_PATCH_SHA256
    manifest_path = roots["manifest"]
    config_path = roots["config"]
    if _stable_regular_file_hash(manifest_path, label="installed manifest") != expected:
        raise SystemExit("C2 compatibility: original manifest CAS mismatch")
    if personal and expected != C2_PERSONAL_CURRENT_MANIFEST_SHA256:
        raise SystemExit("C2 compatibility: Personal identity mismatch")
    prior = _verify_staged_install(
        account, label, roots, require_runtime_seal=True)
    if (prior.get("version") != MANIFEST_VERSION
            or frozenset(prior["files"]) != V2_C2_BUSINESS_FLEET_PREDECESSOR
            or not prior.get("dependencyTreeHash")
            or prior.get("node") != str(node_abs)
            or prior.get("backend") != str(backend_abs)
            or prior.get("host") != "127.0.0.1"
            or prior.get("port") != port):
        raise SystemExit("C2 compatibility: original sealed identity does not match")
    original_blobs = C2_PAPER_FILES_SHA256 if personal else C2_BUSINESS_V10_ORIGINAL_BLOBS
    for name, expected_blob in original_blobs.items():
        installed = roots["base"] / name
        _assert_dest_safe(installed)
        raw = installed.read_bytes()
        observed_blob = hashlib.sha1(
            b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw
        ).hexdigest()
        if (hashlib.sha256(raw).hexdigest() if personal else observed_blob) != expected_blob:
            raise SystemExit("C2 compatibility: original generation changed")
    if frozenset(original_blobs) != V2_C2_BUSINESS_FLEET_PREDECESSOR:
        raise SystemExit("C2 compatibility: pinned predecessor incomplete")
    if (_stable_regular_file_hash(config_path, label="installed config")
            != prior["configHash"]):
        raise SystemExit("C2 compatibility: original config changed")
    old_config_bytes = config_path.read_bytes()
    try:
        old_config = json.loads(old_config_bytes)
    except (ValueError, UnicodeError) as exc:
        raise SystemExit("C2 compatibility: original config unreadable") from exc
    if (type(old_config) is not dict
            or "repositoryWorkspaces" in old_config
            or old_config.get("gitPublish") != _typed_git_config(_user_root())
            or old_config.get("fleetRouting", {}).get("enabled") is not True
            or len(old_config["fleetRouting"].get("routes", [])) != 2
            or old_config.get("maxPerSessionConcurrency") != 8
            or old_config.get("maxQueuedPerSession") != 16
            or type(old_config.get("fleetStatus")) is not dict
            or old_config.get("fabricOnly") is True
            or "commissionPublication" in old_config
            or "modernFabricProtocol" in old_config):
        raise SystemExit("C2 compatibility: original Mastermind-only capabilities changed")
    if (hashlib.sha256(old_config_bytes).hexdigest() != prior["configHash"]
            or _stable_regular_file_hash(manifest_path, label="installed manifest") != expected):
        raise SystemExit("C2 compatibility: original snapshot changed")
    if frozenset(target_patch) != frozenset((
            "gateway.mjs", "git-publish.mjs", "workspace-access.mjs")):
        raise SystemExit("C2 compatibility: proposed patch scope invalid")
    old_modules: dict[str, bytes | None] = {}
    new_modules: dict[str, bytes] = {}
    for name, digest in target_patch.items():
        installed = roots["base"] / name
        staged = source / name
        _assert_dest_safe(installed)
        if staged.is_symlink() or not staged.is_file():
            raise SystemExit("C2 compatibility: reviewed source module missing")
        data = staged.read_bytes()
        if hashlib.sha256(data).hexdigest() != digest:
            raise SystemExit("C2 compatibility: reviewed source hash mismatch")
        if name in prior["files"]:
            original = installed.read_bytes()
            if hashlib.sha256(original).hexdigest() != prior["files"][name]:
                raise SystemExit("C2 compatibility: installed module hash mismatch")
            old_modules[name] = original
        else:
            if installed.exists() or installed.is_symlink():
                raise SystemExit("C2 compatibility: new module already exists")
            old_modules[name] = None
        new_modules[name] = data
    new_config = dict(old_config)
    if personal:
        new_config["gitPublish"] = _typed_git_config(_user_root(), closed_repositories=True)
        new_config["repositoryWorkspaces"] = {"enabled": True, "allowedRepositories": ["mastermind", "macro", "terminal"]}
    future = dict(prior)
    future["files"] = dict(prior["files"])
    for name, data in new_modules.items():
        future["files"][name] = hashlib.sha256(data).hexdigest()
    if personal:
        future["configHash"] = hashlib.sha256(json.dumps(new_config, indent=2, sort_keys=True).encode()).hexdigest()
    if (frozenset(future["files"]) != V2_CHATGPT1_FLEET_TAILNET_PREDECESSOR
            or not _valid_manifest(future, account, label)):
        raise SystemExit("C2 compatibility: proposed 12-file sealed manifest refused")
    new_manifest_bytes = json.dumps(
        future, indent=2, sort_keys=True).encode("utf-8")
    if _stable_regular_file_hash(manifest_path, label="installed manifest") != expected:
        raise SystemExit("C2 compatibility: original manifest changed during preflight")
    if preview:
        print(json.dumps({
            "preflight": True, "effect": "NOT_APPLIED",
            "account": account, "originalManifestSha256": expected,
            "changedModules": sorted(new_modules),
            "noNewRepositoryGrants": not personal, "closedRepositoriesEnabled": personal,
            "fleetRoutesPreserved": 2,
            "concurrencyPreserved": [8, 16],
            "serviceStarted": False,
        }, sort_keys=True))
        return 0
    if _launchd_inspect(label) is not None:
        raise SystemExit("refusing C2 compatibility upgrade while service is loaded; stop first")
    if (_stable_regular_file_hash(manifest_path, label="installed manifest") != expected
            or _stable_regular_file_hash(config_path, label="installed config") != prior["configHash"]
            or any(_sha256_file(roots["base"] / n) != prior["files"][n]
                   for n in prior["files"])
            or (roots["base"] / "workspace-access.mjs").exists()):
        raise SystemExit("C2 compatibility: previous installation changed before write")
    before = {roots["base"] / n: old_modules[n] for n in new_modules}
    if personal:
        before[config_path] = old_config_bytes
    before[manifest_path] = manifest_path.read_bytes()
    planned = {roots["base"] / n: new_modules[n] for n in new_modules}
    if personal:
        planned[config_path] = json.dumps(new_config, indent=2, sort_keys=True).encode()
    planned[manifest_path] = new_manifest_bytes
    committed = False
    try:
        for target, payload in planned.items():
            # A file which was previously absent must still be absent immediately
            # before the attempted create. Unexpected new files never get clobbered.
            if before[target] is None and (target.exists() or target.is_symlink()):
                raise RuntimeError("unexpected third-party new module")
            _atomic_write_bytes(target, payload)
        committed = True
        _verify_staged_install(
            account, label, roots, require_runtime_seal=True)
    except BaseException as exc:
        if committed:
            raise SystemExit(
                "C2 compatibility: EFFECT_UNKNOWN after manifest commit; "
                "inspect original installed state before recovery"
            ) from exc
        try:
            if _launchd_inspect(label) is not None:
                raise RuntimeError("service became loaded during compatibility transaction")
            observed = {}
            for target, new_bytes in planned.items():
                if target.is_symlink():
                    raise RuntimeError("unexpected symlink during recovery")
                observed[target] = target.read_bytes() if target.exists() else None
                if observed[target] not in (before[target], new_bytes):
                    raise RuntimeError("concurrent out-of-scope file mutation")
            for target in reversed(tuple(planned)):
                if observed[target] == before[target]:
                    continue
                if before[target] is None:
                    # This pathname was absent before our transaction.
                    target.unlink()
                    parent_fd = os.open(target.parent, os.O_RDONLY)
                    try:
                        os.fsync(parent_fd)
                    finally:
                        os.close(parent_fd)
                else:
                    _atomic_write_bytes(target, before[target])
            if (any((t.read_bytes() if t.exists() else None) != before[t]
                    for t in planned)
                    or _stable_regular_file_hash(manifest_path, label="installed manifest") != expected):
                raise RuntimeError("original installation could not be restored")
            _verify_staged_install(
                account, label, roots, require_runtime_seal=True)
        except BaseException as recovery_error:
            raise SystemExit(
                "C2 compatibility: EFFECT_UNKNOWN during rollback; "
                "do not retry or restart without exact effect reconciliation"
            ) from recovery_error
        raise SystemExit("C2 compatibility: NOT_APPLIED original state restored") from exc
    print(json.dumps({
        "account": account, "effect": "APPLIED",
        "gatewayCompatibilityInstalled": True,
        "manifestSha256": _sha256_file(manifest_path),
        "noNewRepositoryGrants": not personal, "closedRepositoriesEnabled": personal,
        "fleetModulesPreserved": True,
        "serviceStarted": False,
    }, sort_keys=True))
    return 0


def _enroll_c2_business_closed_repositories(
    args, node_abs: Path, backend_abs: Path, account: str,
    label: str, port: int, roots: dict,
) -> int:
    """One existing-installer CAS grant, only after the reviewed C2 11->12 repair.

    This does not replace a fleet gateway, switch a source/credential, create a
    repository or execute Git. Only the existing closed profile and its exact
    manifest hash may change. Caller-selected destinations remain impossible.
    """
    expected = getattr(args, "publisher_expected_manifest_sha256", None)
    preview = getattr(args, "publisher_preflight_only", False)
    if (account != "chatgpt2-business" or type(preview) is not bool
            or not _sha256_hex(expected)
            or getattr(args, "enable_repository_workspaces", False) is not True
            or getattr(args, "publisher_only_fleet_v10", False) is True
            or getattr(args, "c2_business_fleet_compat", False) is True
            or getattr(args, "fabric_only", False) is True
            or getattr(args, "c2_personal_git_timeout_only", False) is True
            or getattr(args, "os_commission_config_sha256", None) is not None):
        raise SystemExit("C2 repository enrollment requires the exact Business profile, explicit opt-in and manifest CAS")

    manifest_path, config_path = roots["manifest"], roots["config"]
    for target in (manifest_path, config_path):
        _assert_dest_safe(target)
    if _stable_regular_file_hash(manifest_path, label="installed manifest") != expected:
        raise SystemExit("C2 repository enrollment: original manifest CAS mismatch")
    prior = _verify_staged_install(
        account, label, roots, require_runtime_seal=True)
    if (prior.get("version") != MANIFEST_VERSION
            or not prior.get("dependencyTreeHash")
            or frozenset(prior["files"]) != V2_CHATGPT1_FLEET_TAILNET_PREDECESSOR
            or frozenset(prior["files"]) !=
                (frozenset(C2_BUSINESS_V10_ORIGINAL_BLOBS) | {"workspace-access.mjs"})
            or prior.get("node") != str(node_abs)
            or prior.get("backend") != str(backend_abs)
            or prior.get("host") != "127.0.0.1"
            or prior.get("port") != port):
        raise SystemExit("C2 repository enrollment: reviewed installed generation does not match")

    # The earlier C2 compatibility transaction pins all original unchanged
    # modules and exactly three reviewed replacements, including the publisher.
    # Never grant closed repository access to an unknown source generation.
    for name in prior["files"]:
        path = roots["base"] / name
        _assert_dest_safe(path)
        reviewed_digest = C2_BUSINESS_TARGET_PATCH_SHA256.get(name)
        if reviewed_digest is not None:
            if prior["files"][name] != reviewed_digest or _sha256_file(path) != reviewed_digest:
                raise SystemExit("C2 repository enrollment: reviewed publisher source changed")
        else:
            raw = path.read_bytes()
            blob = hashlib.sha1(
                b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw
            ).hexdigest()
            if blob != C2_BUSINESS_V10_ORIGINAL_BLOBS[name]:
                raise SystemExit("C2 repository enrollment: original fleet source changed")

    old_manifest = manifest_path.read_bytes()
    old_config = config_path.read_bytes()
    if (hashlib.sha256(old_manifest).hexdigest() != expected
            or hashlib.sha256(old_config).hexdigest() != prior["configHash"]):
        raise SystemExit("C2 repository enrollment: original snapshot changed")
    try:
        current = json.loads(old_config)
    except (ValueError, UnicodeError) as exc:
        raise SystemExit("C2 repository enrollment: original configuration unreadable") from exc
    user_root = _user_root()
    if (type(current) is not dict
            or current.get("accountLabel") != account
            or current.get("gitPublish") != _typed_git_config(user_root)
            or "repositoryWorkspaces" in current
            or current.get("fleetRouting", {}).get("enabled") is not True
            or len(current["fleetRouting"].get("routes", [])) != 2
            or current.get("maxPerSessionConcurrency") != 8
            or current.get("maxQueuedPerSession") != 16
            or type(current.get("fleetStatus")) is not dict
            or type(current.get("paperDesign")) is not dict
            or current.get("fabricOnly") is True
            or "commissionPublication" in current
            or "modernFabricProtocol" in current):
        raise SystemExit("C2 repository enrollment: original Mastermind-only fleet profile changed")

    future_config = dict(current)
    future_config["gitPublish"] = _typed_git_config(
        user_root, closed_repositories=True)
    future_config["repositoryWorkspaces"] = {
        "enabled": True,
        "allowedRepositories": ["mastermind", "macro", "terminal"],
    }
    preserved = set(current) - {"gitPublish", "repositoryWorkspaces"}
    if any(future_config[key] != current[key] for key in preserved):
        raise SystemExit("C2 repository enrollment: unrelated configuration changed")
    new_config = json.dumps(
        future_config, indent=2, sort_keys=True).encode("utf-8")
    future_manifest = dict(prior)
    future_manifest["configHash"] = hashlib.sha256(new_config).hexdigest()
    if not _valid_manifest(future_manifest, account, label):
        raise SystemExit("C2 repository enrollment: proposed sealed manifest refused")
    new_manifest = json.dumps(
        future_manifest, indent=2, sort_keys=True).encode("utf-8")
    target_sha = hashlib.sha256(new_manifest).hexdigest()
    if _stable_regular_file_hash(manifest_path, label="installed manifest") != expected:
        raise SystemExit("C2 repository enrollment: manifest changed during preflight")
    receipt = {
        "account": account,
        "originalManifestSha256": expected,
        "targetManifestSha256": target_sha,
        "closedRepositories": ["mastermind", "macro", "terminal"],
        "fleetRoutesPreserved": 2,
        "concurrencyPreserved": [8, 16],
        "gatewayAndModuleBytesPreserved": True,
        "serviceStarted": False,
    }
    if preview:
        print(json.dumps({**receipt, "preflight": True, "effect": "NOT_APPLIED"}, sort_keys=True))
        return 0

    if _lifecycle_inspect(account, label, roots) is not None:
        raise SystemExit("refusing C2 repository enrollment while service is loaded; stop first")
    if (_verify_staged_install(account, label, roots, require_runtime_seal=True) != prior
            or _stable_regular_file_hash(manifest_path, label="installed manifest") != expected
            or _stable_regular_file_hash(config_path, label="installed config") != prior["configHash"]):
        raise SystemExit("C2 repository enrollment: original state changed before write")

    planned = {config_path: new_config, manifest_path: new_manifest}
    original = {config_path: old_config, manifest_path: old_manifest}
    committed = False
    try:
        _atomic_write_bytes(config_path, new_config)
        if (_stable_regular_file_hash(manifest_path, label="installed manifest") != expected
                or _stable_regular_file_hash(config_path, label="installed config") != future_manifest["configHash"]
                or _lifecycle_inspect(account, label, roots) is not None):
            raise RuntimeError("C2 repository enrollment: original state changed before manifest commit")
        _atomic_write_bytes(manifest_path, new_manifest)
        committed = True
        if (_verify_staged_install(account, label, roots, require_runtime_seal=True) != future_manifest
                or _stable_regular_file_hash(manifest_path, label="installed manifest") != target_sha
                or _lifecycle_inspect(account, label, roots) is not None):
            raise RuntimeError("C2 repository enrollment: committed identity mismatch")
    except BaseException as exc:
        if committed:
            raise SystemExit(
                "C2 repository enrollment: EFFECT_UNKNOWN after manifest commit; "
                "reconcile exact original install before restart"
            ) from exc
        try:
            if _lifecycle_inspect(account, label, roots) is not None:
                raise RuntimeError("service became loaded during rollback")
            for path in planned:
                _assert_dest_safe(path)
                observed = path.read_bytes()
                if observed not in (planned[path], original[path]):
                    raise RuntimeError("non-owned mutation during recovery")
                if observed != original[path]:
                    _atomic_write_bytes(path, original[path])
            if (any(path.read_bytes() != original[path] for path in planned)
                    or _stable_regular_file_hash(manifest_path, label="installed manifest") != expected):
                raise RuntimeError("original state not restored")
            _verify_staged_install(account, label, roots, require_runtime_seal=True)
        except BaseException as rollback_error:
            raise SystemExit(
                "C2 repository enrollment: EFFECT_UNKNOWN during rollback; "
                "do not retry or restart without reconciliation"
            ) from rollback_error
        raise SystemExit("C2 repository enrollment: NOT_APPLIED original state restored") from exc

    print(json.dumps({**receipt, "preflight": False, "effect": "APPLIED"}, sort_keys=True))
    return 0


def _upgrade_c2_personal_git_timeout_only(
    args, source: Path, node_abs: Path, backend_abs: Path,
    account: str, label: str, port: int, roots: dict,
) -> int:
    """Change only the bounded Git command timeout on exact sealed C2 Personal.

    Status prechecks can exceed 15s on the 127k-index Macro checkout under M2
    contention. This is not a repository grant, module upgrade, transport
    retry or a new publication authority. Manifest/config writes are fenced
    and the service must be unloaded before any mutation.
    """
    expected = getattr(args, "publisher_expected_manifest_sha256", None)
    preview = getattr(args, "publisher_preflight_only", False)
    if (account != C2_PAPER_ACCOUNT
            or getattr(args, "c2_personal_git_timeout_only", False) is not True
            or type(preview) is not bool or not _sha256_hex(expected)
            or expected != C2_PERSONAL_TIMEOUT_PREDECESSOR_SHA256
            or getattr(args, "c2_business_fleet_compat", False) is True
            or getattr(args, "c2_personal_closed_publisher", False) is True
            or getattr(args, "c2_business_repository_enrollment", False) is True
            or getattr(args, "publisher_only_fleet_v10", False) is True
            or getattr(args, "enable_repository_workspaces", False) is True
            or getattr(args, "fabric_only", False) is True
            or type(getattr(args, "os_commission_config_sha256", None)) is str):
        raise SystemExit("C2 Git timeout: original closed owner and manifest CAS required")
    manifest_path, config_path = roots["manifest"], roots["config"]
    if _stable_regular_file_hash(manifest_path, label="installed manifest") != expected:
        raise SystemExit("C2 Git timeout: installed manifest CAS mismatch")
    prior = _verify_staged_install(account, label, roots, require_runtime_seal=True)
    if (prior.get("version") != MANIFEST_VERSION
            or prior.get("source") != str(source)
            or prior.get("node") != str(node_abs)
            or prior.get("backend") != str(backend_abs)
            or prior.get("host") != "127.0.0.1"
            or prior.get("port") != port
            or not prior.get("dependencyTreeHash")
            or frozenset(prior["files"]) != V2_CHATGPT1_FLEET_TAILNET_PREDECESSOR):
        raise SystemExit("C2 Git timeout: runtime/source identity mismatch")
    if any(prior["files"].get(n) != digest
           for n, digest in C2_PERSONAL_TARGET_PATCH_SHA256.items()):
        raise SystemExit("C2 Git timeout: reviewed installed modules changed")
    old_config_bytes, old_manifest_bytes = config_path.read_bytes(), manifest_path.read_bytes()
    if (hashlib.sha256(old_config_bytes).hexdigest() != prior["configHash"]
            or hashlib.sha256(old_manifest_bytes).hexdigest() != expected):
        raise SystemExit("C2 Git timeout: sealed snapshot changed")
    try:
        old_config = json.loads(old_config_bytes)
    except (UnicodeError, ValueError) as exc:
        raise SystemExit("C2 Git timeout: config not valid JSON") from exc
    original_git = _typed_git_config(_user_root(), closed_repositories=True)
    if (type(old_config) is not dict or old_config.get("accountLabel") != account
            or old_config.get("gitPublish") != original_git
            or old_config.get("repositoryWorkspaces") != {
                "enabled": True, "allowedRepositories": ["mastermind", "macro", "terminal"]}
            or old_config.get("fleetRouting", {}).get("enabled") is not True
            or len(old_config["fleetRouting"].get("routes", [])) != 2
            or old_config.get("maxPerSessionConcurrency") != 8
            or old_config.get("maxQueuedPerSession") != 16
            or old_config.get("paperDesign", {}).get("enabled") is not True
            or old_config.get("fabricOnly") is True
            or "commissionPublication" in old_config
            or "modernFabricProtocol" in old_config):
        raise SystemExit("C2 Git timeout: installed capability identity changed")
    new_config = dict(old_config)
    new_git = dict(original_git)
    new_git["commandTimeoutMs"] = C2_PERSONAL_TIMEOUT_COMMAND_MS
    new_config["gitPublish"] = new_git
    if ({k: v for k, v in new_config.items() if k != "gitPublish"}
            != {k: v for k, v in old_config.items() if k != "gitPublish"}):
        raise SystemExit("C2 Git timeout: unrelated config change")
    config_bytes = json.dumps(new_config, indent=2, sort_keys=True).encode("utf-8")
    future = dict(prior)
    future["configHash"] = hashlib.sha256(config_bytes).hexdigest()
    if not _valid_manifest(future, account, label):
        raise SystemExit("C2 Git timeout: target sealed manifest refused")
    manifest_bytes = json.dumps(future, indent=2, sort_keys=True).encode("utf-8")
    if _stable_regular_file_hash(manifest_path, label="installed manifest") != expected:
        raise SystemExit("C2 Git timeout: manifest moved during planning")
    if preview:
        print(json.dumps({
            "account": account, "effect": "NOT_APPLIED", "preflight": True,
            "originalManifestSha256": expected,
            "commandTimeoutBeforeMs": original_git["commandTimeoutMs"],
            "commandTimeoutAfterMs": C2_PERSONAL_TIMEOUT_COMMAND_MS,
            "pushTimeoutPreservedMs": original_git["pushTimeoutMs"],
            "changedFiles": ["config.json", "manifest.json"],
            "sourceModulesPreserved": True, "fleetAndPaperPreserved": True,
            "serviceStarted": False,
        }, sort_keys=True))
        return 0
    if _lifecycle_inspect(account, label, roots) is not None:
        raise SystemExit("C2 Git timeout: service must be stopped")
    if (_stable_regular_file_hash(manifest_path, label="installed manifest") != expected
            or _stable_regular_file_hash(config_path, label="installed config") != prior["configHash"]
            or _verify_staged_install(account, label, roots, require_runtime_seal=True) != prior):
        raise SystemExit("C2 Git timeout: original installation changed before mutation")
    before = {config_path: old_config_bytes, manifest_path: old_manifest_bytes}
    planned = {config_path: config_bytes, manifest_path: manifest_bytes}
    committed = False
    try:
        for target, payload in planned.items():
            _atomic_write_bytes(target, payload)
        committed = True
        _verify_staged_install(account, label, roots, require_runtime_seal=True)
    except BaseException as exc:
        if committed:
            raise SystemExit("C2 Git timeout: EFFECT_UNKNOWN after manifest commit") from exc
        try:
            if _lifecycle_inspect(account, label, roots) is not None:
                raise RuntimeError("service restarted during config transaction")
            observed = {}
            for target in planned:
                if target.is_symlink():
                    raise RuntimeError("symlink detected during rollback")
                observed[target] = target.read_bytes()
                if observed[target] not in (before[target], planned[target]):
                    raise RuntimeError("concurrent out-of-scope change during rollback")
            for target in reversed(tuple(planned)):
                if observed[target] != before[target]:
                    _atomic_write_bytes(target, before[target])
            if (any(target.read_bytes() != before[target] for target in planned)
                    or _stable_regular_file_hash(manifest_path, label="installed manifest") != expected):
                raise RuntimeError("original sealed bytes could not be restored")
            _verify_staged_install(account, label, roots, require_runtime_seal=True)
        except BaseException as recovery_error:
            raise SystemExit("C2 Git timeout: EFFECT_UNKNOWN during rollback") from recovery_error
        raise SystemExit("C2 Git timeout: NOT_APPLIED original state restored") from exc
    print(json.dumps({
        "account": account, "effect": "APPLIED",
        "manifestSha256": _sha256_file(manifest_path),
        "commandTimeoutMs": C2_PERSONAL_TIMEOUT_COMMAND_MS,
        "pushTimeoutPreservedMs": original_git["pushTimeoutMs"],
        "sourceModulesPreserved": True, "fleetAndPaperPreserved": True,
        "serviceStarted": False,
    }, sort_keys=True))
    return 0


@_fabric_lifecycle_serialized()
@_original_upgrade_serialized
def cmd_upgrade(args) -> int:
    account = args.account
    # The closed C1 gateway-only route is dispatched before the generic restage
    # refusal. It qualifies the retained native-pool pin itself, replaces one
    # module and never restages the seat, so it is not a generic capability
    # rebuild. Every other account and every generic upgrade keeps the
    # existing refusal unchanged.
    if getattr(args, "c1_fleet_git_failure_compat", False) is True:
        return _cmd_c1_fleet_git_failure_compat(args, account)
    _pin_reject_generic_restage(account)
    _validate_account_label(account)
    label = f"com.mastermind.studio-direct-private.{account}"
    host = "127.0.0.1"

    if not os.path.isabs(args.source):
        raise SystemExit("--source must be absolute")
    source = Path(args.source)
    if source.is_symlink() or not source.is_dir():
        raise SystemExit(f"source dir invalid: {source}")
    # C2 fleet predecessor migration is a tightly hash-pinned three-module
    # compatibility package, NOT the incompatible current STAGE_FILES bundle.
    if not (
        getattr(args, "c2_business_fleet_compat", False) is True
        or getattr(args, "c2_personal_closed_publisher", False) is True
        or getattr(args, "c2_personal_git_timeout_only", False) is True
        or getattr(args, "c2_business_repository_enrollment", False) is True
    ):
        _check_source_files(source)
    node_abs = _resolve_abs("--node", args.node)
    backend_abs = _resolve_abs("--backend", args.backend)
    port = int(args.port)
    _validate_port(port)

    roots = _build_runtime_roots(account)
    if getattr(args, "c2_personal_git_timeout_only", False) is True:
        # The C2 Personal timeout migration shares the exact same installed
        # files/manifest with Paper and publisher writers. Retain the protected
        # C2 lifecycle mutex for a modifying transaction, not for read-only
        # preflight. Do not introduce a second lock/owner or a bypass.
        if (account == C2_PAPER_ACCOUNT
                and getattr(args, "publisher_preflight_only", False) is False):
            with _c2_lifecycle_mutex(account):
                return _upgrade_c2_personal_git_timeout_only(
                    args, source, node_abs, backend_abs, account, label, port, roots)
        return _upgrade_c2_personal_git_timeout_only(
            args, source, node_abs, backend_abs, account, label, port, roots)
    if (getattr(args, "c2_business_fleet_compat", False) is True
            or getattr(args, "c2_personal_closed_publisher", False) is True):
        # Both existing C2 compatibility writers share installation state with
        # Paper/lifecycle operations. Hold the same inode through recovery too.
        # Read-only preflight and the helper's exact eligibility stay unchanged.
        if (account in C2_PAPER_UPGRADE_ACCOUNTS
                and getattr(args, "publisher_preflight_only", False) is False):
            with _c2_lifecycle_mutex(account):
                return _upgrade_c2_business_original_fleet_mastermind_only(
                    args, source, node_abs, backend_abs, account, label, port, roots)
        return _upgrade_c2_business_original_fleet_mastermind_only(
            args, source, node_abs, backend_abs, account, label, port, roots)
    if getattr(args, "c2_business_repository_enrollment", False) is True:
        if getattr(args, "publisher_preflight_only", False) is True:
            return _enroll_c2_business_closed_repositories(
                args, node_abs, backend_abs, account, label, port, roots)
        with _c2_lifecycle_mutex(account):
            return _enroll_c2_business_closed_repositories(
                args, node_abs, backend_abs, account, label, port, roots)
    if getattr(args, "publisher_only_fleet_v10", False) is True:
        return _upgrade_fleet_v10_publisher_only(
            args, source, node_abs, backend_abs, account, label, port, roots)
    # Legacy call sites carry mock objects with no new CLI attributes.
    # Reject only actual explicit option values, not arbitrary Mock values.
    if (getattr(args, "publisher_preflight_only", False) is True
            or type(getattr(args, "publisher_expected_manifest_sha256", None)) is str):
        raise SystemExit(
            "publisher preflight and CAS options require --publisher-only-fleet-v10 "
            "or --c1-fleet-git-failure-compat")
    observed = (_lifecycle_inspect(account, label, roots)
                if account == ORIGINAL_COLLECTION_ACCOUNT else _launchd_inspect(label))
    if observed is not None:
        raise SystemExit("refusing upgrade while service is running; stop first")
    # No original helper may still be in flight across the transition. A stale
    # marker is evidence of an interrupted dispatch and is never deleted
    # blindly; the owner resolves it explicitly.
    pending_helpers = _original_helper_pending(account)
    if pending_helpers:
        raise SystemExit(
            "refusing upgrade: an original collection helper is still pending: "
            + ", ".join(pending_helpers))
    resumed = _original_install_resume(args, source, node_abs, backend_abs, port, roots)
    if resumed is not None:
        return resumed
    prior = _verify_staged_install(
        account, label, roots, require_runtime_seal=False
    )
    if _sealed_v2_fleet_gateway_predecessor(prior, account):
        raise SystemExit(
            "refusing upgrade: sealed historical fleet modules require an "
            "independently reviewed capability-preserving migration"
        )
    if prior.get("version") == MANIFEST_VERSION and prior.get("dependencyTreeHash") is not None:
        _verify_staged_install(account, label, roots, require_runtime_seal=True)
    if (
        prior.get("node") != str(node_abs)
        or prior.get("backend") != str(backend_abs)
        or prior.get("host") != host
        or prior.get("port") != port
    ):
        raise SystemExit(
            "refusing upgrade: node, backend, host and port must match the existing install"
        )
    for path in _stage_dest_files(roots):
        _assert_dest_safe(path)
    fabric_only = _fabric_profile_setting(args, roots, prior)
    repository_workspaces = _repository_workspace_setting(args, roots, prior)
    commission_digest = _commission_setting(args, roots, prior)
    # Compute the exact target policy BEFORE the first installation write.
    # Recognizing a sealed historical manifest is not permission to remove
    # the original fleet routes, tailnet adapter, concurrency or telemetry.
    if frozenset(prior["files"]) in (
        V2_CHATGPT1_FLEET_TAILNET_PREDECESSOR,
        frozenset(C2_PAPER_FILES_SHA256),
        V2_C2_BUSINESS_FLEET_PREDECESSOR,
    ):
        projected = _build_config(
            account, host, port, node_abs, backend_abs, roots["state"],
            _user_root(), repository_workspaces=repository_workspaces,
            commission_digest=commission_digest, fabric_only=fabric_only,
        )
        _verify_upgrade_preserves_installed_fleet_capabilities(
            prior, roots, projected)
    retained_raw = _fabric_release_bytes(roots["config"])
    if hashlib.sha256(retained_raw).hexdigest() != prior["configHash"]:
        raise SystemExit("original upgrade configuration changed")
    previous_config = _original_json(retained_raw.decode("utf-8"))
    # Keep the existing restricted profile and the fixed publication seat's
    # already selected Paper generation. Runtime qualification precedes writes.
    retained_paper = None
    if not fabric_only:
        retained_paper = _publication_upgrade_paper_config(account, previous_config, _user_root())
        if retained_paper is None:
            _verify_paper_runtime(_user_root())

    modern_fabric = _modern_fabric_setting(args, roots, prior, fabric_only)
    original_collection = _original_collection_setting(args, roots, prior, fabric_only, modern_fabric)
    retained_config = None
    if previous_config.get("originalCollection") is not None:
        retained_config = dict(previous_config)
        if original_collection is None:
            retained_config.pop("originalCollection")
        else:
            retained_config["originalCollection"] = original_collection
    if retained_paper is not None:
        # Rebuild through the normal owner so an explicitly refreshed commission
        # digest still takes effect; retain only the exact qualified Paper member.
        if retained_config is None:
            retained_config = _build_config(
                account, host, port, node_abs, backend_abs, roots["state"], _user_root(),
                repository_workspaces=repository_workspaces, commission_digest=commission_digest,
                fabric_only=fabric_only, modern_fabric=modern_fabric,
                original_collection=original_collection,
            )
        retained_config["paperDesign"] = retained_paper
    return _write_install(
        source, node_abs, backend_abs, account, label, host, port, roots,
        result_key="upgraded", previous_source=str(prior.get("source") or ""),
        repository_workspaces=repository_workspaces,
        commission_digest=commission_digest,
        fabric_only=fabric_only,
        modern_fabric=modern_fabric,
        original_collection=original_collection,
        retained_config=retained_config,
        original_request=(_original_install_request(args)
            if account == ORIGINAL_COLLECTION_ACCOUNT and original_collection is not None
            and original_collection.get("predecessor") is not None else None),
        dependency_tree_hash=prior.get("dependencyTreeHash"),
    )


def _m1_paper_v20_upgrade(args) -> int:
    """Exact M1 chrisadmin v5->v20 Paper-only CAS. Never restage or start a service."""
    account = args.account
    if account != M1_PAPER_V20_ACCOUNT or getattr(args, "m1_v20", False) is not True:
        raise SystemExit("M1 Paper v20 requires its exact enrolled account and selector")
    if args.expected_manifest_sha256 != M1_PAPER_V5_MANIFEST_SHA256:
        raise SystemExit("M1 Paper v20 predecessor manifest CAS mismatch")
    label = f"com.mastermind.studio-direct-private.{account}"
    roots = _build_runtime_roots(account)
    for path in (roots["config"], roots["manifest"], roots["plist"]):
        _assert_dest_safe(path)
    if _stable_regular_file_hash(roots["manifest"], label="M1 manifest") != M1_PAPER_V5_MANIFEST_SHA256:
        raise SystemExit("M1 Paper v20 actual predecessor manifest changed")
    if _stable_regular_file_hash(roots["config"], label="M1 config") != M1_PAPER_V5_CONFIG_SHA256:
        raise SystemExit("M1 Paper v20 actual predecessor config changed")
    if _stable_regular_file_hash(roots["plist"], label="M1 plist") != M1_PAPER_V5_PLIST_SHA256:
        raise SystemExit("M1 Paper v20 original service identity changed")
    prior = _verify_staged_install(account, label, roots, require_runtime_seal=True)
    user_root = _user_root()
    _verify_paper_runtime(
        user_root, runtime_rel=M1_PAPER_V20_RUNTIME_REL,
        expected_sha=M1_PAPER_V20_BRIDGE_SHA256,
    )
    _verify_paper_runtime(
        user_root, runtime_rel=M1_PAPER_V5_RUNTIME_REL,
        expected_sha=M1_PAPER_V5_BRIDGE_SHA256,
    )
    old_config_bytes = roots["config"].read_bytes()
    old_manifest_bytes = roots["manifest"].read_bytes()
    try:
        old_config = json.loads(old_config_bytes)
    except (UnicodeError, ValueError) as exc:
        raise SystemExit("M1 Paper v20 original config invalid") from exc
    if type(old_config) is not dict:
        raise SystemExit("M1 Paper v20 original config invalid")
    old_paper = {
        "enabled": True,
        "pythonPath": str(user_root / M1_PAPER_V5_RUNTIME_REL / "venv/bin/python"),
        "bridgePath": str(user_root / M1_PAPER_V5_RUNTIME_REL / "source/bridge.py"),
        "bridgeSha256": M1_PAPER_V5_BRIDGE_SHA256,
        "appPath": str(user_root / PAPER_APP_REL),
        "commandTimeoutMs": PAPER_COMMAND_TIMEOUT_MS,
    }
    if old_config.get("paperDesign") != old_paper:
        raise SystemExit("M1 Paper v20 original Paper selection differs")
    nonpaper = {key: value for key, value in old_config.items() if key != "paperDesign"}
    nonpaper_sha = hashlib.sha256(json.dumps(
        nonpaper, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")).hexdigest()
    if nonpaper_sha != M1_PAPER_V5_NONPAPER_SHA256:
        raise SystemExit("M1 Paper v20 unrelated gateway configuration changed")
    target_paper = {
        **old_paper,
        "pythonPath": str(user_root / M1_PAPER_V20_RUNTIME_REL / "venv/bin/python"),
        "bridgePath": str(user_root / M1_PAPER_V20_RUNTIME_REL / "source/bridge.py"),
        "bridgeSha256": M1_PAPER_V20_BRIDGE_SHA256,
    }
    future_config = {**old_config, "paperDesign": target_paper}
    config_bytes = json.dumps(future_config, indent=2, sort_keys=True).encode("utf-8")
    future = {**prior, "configHash": hashlib.sha256(config_bytes).hexdigest()}
    if not _valid_manifest(future, account, label):
        raise SystemExit("M1 Paper v20 target manifest invalid")
    manifest_bytes = json.dumps(future, indent=2, sort_keys=True).encode("utf-8")
    target_manifest_sha = hashlib.sha256(manifest_bytes).hexdigest()
    receipt = {
        "account": account,
        "fromGeneration": "v5", "toGeneration": "v20",
        "protectedSourceRevision": M1_PAPER_V20_MERGE,
        "originalManifestSha256": M1_PAPER_V5_MANIFEST_SHA256,
        "targetManifestSha256": target_manifest_sha,
        "bridgeSha256": M1_PAPER_V20_BRIDGE_SHA256,
        "nonPaperConfigSha256": nonpaper_sha,
        "preservedGatewayFiles": len(prior["files"]),
        "runtimeSealPreserved": True, "sourcePointerPreserved": True,
        "serviceStarted": False,
    }
    if args.preflight_only:
        print(json.dumps({**receipt, "preflight": True, "effect": "NOT_APPLIED"}, sort_keys=True))
        return 0

    # The owner must bootout and drain the ORIGINAL service before one apply.
    # Keep the existing install lifecycle lock, no second lock or runtime plane.
    with _c2_lifecycle_mutex(account):
        if _lifecycle_inspect(account, label, roots, require_positive=True) is not None:
            raise SystemExit("M1 Paper v20 refusing selector while original service is loaded")
        if (_verify_staged_install(account, label, roots, require_runtime_seal=True) != prior
                or _stable_regular_file_hash(roots["manifest"], label="M1 manifest")
                != M1_PAPER_V5_MANIFEST_SHA256
                or _stable_regular_file_hash(roots["config"], label="M1 config")
                != M1_PAPER_V5_CONFIG_SHA256):
            raise SystemExit("M1 Paper v20 predecessor changed before selection")
        _verify_paper_runtime(user_root, runtime_rel=M1_PAPER_V20_RUNTIME_REL)
        committed = False
        try:
            _atomic_write_bytes(roots["config"], config_bytes)
            if (_stable_regular_file_hash(roots["manifest"], label="M1 manifest")
                    != M1_PAPER_V5_MANIFEST_SHA256
                    or _stable_regular_file_hash(roots["config"], label="M1 config")
                    != future["configHash"]
                    or _lifecycle_inspect(account, label, roots, require_positive=True) is not None):
                raise RuntimeError("M1 Paper v20 concurrent change before manifest commit")
            _atomic_write_bytes(roots["manifest"], manifest_bytes)
            committed = True
            if (_verify_staged_install(account, label, roots, require_runtime_seal=True) != future
                    or _stable_regular_file_hash(roots["manifest"], label="M1 manifest")
                    != target_manifest_sha):
                raise RuntimeError("M1 Paper v20 post-commit manifest verification failed")
            _verify_paper_runtime(user_root, runtime_rel=M1_PAPER_V20_RUNTIME_REL)
            if _lifecycle_inspect(account, label, roots, require_positive=True) is not None:
                raise RuntimeError("M1 Paper v20 service reappeared during commit")
        except BaseException as exc:
            if committed:
                raise SystemExit("M1 Paper v20 EFFECT_UNKNOWN after manifest commit; reconcile same original owner") from exc
            # Do not overwrite any concurrent writer on the sole original carrier.
            restored = ((roots["config"].read_bytes() in (old_config_bytes, config_bytes))
                        and roots["manifest"].read_bytes() == old_manifest_bytes
                        and _lifecycle_inspect(account, label, roots, require_positive=True) is None)
            if not restored:
                raise SystemExit("M1 Paper v20 EFFECT_UNKNOWN before commit; reconcile original owner") from exc
            if roots["config"].read_bytes() != old_config_bytes:
                _atomic_write_bytes(roots["config"], old_config_bytes)
            _verify_staged_install(account, label, roots, require_runtime_seal=True)
            raise
    print(json.dumps({**receipt, "effect": "INSTALLED_NOT_STARTED"}, sort_keys=True))
    return 0


@_c2_lifecycle_serialized(readonly_preflight=True)
def cmd_paper_runtime_upgrade(args) -> int:
    """Select a reviewed Paper runtime on an exact qualified fleet without restaging it.

    This dedicated transaction grants no new account, file cohort or capability.
    It cannot stop/start a service, copy gateway source or select an arbitrary bridge.
    The original manifest CAS is intentionally single-use; a replay must fresh-read.
    The exact sealed C2 Personal v12 cohort selects the accepted immutable v20
    generation through the same transaction; every other admission remains the
    historical v10 -> v12 selection.
    """
    account = args.account
    _validate_account_label(account)
    if getattr(args, "m1_v20", False) is True and getattr(args, "fleet_v20", False) is True:
        raise SystemExit("Paper v20 conflicting cohort selection flags")
    if getattr(args, "m1_v20", False) is True:
        return _m1_paper_v20_upgrade(args)
    if getattr(args, "fleet_v20", False) is True:
        return _upgrade_paper_frozen_fleet_v20(args)
    expected = args.expected_manifest_sha256
    preview = args.preflight_only
    if account == C2_PAPER_ACCOUNT and expected == C2_PAPER_V12_MANIFEST_SHA256:
        return _upgrade_paper_c2_personal_v20(args)
    if account == C2_PAPER_ACCOUNT:
        original_manifest = C2_PAPER_ORIGINAL_MANIFEST_SHA256
        non_paper_pin = C2_PAPER_NON_PAPER_CONFIG_SHA256
        runtime_identity = C2_PAPER_RUNTIME_IDENTITY
    elif account == C2_PAPER_BUSINESS_ACCOUNT:
        original_manifest = C2_PAPER_BUSINESS_ORIGINAL_MANIFEST_SHA256
        non_paper_pin = C2_PAPER_BUSINESS_NON_PAPER_CONFIG_SHA256
        runtime_identity = C2_PAPER_BUSINESS_RUNTIME_IDENTITY
    elif account == C4_PAPER_ACCOUNT:
        original_manifest = C4_PAPER_ORIGINAL_MANIFEST_SHA256
        non_paper_pin = C4_PAPER_NON_PAPER_CONFIG_SHA256
        runtime_identity = C4_PAPER_RUNTIME_IDENTITY
    else:
        raise SystemExit("paper runtime compatibility requires the exact enrolled Paper account")
    if type(preview) is not bool:
        raise SystemExit("paper runtime compatibility preflight flag invalid")
    if not _sha256_hex(expected):
        raise SystemExit("paper runtime compatibility requires an exact manifest CAS")
    if expected != original_manifest:
        raise SystemExit("paper runtime compatibility: original manifest is not the reviewed predecessor")
    if PAPER_RUNTIME_REL.name != "v12":
        raise SystemExit("paper runtime compatibility requires the reviewed v12 target")

    label = f"com.mastermind.studio-direct-private.{account}"
    roots = _build_runtime_roots(account)
    config_path, manifest_path = roots["config"], roots["manifest"]
    for path in (config_path, manifest_path, roots["plist"]):
        _assert_dest_safe(path)
    if _stable_regular_file_hash(manifest_path, label="installed manifest") != expected:
        raise SystemExit("paper runtime compatibility: installed manifest CAS mismatch")
    prior = _verify_staged_install(account, label, roots, require_runtime_seal=True)
    if (prior.get("files") != C2_PAPER_FILES_SHA256
            or any(prior.get(key) != value for key, value in runtime_identity.items())):
        raise SystemExit("paper runtime compatibility: original sealed identity does not match")
    for name in prior["files"]:
        _assert_dest_safe(roots["base"] / name)
    old_config_bytes, old_manifest_bytes = config_path.read_bytes(), manifest_path.read_bytes()
    if (hashlib.sha256(old_config_bytes).hexdigest() != prior["configHash"]
            or hashlib.sha256(old_manifest_bytes).hexdigest() != expected):
        raise SystemExit("paper runtime compatibility: verified snapshot changed during preflight")
    try:
        old_config = json.loads(old_config_bytes)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise SystemExit("paper runtime compatibility: original config invalid") from exc
    if type(old_config) is not dict:
        raise SystemExit("paper runtime compatibility: original config invalid")
    non_paper = {key: value for key, value in old_config.items() if key != "paperDesign"}
    non_paper_sha = hashlib.sha256(json.dumps(
        non_paper, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")).hexdigest()
    if non_paper_sha != non_paper_pin:
        raise SystemExit("paper runtime compatibility: original non-Paper profile changed")

    user_root = _user_root()
    target_paper = _paper_design_config(user_root)
    old_runtime = user_root / ".local/share/mastermind-paper/runtime/v10"
    expected_old_paper = {
        **target_paper,
        "pythonPath": str(old_runtime / "venv/bin/python"),
        "bridgePath": str(old_runtime / "source/bridge.py"),
        "bridgeSha256": C2_PAPER_ORIGINAL_BRIDGE_SHA256,
    }
    if old_config.get("paperDesign") != expected_old_paper:
        raise SystemExit("paper runtime compatibility: original Paper selection is not exact v10")
    _verify_paper_runtime(user_root)
    new_config = {**old_config, "paperDesign": target_paper}
    config_bytes = json.dumps(new_config, indent=2, sort_keys=True).encode("utf-8")
    future = {**prior, "configHash": hashlib.sha256(config_bytes).hexdigest()}
    if not _valid_manifest(future, account, label):
        raise SystemExit("paper runtime compatibility: prospective manifest invalid")
    manifest_bytes = json.dumps(future, indent=2, sort_keys=True).encode("utf-8")
    target_manifest_sha = hashlib.sha256(manifest_bytes).hexdigest()
    receipt = {
        "account": account, "fromGeneration": "v10", "toGeneration": "v12",
        "originalManifestSha256": expected, "targetManifestSha256": target_manifest_sha,
        "bridgeSha256": PAPER_BRIDGE_SHA256, "nonPaperConfigSha256": non_paper_sha,
        "preservedGatewayFiles": len(prior["files"]), "runtimeSealPreserved": True,
        "sourcePointerPreserved": True, "serviceStarted": False,
    }
    return _apply_paper_selection(
        account=account, label=label, roots=roots, expected=expected, prior=prior,
        old_config_bytes=old_config_bytes, old_manifest_bytes=old_manifest_bytes,
        config_bytes=config_bytes, target_manifest_sha=target_manifest_sha,
        receipt=receipt, preview=preview,
        runtime_verifier=lambda: _verify_paper_runtime(user_root),
    )


def _upgrade_paper_c2_personal_v20(args) -> int:
    """Select the accepted immutable v20 runtime on the sealed v12 C2 Personal seat.

    One exact observed cohort, one direction, and the same single-use
    manifest-CAS transaction as the historical selection. Admission re-derives
    the installed 12-file cohort from the reviewed closed-publisher patch plus
    unchanged fleet modules, requires the freshly observed predecessor CAS and
    non-Paper profile, and verifies both the retained v12 runtime and the
    staged v20 generation through the existing owners. No runtime path, bridge
    or file byte is caller-selectable, and nothing is restaged or restarted.
    """
    account = args.account
    expected = args.expected_manifest_sha256
    preview = args.preflight_only
    if type(preview) is not bool:
        raise SystemExit("paper runtime compatibility preflight flag invalid")
    if not _sha256_hex(expected):
        raise SystemExit("paper runtime compatibility requires an exact manifest CAS")
    if PAPER_RUNTIME_REL.name != "v12":
        raise SystemExit("paper runtime compatibility: v20 selection requires the reviewed v12 predecessor pin")

    label = f"com.mastermind.studio-direct-private.{account}"
    roots = _build_runtime_roots(account)
    config_path, manifest_path = roots["config"], roots["manifest"]
    for path in (config_path, manifest_path, roots["plist"]):
        _assert_dest_safe(path)
    if _stable_regular_file_hash(manifest_path, label="installed manifest") != expected:
        raise SystemExit("paper runtime compatibility: installed manifest CAS mismatch")
    prior = _verify_staged_install(account, label, roots, require_runtime_seal=True)
    if (prior.get("files") != C2_PAPER_V12_FILES_SHA256
            or any(prior.get(key) != value for key, value in C2_PAPER_RUNTIME_IDENTITY.items())):
        raise SystemExit("paper runtime compatibility: original sealed identity does not match")
    for name in prior["files"]:
        _assert_dest_safe(roots["base"] / name)
    old_config_bytes, old_manifest_bytes = config_path.read_bytes(), manifest_path.read_bytes()
    if (hashlib.sha256(old_config_bytes).hexdigest() != prior["configHash"]
            or hashlib.sha256(old_manifest_bytes).hexdigest() != expected):
        raise SystemExit("paper runtime compatibility: verified snapshot changed during preflight")
    try:
        old_config = json.loads(old_config_bytes)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise SystemExit("paper runtime compatibility: original config invalid") from exc
    if type(old_config) is not dict:
        raise SystemExit("paper runtime compatibility: original config invalid")
    non_paper = {key: value for key, value in old_config.items() if key != "paperDesign"}
    non_paper_sha = hashlib.sha256(json.dumps(
        non_paper, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")).hexdigest()
    if non_paper_sha != C2_PAPER_V12_NON_PAPER_CONFIG_SHA256:
        raise SystemExit("paper runtime compatibility: original non-Paper profile changed")

    user_root = _user_root()
    target_paper = _paper_design_config(
        user_root, rel=PAPER_RUNTIME_V20_REL, bridge_sha256=PAPER_V20_BRIDGE_SHA256)
    expected_old_paper = {
        **target_paper,
        "pythonPath": str(user_root / PAPER_RUNTIME_REL / "venv/bin/python"),
        "bridgePath": str(user_root / PAPER_RUNTIME_REL / "source/bridge.py"),
        "bridgeSha256": PAPER_BRIDGE_SHA256,
    }
    if old_config.get("paperDesign") != expected_old_paper:
        raise SystemExit("paper runtime compatibility: original Paper selection is not exact v12")
    _verify_paper_runtime(user_root)
    _verify_paper_runtime(
        user_root, rel=PAPER_RUNTIME_V20_REL, expected_sha=PAPER_V20_BRIDGE_SHA256)
    new_config = {**old_config, "paperDesign": target_paper}
    config_bytes = json.dumps(new_config, indent=2, sort_keys=True).encode("utf-8")
    future = {**prior, "configHash": hashlib.sha256(config_bytes).hexdigest()}
    if not _valid_manifest(future, account, label):
        raise SystemExit("paper runtime compatibility: prospective manifest invalid")
    manifest_bytes = json.dumps(future, indent=2, sort_keys=True).encode("utf-8")
    target_manifest_sha = hashlib.sha256(manifest_bytes).hexdigest()
    receipt = {
        "account": account, "fromGeneration": "v12", "toGeneration": "v20",
        "originalManifestSha256": expected, "targetManifestSha256": target_manifest_sha,
        "bridgeSha256": PAPER_V20_BRIDGE_SHA256, "nonPaperConfigSha256": non_paper_sha,
        "preservedGatewayFiles": len(prior["files"]), "runtimeSealPreserved": True,
        "sourcePointerPreserved": True, "serviceStarted": False,
    }
    return _apply_paper_selection(
        account=account, label=label, roots=roots, expected=expected, prior=prior,
        old_config_bytes=old_config_bytes, old_manifest_bytes=old_manifest_bytes,
        config_bytes=config_bytes, target_manifest_sha=target_manifest_sha,
        receipt=receipt, preview=preview,
        runtime_verifier=lambda: (
            _verify_paper_runtime(user_root),
            _verify_paper_runtime(
                user_root, rel=PAPER_RUNTIME_V20_REL,
                expected_sha=PAPER_V20_BRIDGE_SHA256)),
    )



def _frozen_paper_fleet_module():
    """Read the approved eight-cohort pure data file beside this installer."""
    from types import ModuleType
    path = Path(__file__).with_name("paper_v20_fleet_cohorts.py")
    # Reuse the original private-service no-follow, owner/mode and inode-stable
    # bounded reader. Verify exactly the bytes that will execute: re-opening
    # the file through a Python loader after a hash check creates a swap race.
    source_bytes = (_INSTALLED_CONTROL_CONTEXT["files"]["paper_v20_fleet_cohorts.py"]
                    if _INSTALLED_CONTROL_CONTEXT is not None
                    else _fabric_release_bytes(path, limit=64 * 1024))
    if hashlib.sha256(source_bytes).hexdigest() != FLEET_V20_COHORT_SOURCE_SHA256:
        raise SystemExit("Paper fleet cohort source hash differs from the reviewed release")
    module = ModuleType("_private_paper_fleet_v20_cohorts")
    module.__file__ = str(path)
    exec(compile(source_bytes, str(path), "exec"), module.__dict__)
    if (frozenset(module.COHORTS) != FLEET_V20_ENROLLED_ACCOUNTS
            or frozenset(module.WORKSPACE_12FILE_SUCCESSORS)
               != frozenset((
                   "admin-business",
                   "chatgpt3-w570f6f34",
                   "chatgpt3-wa2a9e6f9",
               ))
            or module.C4_POST_ENROLLMENT["manifest_sha256"]
               != "3648a9a8e9711bab7be9fc7a3950f73579ce7d78358a18c15ac7d39adf924a9f"
            or module.TARGET_BRIDGE_SHA256 != PAPER_V20_BRIDGE_SHA256
            or module.PREDECESSORS != {
                "v10": PAPER_V10_BRIDGE_SHA256,
                "v12": PAPER_BRIDGE_SHA256,
            }):
        raise SystemExit("Paper fleet source cohort identity drift")
    return module


def _upgrade_paper_frozen_fleet_v20(args) -> int:
    """Use the sole original manifest-CAS transaction for eight frozen M2 seats."""
    account, expected, preview = args.account, args.expected_manifest_sha256, args.preflight_only
    if type(preview) is not bool or not _sha256_hex(expected):
        raise SystemExit("Paper fleet requires exact CAS and boolean preflight")
    cohorts = _frozen_paper_fleet_module()
    if account not in cohorts.COHORTS:
        raise SystemExit("Paper fleet account not in reviewed cohort")
    enrolled_c4 = (
        account == C4_PAPER_ACCOUNT
        and expected == cohorts.C4_POST_ENROLLMENT["manifest_sha256"]
    )
    workspace_successor = (
        account in cohorts.WORKSPACE_12FILE_SUCCESSORS
        and expected ==
            cohorts.WORKSPACE_12FILE_SUCCESSORS[account]["manifest_sha256"]
    )
    if (expected != cohorts.COHORTS[account]["manifest_sha256"]
            and not enrolled_c4 and not workspace_successor):
        raise SystemExit("Paper fleet original manifest is not frozen predecessor")
    label = f"com.mastermind.studio-direct-private.{account}"
    roots = _build_runtime_roots(account)
    for path in (roots["config"], roots["manifest"], roots["plist"]):
        _assert_dest_safe(path)
    if _stable_regular_file_hash(roots["manifest"], label="fleet manifest") != expected:
        raise SystemExit("Paper fleet manifest CAS mismatch")
    prior = _verify_staged_install(account, label, roots, require_runtime_seal=True)
    old_config_bytes = roots["config"].read_bytes()
    old_manifest_bytes = roots["manifest"].read_bytes()
    plist_bytes = roots["plist"].read_bytes()
    if (hashlib.sha256(old_manifest_bytes).hexdigest() != expected
            or hashlib.sha256(old_config_bytes).hexdigest() != prior["configHash"]
            or hashlib.sha256(plist_bytes).hexdigest() != prior["plistHash"]):
        raise SystemExit("Paper fleet predecessor changed during inspection")
    if enrolled_c4:
        # Read-only qualification of the actual accepted enrollment owner and
        # original native-pool receipt, not a hash-only assertion. It must be
        # committed and selected before this second Paper-only CAS can begin.
        _pin_enrollment_owner_module().require_start(
            sys.modules[__name__], account, roots)
    home = _user_root()
    try:
        plan = cohorts.plan_selection(
            account, manifest_bytes=old_manifest_bytes, config_bytes=old_config_bytes,
            plist_bytes=plist_bytes, home=home)
    except ValueError as exc:
        raise SystemExit(f"Paper fleet predecessor refused: {exc}") from exc
    generation = plan["fromGeneration"]
    if generation not in ("v10", "v12"):
        raise SystemExit("Paper fleet generation is not admitted")
    predecessor_rel = PAPER_RUNTIME_V10_REL if generation == "v10" else PAPER_RUNTIME_REL
    predecessor_sha = cohorts.PREDECESSORS[generation]
    def verify_runtimes():
        _verify_paper_runtime(home, runtime_rel=predecessor_rel, expected_sha=predecessor_sha)
        _verify_paper_runtime(home, runtime_rel=PAPER_RUNTIME_V20_REL,
                              expected_sha=PAPER_V20_BRIDGE_SHA256)
    verify_runtimes()
    future = {**prior, "configHash": hashlib.sha256(plan["configBytes"]).hexdigest()}
    if (plan["manifest"] != future
            or not _valid_manifest(future, account, label)
            or hashlib.sha256(plan["manifestBytes"]).hexdigest() != plan["targetManifestSha256"]):
        raise SystemExit("Paper fleet prospective manifest is not the reviewed target")
    receipt = {key:value for key,value in plan.items()
               if key not in ("configBytes", "manifestBytes", "manifest")}
    receipt.update(runtimeSealPreserved=True, sourcePointerPreserved=True)
    return _apply_paper_selection(
        account=account, label=label, roots=roots, expected=expected, prior=prior,
        old_config_bytes=old_config_bytes, old_manifest_bytes=old_manifest_bytes,
        config_bytes=plan["configBytes"], target_manifest_sha=plan["targetManifestSha256"],
        receipt=receipt, preview=preview, runtime_verifier=verify_runtimes,
    )

def _apply_paper_selection(
    *, account: str, label: str, roots: dict, expected: str, prior: dict,
    old_config_bytes: bytes, old_manifest_bytes: bytes, config_bytes: bytes,
    target_manifest_sha: str, receipt: dict, preview: bool, runtime_verifier,
) -> int:
    """Shared single-use Paper selection transaction behind both admissions.

    Extracted unchanged from the reviewed v10 -> v12 selection so the v20 path
    inherits its exact planning recheck, loaded-service refusal, commit order,
    rollback and EFFECT_UNKNOWN semantics. The manifest commits last so fresh
    integrity checks reject partial file updates; a post-commit failure stays
    EFFECT_UNKNOWN on this operation and is never replayed or self-repaired.
    """
    config_path, manifest_path = roots["config"], roots["manifest"]
    future = {**prior, "configHash": hashlib.sha256(config_bytes).hexdigest()}
    manifest_bytes = json.dumps(future, indent=2, sort_keys=True).encode("utf-8")
    if _stable_regular_file_hash(manifest_path, label="installed manifest") != expected:
        raise SystemExit("paper runtime compatibility: installed manifest changed during planning")
    if preview:
        print(json.dumps({**receipt, "preflight": True, "effect": "NOT_APPLIED"}, sort_keys=True))
        return 0
    if _lifecycle_inspect(account, label, roots, require_positive=True) is not None:
        raise SystemExit("refusing Paper runtime upgrade while service is loaded; stop first")
    # Reconfirm the complete sealed installation and target before the first write.
    if _verify_staged_install(account, label, roots, require_runtime_seal=True) != prior:
        raise SystemExit("paper runtime compatibility: original installation changed")
    runtime_verifier()
    if (_stable_regular_file_hash(manifest_path, label="installed manifest") != expected
            or _stable_regular_file_hash(config_path, label="installed config") != prior["configHash"]):
        raise SystemExit("paper runtime compatibility: original snapshot CAS mismatch")
    if _lifecycle_inspect(account, label, roots, require_positive=True) is not None:
        raise SystemExit("refusing Paper runtime upgrade while service is loaded; stop first")

    old_bytes = {config_path: old_config_bytes, manifest_path: old_manifest_bytes}
    planned = {config_path: config_bytes, manifest_path: manifest_bytes}
    committed = False
    try:
        _atomic_write_bytes(config_path, config_bytes)
        # Manifest commits last so fresh integrity checks reject partial file updates.
        if (_stable_regular_file_hash(manifest_path, label="installed manifest") != expected
                or _stable_regular_file_hash(config_path, label="installed config") != future["configHash"]
                or _lifecycle_inspect(account, label, roots, require_positive=True) is not None):
            raise RuntimeError("installed state changed before manifest commit")
        _atomic_write_bytes(manifest_path, manifest_bytes)
        committed = True
        if (_verify_staged_install(account, label, roots, require_runtime_seal=True) != future
                or _stable_regular_file_hash(manifest_path, label="installed manifest") != target_manifest_sha):
            raise RuntimeError("committed installation does not match the planned result")
        runtime_verifier()
        if _lifecycle_inspect(account, label, roots, require_positive=True) is not None:
            raise RuntimeError("service became loaded during commit verification")
    except BaseException as exc:
        if committed:
            raise SystemExit(
                "paper runtime compatibility: EFFECT_UNKNOWN after manifest commit; "
                "inspect the original service before recovery or restart"
            ) from exc
        try:
            if _lifecycle_inspect(account, label, roots, require_positive=True) is not None:
                raise RuntimeError("service became loaded during transaction")
            observed = {}
            for path in planned:
                _assert_dest_safe(path)
                digest = _stable_regular_file_hash(path, label="rollback target")
                observed[path] = path.read_bytes()
                if hashlib.sha256(observed[path]).hexdigest() != digest:
                    raise RuntimeError("rollback target changed while reading")
                if observed[path] not in (old_bytes[path], planned[path]):
                    raise RuntimeError("non-owned concurrent mutation while recovering")
            for path in reversed(tuple(planned)):
                if observed[path] != old_bytes[path]:
                    if (_lifecycle_inspect(account, label, roots, require_positive=True) is not None
                            or _stable_regular_file_hash(path, label="rollback target")
                            != hashlib.sha256(observed[path]).hexdigest()):
                        raise RuntimeError("rollback target or service changed before restoration")
                    _atomic_write_bytes(path, old_bytes[path])
            if (any(path.read_bytes() != old_bytes[path] for path in planned)
                    or _stable_regular_file_hash(manifest_path, label="installed manifest") != expected):
                raise RuntimeError("rollback byte identity differs")
            _verify_staged_install(account, label, roots, require_runtime_seal=True)
            if _lifecycle_inspect(account, label, roots, require_positive=True) is not None:
                raise RuntimeError("service became loaded during rollback verification")
        except BaseException as rollback_exc:
            raise SystemExit(
                "paper runtime compatibility: EFFECT_UNKNOWN during rollback; "
                "do not restart or replay until the original state is reconciled"
            ) from rollback_exc
        raise SystemExit("paper runtime compatibility: NOT_APPLIED; original state restored") from exc
    print(json.dumps({**receipt, "preflight": False, "effect": "APPLIED"}, sort_keys=True))
    return 0


def _fabric_release_bytes(path: Path, *, limit: int = 2 * 1024 * 1024) -> bytes:
    """Read a bounded, owned regular file without following a replacement link."""
    _assert_dest_safe(path)
    current = path.parent
    while True:
        info = current.lstat()
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid()
                or info.st_mode & 0o022):
            raise SystemExit("Fabric release file parent is unsafe")
        if current == _user_root():
            break
        current = current.parent
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK)
    except OSError as exc:
        raise SystemExit("Fabric release file unavailable") from exc
    try:
        before = os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode) or before.st_uid != os.getuid()
                or before.st_nlink != 1 or before.st_mode & 0o022
                or before.st_size > limit):
            raise SystemExit("Fabric release file is unsafe or too large")
        data = bytearray()
        while len(data) <= limit:
            part = os.read(fd, min(65536, limit + 1 - len(data)))
            if not part:
                break
            data.extend(part)
        after = os.fstat(fd)
        named = path.lstat()
        identity = lambda x: (x.st_dev, x.st_ino, x.st_mode, x.st_size, x.st_mtime_ns, x.st_ctime_ns)
        if (len(data) > limit or identity(before) != identity(after)
                or identity(after) != identity(named)):
            raise SystemExit("Fabric release file changed while reading")
        return bytes(data)
    finally:
        os.close(fd)


def _fabric_release_local_source(release_commit: str, expected_sha: str) -> tuple[Path, dict]:
    """Bind the sole backend path to a commit already in observed protected master.

    The operator refreshes the fixed source-admin repository and checks protected
    merge evidence before invoking this local installer. This does not fetch,
    change a ref, bypass review, or treat an arbitrary path/hash as a release.
    """
    if (not isinstance(release_commit, str)
            or re.fullmatch(r"[0-9a-f]{40}", release_commit) is None
            or not _sha256_hex(expected_sha)):
        raise SystemExit("Fabric release requires an exact commit and backend SHA256")
    home = _user_root()
    repo = home / TYPED_GIT_SOURCE_REPOSITORY_REL
    _assert_no_symlink_ancestors(repo)
    if not repo.is_dir():
        raise SystemExit("Fabric release source-admin repository unavailable")

    def git(*argv):
        try:
            result = _run([TYPED_GIT_BINARY, "--no-replace-objects", "-C", str(repo),
                           "--git-dir", str(repo / ".git"), *argv], check=False, timeout=15)
        except Exception as exc:
            raise SystemExit("Fabric release Git evidence unavailable") from exc
        if result.returncode != 0:
            raise SystemExit("Fabric release Git evidence refused")
        return result.stdout

    if git("remote", "get-url", "--all", "origin").splitlines() != [TYPED_GIT_REMOTE_URL]:
        raise SystemExit("Fabric release requires the exact Mastermind origin")
    observed = git("rev-parse", "--verify", "refs/remotes/origin/master^{commit}").strip()
    if re.fullmatch(r"[0-9a-f]{40}", observed) is None:
        raise SystemExit("Fabric release protected-master observation invalid")
    if git("rev-parse", "--verify", release_commit + "^{commit}").strip() != release_commit:
        raise SystemExit("Fabric release commit is not exact")
    git("merge-base", "--is-ancestor", release_commit, observed)
    tree = git("ls-tree", "--full-tree", release_commit, "--", FABRIC_BACKEND_SOURCE)
    match = re.fullmatch(r"100(?:644|755) blob ([0-9a-f]{40})\t" + re.escape(FABRIC_BACKEND_SOURCE) + r"\n", tree)
    if match is None:
        raise SystemExit("Fabric release backend is not the exact regular Git source")
    backend = home / FABRIC_BACKEND_RELEASES_REL / ("fabric-c3-" + release_commit) / FABRIC_BACKEND_SOURCE
    raw = _fabric_release_bytes(backend)
    blob = hashlib.sha1(b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw).hexdigest()
    if hashlib.sha256(raw).hexdigest() != expected_sha or blob != match.group(1):
        raise SystemExit("Fabric release backend differs from the merged source or pinned SHA256")
    return backend, {"releaseCommit": release_commit, "backendGitBlob": blob,
                     "backendSha256": expected_sha, "observedProtectedMaster": observed}


def _fabric_public_json_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


class _FabricNoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _fabric_public_opener():
    # An explicit empty ProxyHandler prevents environment, macOS system proxy,
    # and proxy-credential discovery. The standard HTTPS handler retains its
    # default certificate and hostname verification.
    return urllib.request.build_opener(urllib.request.ProxyHandler({}), _FabricNoRedirect())


def _fabric_public_remaining(deadline: float) -> float:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise SystemExit("Fabric public release: total GitHub metadata deadline exceeded")
    return remaining


def _fabric_public_bounded_read(url: str, deadline: float) -> None:
    """One canonical read inside the finite child's independent lifetime."""
    _fabric_public_remaining(deadline)
    opener = _fabric_public_opener()
    request = urllib.request.Request(url, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": "studio-direct-mcp-public-release-provenance",
        "X-GitHub-Api-Version": "2022-11-28",
    }, method="GET")
    response = None
    try:
        response = opener.open(request, timeout=_fabric_public_remaining(deadline))
        if response.status != 200:
            raise SystemExit("Fabric public release: GitHub metadata refused")
        # The socket timeout is a secondary inactivity guard. Both the parent's
        # kill/wait and the child's process timer enforce the original deadline.
        raw = response.read(FABRIC_PUBLIC_JSON_LIMIT + 1)
        if len(raw) > FABRIC_PUBLIC_JSON_LIMIT:
            raise SystemExit("Fabric public release: GitHub metadata too large")
        _fabric_public_remaining(deadline)
        sys.stdout.buffer.write(raw)
        sys.stdout.buffer.flush()
    except urllib.error.HTTPError as exc:
        # HTTPError owns the response even when opener.open never returned it.
        # Do not depend on exception destruction or include response details.
        try:
            exc.close()
        finally:
            raise SystemExit("Fabric public release: bounded GitHub metadata unavailable") from None
    except SystemExit:
        raise
    except Exception:
        raise SystemExit("Fabric public release: bounded GitHub metadata unavailable") from None
    finally:
        if response is not None:
            response.close()


def _fabric_public_child_source() -> tuple[str, str]:
    """Capture this qualified source; never ask the child to import a path."""
    context = _INSTALLED_CONTROL_CONTEXT
    if context is not None:
        path = context["root"] / "private_service.py"
        raw = context["files"]["private_service.py"]
    else:
        # Genuine source execution remains supported. This is the running
        # module's exact filename, not a caller-selected repository or module.
        path = Path(os.path.abspath(__file__))
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK)
        try:
            before = os.fstat(fd)
            if (not stat.S_ISREG(before.st_mode) or before.st_uid != os.getuid()
                    or before.st_nlink != 1 or before.st_mode & 0o022
                    or before.st_size > 2 * 1024 * 1024):
                raise SystemExit("Fabric public release: qualified source refused")
            with os.fdopen(fd, "rb", closefd=False) as source:
                raw = source.read(2 * 1024 * 1024 + 1)
            after, named = os.fstat(fd), path.lstat()
            identity = lambda value: (value.st_dev, value.st_ino, value.st_mode,
                                     value.st_size, value.st_mtime_ns, value.st_ctime_ns)
            if (len(raw) > 2 * 1024 * 1024 or identity(before) != identity(after)
                    or identity(after) != identity(named)):
                raise SystemExit("Fabric public release: qualified source changed")
        finally:
            os.close(fd)
    return str(path), raw.decode("utf-8")


def _fabric_public_https_json_child(url: str, deadline: float) -> bytes:
    """One finite child, captured source, closed environment and absolute TTL.

    The child's process timer bounds DNS/connect/TLS/headers/body/cleanup even
    if the parent terminates. subprocess.run also guarantees kill/wait on its
    timeout. Local process creation itself is not separately claimed to be
    interruptible on every platform.
    """
    _fabric_public_remaining(deadline)
    source_path, source_text = _fabric_public_child_source()
    document = json.dumps([source_path, source_text, url]).encode("utf-8")
    # Python 3.9 on macOS has process-local monotonic origins. Translate the
    # remaining budget to the shared POSIX clock before crossing a process.
    child_deadline = time.clock_gettime(time.CLOCK_MONOTONIC) + _fabric_public_remaining(deadline)
    try:
        result = subprocess.run(
            [sys.executable, "-I", "-S", "-B", "-c", _FABRIC_PUBLIC_READ_CHILD, str(child_deadline)],
            input=document, capture_output=True, check=False,
            env={"HOME": str(Path.home())},
            timeout=_fabric_public_remaining(deadline))
    except subprocess.TimeoutExpired:
        raise SystemExit("Fabric public release: total GitHub metadata deadline exceeded") from None
    except Exception:
        raise SystemExit("Fabric public release: bounded GitHub metadata unavailable") from None
    _fabric_public_remaining(deadline)
    if result.returncode != 0:
        raise SystemExit("Fabric public release: bounded GitHub metadata unavailable")
    if len(result.stdout) > FABRIC_PUBLIC_JSON_LIMIT:
        raise SystemExit("Fabric public release: GitHub metadata too large")
    return result.stdout


_FABRIC_PUBLIC_READ_CHILD = r"""
import signal,sys,time
remaining = float(sys.argv[1]) - time.clock_gettime(time.CLOCK_MONOTONIC)
deadline = time.monotonic() + remaining
if remaining <= 0:
    raise SystemExit("Fabric public release: total GitHub metadata deadline exceeded")
signal.signal(signal.SIGALRM, signal.SIG_DFL)
signal.pthread_sigmask(signal.SIG_UNBLOCK, {signal.SIGALRM})
signal.setitimer(signal.ITIMER_REAL, remaining)
import json,types
canonical_source = json.loads(sys.stdin.buffer.read())
private_service = types.ModuleType("_studio_public_provenance_child")
private_service.__file__ = canonical_source[0]
sys.modules[private_service.__name__] = private_service
exec(compile(canonical_source[1], canonical_source[0], "exec"), private_service.__dict__)
private_service._fabric_public_bounded_read(canonical_source[2], deadline)
"""


def _fabric_public_https_json(url: str, *, deadline: float = None) -> dict:
    """Run one finite direct read under the qualified interpreter/source."""
    if type(url) is not str or FABRIC_PUBLIC_METADATA_URL_RE.fullmatch(url) is None:
        raise SystemExit("Fabric public release: non-canonical metadata URL refused")
    if deadline is None:
        deadline = time.monotonic() + FABRIC_PUBLIC_TIMEOUT_SECONDS
    raw = _fabric_public_https_json_child(url, deadline)
    if type(raw) is not bytes or len(raw) > FABRIC_PUBLIC_JSON_LIMIT:
        raise SystemExit("Fabric public release: GitHub metadata too large")
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_fabric_public_json_pairs,
                           parse_constant=lambda value: (_ for _ in ()).throw(ValueError("non-finite JSON")))
    except (ValueError, UnicodeError) as exc:
        raise SystemExit("Fabric public release: strict GitHub JSON required") from exc
    if type(value) is not dict:
        raise SystemExit("Fabric public release: GitHub JSON object required")
    _fabric_public_remaining(deadline)
    return value


def _fabric_public_provenance(release_commit: str, expected_sha: str) -> tuple[Path, dict]:
    """Read fixed public metadata only, with one absolute deadline and no fallback."""
    if not _fabric_git_sha(release_commit) or not _sha256_hex(expected_sha):
        raise SystemExit("Fabric release requires an exact commit and backend SHA256")
    deadline = time.monotonic() + FABRIC_PUBLIC_TIMEOUT_SECONDS
    ref = _fabric_public_https_json(FABRIC_PUBLIC_API_ROOT + "/git/ref/heads/master", deadline=deadline)
    if (ref.get("ref") != FABRIC_PUBLIC_REF or type(ref.get("object")) is not dict
            or ref["object"].get("type") != "commit"
            or ref["object"].get("sha") != release_commit):
        raise SystemExit("Fabric public release: protected master does not equal requested commit")
    commit = _fabric_public_https_json(FABRIC_PUBLIC_API_ROOT + "/git/commits/" + release_commit,
                                       deadline=deadline)
    if (commit.get("sha") != release_commit or type(commit.get("tree")) is not dict
            or not _fabric_git_sha(commit["tree"].get("sha"))):
        raise SystemExit("Fabric public release: exact commit/tree evidence required")
    tree_sha = commit["tree"]["sha"]
    current_sha, entry, components = tree_sha, None, FABRIC_BACKEND_SOURCE.split("/")
    for component in components:
        if not _fabric_git_sha(current_sha):
            raise SystemExit("Fabric public release: every intermediate tree needs an exact Git SHA")
        tree = _fabric_public_https_json(FABRIC_PUBLIC_API_ROOT + "/git/trees/" + current_sha,
                                         deadline=deadline)
        if (tree.get("sha") != current_sha or tree.get("truncated") is not False
                or type(tree.get("tree")) is not list):
            raise SystemExit("Fabric public release: complete exact tree required")
        matches = [item for item in tree["tree"]
                   if type(item) is dict and item.get("path") == component]
        if len(matches) != 1:
            raise SystemExit("Fabric public release: fixed backend path missing or ambiguous")
        entry = matches[0]
        if component != components[-1]:
            if entry.get("type") != "tree" or entry.get("mode") != "040000":
                raise SystemExit("Fabric public release: fixed backend parent is not a tree")
            current_sha = entry.get("sha")
            if not _fabric_git_sha(current_sha):
                raise SystemExit("Fabric public release: every intermediate tree needs an exact Git SHA")
    if (entry.get("type") != "blob" or entry.get("mode") not in ("100644", "100755")
            or not _fabric_git_sha(entry.get("sha"))
            or type(entry.get("size")) is not int or entry["size"] < 0):
        raise SystemExit("Fabric public release: backend must be one regular public Git blob")
    backend = _user_root() / FABRIC_BACKEND_RELEASES_REL / ("fabric-c3-" + release_commit) / FABRIC_BACKEND_SOURCE
    before = backend.lstat()
    raw = _fabric_release_bytes(backend)
    after = backend.lstat()
    if ((before.st_dev, before.st_ino, before.st_mode, before.st_size, before.st_mtime_ns, before.st_ctime_ns)
            != (after.st_dev, after.st_ino, after.st_mode, after.st_size, after.st_mtime_ns, after.st_ctime_ns)):
        raise SystemExit("Fabric public release: staged backend inode changed during observation")
    blob = hashlib.sha1(b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw).hexdigest()
    if (hashlib.sha256(raw).hexdigest() != expected_sha or blob != entry["sha"]
            or len(raw) != entry["size"]):
        raise SystemExit("Fabric release backend differs from the public source or pinned SHA256")
    _fabric_public_remaining(deadline)
    return backend, {
        "sourceProvenance": FABRIC_RELEASE_PUBLIC_PROVENANCE,
        "repository": FABRIC_PUBLIC_REPOSITORY, "ref": FABRIC_PUBLIC_REF,
        "releaseCommit": release_commit, "observedProtectedMaster": release_commit,
        "commitTree": tree_sha, "backendGitBlob": entry["sha"],
        "backendMode": entry["mode"], "backendSha256": expected_sha,
        "backendSize": len(raw), "stagedBackendPath": str(backend),
        "stagedBackendDevice": after.st_dev, "stagedBackendInode": after.st_ino,
    }


def _fabric_release_source(release_commit: str, expected_sha: str,
                           provenance: str = FABRIC_RELEASE_LOCAL_PROVENANCE) -> tuple[Path, dict]:
    if provenance == FABRIC_RELEASE_PUBLIC_PROVENANCE:
        return _fabric_public_provenance(release_commit, expected_sha)
    if provenance == FABRIC_RELEASE_LOCAL_PROVENANCE:
        return _fabric_release_local_source(release_commit, expected_sha)
    raise SystemExit("Fabric backend release: closed source provenance selector required")


def _fabric_release_new(path: Path, data: bytes) -> None:
    """Persist evidence exactly once; interrupted operations are never replayed."""
    _assert_dest_safe(path)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, FILE_MODE)
    with os.fdopen(fd, "wb") as stream:
        os.fchmod(stream.fileno(), FILE_MODE)
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    _fsync_dir(path.parent)


def _fabric_release_json(value: dict) -> bytes:
    return json.dumps(value, indent=2, sort_keys=True, allow_nan=False).encode("utf-8")


def _validate_legacy_fleet_status(config: dict, user_root: Path) -> bool:
    """Admit only the narrow legacy fleetStatus on an existing restricted profile.

    The legacy sealed config contained fleetStatus but predated the
    modernFabricProtocol and backendMode selectors. This validator never invokes
    the launcher. It re-derives the owner-bound helper and requires exact field
    and type equality with the freshly derived owner configuration; the launcher
    descriptor bytes are then read through the existing owned, regular-file,
    no-symlink, no-follow reader and their SHA256 must equal the freshly
    derived expected['launcherSha256']. A None, missing, or unsafe launcher,
    wrong field type, ownership/file-type/links/permissions/read/stability or
    digest error, or any extra/omitted key fails closed. Profile-driven
    launcher execution is not authorised by this validator; only sealed
    fleetStatus identity is admitted.

    Profiles without fleetStatus continue to be governed by every other check.
    """
    if "fleetStatus" not in config:
        return True
    if "modernFabricProtocol" in config or "backendMode" in config:
        raise SystemExit(
            "Fabric backend release: legacy fleetStatus requires absent "
            "modernFabricProtocol and backendMode selectors"
        )
    fleet_status = config["fleetStatus"]
    required_keys = frozenset(("enabled", "launcherPath", "launcherSha256", "timeoutMs"))
    if type(fleet_status) is not dict or set(fleet_status) != required_keys:
        raise SystemExit(
            "Fabric backend release: legacy fleetStatus requires exact "
            "enabled/launcherPath/launcherSha256/timeoutMs keys"
        )
    if (fleet_status["enabled"] is not True
            or type(fleet_status["launcherPath"]) is not str
            or type(fleet_status["launcherSha256"]) is not str
            or type(fleet_status["timeoutMs"]) is not int):
        raise SystemExit(
            "Fabric backend release: legacy fleetStatus field types are invalid"
        )
    expected = _fleet_status_config(user_root)
    if expected is None:
        raise SystemExit(
            "Fabric backend release: legacy fleetStatus owner launcher unavailable"
        )
    # _fleet_status_config delegates launcher reads to _stable_regular_file_hash,
    # which does not check st_uid. Read the launcher descriptor via the existing
    # owned, regular, no-follow, bounded reader so a wrong-owner launcher is
    # caught before this validator returns. Any ownership, file-type, links,
    # permissions, read/stability or digest error must refuse the release.
    launcher_bytes = _fabric_release_bytes(user_root / FLEET_STATUS_LAUNCHER_REL)
    if hashlib.sha256(launcher_bytes).hexdigest() != expected["launcherSha256"]:
        raise SystemExit(
            "Fabric backend release: legacy fleetStatus owner launcher digest mismatch"
        )
    if fleet_status != expected:
        raise SystemExit(
            "Fabric backend release: legacy fleetStatus does not match owner"
        )
    return True


@_fabric_lifecycle_serialized(readonly_preflight=True)
def cmd_fabric_backend_release(args) -> int:
    """Select one merged Fabric backend while preserving the entire sealed seat.

    Preview is read-only. Apply requires its exact plan and the unloaded original
    service. It changes config args[0] and three manifest fields only; the same
    private-service owner performs any later explicit start.
    """
    account = args.account
    _validate_account_label(account)
    if account not in FABRIC_BACKEND_ACCOUNTS or type(args.preflight_only) is not bool:
        raise SystemExit("Fabric backend release requires an explicitly enrolled restricted c3 account")
    expected = args.expected_manifest_sha256
    if not _sha256_hex(expected):
        raise SystemExit("Fabric backend release requires the original manifest CAS")
    label = f"com.mastermind.studio-direct-private.{account}"
    roots = _build_runtime_roots(account)
    config_path, manifest_path = roots["config"], roots["manifest"]
    before_manifest = _fabric_release_bytes(manifest_path)
    if hashlib.sha256(before_manifest).hexdigest() != expected:
        raise SystemExit("Fabric backend release: original manifest CAS mismatch")
    prior = _verify_staged_install(account, label, roots, require_runtime_seal=True)
    before_config = _fabric_release_bytes(config_path)
    if (hashlib.sha256(before_config).hexdigest() != prior["configHash"]
            or _fabric_release_bytes(manifest_path) != before_manifest):
        raise SystemExit("Fabric backend release: sealed snapshot changed")
    try:
        old_config = json.loads(before_config)
    except (ValueError, UnicodeError) as exc:
        raise SystemExit("Fabric backend release: original config invalid") from exc
    argv = old_config.get("args") if isinstance(old_config, dict) else None
    # The live modern seat is one exact enrollment, not permission to migrate
    # another profile or change its protocol, port, or capability boundary.
    if account == FABRIC_BACKEND_MODERN_ACCOUNT and (
            type(old_config) is not dict
            or old_config.get("modernFabricProtocol") is not True
            or old_config.get("backendMode") != "shared-account"
            or type(old_config.get("port")) is not int
            or old_config["port"] != FABRIC_BACKEND_MODERN_PORT
            or "fleetStatus" in old_config):
        raise SystemExit("Fabric backend release: exact enrolled modern profile required")
    if (type(old_config) is not dict or old_config.get("fabricOnly") is not True
            or old_config.get("gitPublish") is not False or old_config.get("paperDesign") is not False
            or any(key in old_config for key in ("repositoryWorkspaces", "commissionPublication", "fleetRouting", "publicUrl"))
            or not _validate_legacy_fleet_status(old_config, _user_root())
            or old_config.get("testMode") is not False
            or old_config.get("accountLabel") != account
            or old_config.get("command") != prior["node"]
            or old_config.get("host") != "127.0.0.1" or prior.get("host") != "127.0.0.1"
            or old_config.get("port") != prior["port"]
            or old_config.get("stateDir") != str(roots["state"])
            or type(argv) is not list or not argv or not all(isinstance(x, str) for x in argv)
            or argv[0] != prior["backend"] or type(old_config.get("childEnv")) is not dict
            or old_config["childEnv"].get("MMX_FABRIC_SDK_PACKAGE") != str(roots["base"] / "package.json")):
        raise SystemExit("Fabric backend release: original restricted profile or SDK binding differs")
    backend, source = _fabric_release_source(args.release_commit, args.backend_sha256,
        getattr(args, "source_provenance", FABRIC_RELEASE_LOCAL_PROVENANCE))
    if str(backend) == prior["backend"]:
        raise SystemExit("Fabric backend release: backend already selected; no replay")
    new_config = {**old_config, "args": [str(backend), *argv[1:]]}
    config_bytes = _fabric_release_json(new_config)
    future = {**prior, "backend": str(backend), "backendHash": args.backend_sha256,
              "configHash": hashlib.sha256(config_bytes).hexdigest()}
    if not _valid_manifest(future, account, label):
        raise SystemExit("Fabric backend release: prospective manifest invalid")
    manifest_bytes = _fabric_release_json(future)
    target_manifest = hashlib.sha256(manifest_bytes).hexdigest()
    plan = {
        "schema": FABRIC_BACKEND_RELEASE_SCHEMA, "account": account,
        "originalManifestSha256": expected, "targetManifestSha256": target_manifest,
        "originalConfigSha256": prior["configHash"], "targetConfigSha256": future["configHash"],
        "originalBackend": prior["backend"], "originalBackendSha256": prior["backendHash"],
        "targetBackend": str(backend), "targetBackendSha256": args.backend_sha256,
        "releaseCommit": source["releaseCommit"], "backendGitBlob": source["backendGitBlob"],
        "releaseProvenance": source,
        "preservedGatewayFiles": len(prior["files"]), "preservedDependencyTreeSha256": prior["dependencyTreeHash"],
        "preservedPlistSha256": prior["plistHash"], "serviceStarted": False,
        "changedConfigFields": ["args[0]"], "changedManifestFields": ["backend", "backendHash", "configHash"],
    }
    plan_sha = _canonical_json_sha256(plan)
    evidence_root = roots["state"] / "fabric-backend-releases"
    transaction = evidence_root / plan_sha
    if transaction.exists() or transaction.is_symlink():
        raise SystemExit("Fabric backend release: retained transaction already exists; inspect its exact effect before proceeding")
    if (_fabric_release_bytes(manifest_path) != before_manifest
            or _fabric_release_bytes(config_path) != before_config):
        raise SystemExit("Fabric backend release: original snapshot changed while planning")
    if args.preflight_only:
        print(json.dumps({**plan, "planSha256": plan_sha, "preflight": True,
                          "effect": "NOT_APPLIED", "observedProtectedMaster": source["observedProtectedMaster"]}, sort_keys=True))
        return 0
    if not _sha256_hex(args.expected_plan_sha256):
        raise SystemExit("Fabric backend release: exact reviewed preview plan is required")
    if args.expected_plan_sha256 != plan_sha:
        raise SystemExit("Fabric backend release: exact reviewed preview plan is required")
    if _lifecycle_inspect(account, label, roots) is not None:
        raise SystemExit("refusing Fabric backend release while service is loaded; stop first")
    if (_verify_staged_install(account, label, roots, require_runtime_seal=True) != prior
            or _fabric_release_bytes(manifest_path) != before_manifest
            or _fabric_release_bytes(config_path) != before_config):
        raise SystemExit("Fabric backend release: original runtime changed before write")
    if _fabric_release_source(args.release_commit, args.backend_sha256,
            getattr(args, "source_provenance", FABRIC_RELEASE_LOCAL_PROVENANCE))[1] != source:
        raise SystemExit("Fabric backend release: protected source or staged bytes changed before write")
    if _lifecycle_inspect(account, label, roots) is not None:
        raise SystemExit("refusing Fabric backend release while service is loaded; stop first")
    _ensure_secure_dir(evidence_root)
    _assert_dest_safe(transaction)
    transaction.mkdir(mode=DIR_MODE)
    _fsync_dir(evidence_root)
    _fabric_release_new(transaction / "config.before.json", before_config)
    _fabric_release_new(transaction / "manifest.before.json", before_manifest)
    intent_bytes = _fabric_release_json({**plan, "planSha256": plan_sha,
        "observedProtectedMaster": source["observedProtectedMaster"], "intentRecordedAt": time.time()})
    _fabric_release_new(transaction / "intent.json", intent_bytes)
    intent_sha = hashlib.sha256(intent_bytes).hexdigest()

    def record(name, effect, **extra):
        value = {"schema": FABRIC_BACKEND_RELEASE_SCHEMA, "account": account,
                 "planSha256": plan_sha, "intentSha256": intent_sha,
                 "effect": effect, "serviceStarted": False, "recordedAt": time.time(), **extra}
        _fabric_release_new(transaction / name, _fabric_release_json(value))

    try:
        if (_fabric_release_bytes(manifest_path) != before_manifest
                or _fabric_release_bytes(config_path) != before_config
                or _lifecycle_inspect(account, label, roots) is not None):
            raise RuntimeError("original state changed after intent persistence")
        _atomic_write_bytes(config_path, config_bytes)
        if (_fabric_release_bytes(manifest_path) != before_manifest
                or _fabric_release_bytes(config_path) != config_bytes
                or _stable_regular_file_hash(backend, label="Fabric backend") != args.backend_sha256
                or _lifecycle_inspect(account, label, roots) is not None):
            raise RuntimeError("original state changed before manifest commit")
        # The sealed manifest commits last. A partial config update fails all
        # incumbent start/integrity checks until it is restored or reconciled.
        _atomic_write_bytes(manifest_path, manifest_bytes)
        if (_verify_staged_install(account, label, roots, require_runtime_seal=True) != future
                or _fabric_release_bytes(manifest_path) != manifest_bytes
                or _fabric_release_bytes(config_path) != config_bytes
                or _lifecycle_inspect(account, label, roots) is not None):
            raise RuntimeError("committed runtime differs from the planned selection")
        record("result.json", "APPLIED", manifestSha256=target_manifest,
               backendSha256=args.backend_sha256, runtimeSealVerified=True)
    except BaseException as exc:
        # Any observed commit or concurrent change requires effect reconciliation.
        # Never overwrite a manifest which may already have committed successfully.
        rollback_proven = False
        try:
            if (_lifecycle_inspect(account, label, roots) is not None
                    or _fabric_release_bytes(manifest_path) != before_manifest):
                raise RuntimeError("manifest committed or service absence is unverified")
            observed = _fabric_release_bytes(config_path)
            if observed not in (before_config, config_bytes):
                raise RuntimeError("non-owned concurrent configuration change")
            if observed != before_config:
                if (_fabric_release_bytes(config_path) != observed
                        or _fabric_release_bytes(manifest_path) != before_manifest
                        or _lifecycle_inspect(account, label, roots) is not None):
                    raise RuntimeError("rollback target or service changed before restoration")
                _atomic_write_bytes(config_path, before_config)
            if (_fabric_release_bytes(manifest_path) != before_manifest
                    or _fabric_release_bytes(config_path) != before_config
                    or _verify_staged_install(account, label, roots, require_runtime_seal=True) != prior
                    or _lifecycle_inspect(account, label, roots) is not None):
                raise RuntimeError("original sealed runtime restoration unverified")
            record("rollback.json", "ROLLED_BACK", originalManifestSha256=expected,
                   originalConfigSha256=prior["configHash"], runtimeSealVerified=True)
            record("result.json", "NOT_APPLIED", originalManifestSha256=expected,
                   originalStateRestored=True)
            rollback_proven = True
        except BaseException:
            try:
                record("failure.json", "EFFECT_UNKNOWN", retryAllowed=False,
                       recovery="Inspect retained intent and exact original account before any retry or start")
            except BaseException:
                pass
        if rollback_proven:
            raise SystemExit("Fabric backend release: NOT_APPLIED; original sealed state restored; evidence retained") from exc
        raise SystemExit("Fabric backend release: EFFECT_UNKNOWN; inspect retained intent and original account before retry or start") from exc
    print(json.dumps({**plan, "planSha256": plan_sha, "intentSha256": intent_sha,
                      "preflight": False, "effect": "APPLIED", "evidenceDirectory": str(transaction)}, sort_keys=True))
    return 0


@_pin_lifecycle_serialized
@_fabric_lifecycle_serialized()
@_c2_lifecycle_serialized()
def cmd_seal_runtime(args) -> int:
    account = args.account
    _validate_account_label(account)
    label = f"com.mastermind.studio-direct-private.{account}"
    roots = _build_runtime_roots(account)
    if _lifecycle_inspect(account, label, roots) is not None:
        raise SystemExit("refusing runtime seal while service is loaded; stop first")
    manifest = _verify_native_pin_install(
        account, label, roots, require_runtime_seal=False
    )
    if manifest.get("version") != MANIFEST_VERSION:
        raise SystemExit("legacy manifest must be upgraded before runtime seal")
    node = Path(manifest["node"])
    backend = Path(manifest["backend"])
    if _stable_regular_file_hash(node, label="node") != manifest.get("nodeHash"):
        raise SystemExit("runtime seal refused: node hash mismatch")
    if _stable_regular_file_hash(backend, label="backend") != manifest.get("backendHash"):
        raise SystemExit("runtime seal refused: backend hash mismatch")
    dependency_hash = _dependency_tree_hash(roots["node_modules"])
    prior_hash = manifest.get("dependencyTreeHash")
    if prior_hash is not None and prior_hash != dependency_hash:
        raise SystemExit("runtime seal refused: dependency tree changed after seal")
    sealed = dict(manifest)
    sealed["dependencyTreeHash"] = dependency_hash
    _atomic_write_text(
        roots["manifest"], json.dumps(sealed, indent=2, sort_keys=True)
    )
    print(json.dumps({
        "sealed": True,
        "account": account,
        "dependencyTreeHash": dependency_hash,
    }, sort_keys=True))
    return 0


@_pin_lifecycle_serialized
@_fabric_lifecycle_serialized()
@_c2_lifecycle_serialized()
def cmd_start(args) -> int:
    if args.account == ORIGINAL_COLLECTION_ACCOUNT and _original_install_pending(_build_runtime_roots(args.account)):
        raise SystemExit("original preserving upgrade requires reconciliation before start")
    account = args.account
    _validate_account_label(account)
    label = f"com.mastermind.studio-direct-private.{account}"
    roots = _build_runtime_roots(account)

    _verify_native_pin_install(account, label, roots)
    _pin_require_start(account, roots)

    info = _lifecycle_inspect(account, label, roots)
    if info is not None:
        path = info.get("path")
        if path and path != str(roots["plist"]):
            raise SystemExit("loaded job is not our exact install")
        if not _info_is_running(info):
            _run(["launchctl", "kickstart", _launchd_target(label)])
        print(json.dumps({"started": True, "already": True, "loaded": True}))
        return 0

    _run(["launchctl", "bootstrap", _launchd_domain(), str(roots["plist"])])
    print(json.dumps({"started": True, "account": account}))
    return 0


def cmd_status(args) -> int:
    account = args.account
    _validate_account_label(account)
    label = f"com.mastermind.studio-direct-private.{account}"
    roots = _build_runtime_roots(account)

    info = _launchd_inspect(label)
    loaded = info is not None
    running = bool(info) and _info_is_running(info)
    pid = info.get("pid") if info and running else None

    manifest = _read_manifest(roots["manifest"], account, label)
    port = manifest.get("port") if manifest else None

    print(
        json.dumps(
            {
                "account": account,
                "label": label,
                "loaded": loaded,
                "running": running,
                "pid": pid,
                "port": port,
            },
            sort_keys=True,
        )
    )
    return 0


@_pin_lifecycle_serialized
@_fabric_lifecycle_serialized()
@_c2_lifecycle_serialized()
def cmd_stop(args) -> int:
    account = args.account
    _validate_account_label(account)
    label = f"com.mastermind.studio-direct-private.{account}"
    roots = _build_runtime_roots(account)

    info = _lifecycle_inspect(account, label, roots)
    if info is None:
        print(json.dumps({"stopped": True, "already": True, "account": account}))
        return 0

    _verify_native_pin_install(
        account, label, roots, require_runtime_seal=False
    )

    if info.get("path") != str(roots["plist"]):
        raise SystemExit("loaded job is not our exact install")

    res = _run(["launchctl", "bootout", _launchd_target(label)], check=False)
    if res.returncode != 0:
        print(json.dumps({"stopped": False, "reason": "bootout failed", "stderr": res.stderr}))
        return 1

    deadline = time.monotonic() + 10
    strict_account = (account in (C2_PAPER_ACCOUNT, C4_PAPER_ACCOUNT)
                      or account in FABRIC_BACKEND_ACCOUNTS
                      or account in _NATIVE_POOL_PIN_TAILNET_CANONICAL)
    # launchd may transiently report an indeterminate state immediately after a
    # successful bootout. Continue OBSERVING only, never repeat the bootout.
    # A strict owner must still see an exact positive ABSENT receipt before
    # reporting stopped; persistent uncertainty remains EFFECT_UNKNOWN.
    for poll in range(51):
        try:
            remaining = _lifecycle_inspect(account, label, roots)
        except SystemExit as exc:
            if not strict_account:
                raise
            if time.monotonic() >= deadline or poll == 50:
                subject = ("Tailnet" if account in _NATIVE_POOL_PIN_TAILNET_CANONICAL
                           else "Fabric" if account in FABRIC_BACKEND_ACCOUNTS else "Paper")
                raise SystemExit(
                    f"{subject} stop: EFFECT_UNKNOWN after bootout; "
                    "service absence is unverified"
                ) from exc
            time.sleep(0.2)
            continue
        if remaining is None:
            break
        if time.monotonic() >= deadline or poll == 50:
            print(json.dumps({"stopped": False, "reason": "still loaded"}))
            return 1
        time.sleep(0.2)

    print(json.dumps({"stopped": True, "account": account}))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="private_service")
    sub = p.add_subparsers(dest="cmd", required=True)

    original = sub.add_parser("_original-collection-helper", help=argparse.SUPPRESS)
    original.set_defaults(func=cmd_original_collection_helper)

    readback = sub.add_parser("original-predecessor-readback",
        help="read back the installed sealed original predecessor import")
    readback.add_argument("--account", required=True)
    readback.set_defaults(func=cmd_original_predecessor_readback)

    status = sub.add_parser("fleet-status-module-upgrade")
    status.add_argument("--account", choices=(
        "admin-business", "chatgpt1", "chatgpt2-business", "chatgpt2-personal",
        "chatgpt3", "chatgpt3-w570f6f34", "chatgpt3-wa2a9e6f9", "chatgpt4",
    ), required=True)
    status.add_argument("--operation", choices=(
        "preview", "apply", "status", "reconcile",
    ), required=True)
    status.add_argument("--release-commit",
                        help="accepted protected Mastermind merge commit; required for preview/apply")
    status.add_argument("--expected-manifest-sha256",
                        help="exact frozen original public-seat manifest CAS")
    status.add_argument("--expected-plan-sha256",
                        help="exact owner preview plan SHA256; required for apply")
    status.set_defaults(func=cmd_fleet_status_module_upgrade)

    pin = sub.add_parser("native-pool-pin")
    pin.add_argument("--account", required=True)
    pin.add_argument("--expected-manifest-sha256", required=True)
    pin.add_argument("--successor-bundle", required=True)
    pin.add_argument("--successor-plan-sha256", required=True)
    pin.add_argument("--expected-plan-sha256")
    pin.add_argument("--operation", choices=("preview", "apply", "status", "reconcile"), required=True)
    pin.set_defaults(func=cmd_native_pool_pin)

    forward = sub.add_parser("native-pool-pin-forward")
    forward.add_argument("--account", required=True)
    forward.add_argument("--forward-go-bundle", required=True,
                         help="exact qualified retained Go ingress bundle for this transition")
    forward.add_argument("--expected-plan-sha256",
                         help="exact owner preview plan SHA256; required for apply, status and reconcile")
    forward.add_argument("--operation", choices=("preview", "apply", "status", "reconcile"), required=True)
    forward.set_defaults(func=cmd_native_pool_pin_forward)
    publisher = sub.add_parser("native-pool-pin-publisher")
    publisher.add_argument("--account", choices=("chatgpt2-personal",), required=True)
    publisher.add_argument("--operation",
                           choices=("preview", "apply", "status", "reconcile"), required=True)
    publisher.add_argument("--source", help="exact reviewed publisher source; preview/apply")
    publisher.add_argument("--expected-manifest-sha256", required=True)
    publisher.add_argument("--expected-plan-sha256")
    publisher.set_defaults(func=cmd_native_pool_pin_publisher)

    enrollment = sub.add_parser("native-pool-pin-enrollment")
    enrollment.add_argument("--account", choices=("chatgpt4", "admin-business", "chatgpt3-w570f6f34", "chatgpt3-wa2a9e6f9"), required=True)
    enrollment.add_argument("--expected-manifest-sha256", required=True)
    enrollment.add_argument("--expected-plan-sha256")
    enrollment.add_argument("--source", help="exact reviewed payload under the installed owner's home; preview/apply only")
    enrollment.add_argument("--operation", choices=("preview", "apply", "status", "reconcile"), required=True)
    enrollment.set_defaults(func=cmd_native_pool_pin_enrollment)

    fabric = sub.add_parser("fabric-backend-release")
    fabric.add_argument("--account", required=True)
    fabric.add_argument("--expected-manifest-sha256", required=True)
    fabric.add_argument("--release-commit", required=True,
                        help="exact protected merged commit for the fixed Fabric backend release path")
    fabric.add_argument("--backend-sha256", required=True)
    fabric.add_argument("--source-provenance", choices=(FABRIC_RELEASE_LOCAL_PROVENANCE,
                        FABRIC_RELEASE_PUBLIC_PROVENANCE), default=FABRIC_RELEASE_LOCAL_PROVENANCE,
                        help="closed release source; public mode never reads a local Git source or falls back")
    fabric.add_argument("--expected-plan-sha256",
                        help="exact plan digest returned by the reviewed read-only preview; required for apply")
    fabric.add_argument("--preflight-only", action="store_true")
    fabric.set_defaults(func=cmd_fabric_backend_release)

    paper = sub.add_parser("paper-runtime-upgrade")
    paper.add_argument("--account", required=True)
    paper.add_argument("--expected-manifest-sha256", required=True,
                       help="CAS pin for the exact reviewed sealed Paper predecessor")
    paper.add_argument("--preflight-only", action="store_true",
                       help="read-only Paper selection plan; no service or installation changes")
    paper.add_argument("--m1-v20", action="store_true",
                       help="exact reviewed M1 chrisadmin v5-to-v20 Paper-only selector")
    paper.add_argument("--fleet-v20", action="store_true",
                       help="only eight frozen M2 original v10/v12 Paper cohorts, exact predecessor CAS")
    paper.set_defaults(func=cmd_paper_runtime_upgrade)

    for name in ("stage", "upgrade"):
        s = sub.add_parser(name)
        s.add_argument("--account", required=True)
        s.add_argument("--port", type=int, required=True)
        s.add_argument("--source", required=True)
        s.add_argument("--node", required=True)
        s.add_argument("--backend", required=True)
        s.add_argument("--modern-fabric-protocol", action=argparse.BooleanOptionalAction, default=None,
                       help="opt into stateless MCP for the private Fabric-only shared backend; otherwise preserve verified selection")
        s.add_argument("--original-collection", action=argparse.BooleanOptionalAction, default=None,
                       help="explicit fixed J/carrier collection capability for the existing modern C3 service")
        s.add_argument("--original-predecessor-receipt",
                       help="retained original first-call receipt file for the preserving migration")
        s.add_argument("--original-predecessor-sha256",
                       help="expected whole-file sha256 of --original-predecessor-receipt")
        s.add_argument("--fabric-only", action="store_true", help="new Fabric-only installation; no Git, Paper or repository tools")
        s.add_argument("--os-commission-config-sha256", help="opt into the exact root-sealed OS publication grant")
        s.add_argument("--enable-repository-workspaces", action="store_true",
                       help="enable the closed installed repository-workspace consumer")
        if name == "upgrade":
            s.add_argument("--c2-business-fleet-compat", action="store_true",
                           help="exact hash-pinned C2 11-to-12-file gateway compatibility; no new repo grants")
            s.add_argument("--c2-personal-closed-publisher", action="store_true")
            s.add_argument("--c2-business-repository-enrollment", action="store_true",
                           help="explicit closed Macro/Terminal opt-in after reviewed C2 11-to-12 migration; manifest CAS required")
            s.add_argument("--c2-personal-git-timeout-only", action="store_true",
                           help="exact sealed C2 Personal stopped-service Git command budget patch")
            s.add_argument("--publisher-only-fleet-v10", action="store_true",
                           help="preserve the exact sealed enrolled fleet v0.1.10 runtime; patch only two publisher modules")
            s.add_argument("--c1-fleet-git-failure-compat", action="store_true",
                           help="closed chatgpt1-only fleet gateway Git-failure successor; exact manifest CAS required")
            s.add_argument("--publisher-expected-manifest-sha256",
                           help="CAS pin for the original sealed, approved fleet manifest")
            s.add_argument("--publisher-preflight-only", action="store_true",
                           help="read-only exact fleet publisher upgrade preflight, even while service is running")
        s.set_defaults(func=globals()[f"cmd_{name}"])

    for name in ("seal-runtime", "start", "status", "stop"):
        sp = sub.add_parser(name)
        sp.add_argument("--account", required=True)
        function_name = "cmd_seal_runtime" if name == "seal-runtime" else f"cmd_{name}"
        sp.set_defaults(func=globals()[function_name])

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except SystemExit:
        raise
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


_INSTALLED_CONTROL_CONTEXT = _installed_control_context()

if __name__ == "__main__":
    sys.exit(main())
