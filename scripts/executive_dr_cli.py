"""Operator CLI for Executive OS off-host disaster-recovery export/transport.

Mirrors ``scripts/executive_os_phase1c.py``'s CLI conventions: absolute-path
arguments only, a master key is never accepted on argv, and every command
prints one JSON receipt to stdout on success. Stdlib only (no third-party
imports) -- this CLI runs under the same isolated ``python3.12 -I -S``
runtime as the rest of Executive OS.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from control_plane.executive_backup import verify_restore_drill
from control_plane.executive_dr import (
    ExecutiveDRError,
    ExecutiveDRTypedError,
    decrypt_export,
    encrypt_export,
    fetch_export_directory,
    fetch_export_github,
    quarantine_artifact,
    read_export_backup_manifest,
    ship_export_directory,
    ship_export_github,
    verify_export_envelope,
)
from control_plane.executive_dr import _write_private_json


def _decrypt_with_manifest(
    ciphertext_path: Path, envelope_path: Path, key: str, output_dir: Path, *, openssl_binary: str | None = None
) -> tuple[Path, Path, Any]:
    """Decrypt into the manifest's OWN recorded filename, then materialize a
    manifest sidecar next to it.

    ``verify_backup``'s manifest cross-check requires the database file's
    basename to exactly equal ``manifest["database"]["filename"]`` (the name
    the original online/offline backup was created under) -- an arbitrary
    output filename such as ``restored.sqlite3`` would fail that check even
    though the bytes are byte-for-byte correct. Reading the manifest first
    (no key required) and decrypting straight into that exact name keeps
    ``verify_restore_drill`` the SAME verifier a live restore uses, with no
    second manifest schema.
    """

    manifest = read_export_backup_manifest(envelope_path)
    database = manifest.get("database")
    if not isinstance(database, dict) or not isinstance(database.get("filename"), str) or not database["filename"]:
        raise SystemExit("DR export manifest has no usable database filename")
    output_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    output_dir.chmod(0o700)
    output_path = output_dir / database["filename"]
    decrypt_receipt = decrypt_export(ciphertext_path, envelope_path, key, output_path, openssl_binary=openssl_binary)
    manifest_path = output_path.with_suffix(".manifest.json")
    _write_private_json(manifest_path, manifest)
    return output_path, manifest_path, decrypt_receipt


def _absolute_path(value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        raise argparse.ArgumentTypeError("path must be absolute")
    return path


def _read_master_key(args: argparse.Namespace) -> str:
    if bool(args.key_file) == bool(args.key_env):
        raise SystemExit("exactly one of --key-file or --key-env is required")
    if args.key_file:
        text = Path(args.key_file).read_text(encoding="utf-8").strip()
    else:
        text = os.environ.get(args.key_env, "").strip()
    if not text:
        raise SystemExit("DR master key source produced no data")
    return text


def _add_key_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--key-file", type=_absolute_path, default=None, help="Absolute path to a file holding the base64 master key.")
    parser.add_argument("--key-env", default=None, help="Name of an environment variable holding the base64 master key.")


def _add_token_args(parser: argparse.ArgumentParser) -> None:
    # Adversarial review B3: a 0644 launchd plist's EnvironmentVariables is
    # world-readable, so a standing PAT must never live there. --token-file
    # mirrors --key-file exactly -- a 0400 file this process reads itself;
    # --token-env stays available for the ephemeral, repo-scoped
    # GITHUB_TOKEN a CI workflow already injects into its own step env.
    parser.add_argument("--token-file", type=_absolute_path, default=None, help="Absolute path to a file holding the transport credential (0400).")
    parser.add_argument("--token-env", default=None, help="Name of an environment variable already holding the transport credential.")


def _resolve_token_args(args: argparse.Namespace) -> tuple[str | None, str | None]:
    if bool(args.token_file) == bool(args.token_env):
        raise SystemExit("exactly one of --token-file or --token-env is required")
    if args.token_file:
        text = Path(args.token_file).read_text(encoding="utf-8").strip()
        if not text:
            raise SystemExit("DR transport credential file produced no data")
        return text, None
    return None, args.token_env


def _add_openssl_binary_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--openssl-binary",
        default=None,
        help="Override the openssl binary (default: $MASTERMIND_DR_OPENSSL or /usr/bin/openssl).",
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Encrypt, ship, fetch, and verify Executive OS off-host DR exports.")
    sub = parser.add_subparsers(dest="command", required=True)

    export = sub.add_parser("export", help="Verify a local backup and produce an encrypted DR export.")
    export.add_argument("--artifact", type=_absolute_path, required=True)
    export.add_argument("--manifest", type=_absolute_path, required=True)
    export.add_argument("--staging-dir", type=_absolute_path, required=True)
    export.add_argument("--transport-target", required=True)
    export.add_argument("--retention-class", required=True)
    export.add_argument("--source-release-commit", required=True)
    export.add_argument("--key-id", default="v1")
    _add_key_args(export)
    _add_openssl_binary_arg(export)

    ship = sub.add_parser("ship", help="Ship an already-encrypted export to a transport target.")
    ship.add_argument("--ciphertext", type=_absolute_path, required=True)
    ship.add_argument("--envelope", type=_absolute_path, required=True)
    ship.add_argument("--transport", choices=("github", "directory"), required=True)
    ship.add_argument("--repo", default=None, help="owner/repo, required for --transport github")
    ship.add_argument("--directory", type=_absolute_path, default=None, help="required for --transport directory")
    ship.add_argument("--api-base", default="https://api.github.com")
    ship.add_argument(
        "--draft",
        action="store_true",
        help="Create a DRAFT GitHub release (drill lane only -- no git tag is created; never for the production/vault lane).",
    )
    _add_token_args(ship)

    fetch = sub.add_parser("fetch", help="Fetch a shipped export back from a transport target.")
    fetch.add_argument("--tag", required=True)
    fetch.add_argument("--dest-dir", type=_absolute_path, required=True)
    fetch.add_argument("--transport", choices=("github", "directory"), required=True)
    fetch.add_argument("--repo", default=None)
    fetch.add_argument("--directory", type=_absolute_path, default=None)
    fetch.add_argument("--api-base", default="https://api.github.com")
    _add_token_args(fetch)

    verify_envelope = sub.add_parser("verify-envelope", help="Offline structural + digest check; never needs the key.")
    verify_envelope.add_argument("--envelope", type=_absolute_path, required=True)
    verify_envelope.add_argument("--ciphertext", type=_absolute_path, default=None)
    verify_envelope.add_argument(
        "--quarantine-on-failure",
        action="store_true",
        help="Rename the ciphertext aside with a receipt instead of leaving it in place if verification fails.",
    )

    restore_verify = sub.add_parser(
        "restore-verify", help="Decrypt a fetched export, then run the existing offline restore-drill verifier."
    )
    restore_verify.add_argument("--ciphertext", type=_absolute_path, required=True)
    restore_verify.add_argument("--envelope", type=_absolute_path, required=True)
    restore_verify.add_argument(
        "--output-dir", type=_absolute_path, required=True, help="Directory to decrypt into, under the manifest's own filename."
    )
    _add_key_args(restore_verify)
    _add_openssl_binary_arg(restore_verify)

    drill_local = sub.add_parser(
        "drill-local", help="Full local round trip (export -> directory ship -> fetch -> decrypt -> restore-verify), no network."
    )
    drill_local.add_argument("--artifact", type=_absolute_path, required=True)
    drill_local.add_argument("--manifest", type=_absolute_path, required=True)
    drill_local.add_argument("--work-dir", type=_absolute_path, required=True)
    drill_local.add_argument("--source-release-commit", required=True)
    _add_key_args(drill_local)

    return parser


def _print(value: Any) -> None:
    json.dump(value, sys.stdout, sort_keys=True, indent=2)
    sys.stdout.write("\n")


def _run_export(args: argparse.Namespace) -> int:
    key = _read_master_key(args)
    receipt = encrypt_export(
        args.artifact,
        args.manifest,
        key,
        args.staging_dir,
        transport_target=args.transport_target,
        retention_class=args.retention_class,
        source_release_commit=args.source_release_commit,
        key_id=args.key_id,
        openssl_binary=args.openssl_binary,
    )
    _print(receipt.to_dict())
    return 0


def _run_ship(args: argparse.Namespace) -> int:
    if args.transport == "github":
        if not args.repo:
            raise SystemExit("--repo is required for --transport github")
        token, token_env = _resolve_token_args(args)
        receipt = ship_export_github(
            args.ciphertext, args.envelope, repo=args.repo, token=token, token_env=token_env,
            api_base=args.api_base, draft=args.draft,
        )
    else:
        if not args.directory:
            raise SystemExit("--directory is required for --transport directory")
        receipt = ship_export_directory(args.ciphertext, args.envelope, directory=args.directory)
    _print(receipt.to_dict())
    return 0


def _run_fetch(args: argparse.Namespace) -> int:
    if args.transport == "github":
        if not args.repo:
            raise SystemExit("--repo is required for --transport github")
        token, token_env = _resolve_token_args(args)
        receipt = fetch_export_github(
            args.tag, repo=args.repo, dest_dir=args.dest_dir, token=token, token_env=token_env, api_base=args.api_base
        )
    else:
        if not args.directory:
            raise SystemExit("--directory is required for --transport directory")
        receipt = fetch_export_directory(args.tag, directory=args.directory, dest_dir=args.dest_dir)
    _print(receipt.to_dict())
    return 0


def _run_verify_envelope(args: argparse.Namespace) -> int:
    try:
        receipt = verify_export_envelope(args.envelope, args.ciphertext)
    except ExecutiveDRTypedError:
        if args.quarantine_on_failure and args.ciphertext is not None and Path(args.ciphertext).exists():
            quarantine = quarantine_artifact(args.ciphertext, reason="failed offline envelope/digest verification")
            _print({"quarantined": quarantine.to_dict()})
            return 1
        raise
    _print(receipt.to_dict())
    return 0


def _run_restore_verify(args: argparse.Namespace) -> int:
    key = _read_master_key(args)
    output_path, manifest_path, decrypt_receipt = _decrypt_with_manifest(
        args.ciphertext, args.envelope, key, args.output_dir, openssl_binary=args.openssl_binary
    )
    drill_receipt = verify_restore_drill(output_path, manifest_path)
    _print({"decrypt": decrypt_receipt.to_dict(), "restore_drill": drill_receipt.to_dict()})
    return 0


def _run_drill_local(args: argparse.Namespace) -> int:
    key = _read_master_key(args)
    work = Path(args.work_dir)
    staging = work / "staging"
    vault = work / "vault"
    fetched = work / "fetched"

    export_receipt = encrypt_export(
        args.artifact,
        args.manifest,
        key,
        staging,
        transport_target="directory",
        retention_class="drill",
        source_release_commit=args.source_release_commit,
    )
    ship_receipt = ship_export_directory(export_receipt.ciphertext_path, export_receipt.envelope_path, directory=vault)
    fetch_receipt = fetch_export_directory(ship_receipt.tag, directory=vault, dest_dir=fetched)
    output_path, manifest_path, decrypt_receipt = _decrypt_with_manifest(
        Path(fetch_receipt.ciphertext_path), Path(fetch_receipt.envelope_path), key, work / "restored"
    )
    drill_receipt = verify_restore_drill(output_path, manifest_path)
    _print(
        {
            "export": export_receipt.to_dict(),
            "ship": ship_receipt.to_dict(),
            "fetch": fetch_receipt.to_dict(),
            "decrypt": decrypt_receipt.to_dict(),
            "restore_drill": drill_receipt.to_dict(),
        }
    )
    return 0


_HANDLERS = {
    "export": _run_export,
    "ship": _run_ship,
    "fetch": _run_fetch,
    "verify-envelope": _run_verify_envelope,
    "restore-verify": _run_restore_verify,
    "drill-local": _run_drill_local,
}


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    handler = _HANDLERS[args.command]
    try:
        return handler(args)
    except ExecutiveDRError as exc:
        sys.stderr.write(f"{exc}\n")
        return 65


if __name__ == "__main__":
    raise SystemExit(main())
