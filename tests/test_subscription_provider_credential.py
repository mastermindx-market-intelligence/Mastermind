from __future__ import annotations

import io
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import pytest

from control_plane.codex_provider_realm import (
    ALIBABA_TOKEN_PLAN,
    PROVIDER_CREDENTIAL_FILENAME,
)
from control_plane import codex_provider_realm
from control_plane.codex_provider_realm import (
    ProviderRealmError,
    load_private_provider_credential,
)
from control_plane.executive_ambient_process import (
    AmbientClassification,
    AmbientProcessIdentity,
)
from ops.executive_os import subscription_provider_credential as credential


class _Stream(io.BytesIO):
    def __init__(self, value: bytes, *, tty: bool = False) -> None:
        super().__init__(value)
        self._tty = tty

    def isatty(self) -> bool:
        return self._tty


class _Classifier:
    def __init__(self, classification: AmbientClassification) -> None:
        self.classification = classification

    def classify(self, *, worker_uid: int) -> AmbientClassification:
        return self.classification


def _ambient(pid: int, uid: int) -> AmbientProcessIdentity:
    return AmbientProcessIdentity(
        pid=pid,
        uid=uid,
        launchd_domain=f"user/{uid}",
        launchd_label="com.apple.distnoted.xpc.agent",
        launchd_reported_pid=pid,
        plist_path="/System/Library/LaunchAgents/com.apple.distnoted.xpc.agent.plist",
        program_path="/usr/sbin/distnoted",
        executable_path="/usr/sbin/distnoted",
        executable_device=1,
        executable_inode=2,
        codesign_identifier="com.apple.distnoted.xpc.agent",
        codesign_verified=True,
    )


def _config(root: Path) -> dict[str, object]:
    home = root / "provider-home"
    home.mkdir(mode=0o700)
    os.chown(home, os.getuid(), os.getgid())
    home.chmod(0o700)
    return {
        "provider_home": str(home),
        "worker_uid": os.getuid(),
        "worker_gid": os.getgid(),
    }


def _installed_config(root: Path) -> tuple[dict[str, object], Path]:
    config = _config(root)
    path = Path(str(config["provider_home"])) / PROVIDER_CREDENTIAL_FILENAME
    path.write_bytes(b"opaque-subscription-key")
    os.chown(path, os.getuid(), os.getgid())
    path.chmod(0o600)
    return config, path


def _add_read_acl(path: Path) -> None:
    subprocess.run(
        ["/bin/chmod", "+a", "everyone allow read", os.fspath(path)],
        check=True,
    )


class SubscriptionProviderCredentialTest(unittest.TestCase):
    def test_stdin_accepts_one_terminal_newline_only(self) -> None:
        self.assertEqual(
            credential._read_stdin_credential(
                ALIBABA_TOKEN_PLAN,
                stream=_Stream(b"opaque-subscription-key\n"),
            ),
            b"opaque-subscription-key",
        )
        with self.assertRaises(credential.SubscriptionCredentialError):
            credential._read_stdin_credential(
                ALIBABA_TOKEN_PLAN,
                stream=_Stream(b"opaque\nsubscription-key\n"),
            )
        with self.assertRaises(credential.SubscriptionCredentialError):
            credential._read_stdin_credential(
                ALIBABA_TOKEN_PLAN,
                stream=_Stream(b" opaque-subscription-key\n"),
            )
        with self.assertRaises(credential.SubscriptionCredentialError):
            credential._read_stdin_credential(
                ALIBABA_TOKEN_PLAN,
                stream=_Stream(b"opaque-subscription-key", tty=True),
            )

    def test_install_and_verify_are_atomic_and_metadata_only(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            config = _config(Path(raw))
            path = credential.install_provider_credential(
                config,
                ALIBABA_TOKEN_PLAN,
                credential=b"first-provider-key",
                replace_existing=False,
            )
            self.assertEqual(path.name, PROVIDER_CREDENTIAL_FILENAME)
            self.assertEqual(path.read_bytes(), b"first-provider-key")
            self.assertEqual(credential.verify_provider_credential(config), path)
            with self.assertRaisesRegex(
                credential.SubscriptionCredentialError,
                "explicit replacement",
            ):
                credential.install_provider_credential(
                    config,
                    ALIBABA_TOKEN_PLAN,
                    credential=b"second-provider-key",
                    replace_existing=False,
                )
            credential.install_provider_credential(
                config,
                ALIBABA_TOKEN_PLAN,
                credential=b"second-provider-key",
                replace_existing=True,
            )
            self.assertEqual(path.read_bytes(), b"second-provider-key")
            self.assertFalse(
                any(
                    child.name.startswith(f".{PROVIDER_CREDENTIAL_FILENAME}.new.")
                    for child in path.parent.iterdir()
                )
            )

    def test_post_replace_durability_failure_is_effect_unknown(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            config = _config(Path(raw))
            with mock.patch.object(
                credential, "_fsync_directory", side_effect=OSError("fixture")
            ):
                with self.assertRaises(
                    credential.SubscriptionCredentialEffectUnknown
                ):
                    credential.install_provider_credential(
                        config,
                        ALIBABA_TOKEN_PLAN,
                        credential=b"provider-key",
                        replace_existing=False,
                    )
            path = Path(str(config["provider_home"])) / PROVIDER_CREDENTIAL_FILENAME
            self.assertTrue(path.exists())
            self.assertEqual(credential.verify_provider_credential(config), path)

    def test_replace_requires_existing_reviewed_target(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            config = _config(Path(raw))
            with self.assertRaisesRegex(
                credential.SubscriptionCredentialError,
                "replacement target is absent",
            ):
                credential.install_provider_credential(
                    config,
                    ALIBABA_TOKEN_PLAN,
                    credential=b"provider-key",
                    replace_existing=True,
                )

    def test_verify_rejects_unsafe_target_mode_and_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            config = _config(Path(raw))
            path = credential.install_provider_credential(
                config,
                ALIBABA_TOKEN_PLAN,
                credential=b"provider-key",
                replace_existing=False,
            )
            path.chmod(0o644)
            with self.assertRaisesRegex(
                credential.SubscriptionCredentialError,
                "metadata is unsafe",
            ):
                credential.verify_provider_credential(config)

            path.unlink()
            target = path.parent / "elsewhere"
            target.write_bytes(b"provider-key")
            os.chown(target, os.getuid(), os.getgid())
            target.chmod(0o600)
            path.symlink_to(target)
            with self.assertRaises(credential.SubscriptionCredentialError):
                credential.verify_provider_credential(config)

    def test_quiescence_accepts_only_exact_attested_ambient_pid(self) -> None:
        uid = os.getuid()
        ambient = _ambient(123, uid)
        classifier = _Classifier(
            AmbientClassification(status="attested", identities=(ambient,))
        )
        credential._assert_worker_quiescent(
            uid,
            ambient_classifier=classifier,
            process_lister=lambda _uid: (123,),
        )
        with self.assertRaisesRegex(
            credential.SubscriptionCredentialError,
            "not quiescent",
        ):
            credential._assert_worker_quiescent(
                uid,
                ambient_classifier=classifier,
                process_lister=lambda _uid: (123, 456),
            )

    def test_quiescence_fails_closed_when_attribution_fails(self) -> None:
        classifier = _Classifier(AmbientClassification(status="failed_closed"))
        with self.assertRaises(credential.SubscriptionCredentialError):
            credential._assert_worker_quiescent(
                os.getuid(),
                ambient_classifier=classifier,
                process_lister=lambda _uid: (123,),
            )

    def test_no_processes_is_quiescent_without_ambient_probe(self) -> None:
        class _ExplodingClassifier:
            def classify(self, *, worker_uid: int) -> AmbientClassification:
                raise AssertionError("ambient classifier should not run")

        credential._assert_worker_quiescent(
            os.getuid(),
            ambient_classifier=_ExplodingClassifier(),
            process_lister=lambda _uid: (),
        )


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS ACL observer")
class TestDarwinACLBoundary:
    def test_file_acl_is_refused_at_read_verify_and_enroll(self, tmp_path: Path) -> None:
        config, path = _installed_config(tmp_path)
        _add_read_acl(path)

        with pytest.raises(ProviderRealmError, match="provider credential is unavailable"):
            load_private_provider_credential(
                path.parent,
                expected_uid=os.getuid(),
                expected_gid=os.getgid(),
            )
        with pytest.raises(
            credential.SubscriptionCredentialError,
            match="credential metadata is unsafe",
        ):
            credential.verify_provider_credential(config)
        with pytest.raises(
            credential.SubscriptionCredentialError,
            match="credential metadata is unsafe",
        ):
            credential.install_provider_credential(
                config,
                ALIBABA_TOKEN_PLAN,
                credential=b"replacement-provider-key",
                replace_existing=True,
            )

    def test_home_acl_is_refused_at_enroll(self, tmp_path: Path) -> None:
        config, _ = _installed_config(tmp_path)
        home = Path(str(config["provider_home"]))
        _add_read_acl(home)

        with pytest.raises(
            credential.SubscriptionCredentialError,
            match="provider home metadata is unsafe",
        ):
            credential.install_provider_credential(
                config,
                ALIBABA_TOKEN_PLAN,
                credential=b"replacement-provider-key",
                replace_existing=True,
            )
        with pytest.raises(
            credential.SubscriptionCredentialError,
            match="provider home metadata is unsafe",
        ):
            credential.verify_provider_credential(config)

    def test_home_without_acl_allows_read_verify_and_enroll(self, tmp_path: Path) -> None:
        config, path = _installed_config(tmp_path)

        assert (
            load_private_provider_credential(
                path.parent,
                expected_uid=os.getuid(),
                expected_gid=os.getgid(),
            )
            == "opaque-subscription-key"
        )
        assert credential.verify_provider_credential(config) == path
        assert (
            credential.install_provider_credential(
                config,
                ALIBABA_TOKEN_PLAN,
                credential=b"replacement-provider-key",
                replace_existing=True,
            )
            == path
        )

    def test_same_fixtures_without_acl_are_accepted(self, tmp_path: Path) -> None:
        config, path = _installed_config(tmp_path)

        assert (
            load_private_provider_credential(
                path.parent,
                expected_uid=os.getuid(),
                expected_gid=os.getgid(),
            )
            == "opaque-subscription-key"
        )
        assert credential.verify_provider_credential(config) == path
        assert (
            credential.install_provider_credential(
                config,
                ALIBABA_TOKEN_PLAN,
                credential=b"replacement-provider-key",
                replace_existing=True,
            )
            == path
        )

    def test_observer_failure_refuses_for_file_and_home(self, tmp_path: Path) -> None:
        config, path = _installed_config(tmp_path)

        with mock.patch.object(
            credential,
            "_has_macos_acl",
            side_effect=credential.SubscriptionCredentialError("observer fixture"),
        ):
            with pytest.raises(
                credential.SubscriptionCredentialError,
                match="observer fixture",
            ):
                credential._credential_metadata(
                    path,
                    worker_uid=os.getuid(),
                    worker_gid=os.getgid(),
                )
            with pytest.raises(
                credential.SubscriptionCredentialError,
                match="observer fixture",
            ):
                credential.verify_provider_credential(config)
            with pytest.raises(
                credential.SubscriptionCredentialError,
                match="observer fixture",
            ):
                credential.install_provider_credential(
                    config,
                    ALIBABA_TOKEN_PLAN,
                    credential=b"replacement-provider-key",
                    replace_existing=True,
                )

        with mock.patch.object(
            credential,
            "_has_macos_acl",
            side_effect=credential.SubscriptionCredentialError("observer fixture"),
        ):
            with pytest.raises(
                credential.SubscriptionCredentialError,
                match="observer fixture",
            ):
                credential.verify_provider_credential(config)

        with mock.patch.object(
            codex_provider_realm,
            "_has_macos_acl",
            side_effect=ProviderRealmError("observer fixture"),
        ):
            with pytest.raises(ProviderRealmError, match="provider credential is unavailable"):
                load_private_provider_credential(
                    path.parent,
                    expected_uid=os.getuid(),
                    expected_gid=os.getgid(),
                )

    def test_old_stat_probe_does_not_observe_the_acl_fixture(self, tmp_path: Path) -> None:
        _, path = _installed_config(tmp_path)
        _add_read_acl(path)
        completed = subprocess.run(
            ["/usr/bin/stat", "-f", "%Sp", os.fspath(path)],
            check=True,
            stdout=subprocess.PIPE,
            text=True,
        )
        assert not completed.stdout.strip().endswith("+")


if __name__ == "__main__":
    unittest.main()
