"""Bounded role metadata read facade contract tests.

Synthetic disposable fixtures only. The fixture is a real incumbent
installation written by the existing runtime installer into a temporary
directory. No installed-role path, real secret value, provider, model, Slack,
network, service or host provision action is used: nothing here starts a
process, opens a socket, reads a credential or observes a running service.
"""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

REPO = Path(__file__).resolve().parents[3]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from integrations.hermes_harness import metadata  # noqa: E402
from integrations.hermes_harness.cli import _model_selection, _models, _status, main  # noqa: E402
from integrations.hermes_harness.metadata import (  # noqa: E402
    ABSENT,
    CONFIGURATION_OBSERVED,
    QUALIFIED_ROLES,
    REASON_CODES,
    ROLE_METADATA_SCHEMA,
    UNAVAILABLE,
    model_choices,
    model_selection,
    profile_for_role_id,
    role_metadata,
)
from integrations.hermes_runtime.constants import PINNED_UPSTREAM_SHA  # noqa: E402
from integrations.hermes_runtime.profile import load_profile  # noqa: E402

GATEWAY_TOKEN = "local-test-gateway-token"
PROOF = {
    "credentials_read": False,
    "provider_called": False,
    "service_observed": False,
    "served_model_verified": False,
    "credential_enrollment": "UNVERIFIED",
}


def _write_secrets(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"HERMES_GATEWAY_TOKEN={GATEWAY_TOKEN}\n", encoding="utf-8")
    os.chmod(path, 0o600)


class RoleMetadataFixture(unittest.TestCase):
    """A disposable incumbent installation of one role."""

    role = "mmmeta"
    native_provider_id = "zai.glm-5.3"

    def setUp(self) -> None:
        from integrations.hermes_harness.native_byok import render_disarmed_native_byok
        from integrations.hermes_harness.stack import write_composed_profile
        from integrations.hermes_runtime.install import install as runtime_install

        temporary = tempfile.TemporaryDirectory(prefix="hermes-role-metadata-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.state = self.root / "state"
        self.unit_dir = self.root / "config" / "systemd" / "user"
        self.unit_dir.mkdir(parents=True)
        self.secrets = self.root / "secrets.env"
        _write_secrets(self.secrets)
        self.upstream = self.root / "upstream-fixture"
        self.upstream.mkdir()
        (self.upstream / "FIXTURE_UPSTREAM").write_text("fixture\n", encoding="utf-8")
        self.binary = self.root / "hermes-bin"
        self.binary.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        os.chmod(self.binary, 0o755)
        self.profile_path = self.root / f"{self.role}.hermes-profile.yaml"
        write_composed_profile(
            self.role,
            state_dir=self.state,
            secrets_file=self.secrets,
            dest=self.profile_path,
            installed_native_only=True,
            native_provider_id=self.native_provider_id,
        )
        runtime_install(
            profile_path=self.profile_path,
            state_dir=self.state,
            systemd_user_dir=self.unit_dir,
            secrets_file=self.secrets,
            hermes_bin=self.binary,
            upstream_source=self.upstream,
            hermes_config_renderer=render_disarmed_native_byok,
        )
        self.release = self.state / "releases" / "1"
        self.manifest_path = self.state / "install-manifest.json"
        self.receipt_path = self.release / "install-receipt.json"
        self.profile_release_path = self.release / "profile.yaml"
        self.config_path = self.release / "hermes-home" / "profiles" / self.role / "config.yaml"

    def read_json(self, path: Path) -> dict:
        return json.loads(path.read_text(encoding="utf-8"))

    def write_json(self, path: Path, payload: dict) -> None:
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


class RoleMetadataObservationTests(RoleMetadataFixture):
    def test_valid_installation_projects_one_consistent_configuration(self) -> None:
        result = role_metadata(self.state, self.role)
        self.assertEqual(result["schema"], ROLE_METADATA_SCHEMA)
        self.assertEqual(result["role"], self.role)
        self.assertEqual(result["state"], CONFIGURATION_OBSERVED)
        self.assertEqual(result["reason"], "CONFIGURATION_CONSISTENT")
        self.assertEqual(result["proof"], PROOF)
        self.assertEqual(result["source_binding"], "NOT_ATTESTED")
        self.assertEqual(
            result["requested"],
            {
                "provider_id": self.native_provider_id,
                "native_provider": "zai-glm",
                "requested_model": "glm-5.3",
            },
        )
        provenance = result["provenance"]
        self.assertEqual(provenance["upstream_sha"], PINNED_UPSTREAM_SHA)
        self.assertEqual(provenance["release"], "1")
        self.assertEqual(provenance["upstream_attested"], False)
        self.assertRegex(provenance["manifest_sha256"], r"^[0-9a-f]{64}$")
        self.assertRegex(provenance["profile_sha256"], r"^[0-9a-f]{64}$")
        self.assertRegex(provenance["hermes_config_sha256"], r"^[0-9a-f]{64}$")

    def test_projection_never_carries_secret_or_pointer_material(self) -> None:
        result = role_metadata(self.state, self.role)
        text = json.dumps(result, sort_keys=True)
        self.assertNotIn(GATEWAY_TOKEN, text)
        self.assertNotIn(str(self.secrets), text)
        self.assertNotIn(str(self.state), text)
        self.assertNotIn("credential_env", text)
        self.assertNotIn("credential_file_env", text)
        self.assertNotIn("ZAI_API_KEY", text)
        self.assertNotIn("gateway", text)

    def test_absence_is_reported_only_for_a_readable_qualified_root(self) -> None:
        empty = self.root / "empty-state"
        empty.mkdir()
        result = role_metadata(empty, self.role)
        self.assertEqual(result["state"], ABSENT)
        self.assertEqual(result["reason"], "INSTALL_MANIFEST_ABSENT")
        self.assertEqual(result["role"], self.role)
        self.assertEqual(result["proof"], PROOF)
        self.assertNotIn("requested", result)
        self.assertNotIn("provenance", result)

    def test_absence_requires_no_surviving_install_evidence(self) -> None:
        # A root whose manifest is gone but whose release survives is a
        # damaged installation, not an absent role.
        self.manifest_path.unlink()
        result = role_metadata(self.state, self.role)
        self.assertEqual(result["state"], UNAVAILABLE)
        self.assertEqual(result["reason"], "MANIFEST_MISSING")

    def test_a_dangling_current_link_is_not_an_absence(self) -> None:
        dangling = self.root / "dangling-state"
        (dangling / "releases").mkdir(parents=True)
        os.symlink("releases/9", dangling / "current")
        result = role_metadata(dangling, self.role)
        self.assertEqual(result["state"], UNAVAILABLE)
        self.assertEqual(result["reason"], "MANIFEST_MISSING")

    def test_an_empty_releases_directory_is_still_an_absence(self) -> None:
        empty = self.root / "empty-releases"
        (empty / "releases").mkdir(parents=True)
        result = role_metadata(empty, self.role)
        self.assertEqual(result["state"], ABSENT)
        self.assertEqual(result["reason"], "INSTALL_MANIFEST_ABSENT")

    def test_missing_root_is_unavailable_and_never_absence(self) -> None:
        result = role_metadata(self.root / "no-such-state", self.role)
        self.assertEqual(result["state"], UNAVAILABLE)
        self.assertEqual(result["reason"], "STATE_ROOT_MISSING")
        self.assertNotIn("requested", result)

    def test_unreadable_root_is_unavailable_and_never_absence(self) -> None:
        if os.geteuid() == 0:
            self.skipTest("root bypasses directory permissions")
        closed = self.root / "closed-state"
        closed.mkdir()
        os.chmod(closed, 0o000)
        self.addCleanup(os.chmod, closed, 0o700)
        result = role_metadata(closed, self.role)
        self.assertEqual(result["state"], UNAVAILABLE)
        self.assertEqual(result["reason"], "STATE_ROOT_UNREADABLE")

    def test_state_root_that_is_not_a_directory_is_unavailable(self) -> None:
        plain = self.root / "plain-file"
        plain.write_text("not a state root\n", encoding="utf-8")
        result = role_metadata(plain, self.role)
        self.assertEqual(result["state"], UNAVAILABLE)
        self.assertEqual(result["reason"], "STATE_ROOT_NOT_DIRECTORY")

    def test_symlinked_state_root_is_refused(self) -> None:
        link = self.root / "linked-state"
        os.symlink(self.state, link)
        result = role_metadata(link, self.role)
        self.assertEqual(result["state"], UNAVAILABLE)
        self.assertEqual(result["reason"], "STATE_ROOT_SYMLINK_REFUSED")

    def test_unqualified_role_is_a_typed_unavailable_projection(self) -> None:
        result = role_metadata(self.state, "vision")
        self.assertEqual(result["state"], UNAVAILABLE)
        self.assertEqual(result["reason"], "ROLE_UNQUALIFIED")
        self.assertEqual(result["role"], "")
        self.assertNotIn("requested", result)

    def test_every_reason_is_a_bounded_fixed_code(self) -> None:
        empty = self.root / "empty-state"
        empty.mkdir()
        seen = {
            role_metadata(self.state, self.role)["reason"],
            role_metadata(empty, self.role)["reason"],
            role_metadata(self.root / "no-such-state", self.role)["reason"],
            role_metadata(self.state, "vision")["reason"],
        }
        self.assertTrue(seen <= REASON_CODES)
        self.assertNotIn("", seen)


class SecretaryRoleMetadataTests(RoleMetadataFixture):
    role = "mmsecretary"
    native_provider_id = "byteplus-modelark.glm-5.3-flash"

    def test_secretary_role_projects_its_own_catalog_selection(self) -> None:
        result = role_metadata(self.state, "mmsecretary")
        self.assertEqual(result["state"], CONFIGURATION_OBSERVED)
        self.assertEqual(result["role"], "mmsecretary")
        self.assertEqual(result["requested"], {
            "provider_id": "byteplus-modelark.glm-5.3-flash",
            "native_provider": "byteplus-modelark",
            "requested_model": "glm-5-3-flash-260828",
        })
        self.assertEqual(result["provenance"]["upstream_sha"], PINNED_UPSTREAM_SHA)

    def test_secretary_state_does_not_report_the_meta_role(self) -> None:
        result = role_metadata(self.state, "mmmeta")
        self.assertEqual(result["state"], UNAVAILABLE)
        self.assertEqual(result["reason"], "MANIFEST_ROLE_MISMATCH")


class RoleMetadataRefusalTests(RoleMetadataFixture):
    def test_wrong_role_is_refused_by_the_service_agreement(self) -> None:
        result = role_metadata(self.state, "mmsecretary")
        self.assertEqual(result["state"], UNAVAILABLE)
        self.assertEqual(result["reason"], "MANIFEST_ROLE_MISMATCH")

    def test_receipt_role_swap_is_refused(self) -> None:
        receipt = self.read_json(self.receipt_path)
        receipt["role"] = "mmsecretary"
        self.write_json(self.receipt_path, receipt)
        result = role_metadata(self.state, self.role)
        self.assertEqual(result["state"], UNAVAILABLE)
        self.assertEqual(result["reason"], "RECEIPT_INCONSISTENT")

    def test_receipt_upstream_sha_disagreement_is_refused(self) -> None:
        receipt = self.read_json(self.receipt_path)
        receipt["sha"] = "0" * 40
        self.write_json(self.receipt_path, receipt)
        result = role_metadata(self.state, self.role)
        self.assertEqual(result["state"], UNAVAILABLE)
        self.assertEqual(result["reason"], "RECEIPT_INCONSISTENT")

    def test_manifest_state_dir_disagreement_is_refused(self) -> None:
        manifest = self.read_json(self.manifest_path)
        manifest["state_dir"] = str(self.root / "elsewhere")
        self.write_json(self.manifest_path, manifest)
        result = role_metadata(self.state, self.role)
        self.assertEqual(result["state"], UNAVAILABLE)
        self.assertEqual(result["reason"], "MANIFEST_INCONSISTENT")

    def test_manifest_without_ownership_is_refused(self) -> None:
        manifest = self.read_json(self.manifest_path)
        manifest["owns_state_dir"] = False
        self.write_json(self.manifest_path, manifest)
        result = role_metadata(self.state, self.role)
        self.assertEqual(result["state"], UNAVAILABLE)
        self.assertEqual(result["reason"], "MANIFEST_INCONSISTENT")

    def test_missing_profile_is_unavailable(self) -> None:
        self.profile_release_path.unlink()
        result = role_metadata(self.state, self.role)
        self.assertEqual(result["state"], UNAVAILABLE)
        self.assertEqual(result["reason"], "PROFILE_MISSING")

    def test_profile_digest_disagreement_is_refused(self) -> None:
        self.profile_release_path.write_text(
            self.profile_release_path.read_text(encoding="utf-8") + "# drift\n",
            encoding="utf-8",
        )
        result = role_metadata(self.state, self.role)
        self.assertEqual(result["state"], UNAVAILABLE)
        self.assertEqual(result["reason"], "PROFILE_DIGEST_MISMATCH")

    def test_config_digest_disagreement_is_refused(self) -> None:
        self.config_path.write_text(
            self.config_path.read_text(encoding="utf-8") + "# drift\n",
            encoding="utf-8",
        )
        result = role_metadata(self.state, self.role)
        self.assertEqual(result["state"], UNAVAILABLE)
        self.assertEqual(result["reason"], "CONFIG_DIGEST_MISMATCH")

    def test_missing_config_is_unavailable(self) -> None:
        self.config_path.unlink()
        result = role_metadata(self.state, self.role)
        self.assertEqual(result["state"], UNAVAILABLE)
        self.assertEqual(result["reason"], "CONFIG_MISSING")

    def test_malformed_manifest_is_unavailable(self) -> None:
        self.manifest_path.write_text("{not json", encoding="utf-8")
        result = role_metadata(self.state, self.role)
        self.assertEqual(result["state"], UNAVAILABLE)
        self.assertEqual(result["reason"], "MANIFEST_MALFORMED")

    def test_duplicate_manifest_key_is_unavailable(self) -> None:
        self.manifest_path.write_text(
            '{"schema": "a", "schema": "b", "owns_state_dir": true}\n', encoding="utf-8",
        )
        result = role_metadata(self.state, self.role)
        self.assertEqual(result["state"], UNAVAILABLE)
        self.assertEqual(result["reason"], "MANIFEST_MALFORMED")

    def test_oversized_manifest_is_unavailable(self) -> None:
        manifest = self.read_json(self.manifest_path)
        manifest["padding"] = "x" * (64 * 1024)
        self.write_json(self.manifest_path, manifest)
        result = role_metadata(self.state, self.role)
        self.assertEqual(result["state"], UNAVAILABLE)
        self.assertEqual(result["reason"], "METADATA_TOO_LARGE")

    def test_symlinked_manifest_is_not_an_absence(self) -> None:
        decoy = self.root / "decoy-manifest.json"
        decoy.write_text("{}\n", encoding="utf-8")
        self.manifest_path.unlink()
        os.symlink(decoy, self.manifest_path)
        result = role_metadata(self.state, self.role)
        self.assertEqual(result["state"], UNAVAILABLE)
        self.assertEqual(result["reason"], "METADATA_NOT_REGULAR_FILE")

    def test_current_link_escape_is_refused(self) -> None:
        for target in ("../../etc", "/etc", "releases/1/../../releases/1", "current"):
            with self.subTest(target=target):
                link = self.state / "current"
                link.unlink()
                os.symlink(target, link)
                result = role_metadata(self.state, self.role)
                self.assertEqual(result["state"], UNAVAILABLE)
                self.assertEqual(result["reason"], "CURRENT_LINK_INVALID")

    def test_current_link_that_is_not_a_symlink_is_refused(self) -> None:
        link = self.state / "current"
        link.unlink()
        link.mkdir()
        result = role_metadata(self.state, self.role)
        self.assertEqual(result["state"], UNAVAILABLE)
        self.assertEqual(result["reason"], "CURRENT_LINK_INVALID")

    def test_missing_current_link_is_refused(self) -> None:
        (self.state / "current").unlink()
        result = role_metadata(self.state, self.role)
        self.assertEqual(result["state"], UNAVAILABLE)
        self.assertEqual(result["reason"], "CURRENT_LINK_INVALID")

    def test_release_disagreement_is_refused(self) -> None:
        manifest = self.read_json(self.manifest_path)
        manifest["current_release"] = "2"
        self.write_json(self.manifest_path, manifest)
        result = role_metadata(self.state, self.role)
        self.assertEqual(result["state"], UNAVAILABLE)
        self.assertEqual(result["reason"], "RELEASE_MISMATCH")

    def test_missing_release_directory_is_refused(self) -> None:
        shutil.rmtree(self.release)
        result = role_metadata(self.state, self.role)
        self.assertEqual(result["state"], UNAVAILABLE)
        self.assertEqual(result["reason"], "RELEASE_UNAVAILABLE")

    def test_symlinked_intermediate_config_directory_is_refused(self) -> None:
        hermes_home = self.release / "hermes-home"
        outside = self.root / "outside-home"
        shutil.copytree(hermes_home, outside)
        shutil.rmtree(hermes_home)
        os.symlink(outside, hermes_home)
        result = role_metadata(self.state, self.role)
        self.assertEqual(result["state"], UNAVAILABLE)
        self.assertEqual(result["reason"], "CONFIG_PATH_INVALID")

    def test_a_fifo_manifest_never_blocks_the_read(self) -> None:
        self.manifest_path.unlink()
        os.mkfifo(self.manifest_path)
        result = role_metadata(self.state, self.role)
        self.assertEqual(result["state"], UNAVAILABLE)
        self.assertEqual(result["reason"], "METADATA_NOT_REGULAR_FILE")

    def test_a_fifo_profile_never_blocks_the_read(self) -> None:
        self.profile_release_path.unlink()
        os.mkfifo(self.profile_release_path)
        result = role_metadata(self.state, self.role)
        self.assertEqual(result["state"], UNAVAILABLE)
        self.assertEqual(result["reason"], "METADATA_NOT_REGULAR_FILE")

    def test_an_unexpected_internal_failure_is_a_typed_unavailable_projection(self) -> None:
        with mock.patch.object(
            metadata, "_observe", side_effect=RuntimeError("unexpected"),
        ):
            result = role_metadata(self.state, self.role)
        self.assertEqual(result["state"], UNAVAILABLE)
        self.assertEqual(result["reason"], "INTERNAL_READ_FAILURE")
        self.assertEqual(result["proof"], PROOF)


class RoleMetadataObservationStabilityTests(RoleMetadataFixture):
    def test_a_metadata_change_during_the_read_is_unavailable(self) -> None:
        real_read = metadata._HeldObservation.read
        mutated: list[bool] = []

        def mutating_read(held, parent, name, **kwargs):
            data = real_read(held, parent, name, **kwargs)
            if name == "install-receipt.json" and not mutated:
                mutated.append(True)
                receipt = self.read_json(self.receipt_path)
                receipt["upstream_attested"] = True
                self.write_json(self.receipt_path, receipt)
            return data

        with mock.patch.object(metadata._HeldObservation, "read", mutating_read):
            result = role_metadata(self.state, self.role)
        self.assertTrue(mutated)
        self.assertEqual(result["state"], UNAVAILABLE)
        self.assertEqual(result["reason"], "OBSERVATION_CHANGED")

    def test_a_current_release_change_during_the_read_is_unavailable(self) -> None:
        real_read = metadata._HeldObservation.read
        swapped: list[bool] = []

        def swapping_read(held, parent, name, **kwargs):
            data = real_read(held, parent, name, **kwargs)
            if name == "profile.yaml" and not swapped:
                swapped.append(True)
                (self.state / "releases" / "2").mkdir()
                temporary = self.state / ".current.swap"
                os.symlink("releases/2", temporary)
                os.replace(temporary, self.state / "current")
            return data

        with mock.patch.object(metadata._HeldObservation, "read", swapping_read):
            result = role_metadata(self.state, self.role)
        self.assertTrue(swapped)
        self.assertEqual(result["state"], UNAVAILABLE)
        self.assertEqual(result["reason"], "OBSERVATION_CHANGED")

    def test_a_profile_change_between_the_digest_and_the_parse_is_unavailable(self) -> None:
        # Parsing uses held bytes; a persistent change is still refused at
        # the final descriptor and directory-edge check.
        real_read = metadata._HeldObservation.read
        changed: list[bool] = []

        def changing_read(held, parent, name, **kwargs):
            data = real_read(held, parent, name, **kwargs)
            if name == "profile.yaml" and not changed:
                changed.append(True)
                self.profile_release_path.write_text(
                    data.decode("utf-8") + "# changed after the digest\n", encoding="utf-8",
                )
            return data

        with mock.patch.object(metadata._HeldObservation, "read", changing_read):
            result = role_metadata(self.state, self.role)
        self.assertTrue(changed)
        self.assertEqual(result["state"], UNAVAILABLE)
        self.assertEqual(result["reason"], "OBSERVATION_CHANGED")


class RoleMetadataDescriptorTests(RoleMetadataFixture):
    def test_profile_declared_state_must_match_held_root(self) -> None:
        raw = self.profile_release_path.read_bytes()
        changed = raw.replace(str(self.state).encode(), str(self.root / "other-state").encode())
        self.assertNotEqual(raw, changed)
        self.profile_release_path.write_bytes(changed)
        receipt = self.read_json(self.receipt_path)
        receipt["profile_sha256"] = hashlib.sha256(changed).hexdigest()
        self.write_json(self.receipt_path, receipt)
        result = role_metadata(self.state, self.role)
        self.assertEqual((result["state"], result["reason"]), (UNAVAILABLE, "PROFILE_UNQUALIFIED"))

    def test_ancestor_alias_and_nonphysical_root_are_refused(self) -> None:
        alias = self.root / "alias"
        alias.symlink_to(self.root, target_is_directory=True)
        self.assertEqual(role_metadata(alias / "state", self.role)["reason"], "STATE_ROOT_SYMLINK_REFUSED")
        for path in (Path("relative-state"), self.state / ".." / "state"):
            self.assertEqual(role_metadata(path, self.role)["reason"], "STATE_ROOT_NOT_QUALIFIED")

    def test_profile_parser_uses_held_bytes_even_during_pathname_change(self) -> None:
        from integrations.hermes_runtime import profile as profile_owner
        original = self.profile_release_path.read_bytes()
        actual = profile_owner.load_profile_bytes
        seen = []

        def parse(data, *, source_path, **kwargs):
            seen.append(data)
            self.profile_release_path.write_bytes(original + b"# transient changed pathname\n")
            try:
                return actual(data, source_path=source_path, **kwargs)
            finally:
                self.profile_release_path.write_bytes(original)

        with mock.patch.object(profile_owner, "load_profile", side_effect=AssertionError("path parser used")), mock.patch.object(
            profile_owner, "load_profile_bytes", parse,
        ):
            result = role_metadata(self.state, self.role)
        self.assertEqual(seen, [original])
        self.assertEqual(result["reason"], "OBSERVATION_CHANGED")

    def test_root_and_intermediate_directory_replacement_are_detected(self) -> None:
        actual = metadata._HeldObservation.read
        for index, path in enumerate((self.state, self.release / "hermes-home")):
            with self.subTest(path=path.name):
                changed = []

                def read(held, parent, name, **kwargs):
                    data = actual(held, parent, name, **kwargs)
                    if name == "config.yaml" and not changed:
                        changed.append(True)
                        retained = self.root / f"retained-{index}"
                        path.rename(retained)
                        shutil.copytree(retained, path, symlinks=True)
                    return data

                with mock.patch.object(metadata._HeldObservation, "read", read):
                    result = role_metadata(self.state, self.role)
                self.assertTrue(changed)
                self.assertEqual(result["reason"], "OBSERVATION_CHANGED")

    def test_same_bytes_in_new_file_do_not_preserve_identity(self) -> None:
        actual = metadata._HeldObservation.read
        changed = []

        def read(held, parent, name, **kwargs):
            data = actual(held, parent, name, **kwargs)
            if name == "config.yaml" and not changed:
                changed.append(True)
                replacement = self.config_path.with_name("replacement.yaml")
                replacement.write_bytes(data)
                os.replace(replacement, self.config_path)
            return data

        with mock.patch.object(metadata._HeldObservation, "read", read):
            result = role_metadata(self.state, self.role)
        self.assertTrue(changed)
        self.assertEqual(result["reason"], "OBSERVATION_CHANGED")

    def test_file_open_races_refuse_symlink_and_fifo_without_content_read(self) -> None:
        original = self.profile_release_path.read_bytes()
        outside = self.root / "outside-profile.yaml"
        outside.write_bytes(original)
        actual_open, actual_read = os.open, os.read
        for kind in ("symlink", "fifo"):
            with self.subTest(kind=kind):
                swapped = []

                def open_race(path, flags, *args, **kwargs):
                    if path == "profile.yaml" and not swapped:
                        self.assertTrue(flags & os.O_NOFOLLOW)
                        self.assertTrue(flags & os.O_NONBLOCK)
                        swapped.append(True)
                        self.profile_release_path.unlink()
                        if kind == "symlink":
                            self.profile_release_path.symlink_to(outside)
                        else:
                            os.mkfifo(self.profile_release_path)
                    return actual_open(path, flags, *args, **kwargs)

                def read_regular(fd, length):
                    self.assertTrue(stat.S_ISREG(os.fstat(fd).st_mode))
                    return actual_read(fd, length)

                with mock.patch("os.open", open_race), mock.patch("os.read", read_regular):
                    result = role_metadata(self.state, self.role)
                self.assertTrue(swapped)
                self.assertEqual(result["reason"], "METADATA_NOT_REGULAR_FILE")
                self.profile_release_path.unlink()
                self.profile_release_path.write_bytes(original)

    def test_intermediate_symlink_swap_cannot_redirect_the_open(self) -> None:
        actual_open = os.open
        home = self.release / "hermes-home"
        retained = self.root / "retained-home"
        swapped = []

        def open_race(path, flags, *args, **kwargs):
            if path == "hermes-home" and not swapped:
                swapped.append(True)
                self.assertTrue(flags & os.O_DIRECTORY and flags & os.O_NOFOLLOW)
                home.rename(retained)
                home.symlink_to(retained, target_is_directory=True)
            return actual_open(path, flags, *args, **kwargs)

        with mock.patch("os.open", open_race):
            result = role_metadata(self.state, self.role)
        self.assertTrue(swapped)
        self.assertEqual(result["reason"], "OBSERVATION_CHANGED")

    def test_root_replacement_between_stat_and_open_is_refused(self) -> None:
        actual_open = os.open
        swapped = []

        def open_race(path, flags, *args, **kwargs):
            if path == "state" and not swapped:
                swapped.append(True)
                self.state.rename(self.root / "retained-state")
                self.state.mkdir()
            return actual_open(path, flags, *args, **kwargs)

        with mock.patch("os.open", open_race):
            result = role_metadata(self.state, self.role)
        self.assertTrue(swapped)
        self.assertEqual(result["reason"], "OBSERVATION_CHANGED")

    def test_absence_is_rechecked_after_all_install_evidence_inspection(self) -> None:
        actual = metadata._HeldObservation.install_evidence
        for kind in ("manifest", "current", "release", "new-releases"):
            with self.subTest(kind=kind):
                root = self.root / ("absent-" + kind)
                root.mkdir()
                if kind != "new-releases":
                    (root / "releases").mkdir()

                def evidence(held):
                    result = actual(held)
                    self.assertFalse(result)
                    if kind == "manifest":
                        (root / "install-manifest.json").write_text("{}")
                    elif kind == "current":
                        (root / "current").symlink_to("releases/1")
                    elif kind == "release":
                        (root / "releases" / "1").mkdir()
                    else:
                        (root / "releases").mkdir()
                    return result

                with mock.patch.object(metadata._HeldObservation, "install_evidence", evidence):
                    result = role_metadata(root, self.role)
                self.assertEqual(result["reason"], "OBSERVATION_CHANGED")

    def test_evidence_appearing_during_final_empty_directory_scan_is_refused(self) -> None:
        actual = os.scandir
        for kind in ("manifest", "current"):
            with self.subTest(kind=kind):
                root = self.root / ("final-scan-" + kind)
                (root / "releases").mkdir(parents=True)
                calls = []

                def scan(fd):
                    calls.append(fd)
                    if len(calls) == 2:
                        if kind == "manifest":
                            (root / "install-manifest.json").write_text("{}")
                        else:
                            (root / "current").symlink_to("releases/1")
                    return actual(fd)

                with mock.patch("os.scandir", scan):
                    result = role_metadata(root, self.role)
                self.assertEqual(len(calls), 2)
                self.assertEqual(result["reason"], "OBSERVATION_CHANGED")

    def test_descriptors_close_on_success_absence_and_refusal(self) -> None:
        empty = self.root / "empty-descriptors"
        empty.mkdir()
        malformed = self.root / "malformed-descriptors"
        malformed.mkdir()
        (malformed / "install-manifest.json").write_text("not-json")
        actual_open, actual_close = os.open, os.close
        for path, expected in ((self.state, CONFIGURATION_OBSERVED), (empty, ABSENT), (malformed, UNAVAILABLE)):
            with self.subTest(state=expected):
                active = set()
                opened = []

                def open_fd(*args, **kwargs):
                    fd = actual_open(*args, **kwargs)
                    self.assertNotIn(fd, active)
                    active.add(fd)
                    opened.append(fd)
                    return fd

                def close_fd(fd):
                    self.assertIn(fd, active)
                    active.remove(fd)
                    return actual_close(fd)

                with mock.patch("os.open", open_fd), mock.patch("os.close", close_fd):
                    result = role_metadata(path, self.role)
                self.assertEqual(result["state"], expected)
                self.assertTrue(opened)
                self.assertEqual(active, set())


class RoleMetadataBoundaryTests(RoleMetadataFixture):
    def test_the_facade_never_opens_the_secrets_file(self) -> None:
        descriptor_paths: dict[int, Path] = {}
        content_reads: set[Path] = set()
        other_opens: list[str] = []
        real_os_open, real_os_read = os.open, os.read
        real_builtin_open, real_io_open = open, io.open
        expected = {self.manifest_path, self.receipt_path,
                    self.profile_release_path, self.config_path}

        def recording_os_open(path, flags, *args, **kwargs):
            fd = real_os_open(path, flags, *args, **kwargs)
            physical = Path(path)
            if not physical.is_absolute():
                physical = descriptor_paths[kwargs["dir_fd"]] / physical
            descriptor_paths[fd] = physical
            # Ancestor directories are held for custody. Content-bearing
            # opens must remain exactly the four incumbent metadata leaves.
            if not stat.S_ISDIR(os.fstat(fd).st_mode):
                self.assertIn(physical, expected)
            return fd

        def recording_os_read(fd, length):
            self.assertIn(descriptor_paths[fd], expected)
            content_reads.add(descriptor_paths[fd])
            return real_os_read(fd, length)

        def recording_builtin_open(file, *args, **kwargs):
            other_opens.append(str(file))
            return real_builtin_open(file, *args, **kwargs)

        def recording_io_open(file, *args, **kwargs):
            other_opens.append(str(file))
            return real_io_open(file, *args, **kwargs)

        with mock.patch("os.open", recording_os_open), mock.patch(
            "os.read", recording_os_read,
        ), mock.patch("builtins.open", recording_builtin_open), mock.patch(
            "io.open", recording_io_open,
        ):
            result = role_metadata(self.state, self.role)
        self.assertEqual(result["state"], CONFIGURATION_OBSERVED)
        self.assertEqual(content_reads, expected)
        self.assertEqual(other_opens, [])
        self.assertNotIn(self.secrets, descriptor_paths.values())

    def test_the_facade_never_invokes_the_secret_loader_doctor_or_a_provider(self) -> None:
        with mock.patch(
            "integrations.hermes_runtime.secrets.load_secrets",
            side_effect=AssertionError("secret loader invoked"),
        ), mock.patch(
            "integrations.hermes_harness.doctor.doctor",
            side_effect=AssertionError("doctor invoked"),
        ), mock.patch(
            "integrations.hermes_models.credentials.load_credential",
            side_effect=AssertionError("credential loader invoked"),
        ), mock.patch(
            "urllib.request.urlopen",
            side_effect=AssertionError("provider transport invoked"),
        ):
            result = role_metadata(self.state, self.role)
        self.assertEqual(result["state"], CONFIGURATION_OBSERVED)
        self.assertEqual(result["proof"], PROOF)

    def test_importing_the_facade_pulls_in_no_mastermind_module(self) -> None:
        program = (
            "import sys\n"
            "import integrations.hermes_harness.metadata\n"
            "expected = {\n"
            "    'integrations',\n"
            "    'integrations.hermes_harness',\n"
            "    'integrations.hermes_harness.metadata',\n"
            "}\n"
            "leaked = sorted(\n"
            "    name for name in sys.modules\n"
            "    if name.startswith('integrations.') and name not in expected\n"
            ")\n"
            "assert not leaked, leaked\n"
            "print('INERT')\n"
        )
        completed = subprocess.run(
            [sys.executable, "-c", program],
            cwd=str(REPO),
            env={**os.environ, "PYTHONPATH": str(REPO)},
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("INERT", completed.stdout)

    def test_the_facade_call_path_never_calls_a_credential_or_doctor_entry_point(self) -> None:
        program = (
            "import sys\n"
            "import integrations.hermes_models.credentials as credentials\n"
            "import integrations.hermes_runtime.secrets as secrets\n"
            "called = []\n"
            "def tripwire(*args, **kwargs):\n"
            "    called.append(args)\n"
            "    raise AssertionError('credential or doctor entry point invoked')\n"
            "credentials.load_credential = tripwire\n"
            "secrets.load_secrets = tripwire\n"
            "# The facade is imported after the tripwires, so a module-level\n"
            "# import of a loader would bind the tripwire and be caught.\n"
            "import integrations.hermes_harness.metadata as metadata\n"
            "result = metadata.role_metadata(sys.argv[1], sys.argv[2])\n"
            "assert not called, called\n"
            "assert result['state'] == 'CONFIGURATION_OBSERVED', result\n"
            "assert 'integrations.hermes_harness.doctor' not in sys.modules\n"
            "print('INERT')\n"
        )
        completed = subprocess.run(
            [sys.executable, "-c", program, str(self.state), self.role],
            cwd=str(REPO),
            env={**os.environ, "PYTHONPATH": str(REPO)},
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("INERT", completed.stdout)

    def test_profile_for_role_id_uses_the_existing_role_catalog(self) -> None:
        self.assertEqual(profile_for_role_id("meta-ceo"), "mmmeta")
        self.assertEqual(profile_for_role_id("secretary"), "mmsecretary")
        with self.assertRaises(KeyError):
            profile_for_role_id("no-such-role")


class CliCompatibilityTests(RoleMetadataFixture):
    def test_models_output_is_unchanged(self) -> None:
        self.assertEqual(_models("mmmeta"), {
            "role": "mmmeta",
            "default_provider_id": "zai.glm-5.3",
            "choices": [{
                "provider_id": "zai.glm-5.3",
                "native_provider": "zai-glm",
                "requested_model": "glm-5.3",
                "credential_file_env": "ZAI_API_KEY_FILE",
            }],
            "selection_is_admission": False,
            "automatic_fallback": False,
            "provider_called": False,
            "credentials_read": False,
        })
        self.assertEqual(_models("mmsecretary"), {
            "role": "mmsecretary",
            "default_provider_id": "byteplus-modelark.glm-5.3-flash",
            "choices": [{
                "provider_id": "byteplus-modelark.glm-5.3-flash",
                "native_provider": "byteplus-modelark",
                "requested_model": "glm-5-3-flash-260828",
                "credential_file_env": "BYTEPLUS_MODELARK_API_KEY_FILE",
            }, {
                "provider_id": "byteplus-modelark.deepseek-v4.1-flash",
                "native_provider": "byteplus-modelark",
                "requested_model": "deepseek-v4-1-flash-261017",
                "credential_file_env": "BYTEPLUS_MODELARK_API_KEY_FILE",
            }],
            "selection_is_admission": False,
            "automatic_fallback": False,
            "provider_called": False,
            "credentials_read": False,
        })
        self.assertEqual(_models("mmmeta"), model_choices("mmmeta"))

    def test_model_selection_output_is_unchanged(self) -> None:
        profile = load_profile(self.profile_release_path)
        self.assertEqual(_model_selection(profile), {
            "provider_id": "zai.glm-5.3",
            "native_provider": "zai-glm",
            "requested_model": "glm-5.3",
            "served_model_verified": False,
            "credential_env": "ZAI_API_KEY",
            "credential_file_env": "ZAI_API_KEY_FILE",
            "automatic_fallback": False,
            "provider_called": False,
        })
        self.assertEqual(_model_selection(profile), model_selection(profile))

    def test_status_output_is_unchanged(self) -> None:
        status = _status(self.state)
        self.assertEqual(status, {
            "schema": "mastermind.hermes_harness.status.v1",
            "status": "INSTALLED",
            "role": "mmmeta",
            "release": "1",
            "sha": PINNED_UPSTREAM_SHA,
            "allowlist": ["clarify"],
            "overlay_present": False,
            "overlay_chain": ["zai.glm-5.3", "cursor-pool"],
            "native_model_selection": {
                "provider_id": "zai.glm-5.3",
                "native_provider": "zai-glm",
                "requested_model": "glm-5.3",
                "served_model_verified": False,
                "credential_env": "ZAI_API_KEY",
                "credential_file_env": "ZAI_API_KEY_FILE",
                "automatic_fallback": False,
                "provider_called": False,
            },
            "provider_called": False,
            "vision_chain": ["minimax.attended", "cursor-pool"],
            "secrets_recorded": False,
        })

    def test_the_facade_and_the_legacy_status_agree_on_the_same_install(self) -> None:
        status = _status(self.state)
        projection = role_metadata(self.state, self.role)
        self.assertEqual(projection["role"], status["role"])
        self.assertEqual(projection["provenance"]["release"], status["release"])
        self.assertEqual(projection["provenance"]["upstream_sha"], status["sha"])
        self.assertEqual(
            projection["requested"]["provider_id"],
            status["native_model_selection"]["provider_id"],
        )

    def test_the_legacy_summary_and_the_qualified_observation_differ_on_damaged_state(self) -> None:
        # ``hermesctl status`` is the incumbent operator summary and keeps its
        # established output. The role metadata facade is a stricter qualified
        # observation of the same tree. Where they disagree is fixed here so
        # the difference is a documented contract rather than an accident.
        missing = self.root / "no-such-state"
        self.assertEqual(_status(missing)["status"], "ABSENT")
        self.assertEqual(role_metadata(missing, self.role)["reason"], "STATE_ROOT_MISSING")

        drifted_profile = self.release / "profile.yaml"
        original_profile = drifted_profile.read_text(encoding="utf-8")
        drifted_profile.write_text(original_profile + "# drift\n", encoding="utf-8")
        self.assertEqual(_status(self.state)["status"], "INSTALLED")
        self.assertEqual(
            role_metadata(self.state, self.role)["reason"], "PROFILE_DIGEST_MISMATCH",
        )
        drifted_profile.write_text(original_profile, encoding="utf-8")

        decoy = self.root / "decoy-manifest.json"
        decoy.write_text(self.manifest_path.read_text(encoding="utf-8"), encoding="utf-8")
        self.manifest_path.unlink()
        os.symlink(decoy, self.manifest_path)
        self.assertEqual(_status(self.state)["status"], "INSTALLED")
        self.assertEqual(
            role_metadata(self.state, self.role)["reason"], "METADATA_NOT_REGULAR_FILE",
        )

    def test_role_metadata_command_prints_the_closed_projection(self) -> None:
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = main(["role-metadata", "--state", str(self.state), "--role", "mmmeta"])
        self.assertEqual(code, 0)
        payload = json.loads(buffer.getvalue())
        self.assertEqual(payload["schema"], ROLE_METADATA_SCHEMA)
        self.assertEqual(payload["state"], CONFIGURATION_OBSERVED)
        self.assertEqual(payload["proof"], PROOF)

    def test_role_metadata_command_reports_absence_without_a_credential_read(self) -> None:
        empty = self.root / "empty-state"
        empty.mkdir()
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = main(["role-metadata", "--state", str(empty), "--role", "mmmeta"])
        self.assertEqual(code, 0)
        payload = json.loads(buffer.getvalue())
        self.assertEqual(payload["state"], ABSENT)
        self.assertEqual(payload["reason"], "INSTALL_MANIFEST_ABSENT")


if __name__ == "__main__":
    unittest.main()
