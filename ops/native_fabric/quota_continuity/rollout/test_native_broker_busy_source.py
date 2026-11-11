"""Busy-scoped broker-busy source fixture for the #2121 AUTO pre-release epoch.

Split from test_native_current_source.py per the squash-probe relocation law:
master's current-source fixture stays byte-identical to origin/master; the
busy-scoped projection lives here as a cleanly-additive sibling module.
The default-path tests never touch these objects; only an explicit
--broker-busy-epoch build stages the six converged busy members.
"""
import hashlib
import json
from pathlib import Path

from test_native_current_source import (
    APPLICATION_MEMBERS,
    BASELINE_INVENTORY_SHA,
    BASELINE_MANIFEST_SHA,
    canonical,
    digest,
)

# ---------------------------------------------------------------------------
# Busy-scoped fixture: the converged #2121 AUTO pre-release broker-busy epoch.
#
# The default-path tests above never touch these objects; the default build
# stages master's reviewed sources and is verified by
# expected_current_source_closure()/verify_current_stage() unchanged. A busy
# build (build_review_stage.py --broker-busy-epoch) stages its six converged
# members from BROKER_BUSY_SOURCE_DIRECTORY, while the two remaining GLM
# application-core members stay at their frozen preimages (the busy epoch
# bypasses the GLM helper composition) with their staged source rebound to the
# sealed preimage directory.
# ---------------------------------------------------------------------------
GLM_CORE_SOURCE_DIRECTORY = "rollout/preimages/glm_application_core_5c3d"
BROKER_BUSY_SOURCE_DIRECTORY = "candidate/broker_busy_2121"
# The busy epoch does not re-derive the GLM helper composition; these two
# members stage their exact sealed preimage bytes.
GLM_CORE_PREIMAGE_SOURCES = {
    "go_lease_capability.py":
        "d8562f38a397900bd851ddbe8bb27f511fcefc2bcd2af6ae1eea5d55d15c5940",
    "go_lease_gateway.py":
        "adad5ea3bcfd091730b92707d1ad231f5566cb200b5ffedfe41ef086aab86949",
}
# The complete six-member AUTO prelease broker-busy epoch: each member's
# baseline (pre-busy) pin advances to its converged candidate bytes.
# The baseline manifest still pins each member's preimage.
BUSY_CORE = {
    "fabric_continuation.py": (
        "7a4050051378fcacada2f2fe6d056649fb514077aacfb02751d61d6e67dfe405",
        "8b3ab69abc6e61bdae98dea026c4dc5075ab7bc0b062624cb205df4a27a98030"),
    "fabric_task.py": (
        "1bdec660216cd3218d46c5740eee7d4f24a74c3f2dc23b61083dfc503c9d1d68",
        "0e85036189cc074c3b1a463304f1ccadba82038beadff3b51255c1ef2ec68d66"),
    "remote_sub.sh": (
        "1b7618c76aedfe058caf5eb0bc21667051af14beffa7a706f1ef5c92551563ca",
        "e140eb481c8c61f70eea6e8b8bcba175c18ba31bb3423f1ec182384cb54db449"),
    # The AUTO prelease broker-busy epoch is the reviewed successor of the
    # GLM-composed broker (a84752dc lineage); the baseline manifest still
    # pins the GLM preimage 0bbf1ca0.
    "lease_broker.py": (
        "0bbf1ca05b655c30e895cebf63c914cbf97f9d17fc8b3e55c852fd4652ed8807",
        "5af51da91f8c13cedca525a906d211e0e03f53cdd19c041d638d35d85e60a24c"),
    "pick.py": (
        "5d37967731337fa6d49a6a119d415c66fcc35802c167b16de7e8a1751f950892",
        "c433384faab5862a05dcc4bd84273ee1b5aa9293271166079c2874375e46a057"),
    "quota_circuit.py": (
        "0b1b07b950625abfa5a935c273594156ea6b8f97ac6426820666f55ac498c303",
        "ba1f2582505a0350260d0bdc4a00f6374a2e1140bc4b6cead84368b606f9970e"),
}
# Busy members staged from their busy-scoped source directory.
BUSY_MEMBERS = frozenset("ext/" + name for name in BUSY_CORE)


def expected_broker_busy_closure(native):
    """Busy-scoped projection of the same immutable 107-file baseline."""
    native = Path(native)
    baseline_raw = (native / "rollout/native-manifest.json").read_bytes()
    baseline_inventory_raw = (native / "rollout/native-source-inventory.json").read_bytes()
    if (digest(baseline_raw) != BASELINE_MANIFEST_SHA
            or digest(baseline_inventory_raw) != BASELINE_INVENTORY_SHA):
        raise AssertionError("immutable native source baseline differs")
    manifest = json.loads(baseline_raw)
    inventory = json.loads(baseline_inventory_raw)
    # The two GLM core members stay at their sealed preimages; only their
    # staged source moves to the preimage directory, mirroring the busy-epoch
    # staging (the GLM helper composition is not re-derived).
    for filename, preimage in GLM_CORE_PREIMAGE_SOURCES.items():
        member = "ext/" + filename
        path = native / GLM_CORE_SOURCE_DIRECTORY / filename
        if not path.is_file() or path.is_symlink():
            raise AssertionError("glm core preimage source is not regular: " + member)
        data = path.read_bytes()
        if digest(data) != preimage:
            raise AssertionError("glm core preimage source differs: " + member)
        row = inventory["files"][member]
        if manifest[member] != preimage or row["sha256"] != preimage:
            raise AssertionError("glm core preimage pin differs: " + member)
        row.update(bytes=len(data),
                   source=GLM_CORE_SOURCE_DIRECTORY + "/" + filename)
    # The complete six-member busy cohort advances to its converged
    # candidates; partial or mixed cohorts are never projected here.
    for filename, (preimage, candidate) in BUSY_CORE.items():
        member = "ext/" + filename
        path = native / BROKER_BUSY_SOURCE_DIRECTORY / filename
        if not path.is_file() or path.is_symlink():
            raise AssertionError("reviewed core source is not regular: " + member)
        data = path.read_bytes()
        row = inventory["files"][member]
        if (manifest[member] != preimage
                or row["sha256"] != preimage or digest(data) != candidate):
            raise AssertionError("reviewed core successor differs: " + member)
        manifest[member] = candidate
        row.update(bytes=len(data), sha256=candidate,
                   source=BROKER_BUSY_SOURCE_DIRECTORY + "/" + filename)
    return manifest, inventory


def verify_broker_busy_stage(output, native, expected_members):
    """Qualify a --broker-busy-epoch stage against the busy-scoped closure."""
    output, native = Path(output), Path(native)
    manifest_raw = (output / "native-manifest.json").read_bytes()
    inventory_raw = (output / "native-source-inventory.json").read_bytes()
    manifest, inventory = json.loads(manifest_raw), json.loads(inventory_raw)
    expected_manifest, expected_inventory = expected_broker_busy_closure(native)
    if (manifest_raw != canonical(expected_manifest)
            or inventory_raw != canonical(expected_inventory)
            or len(manifest) != 107
            or set(manifest) != set(expected_members)
            or set(inventory["files"]) != set(manifest)
            or inventory["native_code_files"] != len(manifest)):
        raise AssertionError("broker busy source closure differs")
    for name, wanted in manifest.items():
        data = (output / "native-code-stage" / name).read_bytes()
        row = inventory["files"][name]
        source = (native / row["source"]).read_bytes()
        if (digest(data) != wanted or row["sha256"] != wanted
                or row["bytes"] != len(data) or source != data):
            raise AssertionError("broker busy captured source differs: " + name)
    return manifest
