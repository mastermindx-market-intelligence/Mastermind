"""Bounded fixed-path capture engine for canonical project-knowledge DRAFT
recipes over the sealed Macro owner store.

Two public functions, both pure capture-and-compile readers over the existing
sealed owner Git object:

* ``compile_project_knowledge_recipe`` - capture the fixed owner sources plus
  the workstream/decision preimages at one pinned commit, execute the ACTUAL
  captured recipe compiler bytes, and return one closed PRIVATE capture.
* ``restore_project_knowledge_recipe`` - recompile the exact retained
  workstream/decision/date snapshot after qualifying only the two fixed code
  blobs at the same recorded commit against the recorded source binding.

Canonical identity this engine enforces:

* ``work_ref`` is the colon citation ``WS:<KEY>``; the canonical record file is
  ``agentos/workstreams/WS-<KEY>.md``.
* The communication preference is the fixed-key decision
  ``agentos/decisions/DEC-PROJECT-COMMUNICATION-PREFERENCE-<KEY>.md``, read
  only as a preference preimage and EMPTY (``decision_text`` null) when that
  record is genuinely absent or when the request is a file add.
* The file add target ``agentos/project-files/WS-<KEY>/<id>.<ext>`` is derived
  as ``SHA256(canonical{"principal_scope", "request_id", "work_ref"})``; the
  membership at that path must be ABSENT at the pinned commit, and any
  existing entry refuses instead of ever overwriting.
* ``source_binding`` carries the actual captured commit plus the content
  SHA-256 of the two fixed code blobs; ``revision``-style Git blob stamps are
  never reused as content identity.

Every call runs a fixed, bounded, immutable Git capture of the one absolute
Macro root pinned by ``expected_macro_sha`` (supplied only by the existing
sealed owner, never by an HTTP caller): HEAD is verified before the first and
after the last Git read, Git replace refs are disabled, lazy fetch is
disabled, no optional locks are taken, nothing is fetched or written, all
ambient ``GIT_*`` environment and config redirects are sanitized into a fresh
per-call environment (the caller's own environment is never mutated), and the
capture reuses the captured ``scripts/agentos.py`` parser and checkers and the
captured ``scripts/project_knowledge_recipes.py`` compiler (module identity
isolated and restored) instead of inferring law from local copies.  Budgets
are UTF-8 byte budgets: 4 MiB cumulative Git output within 15 seconds, code
blobs 1 MiB each, workstream 128 KiB, one decision record 16 KiB, one project
file 32 KiB, and the whole canonical capture at most 524288 bytes.

These functions are INTERNAL source capture, not caller authorization and not
publication.  They never write, upload, fetch, or infer a principal relation;
the trusted ``actor_ref``/``permission_binding_digest``/``decision_date``
bindings arrive from the installed service, never from a public caller.  The
installed collector performs the stronger source/materialized-root pre and
post seal externally: THIS ENGINE ALONE IS NOT INSTALLED SOURCE
QUALIFICATION, and a successful return asserts nothing about grants,
transport, or that anything was published.  Recipe output is always
``state: DRAFT_ONLY``.  Only ``common``-core scoped imports are used; no
facade reuse and no integration imports.
"""

from __future__ import annotations

import contextlib
import datetime
import hashlib
import io
import json
import os
import re
import sys
import time
import types
from pathlib import Path

__all__ = [
    "compile_project_knowledge_recipe",
    "restore_project_knowledge_recipe",
]

CAPTURE_SCHEMA = "mastermind.project_knowledge_recipe_capture.v1"
RECIPE_SCHEMA = "mastermind.project_knowledge_recipe.v1"
FILE_ADD_REQUEST_SCHEMA = "mastermind.project_file_add_request.v1"
PREFERENCE_SET_REQUEST_SCHEMA = "mastermind.project_preference_set_request.v1"

REPOSITORY = "mastermindx-market-intelligence/macro"
PARSER_PATH = "scripts/agentos.py"
COMPILER_PATH = "scripts/project_knowledge_recipes.py"
PARSER_MODULE_ID = "agentos_bound_project_knowledge_owner"
COMPILER_MODULE_ID = "agentos_bound_project_knowledge_recipe_compiler"

_STATE_DRAFT_ONLY = "DRAFT_ONLY"
_ACTION_FILE_ADD = "project_file_add"
_ACTION_PREFERENCE_SET = "project_preference_set"

_FILE_ADD_REQUEST_ID_PREFIX = "mmos-project-file-add-"
_PREFERENCE_REQUEST_ID_PREFIX = "mmos-project-preference-set-"

_CAPTURE_LIMIT = 524288
_TOTAL_BUDGET = 4 * 1048576
_CODE_LIMIT = 1048576
_WS_LIMIT = 131072
_DECISION_LIMIT = 16384
_FILE_LIMIT = 32768
_TIMEOUT_MAX = 15.0

_SHA40 = re.compile(r"[0-9a-f]{40}")
_SHA64 = re.compile(r"[0-9a-f]{64}")
_ACTOR_REF = re.compile(r"workspace:[0-9a-f]{64}")
_WORK_REF = re.compile(r"WS:[A-Z0-9]+(?:-[A-Z0-9]+)*")
_REQUEST_STAMP = re.compile(r"[0-9a-f]{40}")
_DATE = re.compile(r"([0-9]{4})-([0-9]{2})-([0-9]{2})")
_MEMBER = r"100644 blob [0-9a-f]{40}\t"
# Permitted controls are exactly LF, CR and TAB; every other C0, the C1
# range and DEL are refused anywhere a captured or emitted body echoes them.
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f\x80-\x9f]")
_IRREGULAR = object()

_PARSE_FAULTS = (
    ValueError, TypeError, KeyError, AttributeError, RecursionError,
    SyntaxError, MemoryError, SystemExit,
)

_FILE_ADD_KEYS = frozenset(
    ["schema", "request_id", "work_ref", "source_commit", "base_revision", "file"]
)
_PREFERENCE_KEYS = frozenset(
    ["schema", "request_id", "work_ref", "source_commit", "base_revision",
     "expected_preference_revision", "value"]
)
_FILE_KEYS = frozenset(["display_name", "media_type", "content_utf8"])
_TRUSTED_KEYS = frozenset(["actor_ref", "permission_binding_digest", "decision_date"])
_SNAPSHOT_KEYS = frozenset(["workstream_text", "decision_text", "decision_date"])
_BINDING_KEYS = frozenset(["compiler", "owner"])
_BINDING_MEMBER_KEYS = frozenset(["repository", "commit", "path", "content_sha256"])
_CAPTURE_KEYS = frozenset(["schema", "recipe", "initial_snapshot", "source_binding"])
_RECIPE_KEYS = frozenset(
    ["schema", "state", "action", "work_ref", "request_id",
     "request_fingerprint", "captured_commit", "permission_binding_digest",
     "postimages"]
)
_POSTIMAGE_KEYS = frozenset(
    ["path", "content_utf8", "content_sha256", "expected_preimage_sha256"]
)

_MEDIA_TYPES = {"md": "text/markdown", "txt": "text/plain"}


_REJECT = "project_knowledge_recipe_unavailable"
# Every refusal is exactly ``ValueError(_REJECT)``: the fixed closed reason
# token is the only thing that ever travels, and no private exception type,
# path, body, or payload text leaks on any refusal path.


def _default_runner():
    # control_plane.ceo_boot_packet owns the bounded subprocess runner used by
    # the installed collector; tests inject an equivalent runner instead.
    from control_plane.ceo_boot_packet import bounded_subprocess_runner

    return bounded_subprocess_runner


def _ulen(value: str) -> int:
    """UTF-8 byte length: every capture budget is a byte budget."""
    return len(value.encode("utf-8"))


def _canonical(value) -> str:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False,
    )


def _sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _git_env():
    """A fresh sanitized environment: every ambient ``GIT_*`` variable,
    including config and rewrite redirects, is dropped, and lazy fetch plus
    ambient global/system config are pinned off.  ``os.environ`` is never
    mutated."""
    env = {}
    for key, value in os.environ.items():
        if not key.upper().startswith("GIT_"):
            env[key] = value
    env["GIT_NO_LAZY_FETCH"] = "1"
    env["GIT_CONFIG_GLOBAL"] = os.devnull
    env["GIT_CONFIG_SYSTEM"] = os.devnull
    return env


def _validate_decision_date(value) -> str:
    """A real retained YYYY-MM-DD calendar date, never a derived clock."""
    if type(value) is not str or _DATE.fullmatch(value) is None:
        raise ValueError(_REJECT)
    year, month, day = (int(part) for part in _DATE.fullmatch(value).groups())
    try:
        datetime.date(year, month, day)
    except ValueError:
        raise ValueError(_REJECT) from None
    return value


def _validate_bounded_text(value, *, limit):
    """Bounded, control-free UTF-8 text for one captured or retained body."""
    if type(value) is not str:
        raise ValueError(_REJECT)
    try:
        raw = value.encode("utf-8")
    except UnicodeEncodeError:
        raise ValueError(_REJECT) from None
    if len(raw) > limit or _CONTROL.search(value):
        raise ValueError(_REJECT)
    return value


def _bounded_file_content(value) -> str:
    text = _validate_bounded_text(value, limit=_FILE_LIMIT)
    if _ulen(text) > _FILE_LIMIT:
        raise ValueError(_REJECT)
    return text


def _media_suffix(request):
    file_request = request["file"]
    if type(file_request) is not dict or set(file_request) != set(_FILE_KEYS):
        raise ValueError(_REJECT)
    display_name = file_request["display_name"]
    if type(display_name) is not str or not display_name:
        raise ValueError(_REJECT)
    try:
        if _ulen(display_name) > 128:
            raise ValueError(_REJECT)
    except UnicodeError:
        raise ValueError(_REJECT) from None
    if any(ord(char) < 0x20 or 0x7f <= ord(char) <= 0x9f for char in display_name):
        raise ValueError(_REJECT)
    if "." not in display_name or "/" in display_name or "\\" in display_name:
        raise ValueError(_REJECT)
    stem, _, ext = display_name.rpartition(".")
    ext = ext.lower()
    if not stem or ext not in _MEDIA_TYPES:
        raise ValueError(_REJECT)
    if file_request["media_type"] != _MEDIA_TYPES[ext]:
        raise ValueError(_REJECT)
    _bounded_file_content(file_request["content_utf8"])
    if _CONTROL.search(display_name):
        raise ValueError(_REJECT)
    return ext


def _validate_request(request):
    """The closed strict public request.  Extra, missing or mistyped fields
    refuse before any Git read happens at all; deep law stays with the
    captured compiler, which is executed on the real bytes."""
    if type(request) is not dict:
        raise ValueError(_REJECT)
    schema = request.get("schema")
    if schema == FILE_ADD_REQUEST_SCHEMA:
        keys, prefix = _FILE_ADD_KEYS, _FILE_ADD_REQUEST_ID_PREFIX
        mode = "file_add"
    elif schema == PREFERENCE_SET_REQUEST_SCHEMA:
        keys, prefix = _PREFERENCE_KEYS, _PREFERENCE_REQUEST_ID_PREFIX
        mode = "preference"
    else:
        raise ValueError(_REJECT)
    if set(request) != set(keys):
        raise ValueError(_REJECT)
    request_id = request["request_id"]
    if (
        type(request_id) is not str
        or not request_id.startswith(prefix)
        or _REQUEST_STAMP.fullmatch(request_id[len(prefix):]) is None
    ):
        raise ValueError(_REJECT)
    work_ref = request["work_ref"]
    if type(work_ref) is not str or _WORK_REF.fullmatch(work_ref) is None:
        raise ValueError(_REJECT)
    key = work_ref[3:]
    if not 2 <= len(key) <= 64:
        raise ValueError(_REJECT)
    if type(request["source_commit"]) is not str or _SHA40.fullmatch(request["source_commit"]) is None:
        raise ValueError(_REJECT)
    if type(request["base_revision"]) is not str or _SHA64.fullmatch(request["base_revision"]) is None:
        raise ValueError(_REJECT)
    if mode == "file_add":
        _media_suffix(request)
    else:
        value = request["value"]
        if type(value) is not str or not value.strip() or _ulen(value) > 2000:
            raise ValueError(_REJECT)
        if _CONTROL.search(value):
            raise ValueError(_REJECT)
        revision = request["expected_preference_revision"]
        if revision is not None:
            if type(revision) is not str or _SHA64.fullmatch(revision) is None:
                raise ValueError(_REJECT)
    return mode, work_ref, key


def _validate_bindings(actor_ref, permission_binding_digest, decision_date):
    if type(actor_ref) is not str or _ACTOR_REF.fullmatch(actor_ref) is None:
        raise ValueError(_REJECT)
    if type(permission_binding_digest) is not str or _SHA64.fullmatch(permission_binding_digest) is None:
        raise ValueError(_REJECT)
    _validate_decision_date(decision_date)


def _validate_snapshot(initial_snapshot, decision_date):
    """The retained private snapshot is bodies plus the retained date only."""
    if type(initial_snapshot) is not dict or set(initial_snapshot) != set(_SNAPSHOT_KEYS):
        raise ValueError(_REJECT)
    workstream_text = _validate_bounded_text(
        initial_snapshot["workstream_text"], limit=_WS_LIMIT
    )
    decision_text = initial_snapshot["decision_text"]
    if decision_text is not None:
        decision_text = _validate_bounded_text(decision_text, limit=_DECISION_LIMIT)
    if initial_snapshot["decision_date"] != decision_date:
        raise ValueError(_REJECT)
    return workstream_text, decision_text


def _validate_source_binding(source_binding, expected_macro_sha, expected_owners):
    """The recorded binding must name exactly the two fixed code blobs at the
    same recorded commit; content identity is re-hashed against the real
    bytes, never trusted."""
    if type(source_binding) is not dict or set(source_binding) != set(_BINDING_KEYS):
        raise ValueError(_REJECT)
    members = {}
    for role in ("compiler", "owner"):
        member = source_binding[role]
        if type(member) is not dict or set(member) != set(_BINDING_MEMBER_KEYS):
            raise ValueError(_REJECT)
        if (
            member["repository"] != REPOSITORY
            or member["commit"] != expected_macro_sha
            or member["path"] != expected_owners[role]
            or type(member["content_sha256"]) is not str
            or _SHA64.fullmatch(member["content_sha256"]) is None
        ):
            raise ValueError(_REJECT)
        members[role] = member["content_sha256"]
    return members


class _Session:
    """One bounded, immutable Git read session against the sealed Macro root."""

    def __init__(self, macro_root, expected_macro_sha, runner, timeout):
        if (
            not isinstance(macro_root, (str, Path))
            or isinstance(macro_root, bytes)
            or not Path(macro_root).is_absolute()
            or type(expected_macro_sha) is not str
            or _SHA40.fullmatch(expected_macro_sha) is None
            or type(timeout) not in (int, float)
            or isinstance(timeout, bool)
            or not 0 < timeout <= _TIMEOUT_MAX
            or (runner is not None and not callable(runner))
        ):
            raise ValueError(_REJECT)
        self.root = Path(macro_root)
        self.commit = expected_macro_sha
        self.expected_head = expected_macro_sha
        self.deadline = time.monotonic() + timeout
        self.consumed = 0
        self._peer = None
        self._runner = runner
        self.commands = []

    def git(self, *args, limit=262144):
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise ValueError(_REJECT)
        if self._runner is None:
            self._runner = _default_runner()
        self.commands.append(list(args))
        try:
            result = self._runner(
                [
                    "git",
                    "--no-optional-locks",
                    "--no-replace-objects",
                    "-C",
                    str(self.root),
                    *args,
                ],
                cwd=self.root,
                timeout=remaining,
                max_bytes=limit,
                env=_git_env(),
            )
        except (OSError, ValueError, TypeError):
            raise ValueError(_REJECT) from None
        if (
            not isinstance(result, dict)
            or result.get("code") != 0
            or type(result.get("stdout")) is not str
            or result.get("timed_out") is True
            or result.get("invalid_utf8") is True
            or result.get("limit_exceeded") is True
        ):
            raise ValueError(_REJECT)
        value = result["stdout"]
        self.consumed += _ulen(value)
        if self.consumed + (self._peer.consumed if self._peer is not None else 0) > _TOTAL_BUDGET:
            raise ValueError(_REJECT)
        return value

    def head(self):
        raw = self.git("rev-parse", "HEAD", limit=128).strip()
        if _SHA40.fullmatch(raw) is None:
            raise ValueError(_REJECT)
        return raw

    def member(self, path):
        """Tree-entry check: None when absent, _IRREGULAR when not a plain
        100644 blob, otherwise the actual blob SHA-1 revision."""
        raw = self.git("ls-tree", "-z", self.commit, "--", path, limit=16384)
        if not raw:
            return None
        if re.fullmatch(_MEMBER + re.escape(path) + "\x00", raw) is None:
            return _IRREGULAR
        blob = raw.split("\t", 1)[0].split(" ")[2]
        if _SHA40.fullmatch(blob) is None:
            raise ValueError(_REJECT)
        return blob

    def captured(self, path, limit):
        return self.git("show", self.commit + ":" + path, limit=limit)


@contextlib.contextmanager
def _module_session(module_id, path, text):
    """Run captured Macro bytes under an isolated, restored module id with
    stdout and stderr suppressed and the interpreter namespaces restored."""
    module = types.ModuleType(module_id)
    module.__file__ = str(path)
    name = module.__name__
    prior = sys.modules.get(name)
    original_path = list(sys.path)
    sys.modules[name] = module
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            with contextlib.redirect_stderr(io.StringIO()):
                exec(compile(text, module.__file__, "exec"), module.__dict__)
        yield module
    finally:
        sys.path[:] = original_path
        if prior is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = prior


class _CapturedRecord:
    """Path stand-in feeding captured bytes to Macro's own parser."""

    def __init__(self, text):
        self._text = text

    def read_text(self, *, encoding):
        if encoding != "utf-8":
            raise ValueError("record encoding refused")
        return self._text


def _parse_record(module, text):
    record, body = module.parse_record(_CapturedRecord(text))
    return record, body


def _hard(problems):
    return any(problem.hard for problem in problems)


def _code_member(session, path):
    """One fixed code blob, captured and hashed; revision is Git's own."""
    blob = session.member(path)
    if blob is None or blob is _IRREGULAR:
        raise ValueError(_REJECT)
    text = session.captured(path, limit=_CODE_LIMIT)
    if _ulen(text) > _CODE_LIMIT:
        raise ValueError(_REJECT)
    return blob, text


def _record_preimage(session, path, limit):
    """One canonical record preimage; None only when genuinely absent."""
    blob = session.member(path)
    if blob is None:
        return None
    if blob is _IRREGULAR:
        raise ValueError(_REJECT)
    size = session.git("cat-file", "-s", blob, limit=64).strip()
    if not size.isdigit() or int(size) > limit:
        raise ValueError(_REJECT)
    text = session.captured(path, limit=limit + 1)
    if _ulen(text) > limit:
        raise ValueError(_REJECT)
    return text


def _file_target(actor_ref, request, key):
    """The derived, owner-scoped target path for a file add."""
    file_id = hashlib.sha256(
        _canonical(
            {
                "principal_scope": actor_ref[len("workspace:"):],
                "request_id": request["request_id"],
                "work_ref": request["work_ref"],
            }
        ).encode("utf-8")
    ).hexdigest()
    ext = _media_suffix(request)
    return "agentos/project-files/WS-" + key + "/" + file_id + "." + ext, file_id


def _build_recipe(session, compiler_module, mode, request, ws_text, decision_text, decision_date, actor_ref, permission_binding_digest):
    """Execute the ACTUAL captured compiler bytes; the caller can never pass
    a module, callback, compiler or code body - code comes only from the two
    fixed Git blobs."""
    error_type = getattr(compiler_module, "KnowledgeRecipeError", None)
    raise_types = _PARSE_FAULTS
    if isinstance(error_type, type) and issubclass(error_type, BaseException):
        raise_types = _PARSE_FAULTS + (error_type,)
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            with contextlib.redirect_stderr(io.StringIO()):
                if mode == "file_add":
                    recipe = compiler_module.build_project_file_add(
                        request,
                        actor_ref=actor_ref,
                        permission_binding_digest=permission_binding_digest,
                        captured_commit=session.commit,
                        workstream_text=ws_text,
                        existing_file_text=None,
                    )
                else:
                    recipe = compiler_module.build_project_preference_set(
                        request,
                        actor_ref=actor_ref,
                        permission_binding_digest=permission_binding_digest,
                        captured_commit=session.commit,
                        workstream_text=ws_text,
                        decision_text=decision_text,
                        decision_date=decision_date,
                    )
    except raise_types:
        raise ValueError(_REJECT) from None
    if not isinstance(recipe, dict):
        raise ValueError(_REJECT)
    return recipe


def _validate_recipe(session, parser_module, recipe, mode, request, key, ws_text, decision_text, ws_path, decision_path, media_path):
    """Closed engine-side envelope checks plus re-validation of both record
    postimages with the SAME captured canonical parser."""
    if type(recipe) is not dict or set(recipe) != set(_RECIPE_KEYS):
        raise ValueError(_REJECT)
    if (
        recipe["schema"] != RECIPE_SCHEMA
        or recipe["state"] != _STATE_DRAFT_ONLY
        or recipe["work_ref"] != request["work_ref"]
        or recipe["request_id"] != request["request_id"]
        or recipe["captured_commit"] != session.commit
        or type(recipe["request_fingerprint"]) is not str
        or _SHA64.fullmatch(recipe["request_fingerprint"]) is None
        or type(recipe["permission_binding_digest"]) is not str
        or _SHA64.fullmatch(recipe["permission_binding_digest"]) is None
    ):
        raise ValueError(_REJECT)
    expected_action = _ACTION_FILE_ADD if mode == "file_add" else _ACTION_PREFERENCE_SET
    if recipe["action"] != expected_action:
        raise ValueError(_REJECT)
    postimages = recipe["postimages"]
    if type(postimages) is not list or len(postimages) != 2:
        raise ValueError(_REJECT)
    ws_post = None
    record_post = None
    expected_ws_path = "agentos/workstreams/WS-" + key + ".md"
    total = 0
    for image in postimages:
        if type(image) is not dict or set(image) != set(_POSTIMAGE_KEYS):
            raise ValueError(_REJECT)
        path = image["path"]
        content = image["content_utf8"]
        if type(path) is not str or path not in (ws_path, media_path, decision_path):
            raise ValueError(_REJECT)
        if type(content) is not str or _CONTROL.search(content):
            raise ValueError(_REJECT)
        total += _ulen(content)
        if total > _CAPTURE_LIMIT:
            raise ValueError(_REJECT)
        if image["content_sha256"] != _sha256_hex(content):
            raise ValueError(_REJECT)
        if path == ws_path:
            limit, expected_preimage = _WS_LIMIT, _sha256_hex(ws_text)
            ws_post = image
        elif path == media_path:
            limit, expected_preimage = _FILE_LIMIT, None
        else:
            limit = _DECISION_LIMIT
            expected_preimage = None if decision_text is None else _sha256_hex(decision_text)
            record_post = image
        if _ulen(content) > limit or image["expected_preimage_sha256"] != expected_preimage:
            raise ValueError(_REJECT)
    if ws_post is None or (mode == "preference") != (record_post is not None):
        raise ValueError(_REJECT)
    # Re-validate the emitted records with the SAME captured parser, at their
    # canonical paths so the parser's own filename checks apply.
    record, _body = _parse_record(parser_module, ws_post["content_utf8"])
    if _hard(parser_module.check_workstream(record, session.root / ws_path, None)):
        raise ValueError(_REJECT)
    if record.get("key") != key:
        raise ValueError(_REJECT)
    if record_post is not None:
        record, _body = _parse_record(parser_module, record_post["content_utf8"])
        if _hard(parser_module.check_decision(record, session.root / record_post["path"])):
            raise ValueError(_REJECT)
        if record.get("key") != "PROJECT-COMMUNICATION-PREFERENCE-" + key:
            raise ValueError(_REJECT)


def _assemble(session, recipe, initial_snapshot, source_binding):
    capture = {
        "schema": CAPTURE_SCHEMA,
        "recipe": recipe,
        "initial_snapshot": initial_snapshot,
        "source_binding": source_binding,
    }
    if set(capture) != set(_CAPTURE_KEYS):
        raise ValueError(_REJECT)
    encoded = _canonical(capture)
    if _ulen(encoded) > _CAPTURE_LIMIT:
        raise ValueError(_REJECT)
    return capture


def _binding(session, compiler_sha, parser_sha):
    return {
        "compiler": {
            "repository": REPOSITORY,
            "commit": session.commit,
            "path": COMPILER_PATH,
            "content_sha256": compiler_sha,
        },
        "owner": {
            "repository": REPOSITORY,
            "commit": session.commit,
            "path": PARSER_PATH,
            "content_sha256": parser_sha,
        },
    }


def _open_session(macro_root, expected_macro_sha, runner, timeout):
    session = _Session(macro_root, expected_macro_sha, runner, timeout)
    if session.head() != session.expected_head:
        raise ValueError(_REJECT)
    return session


def _code_session(data, code_root, code_commit, runner, timeout):
    # Private child/factory arguments only. Public requests remain closed and
    # cannot select executable code, a path, module or command.
    if (code_root is None) != (code_commit is None):
        raise ValueError(_REJECT)
    if code_root is None:
        return data
    code = _open_session(code_root, code_commit, runner, timeout)
    code.deadline = data.deadline = min(code.deadline, data.deadline)
    code._peer, data._peer = data, code
    return code


def _heads_current(data, code):
    return data.head() == data.expected_head and (code is data or code.head() == code.expected_head)


def _capture_code(session):
    """Both fixed code blobs, hashed; HEAD re-checked around the reads."""
    parser_blob, parser_text = _code_member(session, PARSER_PATH)
    if session.head() != session.expected_head:
        raise ValueError(_REJECT)
    compiler_blob, compiler_text = _code_member(session, COMPILER_PATH)
    if _ulen(parser_text) > _CODE_LIMIT or _ulen(compiler_text) > _CODE_LIMIT:
        raise ValueError(_REJECT)
    return {
        "parser_blob": parser_blob,
        "parser_text": parser_text,
        "compiler_blob": compiler_blob,
        "compiler_text": compiler_text,
        "parser_sha": _sha256_hex(parser_text),
        "compiler_sha": _sha256_hex(compiler_text),
    }


def compile_project_knowledge_recipe(
    *,
    macro_root,
    expected_macro_sha,
    request,
    actor_ref,
    permission_binding_digest,
    decision_date,
    runner=None,
    timeout=10.0,
    code_root=None,
    code_commit=None,
) -> dict:
    """Capture preimages at the pinned commit and compile one closed PRIVATE
    DRAFT capture.  Raises the fixed ``ValueError('project_knowledge_recipe_unavailable')``
    on every refusal; never a private exception, path, or body."""
    _validate_bindings(actor_ref, permission_binding_digest, decision_date)
    mode, _work_ref, key = _validate_request(request)
    if request["source_commit"] != expected_macro_sha:
        raise ValueError(_REJECT)
    session = _open_session(macro_root, expected_macro_sha, runner, timeout)
    code_session = _code_session(session, code_root, code_commit, runner, timeout)
    code = _capture_code(code_session)
    ws_path = "agentos/workstreams/WS-" + key + ".md"
    ws_text = _record_preimage(session, ws_path, _WS_LIMIT)
    if ws_text is None:
        raise ValueError(_REJECT)
    decision_text = None
    decision_path = "agentos/decisions/DEC-PROJECT-COMMUNICATION-PREFERENCE-" + key + ".md"
    media_path = None
    if mode == "file_add":
        media_path, _file_id = _file_target(actor_ref, request, key)
        membership = session.member(media_path)
        if membership is not None:
            # Any existing actual entry at the derived path is already
            # recorded or conflicting; it is never overwritten here.
            raise ValueError(_REJECT)
    else:
        decision_text = _record_preimage(session, decision_path, _DECISION_LIMIT)
        if decision_text is not None:
            revision = request["expected_preference_revision"]
            if revision is not None and revision != _sha256_hex(decision_text):
                raise ValueError(_REJECT)
    with _module_session(PARSER_MODULE_ID, code_session.root / PARSER_PATH, code["parser_text"]) as parser_module:
        # The WS (and any present preference) preimage is qualified through
        # the actual captured parser before the compiler ever sees it.
        record, _body = _parse_record(parser_module, ws_text)
        if _hard(parser_module.check_workstream(record, session.root / ws_path, None)):
            raise ValueError(_REJECT)
        if decision_text is not None:
            decision_record, _body = _parse_record(parser_module, decision_text)
            if _hard(parser_module.check_decision(decision_record, session.root / decision_path)):
                raise ValueError(_REJECT)
        if not _heads_current(session, code_session):
            raise ValueError(_REJECT)
        with _module_session(COMPILER_MODULE_ID, code_session.root / COMPILER_PATH, code["compiler_text"]) as compiler_module:
            recipe = _build_recipe(
                session, compiler_module, mode, request, ws_text, decision_text,
                decision_date, actor_ref, permission_binding_digest,
            )
        _validate_recipe(
            session, parser_module, recipe, mode, request, key, ws_text,
            decision_text, ws_path, decision_path, media_path,
        )
    if not _heads_current(session, code_session):
        raise ValueError(_REJECT)
    return _assemble(
        session,
        recipe,
        {
            "workstream_text": ws_text,
            "decision_text": decision_text,
            "decision_date": decision_date,
        },
        _binding(code_session, code["compiler_sha"], code["parser_sha"]),
    )


def restore_project_knowledge_recipe(
    *,
    macro_root,
    expected_macro_sha,
    request,
    actor_ref,
    permission_binding_digest,
    initial_snapshot,
    source_binding,
    runner=None,
    timeout=10.0,
    code_root=None,
    code_commit=None,
) -> dict:
    """Recompile the exact retained snapshot after qualifying ONLY the two
    fixed code blobs at the same recorded commit.  No current workstream,
    decision, or source-goal read, no rebase and no re-clock: the retained
    bodies and retained date are the preimages, and the code is always the
    actual Git blobs hash-qualified against the recorded binding."""
    if type(initial_snapshot) is not dict or set(initial_snapshot) != set(_SNAPSHOT_KEYS):
        raise ValueError(_REJECT)
    _validate_bindings(actor_ref, permission_binding_digest, initial_snapshot["decision_date"])
    mode, _work_ref, key = _validate_request(request)
    recorded_commit = request["source_commit"]
    try:
        recorded_code = source_binding["compiler"]["commit"]
    except (KeyError, TypeError):
        raise ValueError(_REJECT) from None
    if code_root is None and code_commit is None and recorded_code != recorded_commit:
        raise ValueError(_REJECT)
    expected = _validate_source_binding(
        source_binding, recorded_code,
        {"compiler": COMPILER_PATH, "owner": PARSER_PATH},
    )
    ws_text, decision_text = _validate_snapshot(initial_snapshot, initial_snapshot["decision_date"])
    session = _open_session(macro_root, expected_macro_sha, runner, timeout)
    # The installed collector brackets today's HEAD; code and preimages belong
    # to the exact retained original. No today's record/helper substitution.
    if recorded_commit != expected_macro_sha:
        session.git("merge-base", "--is-ancestor", recorded_commit, expected_macro_sha, limit=128)
    code_session = _code_session(session, code_root, code_commit, runner, timeout)
    session.commit = recorded_commit
    if code_session is not session and recorded_code != code_session.expected_head:
        code_session.git("merge-base", "--is-ancestor", recorded_code, code_session.expected_head, limit=128)
    code_session.commit = recorded_code
    code = _capture_code(code_session)
    if code["compiler_sha"] != expected["compiler"] or code["parser_sha"] != expected["owner"]:
        raise ValueError(_REJECT)
    ws_path = "agentos/workstreams/WS-" + key + ".md"
    decision_path = "agentos/decisions/DEC-PROJECT-COMMUNICATION-PREFERENCE-" + key + ".md"
    with _module_session(PARSER_MODULE_ID, code_session.root / PARSER_PATH, code["parser_text"]) as parser_module:
        if not _heads_current(session, code_session):
            raise ValueError(_REJECT)
        with _module_session(COMPILER_MODULE_ID, code_session.root / COMPILER_PATH, code["compiler_text"]) as compiler_module:
            recipe = _build_recipe(
                session, compiler_module, mode, request, ws_text, decision_text,
                initial_snapshot["decision_date"], actor_ref, permission_binding_digest,
            )
        media_path = None
        if mode == "file_add":
            media_path, _file_id = _file_target(actor_ref, request, key)
        _validate_recipe(
            session, parser_module, recipe, mode, request, key, ws_text,
            decision_text, ws_path, decision_path, media_path,
        )
    if not _heads_current(session, code_session):
        raise ValueError(_REJECT)
    return _assemble(
        session,
        recipe,
        {
            "workstream_text": ws_text,
            "decision_text": decision_text,
            "decision_date": initial_snapshot["decision_date"],
        },
        _binding(code_session, code["compiler_sha"], code["parser_sha"]),
    )
