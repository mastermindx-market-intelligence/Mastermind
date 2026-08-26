import ast
import ctypes
import importlib.util
import io
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "scripts" / "mas112_keychain_verifier_bridge.py"

TOKEN = b"xoxb-" + (b"A" * 40)
SCHEMA = "mastermind.slack_agent_dialogue.metadata_verification.v1"
EXPECTED_PASS = {
    "bot_id": "B0BST4WG996",
    "bot_user_id": "U0BST4WG996",
    "schema": SCHEMA,
    "scopes": ["chat:write", "groups:history"],
    "status": "PASS",
    "team_id": "T0BRD2AQXQV",
}


def _load_helper():
    assert HELPER.exists(), "MAS-112 Keychain verifier bridge is not implemented"
    spec = importlib.util.spec_from_file_location("mas112_keychain_verifier_bridge", HELPER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _receipt_bytes(document: dict[str, object]) -> bytes:
    return (json.dumps(document, sort_keys=True, separators=(",", ":")) + "\n").encode()


def test_helper_has_fixed_coordinates_and_no_alternate_secret_carrier() -> None:
    module = _load_helper()
    source = HELPER.read_text(encoding="utf-8")
    lowered = source.lower()

    assert module._KEYCHAIN_SERVICE == b"mastermind-s0-fixture-slack-bot-token"
    assert module._KEYCHAIN_ACCOUNT == b"mastermind-s0-fixture-bot"
    assert module._EXPECTED_TEAM_ID == "T0BRD2AQXQV"
    assert module._EXPECTED_BOT_USER_ID == "U0BST4WG996"
    assert module._EXPECTED_SCOPES == ("chat:write", "groups:history")

    assert "login.keychain-db" in source
    assert "SecKeychainOpen" in source
    assert "SecKeychainFindGenericPassword" in source
    assert "SecKeychainItemFreeContent" in source

    forbidden_fragments = (
        "argparse",
        "--token",
        "--service",
        "--account",
        "--keychain",
        "os.environ",
        "os.getenv(",
        "tempfile",
        "namedtemporaryfile",
        "mkstemp",
        "write_text(",
        "write_bytes(",
        "security find-generic-password",
        "security add-generic-password",
        "command substitution",
        "shell=true",
        "logging.",
    )
    assert all(fragment not in lowered for fragment in forbidden_fragments)

    tree = ast.parse(source)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name) and node.func.id == "open":
            raise AssertionError("secret helper must not use filesystem open()")
        if isinstance(node.func, ast.Attribute):
            owner = node.func.value
            if isinstance(owner, ast.Name) and owner.id == "os" and node.func.attr in {"system", "popen"}:
                raise AssertionError("secret helper must not use a shell")
            if isinstance(owner, ast.Name) and owner.id == "subprocess" and node.func.attr in {
                "run",
                "call",
                "check_call",
                "check_output",
            }:
                raise AssertionError("secret helper must use the reviewed anonymous Popen stdin pipe")
        for keyword in node.keywords:
            if keyword.arg == "shell" and isinstance(keyword.value, ast.Constant) and keyword.value.value:
                raise AssertionError("shell transport is forbidden")


def test_security_framework_binds_find_to_explicit_login_keychain() -> None:
    module = _load_helper()
    observed: dict[str, object] = {}
    secret_buffer = ctypes.create_string_buffer(TOKEN)

    class FakeFunction:
        def __init__(self, callback):
            self.callback = callback
            self.argtypes = None
            self.restype = None

        def __call__(self, *args):
            return self.callback(*args)

    def open_keychain(path, out_ref):
        observed["path"] = path
        ctypes.cast(out_ref, ctypes.POINTER(ctypes.c_void_p)).contents.value = 0x1111
        return 0

    def find_password(
        keychain_ref,
        service_len,
        service,
        account_len,
        account,
        out_len,
        out_data,
        item_ref,
    ):
        observed["find_keychain"] = keychain_ref.value
        observed["service"] = service[:service_len]
        observed["account"] = account[:account_len]
        ctypes.cast(out_len, ctypes.POINTER(ctypes.c_uint32)).contents.value = len(TOKEN)
        ctypes.cast(out_data, ctypes.POINTER(ctypes.c_void_p)).contents.value = ctypes.cast(
            secret_buffer, ctypes.c_void_p
        ).value
        return 0

    def free_content(_attrs, data):
        observed["freed"] = data.value
        return 0

    def release(ref):
        observed.setdefault("released", []).append(ref.value)

    class Security:
        SecKeychainOpen = FakeFunction(open_keychain)
        SecKeychainFindGenericPassword = FakeFunction(find_password)
        SecKeychainItemFreeContent = FakeFunction(free_content)

    class CoreFoundation:
        CFRelease = FakeFunction(release)

    def loader(path):
        if path.endswith("Security.framework/Security"):
            return Security()
        if path.endswith("CoreFoundation.framework/CoreFoundation"):
            return CoreFoundation()
        raise AssertionError(path)

    api = module._SecurityFramework(loader=loader, home_lookup=lambda: "/Users/chairman")
    secret = api.read_secret()
    try:
        assert observed["path"] == b"/Users/chairman/Library/Keychains/login.keychain-db"
        assert observed["find_keychain"] == 0x1111
        assert observed["service"] == b"mastermind-s0-fixture-slack-bot-token"
        assert observed["account"] == b"mastermind-s0-fixture-bot"
        assert secret == TOKEN
        assert observed["freed"] == ctypes.cast(secret_buffer, ctypes.c_void_p).value
        assert 0x1111 in observed["released"]
    finally:
        secret[:] = b"\0" * len(secret)


def test_caller_cannot_select_keychain_service_or_account() -> None:
    module = _load_helper()
    out = io.StringIO()

    def forbidden_api_factory():
        raise AssertionError("Keychain must not be touched for refused argv")

    result = module.run(
        ["--service", "mastermind-s0-fixture-slack-bot-token", "--keychain", "System"],
        stdout=out,
        api_factory=forbidden_api_factory,
        verifier_runner=lambda _secret: (_ for _ in ()).throw(AssertionError("child must not run")),
    )

    assert result == 2
    assert json.loads(out.getvalue()) == {
        "error": "METADATA_ARGUMENTS_REFUSED",
        "schema": SCHEMA,
        "status": "ERROR",
    }


def test_malformed_secret_never_reaches_verifier_and_is_zeroed() -> None:
    module = _load_helper()
    malformed = bytearray(b"xoxp-" + (b"B" * 40))
    out = io.StringIO()
    called = False

    class FakeApi:
        def read_secret(self):
            return malformed

    def verifier_runner(_secret):
        nonlocal called
        called = True
        raise AssertionError("malformed secret reached verifier")

    result = module.run([], stdout=out, api_factory=FakeApi, verifier_runner=verifier_runner)

    assert result == 2
    assert not called
    assert malformed and set(malformed) == {0}
    assert json.loads(out.getvalue()) == {
        "error": "METADATA_INPUT_REFUSED",
        "schema": SCHEMA,
        "status": "ERROR",
    }


def test_verifier_subprocess_gets_secret_only_over_anonymous_stdin_pipe() -> None:
    module = _load_helper()
    captured: dict[str, object] = {}

    class FakePopen:
        def __init__(self, argv, **kwargs):
            captured["argv"] = list(argv)
            captured["kwargs"] = dict(kwargs)
            self.returncode = 0

        def communicate(self, input=None, timeout=None):
            captured["input"] = bytes(input)
            captured["timeout"] = timeout
            return _receipt_bytes(EXPECTED_PASS), b""

        def kill(self):
            captured["killed"] = True

    result = module._run_verifier(bytearray(TOKEN), popen_factory=FakePopen)

    assert result == (0, _receipt_bytes(EXPECTED_PASS), b"")
    assert captured["input"] == TOKEN
    argv = captured["argv"]
    assert isinstance(argv, list)
    assert TOKEN.decode() not in "\n".join(str(value) for value in argv)
    assert argv[-8:] == [
        "--expected-team-id",
        "T0BRD2AQXQV",
        "--expected-bot-user-id",
        "U0BST4WG996",
        "--expected-scope",
        "chat:write",
        "--expected-scope",
        "groups:history",
    ]
    kwargs = captured["kwargs"]
    assert kwargs["stdin"] is subprocess.PIPE
    assert kwargs["stdout"] is subprocess.PIPE
    assert kwargs["stderr"] is subprocess.PIPE
    assert kwargs["env"] == {}
    assert kwargs["close_fds"] is True
    assert "shell" not in kwargs or kwargs["shell"] is False
    assert TOKEN.decode() not in json.dumps(kwargs, default=str)


def test_valid_pass_receipt_is_allowlisted_and_secret_buffer_is_zeroed() -> None:
    module = _load_helper()
    secret = bytearray(TOKEN)
    out = io.StringIO()

    class FakeApi:
        def read_secret(self):
            return secret

    def verifier_runner(received):
        assert received is secret
        return 0, _receipt_bytes(EXPECTED_PASS), b""

    result = module.run([], stdout=out, api_factory=FakeApi, verifier_runner=verifier_runner)

    assert result == 0
    assert json.loads(out.getvalue()) == EXPECTED_PASS
    assert secret and set(secret) == {0}
    assert TOKEN.decode() not in out.getvalue()


def test_verifier_error_receipt_is_relayed_without_child_error_text() -> None:
    module = _load_helper()
    out = io.StringIO()
    error_receipt = {
        "error": "SLACK_AUTH_REFUSED",
        "schema": SCHEMA,
        "status": "ERROR",
    }

    class FakeApi:
        def read_secret(self):
            return bytearray(TOKEN)

    result = module.run(
        [],
        stdout=out,
        api_factory=FakeApi,
        verifier_runner=lambda _secret: (2, _receipt_bytes(error_receipt), b""),
    )

    assert result == 2
    assert json.loads(out.getvalue()) == error_receipt


def test_synthetic_credential_shaped_child_output_never_reaches_visible_receipt() -> None:
    module = _load_helper()
    canary = TOKEN.decode()
    out = io.StringIO()
    leaked = dict(EXPECTED_PASS)
    leaked["debug"] = canary

    class FakeApi:
        def read_secret(self):
            return bytearray(TOKEN)

    result = module.run(
        [],
        stdout=out,
        api_factory=FakeApi,
        verifier_runner=lambda _secret: (0, _receipt_bytes(leaked), canary.encode()),
    )

    assert result == 2
    assert canary not in out.getvalue()
    assert json.loads(out.getvalue()) == {
        "error": "SECRET_SURFACE_REFUSED",
        "schema": SCHEMA,
        "status": "ERROR",
    }
