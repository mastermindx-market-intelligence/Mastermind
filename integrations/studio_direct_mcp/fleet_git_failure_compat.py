"""Deterministic source compiler for the one reviewed C1 fleet-gateway successor.

This module is a pure source compiler and validator for exactly ONE transition:
the installed C1 fleet gateway (``chatgpt1``) at the pinned predecessor blob is
rewritten to the pinned successor that applies the CURRENT PROTECTED gateway's
typed-Git failure classification to the old fleet module.

It is NOT a runtime listener, an installer, a publisher, a registry, a queue, a
service or a diagnostic endpoint. It never touches a host, an installed
directory, a credential, a launchd label or a live effect. The incumbent
``private_service`` owner owns installation, manifest/seal verification and
lifecycle; this module only decides whether a given byte sequence is exactly
the accepted predecessor and what the exact accepted successor bytes are.

Everything is pinned: the predecessor is accepted only at one Git blob /
SHA256 / size; the two edited regions are byte-exact copies of the current
protected gateway's own failure classifier and typed-Git catch; the successor
is accepted only at one fixed SHA256 / size / Git blob. There is no prefix-only
hash, no marker-only qualification, no automatic hash learning and no broad
text substitution. A predecessor that differs by even one byte, an input with
zero or several candidate anchors, or a successor that does not hash to the
fixed value is refused.

The classifier never inspects or serializes the exception object, the command
arguments, the credentials, the paths or the stderr. That is a property of the
pinned reference block, not of any runtime policy here.
"""
from __future__ import annotations

import difflib
import hashlib
import json
from pathlib import Path

# --------------------------------------------------------------------------
# Pinned byte identities.
# --------------------------------------------------------------------------

#: The exact installed C1 fleet gateway predecessor (public Git object).
PREIMAGE_GIT_BLOB = "f87ac012339e82fe46bce5ddc70d1d04183d1b6e"
PREIMAGE_SHA256 = "17157fa5f8739dbe17aae767a335e97dd713a978dde9b192feb1b41a7b036b30"
PREIMAGE_SIZE = 101068

#: The exact successor this candidate commits. Fixed, not learned.
SUCCESSOR_SHA256 = "336de8ed10e7da483d46e93bd98439fd00c3e277111b39b5baa9cf0e68074674"
SUCCESSOR_SIZE = 102141
SUCCESSOR_GIT_BLOB = "c02bcdada5217bbc987099e90ebdce236f023b86"

#: The current protected gateway whose classification is the narrow reference.
#: It is a semantic reference only: it is NOT a drop-in for the fleet gateway.
REFERENCE_GATEWAY_SHA256 = "c000159636ca5f42b9e91d1d2120f78cd22119711230e264952462e4e2a3f2da"

# --------------------------------------------------------------------------
# Pinned source regions.
#
# The classifier and the catch are byte-exact copies of the current protected
# gateway's own regions, so the successor carries the same truthful
# classification semantics without inheriting that module's different bundle.
# --------------------------------------------------------------------------

#: Insertion boundary: immediately after the closed CLASSIFICATION vocabulary
#: and before the JSON-RPC CODE vocabulary, exactly as in the reference.
INSERTION_BOUNDARY = "  BAD_ORIGIN: 'bad_origin',\n});\n\n"
INSERTION_ANCHOR = "/** JSON-RPC error codes in the server-defined range (-32000..-32099). */\n"

#: The failure classifier, copied verbatim from the current protected gateway.
CLASSIFIER_BLOCK = """\
// Never infer the absence of a Git effect from an exception: a failed commit
// or push response may arrive *after* the source ref was updated. This layer
// sees no authoritative stage receipt, so it reports unqualified mutations
// as unknown while an exclusively read-only status retains NOT_APPLIED.
// The exception object is deliberately not inspected or serialized.
function classifyStudioGitFailure(_error, { modifying = false } = {}) {
  return {
    schema: 'mastermind.studio_git_tool_error.v1',
    status: modifying ? 'UNKNOWN' : 'REFUSED',
    effect_state: modifying ? 'EFFECT_UNKNOWN' : 'NOT_APPLIED',
    code: modifying ? 'TYPED_GIT_EFFECT_UNQUALIFIED' : 'TYPED_GIT_READONLY_INSPECTION_REFUSED',
  };
}
"""

#: The typed-Git catch, copied verbatim from the current protected gateway.
CATCH_BLOCK = """\
      } catch (error) {
        // A thrown mutation is not proof of a preflight refusal. The original
        // owner might have updated its ref before a lost return. Only a typed
        // closed-selector refusal proves that publisher dispatch never began.
        const modifying = name !== STUDIO_GIT_PUBLISH_STATUS_TOOL.name;
        const data = classifyStudioGitFailure(error, { modifying });
        if (data.effect_state === 'EFFECT_UNKNOWN') this.taint('typed git mutation return unqualified');
        log('warn', 'tool_call', {
          sid: this.tag, tool: name, durationMs: Date.now() - started,
          classification: CLASSIFICATION.TOOL_ERROR,
          effect: data.effect_state,
        });
        return gitToolResult(data, true);
      }
"""

#: The incumbent opaque catch that this transition replaces.
LEGACY_CATCH_BLOCK = """\
      } catch {
        log('info', 'tool_call', {
          sid: this.tag, tool: name, durationMs: Date.now() - started,
          classification: CLASSIFICATION.TOOL_ERROR,
        });
        return gitToolResult({
          schema: 'mastermind.studio_git_tool_error.v1',
          status: 'REFUSED',
          effect_state: 'NOT_APPLIED',
          code: 'TYPED_GIT_PRECHECK_REFUSED',
        }, true);
      }
"""

#: The incumbent local-session guard. It is a pre-dispatch authority boundary:
#: it refuses typed Git before the publisher is ever called. It is preserved
#: byte-for-byte and must stay ahead of the typed-Git dispatch block.
GUARD_BLOCK = """\
    if (this.gitPublisher && this.selectedHostRef &&
        (name === STUDIO_GIT_PUBLISH_STATUS_TOOL.name ||
         name === STUDIO_GIT_COMMIT_CURRENT_CHANGES_TOOL.name ||
         name === STUDIO_GIT_PUSH_CURRENT_BRANCH_TOOL.name)) {
      return gitToolResult({
        schema: 'mastermind.studio_git_tool_error.v1',
        status: 'REFUSED',
        effect_state: 'NOT_APPLIED',
        code: 'TYPED_GIT_REQUIRES_LOCAL_STUDIO_SESSION',
      }, true);
    }
"""

#: The typed-Git dispatch block that owns the catch, used to prove that the
#: preserved guard still precedes publisher dispatch in the successor.
DISPATCH_MARKER = "      const data = name === STUDIO_GIT_PUBLISH_STATUS_TOOL.name\n"

#: Self-check pins for the embedded reference regions.
CLASSIFIER_BLOCK_SHA256 = "2633fac80d5d6f85df4fa37487b6f7f913e7b89734e37d2ac686d4a375bcc2c7"
CATCH_BLOCK_SHA256 = "986341c5b3dce91dcd5137bc543cee5ee078745bd1e3092643abc281324543b0"


class CompatError(Exception):
    """One closed refusal code per rejected precondition."""

    def __init__(self, code: str, detail: str = ""):
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code
        self.detail = detail


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git_blob_sha1(data: bytes) -> str:
    return hashlib.sha1(
        b"blob " + str(len(data)).encode("ascii") + b"\0" + data
    ).hexdigest()


def _require(condition: bool, code: str, detail: str = "") -> None:
    if not condition:
        raise CompatError(code, detail)


def _verify_reference_blocks() -> None:
    """Refuse to compile with an edited embedded reference region."""
    _require(
        sha256_hex(CLASSIFIER_BLOCK.encode("utf-8")) == CLASSIFIER_BLOCK_SHA256,
        "REFERENCE_CLASSIFIER_DRIFT",
    )
    _require(
        sha256_hex(CATCH_BLOCK.encode("utf-8")) == CATCH_BLOCK_SHA256,
        "REFERENCE_CATCH_DRIFT",
    )
    # The classifier must not inspect or serialize the exception object, the
    # command arguments, the credentials, the paths or the stderr.
    forbidden = ("JSON.stringify", "Object.keys", "Object.entries", ".stack",
                 ".message", "Object.getOwnPropertyNames", "Reflect.ownKeys",
                 "JSON.parse", "String(", ".args", ".stderr", ".command")
    for token in forbidden:
        _require(token not in CLASSIFIER_BLOCK, "REFERENCE_CLASSIFIER_INSPECT",
                 token)
    _require("_error" in CLASSIFIER_BLOCK, "REFERENCE_CLASSIFIER_INSPECT",
             "the exception parameter must stay unused")


def verify_preimage(data: bytes) -> None:
    """Accept only the exact pinned predecessor bytes."""
    _require(isinstance(data, (bytes, bytearray)), "PREIMAGE_TYPE_REFUSED")
    data = bytes(data)
    _require(len(data) == PREIMAGE_SIZE, "PREIMAGE_SIZE_REFUSED",
             f"{len(data)} != {PREIMAGE_SIZE}")
    _require(sha256_hex(data) == PREIMAGE_SHA256, "PREIMAGE_SHA256_REFUSED")
    _require(git_blob_sha1(data) == PREIMAGE_GIT_BLOB, "PREIMAGE_BLOB_REFUSED")


def verify_successor(data: bytes) -> None:
    """Accept only the exact pinned successor bytes."""
    _require(isinstance(data, (bytes, bytearray)), "SUCCESSOR_TYPE_REFUSED")
    data = bytes(data)
    _require(len(data) == SUCCESSOR_SIZE, "SUCCESSOR_SIZE_REFUSED",
             f"{len(data)} != {SUCCESSOR_SIZE}")
    _require(sha256_hex(data) == SUCCESSOR_SHA256, "SUCCESSOR_SHA256_REFUSED")
    _require(git_blob_sha1(data) == SUCCESSOR_GIT_BLOB, "SUCCESSOR_BLOB_REFUSED")


def compile_successor(preimage: bytes) -> bytes:
    """Reconstruct the complete successor from the exact public preimage.

    Two edits only: one insertion of the pinned classifier at the pinned
    boundary, and one replacement of the pinned legacy catch with the pinned
    reference catch. Every other byte of the predecessor is preserved.
    """
    _verify_reference_blocks()
    try:
        text = preimage.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise CompatError("PREIMAGE_ENCODING_REFUSED") from exc

    # Structural guards first, so an input that is not the reviewed shape is
    # refused for its actual reason. The exact predecessor identity is then
    # required: a shape-correct but different input is still refused.
    _require("classifyStudioGitFailure" not in text, "PREIMAGE_ALREADY_PATCHED")
    _require(text.count(INSERTION_BOUNDARY) == 1, "BOUNDARY_AMBIGUOUS",
             f"count={text.count(INSERTION_BOUNDARY)}")
    _require(text.count(INSERTION_ANCHOR) == 1, "BOUNDARY_AMBIGUOUS",
             f"count={text.count(INSERTION_ANCHOR)}")
    _require(text.count(LEGACY_CATCH_BLOCK) == 1, "CATCH_AMBIGUOUS",
             f"count={text.count(LEGACY_CATCH_BLOCK)}")
    _require(text.count(GUARD_BLOCK) == 1, "GUARD_AMBIGUOUS",
             f"count={text.count(GUARD_BLOCK)}")

    boundary_at = text.index(INSERTION_BOUNDARY) + len(INSERTION_BOUNDARY)
    _require(text.startswith(INSERTION_ANCHOR, boundary_at),
             "BOUNDARY_ORDER_REFUSED")
    catch_at = text.index(LEGACY_CATCH_BLOCK)
    _require(boundary_at < catch_at, "BOUNDARY_ORDER_REFUSED")

    verify_preimage(preimage)

    successor_text = (
        text[:boundary_at]
        + CLASSIFIER_BLOCK
        + "\n"
        + text[boundary_at:catch_at]
        + CATCH_BLOCK
        + text[catch_at + len(LEGACY_CATCH_BLOCK):]
    )

    # Independent reversal: undoing the two edits must reproduce the
    # predecessor exactly. This proves "all other bytes preserved" without
    # trusting the splice itself.
    reversed_text = successor_text
    _require(reversed_text.count(CATCH_BLOCK) == 1, "SUCCESSOR_CATCH_AMBIGUOUS")
    reversed_text = reversed_text.replace(CATCH_BLOCK, LEGACY_CATCH_BLOCK)
    _require(reversed_text.count(CLASSIFIER_BLOCK + "\n") == 1,
             "SUCCESSOR_CLASSIFIER_AMBIGUOUS")
    reversed_text = reversed_text.replace(CLASSIFIER_BLOCK + "\n", "")
    _require(reversed_text.encode("utf-8") == preimage, "SUCCESSOR_DRIFT")

    successor = successor_text.encode("utf-8")
    verify_successor(successor)
    guard_report(successor)
    return successor


def guard_report(successor: bytes) -> dict:
    """Prove the incumbent local-session guard survived, ahead of dispatch."""
    try:
        text = successor.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise CompatError("SUCCESSOR_ENCODING_REFUSED") from exc
    _require(text.count(GUARD_BLOCK) == 1, "GUARD_LOST")
    _require(text.count(DISPATCH_MARKER) == 1, "DISPATCH_AMBIGUOUS")
    guard_at = text.index(GUARD_BLOCK)
    dispatch_at = text.index(DISPATCH_MARKER)
    _require(guard_at < dispatch_at, "GUARD_ORDER_LOST")
    _require("TYPED_GIT_REQUIRES_LOCAL_STUDIO_SESSION" in text, "GUARD_CODE_LOST")
    _require("TYPED_GIT_PRECHECK_REFUSED" not in text, "LEGACY_CODE_RETAINED")
    _require(text.count("classifyStudioGitFailure") == 2,
             "CLASSIFIER_REFERENCE_COUNT")
    return {
        "guardPreserved": True,
        "guardPrecedesDispatch": True,
        "guardOffset": guard_at,
        "dispatchOffset": dispatch_at,
    }


def diff_report(preimage: bytes, successor: bytes) -> dict:
    """Bounded diff proving only the two intended regions changed."""
    before = preimage.decode("utf-8").splitlines()
    after = successor.decode("utf-8").splitlines()
    diff = list(difflib.unified_diff(before, after, fromfile="a/gateway.mjs",
                                     tofile="b/gateway.mjs", n=2, lineterm=""))
    added = sum(1 for line in diff if line.startswith("+") and not line.startswith("+++"))
    removed = sum(1 for line in diff if line.startswith("-") and not line.startswith("---"))
    hunks = sum(1 for line in diff if line.startswith("@@"))
    return {
        "hunks": hunks,
        "addedLines": added,
        "removedLines": removed,
        "diff": "\n".join(diff),
    }


def compile_from_path(path: Path) -> bytes:
    """Compile the successor from one exact predecessor file."""
    data = Path(path).read_bytes()
    return compile_successor(data)


def main(argv: list[str] | None = None) -> int:
    """Source compiler CLI. It never installs and never writes an install path."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Compile the pinned C1 fleet-gateway successor.")
    parser.add_argument("source", help="the exact predecessor gateway file")
    parser.add_argument("--out", help="write the successor bytes here")
    args = parser.parse_args(argv)

    preimage = Path(args.source).read_bytes()
    try:
        successor = compile_successor(preimage)
    except CompatError as exc:
        print(json.dumps({"schema": "mastermind.studio_fleet_git_failure_compat.v1",
                          "effect": "NOT_APPLIED", "code": exc.code,
                          "detail": exc.detail}, sort_keys=True))
        return 1
    if args.out:
        Path(args.out).write_bytes(successor)
    report = diff_report(preimage, successor)
    report.update({
        "schema": "mastermind.studio_fleet_git_failure_compat.v1",
        "effect": "NOT_APPLIED",
        "preimageSha256": PREIMAGE_SHA256,
        "preimageGitBlob": PREIMAGE_GIT_BLOB,
        "preimageSize": PREIMAGE_SIZE,
        "successorSha256": SUCCESSOR_SHA256,
        "successorGitBlob": SUCCESSOR_GIT_BLOB,
        "successorSize": SUCCESSOR_SIZE,
        "referenceGatewaySha256": REFERENCE_GATEWAY_SHA256,
        "guard": guard_report(successor),
    })
    print(json.dumps(report, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
