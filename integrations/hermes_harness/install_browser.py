"""Direct local installer for the existing native bridge and native Hermes plugin.

No GitHub mutation, browser launch, permission grant, restart, or background runner.
A locally committed build plus exact checksums supplies reproducible provenance.
Chrome Load unpacked remains an explicit browser operation.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = "mastermind.browser_direct_build.v1"


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def read_owned(path):
    path = Path(path)
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
    fd = os.open(path, flags)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o022 or info.st_size > 5000000:
            raise RuntimeError("unsafe source: " + str(path))
        with os.fdopen(fd, "rb", closefd=False) as stream:
            return stream.read(5000001)
    finally:
        os.close(fd)


def write_owned(path, content, mode=0o600, expected=None):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.parent.is_symlink():
        raise RuntimeError("symlink destination parent: " + str(path.parent))
    existed=path.exists() or path.is_symlink()
    if not existed and expected is not None:
        raise RuntimeError("expected prior file is missing: " + str(path))
    if existed:
        prior = read_owned(path)
        if prior == content:
            if stat.S_IMODE(path.stat().st_mode) != mode:
                path.chmod(mode)
            return
        if expected is None or digest(prior) != expected:
            raise RuntimeError("existing file differs; no overwrite: " + str(path))
        backup = path.with_name(path.name + ".previous." + digest(prior)[:16])
        write_owned(backup, prior, stat.S_IMODE(path.stat().st_mode))
    descriptor, temporary = tempfile.mkstemp(prefix=".install-", dir=path.parent)
    try:
        os.fchmod(descriptor, mode)
        with os.fdopen(descriptor, "wb") as output:
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        if existed:
            if expected is None or digest(read_owned(path)) != expected:
                raise RuntimeError("destination changed during installation: " + str(path))
            os.replace(temporary, path)
        else:
            # An unexpected concurrent creator must win over this installation.
            os.link(temporary,path)
            os.unlink(temporary)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    if read_owned(path) != content:
        raise RuntimeError("installation readback failed: " + str(path))


def json_bytes(data):
    return (json.dumps(data, indent=2, sort_keys=True) + "\n").encode()


MMX_PIN_FOLDER = ".t3/mcp/mmx-browser"


def _resolved(path):
    return Path(path).expanduser().resolve()


def runtime_pin_program_roots(home=None):
    """Program folders named by the live mmx-browser runtime pin (read-only).

    A running bridge server loaded ``server.js`` from its pin folder — the
    flat ``runtime.json`` location before the versioned migration, the folder
    ``current`` resolves to after it — and re-verifies the pinned
    ``source_root`` closure before every dispatch. Both are folders a running
    program has loaded, so an installer never targets them. A pin that exists
    but cannot be read is a refusal, not a skip: an unverifiable pin proves no
    target safe.
    """
    mmx = (Path(home) if home is not None else Path.home()) / MMX_PIN_FOLDER
    pins = []
    if (mmx / "runtime.json").exists():
        pins.append((mmx, mmx / "runtime.json"))
    current = mmx / "current"
    if current.is_symlink() or current.exists():
        current_root = _resolved(current)
        pins.append((current_root, current_root / "runtime.json"))
    roots = []
    for folder, pin in pins:
        if not pin.is_file():
            raise RuntimeError("live runtime pin folder is missing runtime.json: " + str(pin))
        try:
            document = json.loads(read_owned(pin))
        except (OSError, ValueError, RuntimeError) as error:
            raise RuntimeError("live runtime pin is unreadable; refusing to install without it: "
                               + str(pin)) from error
        source_root = document.get("source_root") if isinstance(document, dict) else None
        if not isinstance(source_root, str) or not source_root:
            raise RuntimeError("live runtime pin names no source_root: " + str(pin))
        roots.append((str(folder), _resolved(folder),
                      "a folder running mmx-browser servers load (live pin " + str(pin) + ")"))
        roots.append((source_root, _resolved(source_root),
                      "the release source_root of the live runtime pin " + str(pin)))
    return roots


def loaded_extension_roots(profile_rows):
    """Folders a Chrome has loaded for our extension id, from profile rows.

    Rows need only ``data_directory`` and ``profile_directory``. Every
    registration state that names a ``loaded_path`` protects it: an
    unverified or identity-mismatched load is still a load.

    A read error on an enrolled profile is a refusal, never a skip
    (BR-MICRO2 item 2): an unreadable registration cannot prove which
    folders Chrome has loaded, so it proves no target safe. "No extension
    loaded" is a normal answer only when ``routes.registration`` returns it
    as a state (``CHROME_LOAD_REQUIRED``, ``PROFILE_DIRECTORY_MISSING``),
    never when the read raises or comes back ``PROFILE_REGISTRATION_UNAVAILABLE``.
    """
    from integrations.hermes_harness import browser_routes as routes
    roots = []
    for row in profile_rows or []:
        if not isinstance(row, dict):
            continue
        data_directory = row.get("data_directory")
        directory = row.get("profile_directory")
        if not isinstance(data_directory, (str, Path)) or not isinstance(directory, str):
            continue
        alias = row.get("alias")
        who = directory + (" (alias " + alias + ")" if isinstance(alias, str) and alias else "")
        try:
            # A synthetic browser_id: registration compares it against the
            # loaded folder's instance_config.js, and the guard protects every
            # path-naming state — loaded, unverified or mismatched — alike.
            state = routes.registration({"data_directory": str(data_directory),
                                         "profile_directory": directory,
                                         "browser_id": ""})
        except Exception as error:
            raise RuntimeError(
                "loaded-extension check refused: the registration read for profile " + who
                + " failed (" + type(error).__name__ + ": " + str(error) + "); an enrolled"
                " profile whose registration cannot be read proves no install target safe,"
                " so the install is refused") from error
        if state.get("activation") == "PROFILE_REGISTRATION_UNAVAILABLE":
            raise RuntimeError(
                "loaded-extension check refused: the registration read for profile " + who
                + " returned PROFILE_REGISTRATION_UNAVAILABLE — its Chrome preferences could"
                " not be read, so nothing proves which folders Chrome has loaded for it;"
                " 'no extension loaded' is a normal answer only when the registration read"
                " returns it as a state, never when it fails")
        loaded_path = state.get("loaded_path")
        if isinstance(loaded_path, str) and loaded_path:
            roots.append((loaded_path, _resolved(loaded_path),
                          "a folder Chrome has loaded for profile " + directory))
    return roots


def refuse_loaded_or_pinned(targets, protected, what):
    """Class rule (ruling-15 micro-fix; principal): an installer never targets
    a folder a running program has loaded. Refuses any target that is a
    protected folder, sits inside one, or contains one, naming the protected
    folder by its recorded path."""
    for label, target in targets:
        resolved = _resolved(target)
        for recorded, protected_resolved, reason in protected:
            if (resolved == protected_resolved
                    or resolved.is_relative_to(protected_resolved)
                    or protected_resolved.is_relative_to(resolved)):
                raise RuntimeError(what + " refused: the " + label + " " + str(target)
                                   + " is, contains, or is inside " + recorded + " — " + reason
                                   + "; an installer never targets a folder a running program has loaded")


def stage_release(build_manifest, install_base):
    manifest = json.loads(read_owned(build_manifest))
    if manifest.get("schema") != SCHEMA or not re.fullmatch("[0-9a-f]{40}", manifest.get("source_commit", "")):
        raise RuntimeError("invalid direct build manifest")
    files = manifest.get("files")
    if not isinstance(files, dict) or not files or len(files) > 300:
        raise RuntimeError("invalid direct build closure")
    release = install_base / "releases" / manifest["source_commit"]
    for name, checksum in sorted(files.items()):
        relative = Path(name)
        if relative.is_absolute() or ".." in relative.parts or not re.fullmatch("[0-9a-f]{64}", checksum):
            raise RuntimeError("invalid source path")
        raw = read_owned(ROOT / relative)
        if digest(raw) != checksum:
            raise RuntimeError("source mismatch: " + name)
        write_owned(release / relative, raw)
    write_owned(release / "BUILD.json", json_bytes(manifest))
    return release, manifest


def install_chrome(release_root, manifest, base, python_executable, chrome_profiles):
    from integrations.chairman_surfaces.web_sol_deployment import WebSolRelease, render_census_extension_bundle, _CENSUS_SOURCE_NAMES, verify_deployment_readback
    from integrations.chairman_surfaces.web_sol_instance import local_browser_instance_id
    from integrations.chairman_surfaces.web_sol_protocol import WEB_SOL_PACKAGE_VERSION
    chrome_root = Path.home() / "Library/Application Support/Google/Chrome"
    native_root = chrome_root / "NativeMessagingHosts"
    # Class rule (ruling-15 micro-fix): this native-messaging installer never
    # targets a folder a running program has loaded. The release root must not
    # be, contain, or sit inside a program folder named by the live runtime
    # pin, and no staged extension folder may be one Chrome has loaded.
    # Checked before any render output, native manifest, or inventory write.
    protected = (loaded_extension_roots([{"data_directory": str(chrome_root),
                                          "profile_directory": name} for name in chrome_profiles])
                 + runtime_pin_program_roots())
    targets = [("release root", Path(release_root))]
    for profile_name in chrome_profiles:
        if not re.fullmatch(r"Default|Profile [0-9]+", profile_name) or not (chrome_root/profile_name).is_dir():
            continue  # the profile loop below raises the canonical error
        try:
            instance = local_browser_instance_id(chrome_root, profile_name)
        except Exception:
            continue  # the profile loop below raises the canonical error
        targets.append(("staged extension folder for profile " + profile_name,
                        release_root / "chrome" / profile_name.replace(" ", "-") / "extensions" / instance[:24]))
    refuse_loaded_or_pinned(targets, protected, "native-messaging install target")
    assets = release_root / "integrations/chairman_surfaces/web_sol_extension"
    source_files = {name: read_owned(assets / name) for name in _CENSUS_SOURCE_NAMES}
    expected = {name: manifest["files"]["integrations/chairman_surfaces/web_sol_extension/" + name] for name in _CENSUS_SOURCE_NAMES}
    profiles, receipts = [], []
    for profile_name in chrome_profiles:
        if not re.fullmatch(r"Default|Profile [0-9]+", profile_name) or not (chrome_root/profile_name).is_dir():
            raise RuntimeError("Chrome profile does not exist: " + profile_name)
        instance = local_browser_instance_id(chrome_root, profile_name)
        install_root = release_root / "chrome" / profile_name.replace(" ", "-")
        release = WebSolRelease(WEB_SOL_PACKAGE_VERSION, manifest["source_commit"], release_root, python_executable, install_root)
        bundle = render_census_extension_bundle({}, release, source_files=source_files,
            expected_source_digests=expected, instance_id=instance)
        for artifact in bundle.artifacts:
            write_owned(artifact.destination, artifact.content, artifact.mode)
        native = next(a for a in bundle.artifacts if a.kind == "native_host_manifest")
        native_path = native_root / native.destination.name
        write_owned(native_path, native.content)
        receipt = verify_deployment_readback(bundle, {str(a.destination): read_owned(a.destination) for a in bundle.artifacts})
        receipt.update(profile=profile_name, instance_id=instance, native_host_manifest=str(native_path),
            extension_path=str(install_root/"extensions"/instance[:24]), chrome_loaded=False)
        receipts.append(receipt)
        profiles.append(dict(browser_id=instance, label="Chrome / " + profile_name, manager="chrome",
            extension_path=receipt["extension_path"], native_host_manifest=str(native_path)))
    inventory = base / "deployments.json"
    write_owned(inventory, json_bytes(dict(schema="mastermind.browser_deployments.v1", profiles=profiles)))
    return inventory, receipts


def plugin_package(release_root, base, source_commit):
    package = base / "packages" / source_commit / "mastermind-browser"
    original = release_root / "integrations/hermes_harness/browser_plugin"
    for source in sorted(original.rglob("*")):
        if source.is_file() and "__pycache__" not in source.parts:
            write_owned(package / source.relative_to(original), read_owned(source), 0o644)
    if not (package / ".git").exists():
        subprocess.run(["git", "init", "-q", str(package)], check=True)
        subprocess.run(["git", "-C", str(package), "add", "."], check=True)
        subprocess.run(["git", "-C", str(package), "-c", "user.name=Mastermind Browser Builder",
            "-c", "user.email=browser-builder@mastermind-x.com", "commit", "-q", "-m", "Mastermind browser " + source_commit], check=True)
    status = subprocess.run(["git", "-C", str(package), "status", "--porcelain"], check=True, text=True, capture_output=True)
    if status.stdout:
        raise RuntimeError("local plugin package has changed")
    commit = subprocess.check_output(["git", "-C", str(package), "rev-parse", "HEAD"], text=True).strip()
    return package, commit


def install_profiles(release_root, manifest, base, python_executable, enrollment, *, prior_source=None, staging_root=None, update_loaded=False):
    """Add/update named profiles using observed prior bytes; never rewrite Chrome preferences.

    The enrollment is host-owned installation input, not a model tool argument.
    Existing unrelated routes survive. A previous immutable source commit is
    required to replace a native registration or loaded extension's code.
    ``staging_root`` is required: this installer has no default staging root
    because the historical default (``~/Downloads/Mastermind-Browser-0.5.0``)
    was a folder Chrome had already loaded. A staging root — or any
    ``Chrome-<alias>`` folder prepared under it — that is, contains, or is
    inside a folder Chrome has loaded or a program folder named by the live
    mmx-browser runtime pin is refused by name before anything is rendered or
    written; that check gates the prepared-extension writes below.
    By default the bytes of a folder Chrome has already loaded are never
    changed: ``update_loaded=False`` skips the loaded-folder rewrite entirely
    and the release is staged under the explicit ``staging_root``. The profile
    is moved to the new bytes by an explicit extension reload from the staging
    folder, never by an unbidden byte change under a running service worker.
    """
    from integrations.hermes_harness import browser_routes as routes
    from integrations.chairman_surfaces.web_sol_deployment import WebSolRelease, render_census_extension_bundle, _CENSUS_SOURCE_NAMES, verify_deployment_readback
    from integrations.chairman_surfaces.web_sol_instance import local_browser_instance_id
    from integrations.chairman_surfaces.web_sol_protocol import WEB_SOL_PACKAGE_VERSION
    if staging_root is None:
        raise RuntimeError("usage error: --staging-root is required; this installer has no default "
                           "staging root — the historical default (~/Downloads/Mastermind-Browser-0.5.0) "
                           "is a folder Chrome has already loaded")
    if set(enrollment) != {"host_ref","label","profiles","remote_hosts","remote_profiles"}:
        raise RuntimeError("invalid host enrollment")
    host_ref=enrollment["host_ref"]
    inventory=base/"deployments-v2.json"
    before=read_owned(inventory) if inventory.exists() else None
    document=routes.validate(json.loads(before)) if before else dict(schema=routes.SCHEMA,local_host_ref=host_ref,
        hosts=[dict(host_ref=host_ref,label=enrollment["label"],transport="local")],profiles=[])
    if document["local_host_ref"]!=host_ref:
        raise RuntimeError("host enrollment identity changed")
    staging_root_path=Path(staging_root).expanduser()
    # Class rule (ruling-15 micro-fix; principal): an installer never targets a
    # folder a running program has already loaded. Refuse a staging root — or
    # any per-profile Chrome-<alias> folder prepared under it — that is,
    # contains, or is inside a folder Chrome has loaded or a program folder
    # named by the live mmx-browser runtime pin. This check gates every
    # prepared-extension write below: nothing is rendered or written before it
    # passes, and the refusal names the protected folder.
    protected=(loaded_extension_roots(enrollment["profiles"])+runtime_pin_program_roots())
    guard_targets=[("staging root",staging_root_path)]
    for supplied in enrollment["profiles"]:
        if isinstance(supplied,dict) and isinstance(supplied.get("alias"),str):
            guard_targets.append(("prepared folder for alias "+supplied["alias"],
                                  staging_root_path/("Chrome-"+supplied["alias"])))
    refuse_loaded_or_pinned(guard_targets,protected,"staging root")
    prior_manifest=None
    if prior_source:
        if not re.fullmatch("[0-9a-f]{40}",prior_source):raise RuntimeError("invalid prior source")
        prior_manifest=json.loads(read_owned(base/"releases"/prior_source/"BUILD.json"))
        if prior_manifest.get("source_commit")!=prior_source:raise RuntimeError("prior source mismatch")
    assets=release_root/"integrations/chairman_surfaces/web_sol_extension"
    sources={name:read_owned(assets/name) for name in _CENSUS_SOURCE_NAMES}
    expected={name:manifest["files"]["integrations/chairman_surfaces/web_sol_extension/"+name] for name in _CENSUS_SOURCE_NAMES}
    rows={(r["host_ref"],r["browser_id"]):r for r in document["profiles"]}
    hosts={h["host_ref"]:h for h in document["hosts"]}
    pending=[];receipts=[]
    seen=set()
    for supplied in enrollment["profiles"]:
        allowed={"alias","label","profile_directory","profile_name","account_hint","data_directory","chrome_executable","upload_roots","launch_environment"}
        if not isinstance(supplied,dict) or set(supplied)-allowed:
            raise RuntimeError("invalid profile enrollment")
        chrome_root=Path(supplied["data_directory"])
        directory=supplied["profile_directory"]
        if not re.fullmatch(r"Default|Profile [0-9]+",directory) or not (chrome_root/directory).is_dir():
            raise RuntimeError("Chrome profile missing: "+directory)
        instance=local_browser_instance_id(chrome_root,directory)
        if instance in seen:raise RuntimeError("duplicate profile enrollment")
        seen.add(instance)
        install_root=release_root/"chrome"/directory.replace(" ","-")
        release=WebSolRelease(WEB_SOL_PACKAGE_VERSION,manifest["source_commit"],release_root,python_executable,install_root)
        bundle=render_census_extension_bundle({},release,source_files=sources,expected_source_digests=expected,instance_id=instance)
        native=next(a for a in bundle.artifacts if a.kind=="native_host_manifest")
        native_path=chrome_root/"NativeMessagingHosts"/native.destination.name
        extension=staging_root_path/("Chrome-"+supplied["alias"])
        row=dict(supplied,host_ref=host_ref,browser_id=instance,manager="chrome",extension_path=str(extension),native_host_manifest=str(native_path))
        # Validate coordinates before constructing any path from an alias.
        routes.validate(dict(schema=routes.SCHEMA,local_host_ref=host_ref,hosts=[hosts[host_ref]],profiles=[row]))
        for root in row["upload_roots"]:
            if not Path(root).is_dir():raise RuntimeError("upload root missing: "+root)
        previous_native=read_owned(native_path) if native_path.exists() else None
        if previous_native is not None and previous_native!=native.content:
            existing=json.loads(previous_native)
            if (prior_manifest is None or not str(existing.get("path","")).startswith(str(base/"releases"/prior_source)+"/")
                    or existing.get("name")!=bundle.native_host_name
                    or existing.get("allowed_origins")!=["chrome-extension://"+routes.EXTENSION_ID+"/"]):
                raise RuntimeError("native registration has a different owner: "+str(native_path))
        changes=[]
        for artifact in bundle.artifacts:
            changes.append((artifact.destination,artifact.content,artifact.mode,None))
            if artifact.destination.parent.name==instance[:24]:
                prepared=extension/artifact.destination.name
                prepared_prior=None
                if prepared.exists() or prepared.is_symlink():
                    old=read_owned(prepared)
                    if old!=artifact.content:
                        prior_hash=(prior_manifest or {}).get("files",{}).get(
                            "integrations/chairman_surfaces/web_sol_extension/"+prepared.name)
                        if prepared.name not in _CENSUS_SOURCE_NAMES or digest(old)!=prior_hash:
                            raise RuntimeError("prepared extension changed: "+str(prepared))
                        prepared_prior=digest(old)
                changes.append((prepared,artifact.content,artifact.mode,prepared_prior))
        changes.append((native_path,native.content,0o600,digest(previous_native) if previous_native else None))
        loaded=routes.registration(row)
        # Default: never change the bytes of a folder Chrome has loaded. The
        # MV3 service worker re-reads its scripts from disk on every wake, so
        # rewriting a loaded folder takes effect with no person acting and
        # can mix an old worker with new page scripts. The reload step moves
        # the profile to the staged bytes instead; the rewrite exists only
        # for an explicitly requested in-place update.
        if update_loaded and loaded.get("installed") and loaded.get("loaded_path")!=str(extension):
            loaded_path=Path(loaded["loaded_path"])
            # Only replace our exact old source assets. Unknown local edits and
            # other extension owners are a reconciliation boundary.
            for name in sorted(_CENSUS_SOURCE_NAMES):
                old=read_owned(loaded_path/name)
                if old==sources[name]:continue
                prior_hash=(prior_manifest or {}).get("files",{}).get("integrations/chairman_surfaces/web_sol_extension/"+name)
                if digest(old)!=prior_hash:
                    raise RuntimeError("loaded extension changed: "+str(loaded_path/name))
                changes.append((loaded_path/name,sources[name],0o600,digest(old)))
        rows[(host_ref,instance)]=row
        pending.append((bundle,changes,row,loaded))
    for host in enrollment["remote_hosts"]:
        if host.get("host_ref")==host_ref:raise RuntimeError("remote host shadows local")
        hosts[host["host_ref"]]=host
    for row in enrollment["remote_profiles"]:
        if row.get("host_ref")==host_ref:raise RuntimeError("remote profile shadows local")
        rows[(row["host_ref"],row["browser_id"])]=row
    document["hosts"]=list(hosts.values());document["profiles"]=list(rows.values())
    routes.validate(document)
    # Validate every replacement before the first write, then CAS each observed
    # file again immediately at publication. Independent unrelated rows survive.
    for _,changes,_,_ in pending:
        for path,content,_,prior in changes:
            if path.exists() or path.is_symlink():
                actual=read_owned(path)
                if actual!=content and (prior is None or digest(actual)!=prior):
                    raise RuntimeError("installation precondition changed: "+str(path))
    for bundle,changes,row,loaded in pending:
        for path,content,mode,prior in changes:write_owned(path,content,mode,expected=prior)
        receipt=verify_deployment_readback(bundle,{str(a.destination):read_owned(a.destination) for a in bundle.artifacts})
        receipt.update(host_ref=host_ref,browser_id=row["browser_id"],alias=row["alias"],label=row["label"],
            profile_directory=row["profile_directory"],extension_path=row["extension_path"],
            loaded_path=loaded.get("loaded_path"),native_host_manifest=row["native_host_manifest"],
            activation="CHROME_RELOAD_REQUIRED" if loaded.get("installed") else "CHROME_LOAD_REQUIRED")
        receipts.append(receipt)
    write_owned(inventory,json_bytes(document),expected=digest(before) if before else None)
    return inventory,receipts


def install_hermes(release_root, manifest, base, inventory, profile, executable, python_executable, package, package_commit):
    if not profile.is_absolute() or not profile.is_dir():
        raise RuntimeError("Hermes profile does not exist")
    env = dict(os.environ, HERMES_HOME=str(profile))
    installed = profile / "plugins/mastermind-browser"
    if installed.exists():
        # No blind reinstall or replacement of an active plugin. Reconcile exact provenance.
        prior = subprocess.run(["git", "-C", str(installed), "rev-parse", "HEAD"], capture_output=True, text=True)
        if prior.returncode or prior.stdout.strip() != package_commit:
            raise RuntimeError("different plugin already installed: " + str(installed))
    else:
        subprocess.run([str(executable), "plugins", "install", package.as_uri(), "--ref", package_commit, "--no-enable"], env=env, check=True)
    if not (installed / "__init__.py").is_file():
        raise RuntimeError("Hermes installer did not create expected plugin")
    spec = importlib.util.spec_from_file_location("mastermind_browser_install_metadata", installed / "__init__.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    uploads = profile / "browser-files/uploads"
    artifacts = profile / "browser-files/artifacts"
    for folder in (uploads, artifacts):
        folder.mkdir(mode=0o700, parents=True, exist_ok=True)
    download_root = Path.home() / "Downloads"
    roots = [str(uploads)]
    if download_root.is_dir():
        roots.append(str(download_root))
    descriptor = dict(schema=module.RUNTIME_SCHEMA, release_commit=manifest["source_commit"],
        source_root=str(release_root), python_executable=str(python_executable), profile_home=str(profile),
        bindings_path=str(inventory), source_files={p:manifest["files"][p] for p in module.SOURCE_FILES},
        upload_roots=roots, artifact_root=str(artifacts))
    write_owned(installed / "_runtime.json", json_bytes(descriptor))
    subprocess.run([str(executable), "plugins", "enable", "mastermind-browser", "--no-allow-tool-override"], env=env, check=True)
    return dict(profile=str(profile), plugin_path=str(installed), package_commit=package_commit,
        descriptor_sha256=digest(read_owned(installed/"_runtime.json")), upload_roots=roots,
        artifact_root=str(artifacts), enabled_by_native_cli=True)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--build-manifest",type=Path,required=True)
    parser.add_argument("--install-base",type=Path,default=Path.home()/".local/share/mastermind-browser-control")
    parser.add_argument("--python",type=Path,required=True)
    parser.add_argument("--hermes",type=Path,default=Path.home()/".local/bin/hermes")
    parser.add_argument("--chrome-profile",action="append",default=[])
    parser.add_argument("--hermes-profile",type=Path,action="append",default=[])
    parser.add_argument("--enrollment",type=Path)
    parser.add_argument("--prior-source")
    parser.add_argument("--staging-root",type=Path,
        help="required with --enrollment: fresh per-release staging root for Chrome-<alias> folders; there is no "
             "default (the historical default was a folder Chrome had loaded), and a loaded or runtime-pinned root is refused")
    parser.add_argument("--update-loaded",action="store_true",
        help="also rewrite extension bytes inside folders Chrome has already loaded (default: never)")
    args=parser.parse_args()
    if args.enrollment and args.staging_root is None:
        parser.error("the following arguments are required for --enrollment: --staging-root "
                     "(this installer has no default staging root; the historical default "
                     "~/Downloads/Mastermind-Browser-0.5.0 is a folder Chrome has already loaded)")
    if sys.platform not in {"darwin","linux"}:
        raise RuntimeError("this installer targets macOS and Linux")
    base=args.install_base.resolve()
    release, manifest=stage_release(args.build_manifest,base)
    if args.enrollment:
        if args.chrome_profile or args.hermes_profile:raise RuntimeError("named enrollment uses the separate native upgrade specification")
        inventory,chrome=install_profiles(release,manifest,base,args.python.resolve(),json.loads(read_owned(args.enrollment)),
            prior_source=args.prior_source,staging_root=args.staging_root,update_loaded=args.update_loaded)
    else:
        if sys.platform!="darwin" or not args.chrome_profile:raise RuntimeError("named enrollment required")
        inventory,chrome=install_chrome(release,manifest,base,args.python.resolve(),args.chrome_profile)
    package, package_commit=plugin_package(release,base,manifest["source_commit"])
    hermes=[]
    if args.enrollment:
        write_owned(base/("installation-"+manifest["source_commit"]+".json"),json_bytes(dict(schema="mastermind.browser_installation.v2",
            source_commit=manifest["source_commit"],release_root=str(release),inventory=str(inventory),chrome=chrome,
            package=str(package),package_commit=package_commit)))
    for profile in args.hermes_profile:
        hermes.append(install_hermes(release,manifest,base,inventory,profile.resolve(),args.hermes,
            args.python.resolve(),package,package_commit))
        write_owned(base/"installation-receipt.json",json_bytes(dict(schema="mastermind.browser_installation.v1",
            source_commit=manifest["source_commit"],release_root=str(release),chrome=chrome,hermes=hermes)),
            expected=digest(read_owned(base/"installation-receipt.json")) if (base/"installation-receipt.json").exists() else None)
    print(json.dumps(dict(state="INSTALLED_PENDING_CHROME_LOAD",source_commit=manifest["source_commit"],
        release_root=str(release),inventory=str(inventory),chrome=chrome,hermes=hermes)))


if __name__=="__main__":
    main()
