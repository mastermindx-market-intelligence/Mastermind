from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(path: str, old: str, new: str) -> None:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected one replacement, found {count}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


replace_once(
    "control_plane/worker_execution_contract.py",
    "import dataclasses\n",
    "import dataclasses\nimport hashlib\nimport json\nimport os\nimport re\nimport stat\n",
)
replace_once(
    "control_plane/worker_execution_contract.py",
    'LAUNCH_ATTESTATION_SCHEMA_VERSION = "mastermind.executive_launch_attestation/v1"\n',
    'LAUNCH_ATTESTATION_SCHEMA_VERSION = "mastermind.executive_launch_attestation/v1"\n'
    'WORKER_RECOVERY_BINDING_VERSION = "mastermind.worker_recovery_binding/v1"\n'
    'DURABLE_COLLECTION_CONTRACT_VERSION = "mastermind.worker_durable_collection/v1"\n'
    '_MAX_RECOVERY_PROMPT_BYTES = 1024 * 1024\n'
    '_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")\n',
)

replace_once(
    "control_plane/worker_execution_contract.py",
    "@dataclasses.dataclass(frozen=True)\nclass ArtifactReceipt:\n",
    r'''class WorkerRecoveryContractError(ValueError):
    """Durable worker recovery evidence is malformed or has drifted."""


def _canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        _jsonable(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _launch_spec_material(spec: WorkerLaunchSpec) -> dict[str, Any]:
    material = {
        field.name: _jsonable(getattr(spec, field.name))
        for field in dataclasses.fields(spec)
        if field.name != "prompt"
    }
    material["prompt_sha256"] = hashlib.sha256(
        spec.prompt.encode("utf-8")
    ).hexdigest()
    return material


def worker_launch_spec_sha256(spec: WorkerLaunchSpec) -> str:
    """Hash the exact provider-neutral launch contract without storing prompt bytes."""

    if not isinstance(spec, WorkerLaunchSpec):
        raise WorkerRecoveryContractError(
            "recovery binding requires WorkerLaunchSpec"
        )
    return _canonical_sha256(_launch_spec_material(spec))


def _recovery_prompt_bytes(path: Path) -> bytes:
    try:
        info = path.lstat()
    except OSError as exc:
        raise WorkerRecoveryContractError(
            "recovery prompt is unavailable"
        ) from exc
    if (
        stat.S_ISLNK(info.st_mode)
        or not stat.S_ISREG(info.st_mode)
        or info.st_nlink != 1
        or info.st_uid != os.geteuid()
        or stat.S_IMODE(info.st_mode) & 0o077
        or info.st_size <= 0
        or info.st_size > _MAX_RECOVERY_PROMPT_BYTES
    ):
        raise WorkerRecoveryContractError(
            "recovery prompt is not a private bounded control-owned file"
        )
    try:
        payload = path.read_bytes()
    except OSError as exc:
        raise WorkerRecoveryContractError(
            "recovery prompt is unavailable"
        ) from exc
    if len(payload) != info.st_size:
        raise WorkerRecoveryContractError(
            "recovery prompt changed while reading"
        )
    try:
        payload.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise WorkerRecoveryContractError(
            "recovery prompt is not strict UTF-8"
        ) from exc
    return payload


def _process_ref_from_recovery(value: Any) -> WorkerProcessRef:
    if not isinstance(value, Mapping):
        raise WorkerRecoveryContractError(
            "recovery process_ref must be an object"
        )
    raw = dict(value)
    binary = raw.get("binary")
    if not isinstance(binary, Mapping):
        raise WorkerRecoveryContractError(
            "recovery process_ref binary is invalid"
        )
    try:
        raw["binary"] = BinaryAttestation(**dict(binary))
        return WorkerProcessRef(**raw)
    except (TypeError, ValueError) as exc:
        raise WorkerRecoveryContractError(
            "recovery process_ref is invalid"
        ) from exc


@dataclasses.dataclass(frozen=True)
class WorkerRecoveryBinding:
    """Provider-neutral durable coordinates for one already-started execution."""

    schema_version: str
    adapter_id: str
    collection_contract_version: str
    launch_spec_sha256: str
    launch_spec: Mapping[str, Any] = dataclasses.field(repr=False)
    process_ref: WorkerProcessRef

    def __post_init__(self) -> None:
        object.__setattr__(self, "launch_spec", _freeze(self.launch_spec))
        if self.schema_version != WORKER_RECOVERY_BINDING_VERSION:
            raise WorkerRecoveryContractError(
                "recovery binding schema is unsupported"
            )
        if (
            self.collection_contract_version
            != DURABLE_COLLECTION_CONTRACT_VERSION
        ):
            raise WorkerRecoveryContractError(
                "recovery collection contract is unsupported"
            )
        if not isinstance(self.adapter_id, str) or not self.adapter_id.strip():
            raise WorkerRecoveryContractError(
                "recovery adapter identity is invalid"
            )
        if (
            not isinstance(self.launch_spec_sha256, str)
            or _SHA256_RE.fullmatch(self.launch_spec_sha256) is None
        ):
            raise WorkerRecoveryContractError(
                "recovery launch digest is invalid"
            )
        fields = self.launch_spec.get("fields")
        if (
            set(self.launch_spec)
            != {"fields", "prompt_path", "prompt_sha256"}
            or not isinstance(fields, Mapping)
            or fields.get("run_id") != self.process_ref.run_id
        ):
            raise WorkerRecoveryContractError(
                "recovery run identity is inconsistent"
            )
        prompt_digest = self.launch_spec.get("prompt_sha256")
        if (
            not isinstance(prompt_digest, str)
            or _SHA256_RE.fullmatch(prompt_digest) is None
        ):
            raise WorkerRecoveryContractError(
                "recovery prompt digest is invalid"
            )

    @classmethod
    def bind(
        cls,
        *,
        adapter_id: str,
        spec: WorkerLaunchSpec,
        process_ref: WorkerProcessRef,
        prompt_path: str | Path,
    ) -> "WorkerRecoveryBinding":
        if process_ref.run_id != spec.run_id:
            raise WorkerRecoveryContractError(
                "recovery run identity is inconsistent"
            )
        path = Path(prompt_path)
        if not path.is_absolute():
            raise WorkerRecoveryContractError(
                "recovery prompt path must be absolute"
            )
        try:
            resolved = path.resolve(strict=True)
            input_root = (Path(spec.run_dir) / "input").resolve(strict=True)
            resolved.relative_to(input_root)
        except (OSError, ValueError) as exc:
            raise WorkerRecoveryContractError(
                "recovery prompt path escapes the run input directory"
            ) from exc
        payload = _recovery_prompt_bytes(resolved)
        if payload != spec.prompt.encode("utf-8"):
            raise WorkerRecoveryContractError(
                "recovery prompt bytes differ from the launch specification"
            )
        fields = {
            field.name: _jsonable(getattr(spec, field.name))
            for field in dataclasses.fields(spec)
            if field.name != "prompt"
        }
        return cls(
            schema_version=WORKER_RECOVERY_BINDING_VERSION,
            adapter_id=str(adapter_id),
            collection_contract_version=DURABLE_COLLECTION_CONTRACT_VERSION,
            launch_spec_sha256=worker_launch_spec_sha256(spec),
            launch_spec={
                "fields": fields,
                "prompt_path": str(resolved),
                "prompt_sha256": hashlib.sha256(payload).hexdigest(),
            },
            process_ref=process_ref,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "adapter_id": self.adapter_id,
            "collection_contract_version": self.collection_contract_version,
            "launch_spec_sha256": self.launch_spec_sha256,
            "launch_spec": _jsonable(self.launch_spec),
            "process_ref": _jsonable(self.process_ref),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "WorkerRecoveryBinding":
        if not isinstance(value, Mapping) or set(value) != {
            "schema_version",
            "adapter_id",
            "collection_contract_version",
            "launch_spec_sha256",
            "launch_spec",
            "process_ref",
        }:
            raise WorkerRecoveryContractError(
                "recovery binding fields are invalid"
            )
        launch_spec = value.get("launch_spec")
        if not isinstance(launch_spec, Mapping):
            raise WorkerRecoveryContractError(
                "recovery launch material is invalid"
            )
        return cls(
            schema_version=value.get("schema_version"),
            adapter_id=value.get("adapter_id"),
            collection_contract_version=value.get(
                "collection_contract_version"
            ),
            launch_spec_sha256=value.get("launch_spec_sha256"),
            launch_spec=dict(launch_spec),
            process_ref=_process_ref_from_recovery(value.get("process_ref")),
        )

    def recover_launch_spec(
        self,
        spec_type: type[WorkerLaunchSpec] = WorkerLaunchSpec,
    ) -> WorkerLaunchSpec:
        if not isinstance(spec_type, type) or not issubclass(
            spec_type, WorkerLaunchSpec
        ):
            raise WorkerRecoveryContractError(
                "recovery launch type is invalid"
            )
        fields = self.launch_spec["fields"]
        if not isinstance(fields, Mapping):
            raise WorkerRecoveryContractError(
                "recovery launch fields are invalid"
            )
        raw = dict(_jsonable(fields))
        prompt_path = Path(str(self.launch_spec["prompt_path"]))
        run_dir = Path(str(raw.get("run_dir", "")))
        try:
            prompt_path.resolve(strict=True).relative_to(
                (run_dir / "input").resolve(strict=True)
            )
        except (OSError, ValueError) as exc:
            raise WorkerRecoveryContractError(
                "recovery prompt path escapes the run input directory"
            ) from exc
        payload = _recovery_prompt_bytes(prompt_path)
        digest = hashlib.sha256(payload).hexdigest()
        if digest != self.launch_spec["prompt_sha256"]:
            raise WorkerRecoveryContractError(
                "recovery prompt digest has drifted"
            )
        try:
            prompt = payload.decode("utf-8", errors="strict")
            for name in (
                "workspace_path",
                "run_dir",
                "result_schema_path",
            ):
                raw[name] = Path(raw[name])
            for name in (
                "isolation_roots",
                "isolation_denied_paths",
                "forbidden_paths",
            ):
                raw[name] = tuple(Path(item) for item in raw[name])
            for name in ("authorities", "allowed_artifact_paths"):
                raw[name] = tuple(raw[name])
            spec = spec_type(prompt=prompt, **raw)
        except (KeyError, TypeError, ValueError) as exc:
            raise WorkerRecoveryContractError(
                "recovery launch specification is invalid"
            ) from exc
        if (
            spec.run_id != self.process_ref.run_id
            or worker_launch_spec_sha256(spec) != self.launch_spec_sha256
        ):
            raise WorkerRecoveryContractError(
                "recovery launch specification digest or run identity has drifted"
            )
        return spec


@dataclasses.dataclass(frozen=True)
class ArtifactReceipt:
''',
)

replace_once(
    "control_plane/worker_execution_contract.py",
    '    "LAUNCH_ATTESTATION_SCHEMA_VERSION",\n',
    '    "LAUNCH_ATTESTATION_SCHEMA_VERSION",\n'
    '    "WORKER_RECOVERY_BINDING_VERSION",\n'
    '    "DURABLE_COLLECTION_CONTRACT_VERSION",\n',
)
replace_once(
    "control_plane/worker_execution_contract.py",
    '    "WorkerLaunchSpec",\n',
    '    "WorkerLaunchSpec",\n'
    '    "WorkerRecoveryBinding",\n'
    '    "WorkerRecoveryContractError",\n'
    '    "worker_launch_spec_sha256",\n',
)

replace_once(
    "control_plane/worker_adapter.py",
    "    WorkerLaunchSpec,\n",
    "    WorkerLaunchSpec,\n    WorkerRecoveryBinding,\n",
)
replace_once(
    "control_plane/worker_adapter.py",
    "    async def status(self, ref: WorkerProcessRef) -> WorkerRunStatus: ...\n",
    "    def reattach(\n"
    "        self, spec: WorkerLaunchSpec, binding: WorkerRecoveryBinding\n"
    "    ) -> WorkerProcessRef: ...\n\n"
    "    async def status(self, ref: WorkerProcessRef) -> WorkerRunStatus: ...\n",
)
