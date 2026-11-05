from __future__ import annotations

import ctypes
import errno
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
from control_plane import fs_security
from control_plane.fs_security import FilesystemSecurityError
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

def _fake_entry_pointer(value: object) -> object:
    return value


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


class TestCredentialOpenDiscriminators(unittest.TestCase):
    @pytest.mark.timeout(5)
    def test_regular_to_fifo_swap_refuses_before_read_without_blocking(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            config, _ = _installed_config(root)
            credential_path = (
                Path(str(config["provider_home"])) / PROVIDER_CREDENTIAL_FILENAME
            )
            regular = root / "regular"
            regular.write_bytes(credential_path.read_bytes())
            real_open = credential.os.open
            swap_occurred = False

            def swap_then_open(*args: object, **kwargs: object) -> int:
                nonlocal swap_occurred
                if Path(args[0]) != credential_path:
                    return real_open(*args, **kwargs)
                credential_path.unlink()
                regular.replace(credential_path)
                credential_path.unlink()
                os.mkfifo(credential_path, 0o600)
                os.chown(credential_path, os.getuid(), os.getgid())
                swap_occurred = True
                return real_open(*args, **kwargs)

            def refuse_wait(*_args: object, **_kwargs: object) -> int:
                raise AssertionError("non-regular credential open must not read or block")

            with (
                mock.patch.object(credential.os, "open", side_effect=swap_then_open),
                mock.patch.object(credential.os, "read", side_effect=refuse_wait),
                mock.patch.object(credential, "_has_macos_acl", return_value=False),
            ):
                with pytest.raises(
                    credential.SubscriptionCredentialError,
                    match="provider credential metadata is unsafe",
                ):
                    credential.verify_provider_credential(config)
            assert swap_occurred

    @pytest.mark.timeout(5)
    def test_credential_opens_require_nonblocking_nofollow_cloexec(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            config, path = _installed_config(Path(raw))
            expected_flags = (
                os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK
            )
            opens: list[tuple[object, int]] = []
            real_credential_open = credential.os.open
            real_realm_open = codex_provider_realm.os.open

            def credential_open(target: object, flags: int, *args: object) -> int:
                opens.append((target, int(flags)))
                return real_credential_open(target, flags, *args)

            def realm_open(target: object, flags: int, *args: object) -> int:
                opens.append((target, int(flags)))
                return real_realm_open(target, flags, *args)

            with (
                mock.patch.object(credential.os, "open", side_effect=credential_open),
                mock.patch.object(codex_provider_realm.os, "open", side_effect=realm_open),
            ):
                assert credential.verify_provider_credential(config) == path
                assert (
                    load_private_provider_credential(
                        path.parent,
                        expected_uid=os.getuid(),
                        expected_gid=os.getgid(),
                    )
                    == "opaque-subscription-key"
                )

            credential_opens = [
                flags
                for target, flags in opens
                if Path(str(target)).name == PROVIDER_CREDENTIAL_FILENAME
            ]
            assert credential_opens == [expected_flags, expected_flags]


@pytest.mark.skipif(sys.platform != "darwin", reason="Darwin credential metadata boundary")
class TestDarwinACLBoundary:
    def test_nonregular_credentials_refuse_before_read_without_blocking(
        self,
        tmp_path: Path,
    ) -> None:
        config = _config(tmp_path)
        home = Path(str(config["provider_home"]))
        fifo = home / PROVIDER_CREDENTIAL_FILENAME
        os.mkfifo(fifo, 0o600)
        os.chown(fifo, os.getuid(), os.getgid())

        with mock.patch.object(codex_provider_realm.os, "read") as realm_read:
            with pytest.raises(
                ProviderRealmError,
                match="provider credential is unavailable",
            ):
                load_private_provider_credential(
                    home,
                    expected_uid=os.getuid(),
                    expected_gid=os.getgid(),
                )
        realm_read.assert_not_called()

        with mock.patch.object(credential.os, "read") as enrollment_read:
            with pytest.raises(
                credential.SubscriptionCredentialError,
                match="provider credential metadata is unsafe",
            ):
                credential.install_provider_credential(
                    config,
                    ALIBABA_TOKEN_PLAN,
                    credential=b"replacement-provider-key",
                    replace_existing=True,
                )
        enrollment_read.assert_not_called()

        fifo.unlink()
        directory = home / PROVIDER_CREDENTIAL_FILENAME
        directory.mkdir(mode=0o600)
        os.chown(directory, os.getuid(), os.getgid())
        with pytest.raises(
            ProviderRealmError,
            match="provider credential is unavailable",
        ):
            load_private_provider_credential(
                home,
                expected_uid=os.getuid(),
                expected_gid=os.getgid(),
            )

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

    def test_home_acl_is_refused_at_read_while_credential_file_is_clean(
        self,
        tmp_path: Path,
    ) -> None:
        config, _ = _installed_config(tmp_path)
        home = Path(str(config["provider_home"]))
        _add_read_acl(home)

        with pytest.raises(ProviderRealmError, match="provider credential is unavailable"):
            load_private_provider_credential(
                home,
                expected_uid=os.getuid(),
                expected_gid=os.getgid(),
            )

    def test_provider_home_open_failure_is_typed_at_each_boundary(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        config, _ = _installed_config(tmp_path)

        def refuse_open(*_args: object, **_kwargs: object) -> int:
            raise OSError(errno.EACCES, "provider-home traversal refused")

        monkeypatch.setattr(credential.os, "open", refuse_open)
        with pytest.raises(
            credential.SubscriptionCredentialError,
            match="provider home is unavailable",
        ):
            credential.install_provider_credential(
                config,
                ALIBABA_TOKEN_PLAN,
                credential=b"replacement-provider-key",
                replace_existing=True,
            )
        with pytest.raises(
            credential.SubscriptionCredentialError,
            match="provider home is unavailable",
        ):
            credential.verify_provider_credential(config)

    def test_file_acl_is_refused_at_read_while_provider_home_is_clean(
        self,
        tmp_path: Path,
    ) -> None:
        config, path = _installed_config(tmp_path)
        _add_read_acl(path)

        with pytest.raises(ProviderRealmError, match="provider credential is unavailable"):
            load_private_provider_credential(
                path.parent,
                expected_uid=os.getuid(),
                expected_gid=os.getgid(),
            )

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

    def test_observer_failure_refuses_for_file_and_home_at_each_boundary(
        self,
        tmp_path: Path,
    ) -> None:
        config, path = _installed_config(tmp_path)

        for target in (path.parent, path):
            with mock.patch.object(
                fs_security,
                "_acl_get_fd",
                return_value=None,
            ) as observer, mock.patch.object(
                ctypes,
                "get_errno",
                return_value=errno.EACCES,
            ):
                with pytest.raises(FilesystemSecurityError, match="errno=13"):
                    fs_security.has_macos_acl(target)

                with pytest.raises(
                    credential.SubscriptionCredentialError,
                    match="credential filesystem metadata unavailable",
                ):
                    credential.install_provider_credential(
                        config,
                        ALIBABA_TOKEN_PLAN,
                        credential=b"replacement-provider-key",
                        replace_existing=True,
                    )
                with pytest.raises(
                    credential.SubscriptionCredentialError,
                    match="credential filesystem metadata unavailable",
                ):
                    credential.verify_provider_credential(config)
                with pytest.raises(
                    ProviderRealmError,
                    match="provider credential is unavailable",
                ):
                    load_private_provider_credential(
                        path.parent,
                        expected_uid=os.getuid(),
                        expected_gid=os.getgid(),
            )
            assert observer.call_count >= 1

    def test_acl_observer_native_semantics_and_error_classification(
        self,
        tmp_path: Path,
    ) -> None:
        path = tmp_path / "observer-fixture"
        path.write_text("fixture", encoding="utf-8")
        path.chmod(0o600)

        assert fs_security.has_macos_acl(path) is False
        _add_read_acl(path)
        assert fs_security.has_macos_acl(path) is True
        subprocess.run(["/bin/chmod", "-N", os.fspath(path)], check=True)
        assert fs_security.has_macos_acl(path) is False

        missing = tmp_path / "absent"
        with pytest.raises(FilesystemSecurityError):
            fs_security.has_macos_acl(missing)

        with mock.patch.object(fs_security, "_acl_get_fd", return_value=None), mock.patch.object(
            ctypes,
            "get_errno",
            return_value=errno.EACCES,
        ):
            with pytest.raises(FilesystemSecurityError, match="errno=13"):
                fs_security.has_macos_acl(path)

        with (
            mock.patch.object(fs_security, "_acl_get_fd", return_value=None),
            mock.patch.object(ctypes, "get_errno", return_value=errno.ENOENT),
        ):
            assert fs_security.has_macos_acl(path) is False

        with (
            mock.patch.object(fs_security, "_acl_get_fd", return_value=1001),
            mock.patch.object(fs_security, "_acl_get_entry", return_value=0),
            mock.patch.object(
                ctypes,
                "byref",
                side_effect=_fake_entry_pointer,
            ),
            mock.patch.object(fs_security, "_acl_free", return_value=0),
        ):
            with pytest.raises(
                FilesystemSecurityError,
                match="macOS ACL object has no enumerable entries",
            ):
                fs_security.has_macos_acl(path)

        _add_read_acl(path)
        with mock.patch.object(
            fs_security,
            "_acl_get_entry",
            return_value=1,
        ) as observer, mock.patch.object(fs_security, "_acl_free", return_value=0):
            with pytest.raises(FilesystemSecurityError, match="enumeration failed"):
                fs_security.has_macos_acl(path)
        observer.assert_called_once()

    def test_acl_observer_raises_for_native_enumeration_eio(self, tmp_path: Path) -> None:
        path = tmp_path / "observer-fixture"
        path.write_text("fixture", encoding="utf-8")

        with (
            mock.patch.object(fs_security, "_acl_get_fd", return_value=1001),
            mock.patch.object(
                fs_security,
                "_acl_get_entry",
                return_value=-1,
            ) as enumeration_observer,
            mock.patch.object(fs_security, "_acl_free", return_value=0),
            mock.patch.object(
                ctypes,
                "get_errno",
                side_effect=[errno.EIO, errno.EIO, errno.EACCES],
            ),
        ):
            with pytest.raises(
                FilesystemSecurityError,
                match="macOS ACL enumeration failed: errno=5",
            ):
                fs_security.has_macos_acl(path)
        enumeration_observer.assert_called_once()

    def test_acl_observer_raises_when_entry_pointer_is_absent(
        self,
        tmp_path: Path,
    ) -> None:
        path = tmp_path / "observer-fixture"
        path.write_text("fixture", encoding="utf-8")

        with (
            mock.patch.object(fs_security, "_acl_get_fd", return_value=1001),
            mock.patch.object(fs_security, "_acl_get_entry", return_value=0),
            mock.patch.object(ctypes, "byref", side_effect=_fake_entry_pointer),
            mock.patch.object(fs_security, "_acl_free", return_value=0),
        ):
            with pytest.raises(
                FilesystemSecurityError,
                match="macOS ACL object has no enumerable entries",
            ):
                fs_security.has_macos_acl(path)

    def test_acl_enumeration_error_survives_cleanup_errno_clobber(
        self,
        tmp_path: Path,
    ) -> None:
        path = tmp_path / "observer-fixture"
        path.write_text("fixture", encoding="utf-8")

        def clobbering_free(*_args: object, **_kwargs: object) -> int:
            ctypes.set_errno(errno.EACCES)
            return 0

        with (
            mock.patch.object(fs_security, "_acl_get_fd", return_value=1001),
            mock.patch.object(fs_security, "_acl_get_entry", return_value=-1),
            mock.patch.object(fs_security, "_acl_free", side_effect=clobbering_free),
        ):
            ctypes.set_errno(errno.EIO)
            with pytest.raises(
                FilesystemSecurityError,
                match="macOS ACL enumeration failed: errno=5",
            ):
                fs_security.has_macos_acl(path)

    def test_acl_observer_closes_its_descriptor_when_observation_is_refused(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        path = tmp_path / "observer-fixture"
        path.write_text("fixture", encoding="utf-8")
        real_open = fs_security.os.open
        real_close = fs_security.os.close
        opened: list[int] = []

        def tracked_open(*args: object, **kwargs: object) -> int:
            descriptor = real_open(*args, **kwargs)
            opened.append(descriptor)
            return descriptor

        def tracked_close(descriptor: int) -> None:
            opened.remove(descriptor)
            real_close(descriptor)

        def refuse_enumeration(*_args: object, **_kwargs: object) -> int:
            raise FilesystemSecurityError("observer fixture refused")

        monkeypatch.setattr(fs_security.os, "open", tracked_open)
        monkeypatch.setattr(fs_security.os, "close", tracked_close)
        monkeypatch.setattr(fs_security, "_acl_get_fd", refuse_enumeration)

        descriptors_before = set(os.listdir("/dev/fd"))

        with pytest.raises(FilesystemSecurityError, match="observer fixture refused"):
            fs_security.has_macos_acl(path)
        assert opened == []
        assert set(os.listdir("/dev/fd")) == descriptors_before

    @pytest.mark.skipif(os.geteuid() == 0, reason="non-root traversal denial")
    def test_acl_observer_fails_closed_for_non_traversable_parent(
        self,
        tmp_path: Path,
    ) -> None:
        parent = tmp_path / "untraversable-parent"
        parent.mkdir(mode=0o700)
        path = parent / "observer-fixture"
        path.write_text("fixture", encoding="utf-8")
        path.chmod(0o600)
        os.chmod(parent, 0)
        try:
            with pytest.raises(
                FilesystemSecurityError,
                match=f"errno={errno.EACCES}",
            ):
                fs_security.has_macos_acl(path)
        finally:
            os.chmod(parent, 0o700)

    def test_acl_observer_fails_closed_when_target_disappears_before_open(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        path = tmp_path / "observer-fixture"
        path.write_text("fixture", encoding="utf-8")

        def unlink_then_open(*args: object, **kwargs: object) -> int:
            path.unlink()
            raise OSError(errno.ENOENT, "target removed between lstat and open")

        monkeypatch.setattr(fs_security.os, "open", unlink_then_open)
        with pytest.raises(FilesystemSecurityError, match="macOS ACL open failed"):
            fs_security.has_macos_acl(path)

    def test_acl_observer_fails_closed_when_target_identity_changes_before_open(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        path = tmp_path / "observer-fixture"
        path.write_text("before", encoding="utf-8")
        replacement = tmp_path / "observer-replacement"
        replacement.write_text("after", encoding="utf-8")
        real_open = fs_security.os.open

        def replace_then_open(*args: object, **kwargs: object) -> int:
            os.replace(path, tmp_path / "observer-old")
            os.replace(replacement, path)
            return real_open(*args, **kwargs)

        monkeypatch.setattr(fs_security.os, "open", replace_then_open)
        with pytest.raises(FilesystemSecurityError, match="identity changed"):
            fs_security.has_macos_acl(path)

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
