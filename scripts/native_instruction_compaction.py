"""Pure, opt-in rendering for the existing project_execution_brief writer.

No filesystem, process, network, policy, runtime, installation or trust effects.
The caller reviews the actual source/target, excludes concurrent writers, and
passes the returned text to project_execution_brief.apply with its exact full
preimage. A digest is content identity, not permission. Nothing runs at startup.
"""
from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping, Sequence

MARKER = 'mastermind-assigned-execution-v1'
MAX_INPUT_BYTES = 512 * 1024
BRIEF_TARGET_BYTES = 8 * 1024
# These are eligibility names, NOT preapproved deletion instructions. Every
# present retirement additionally needs its exact reviewed full-block digest.
RETIRABLE_MARKERS = frozenset({
    'mastermind-leadership-continuity-20261024',
    'mastermind-commercial-data-rights-20261023',
    'pinned-session-delivery-reset-20261017',
    'chris-proportionate-execution-20261015',
    'mastermind-ci-observation-liveness-v1',
    'mastermind-saved-site-credentials-v1',
    'mastermind-portfolio-operations-20261024',
})
SHA = re.compile(r'[0-9a-f]{64}\Z')
# Literal presence is advisory. Never infer the active policy, mount state,
# runtime loading or a release/admission decision from a phrase match.
SIGNALS = {
    'BLANKET_REVIEW_WORDING': 'Independent REVIEW is still',
    'CONDITIONAL_STORAGE_EXCEPTION': '### TEMPORARY OVERRIDE',
    'AUTO_IMPORT_REQUIRES_LOAD_AUDIT': None,
}


def digest(data: str) -> str:
    return hashlib.sha256(data.encode('utf-8')).hexdigest()


def _checked_text(value: str, name: str) -> None:
    if not isinstance(value, str):
        raise ValueError(f'{name} must be UTF-8 text')
    if len(value.encode('utf-8')) > MAX_INPUT_BYTES:
        raise ValueError(f'{name} exceeds the bounded input size')


def _inside_fence(text: str, position: int) -> bool:
    """Conservatively recognize ordinary Markdown fences before a marker.

    Same-character closing fences must be at least as long as the opener and
    carry no info text. This is a refusal check, not a Markdown renderer; an
    ambiguous unclosed fence preserves the input by rejecting its selection.
    """
    opened: tuple[str, int] | None = None
    for line in text[:position].splitlines():
        match = re.fullmatch(r' {0,3}(`{3,}|~{3,})(.*)', line)
        if match is None:
            continue
        fence, tail = match.groups()
        if opened is None:
            opened = (fence[0], len(fence))
        elif fence[0] == opened[0] and len(fence) >= opened[1] and not tail.strip():
            opened = None
    return opened is not None


def _span(text: str, marker: str) -> tuple[int, int] | None:
    start, end = f'<!-- {marker} -->', f'<!-- /{marker} -->'
    a_count, b_count = text.count(start), text.count(end)
    if a_count == b_count == 0:
        return None
    if a_count != 1 or b_count != 1:
        raise ValueError(f'Malformed or duplicate managed block: {marker}')
    a, b = text.index(start), text.index(end)
    if b < a:
        raise ValueError(f'Reversed managed block: {marker}')
    # Do not reinterpret an inline quote/example as an installed managed block.
    for position, literal in ((a, start), (b, end)):
        line_start = text.rfind('\n', 0, position) + 1
        line_end = text.find('\n', position)
        if line_end == -1:
            line_end = len(text)
        if text[line_start:line_end].rstrip('\r') != literal:
            raise ValueError(f'Managed marker is not a standalone line: {marker}')
        if _inside_fence(text, position):
            raise ValueError(f'Managed marker is inside a fenced example: {marker}')
    body = text[a + len(start):b]
    if '<!--' in body:
        raise ValueError(f'Nested/comment-bearing managed block: {marker}')
    return a, b + len(end)


def inspect_text(text: str, *, target_bytes: int = BRIEF_TARGET_BYTES) -> dict:
    """Return descriptive findings only; this is never a runtime gate."""
    _checked_text(text, 'instructions')
    if type(target_bytes) is not int or target_bytes <= 0:
        raise ValueError('target_bytes must be a positive integer')
    findings = [code for code, phrase in SIGNALS.items()
                if phrase is not None and phrase in text]
    if re.search(r'(?m)^\s*@\S+', text):
        findings.append('AUTO_IMPORT_REQUIRES_LOAD_AUDIT')
    size = len(text.encode('utf-8'))
    if size > target_bytes:
        findings.append('ABOVE_ADVISORY_BYTE_TARGET')
    return {
        'bytes': size, 'sha256': digest(text), 'lines': len(text.splitlines()),
        'advisory_target_bytes': target_bytes, 'findings': findings,
        'interpretation': 'Literal/byte evidence only; review context before changing anything.',
        'runtime_loading': 'UNOBSERVED', 'runtime_behavior': 'UNOBSERVED',
        'effect': 'NONE',
    }


def plan_compaction(
    text: str,
    brief: str,
    profile: str,
    *,
    expected_preimage_sha256: str,
    expected_brief_sha256: str,
    reviewed_managed_sha256: Sequence[str],
    retirements: Mapping[str, str] | None = None,
) -> dict:
    """Render an exact reviewed update; keep every other byte unchanged.

    reviewed_managed_sha256 binds the entire old managed block (markers included).
    retirements binds entire historical blocks, never headings alone. Unknown
    text and host-control blocks have no deletion path. Missing retirement blocks
    are harmless on a repeated preview; a changed present block fails closed.
    The existing writer rechecks the full preimage before its actual write.
    """
    _checked_text(text, 'instructions')
    _checked_text(brief, 'brief')
    if profile not in {'codex', 'claude'}:
        raise ValueError('Only existing Codex/Claude instruction profiles are supported')
    for value in (expected_preimage_sha256, expected_brief_sha256):
        if not isinstance(value, str) or not SHA.fullmatch(value):
            raise ValueError('Expected digests must be lowercase SHA-256')
    if digest(text) != expected_preimage_sha256:
        raise ValueError('Instruction preimage differs; no plan produced')
    if digest(brief) != expected_brief_sha256:
        raise ValueError('Selected source brief differs; no plan produced')
    if (isinstance(reviewed_managed_sha256, (str, bytes))
            or not isinstance(reviewed_managed_sha256, Sequence)
            or any(not isinstance(x, str) or not SHA.fullmatch(x)
                   for x in reviewed_managed_sha256)):
        raise ValueError('Reviewed managed identities must be a sequence of SHA-256 values')
    if not brief.strip() or len(brief.encode('utf-8')) > BRIEF_TARGET_BYTES:
        raise ValueError('Compact source brief is empty or exceeds its authoring byte target')
    if '<!--' in brief or re.search(r'(?m)^\s*@\S+', brief):
        raise ValueError('Compact brief must not contain managed comments or automatic imports')
    if retirements is None:
        retirements = {}
    if not isinstance(retirements, Mapping):
        raise ValueError('Retirements must be an explicit marker/digest mapping')
    edits, retired, absent = [], [], []
    main = _span(text, MARKER)
    if main is None:
        raise ValueError('Existing managed execution block is required; this does not enroll a host')
    replacement = f'<!-- {MARKER} -->\n{brief.strip()}\n<!-- /{MARKER} -->'
    old = text[main[0]:main[1]]
    if old != replacement and digest(old) not in reviewed_managed_sha256:
        raise ValueError('Managed instruction block is not an explicitly reviewed preimage')
    edits.append((*main, replacement))
    for marker, expected in retirements.items():
        if marker not in RETIRABLE_MARKERS:
            raise ValueError(f'Unknown or protected retirement marker: {marker}')
        if not isinstance(expected, str) or not SHA.fullmatch(expected):
            raise ValueError(f'Invalid retirement digest: {marker}')
        span = _span(text, marker)
        if span is None:
            absent.append(marker)
            continue
        block = text[span[0]:span[1]]
        if digest(block) != expected:
            raise ValueError(f'Historical block changed; preserve it: {marker}')
        edits.append((*span, ''))
        retired.append({'marker': marker, 'sha256': expected, 'bytes': len(block.encode('utf-8'))})
    ordered = sorted(edits)
    if any(left[1] > right[0] for left, right in zip(ordered, ordered[1:])):
        raise ValueError('Overlapping managed blocks; no plan produced')
    result = text
    for a, b, value in reversed(ordered):
        result = result[:a] + value + result[b:]
    before, after = len(text.encode('utf-8')), len(result.encode('utf-8'))
    return {
        'schema': 'mastermind.native_instruction_compaction_preview.v1',
        'profile': profile, 'effect': 'NONE', 'preview_only': True,
        'before_sha256': digest(text), 'after_sha256': digest(result),
        'source_brief_sha256': expected_brief_sha256,
        'before_bytes': before, 'after_bytes': after, 'bytes_removed': before - after,
        'changed': result != text, 'retired_blocks': retired,
        'already_absent': sorted(absent), 'remaining_diagnostics': inspect_text(result),
        'runtime_loading': 'UNOBSERVED', 'runtime_behavior': 'UNOBSERVED',
        'text': result,
    }
