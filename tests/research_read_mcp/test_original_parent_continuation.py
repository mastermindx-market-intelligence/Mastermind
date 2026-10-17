"""Actual launcher/child/wait control flow over explicitly synthetic producer modules.

This tests source and process composition, not genuine remote settlement or the
real engine's tail analyzer. Those need the separate engine/SDK proofs.
"""
import hashlib
import json
from pathlib import Path

import pytest

from ops.research_producer import launch
from integrations.research_read_mcp.runtime import RuntimeRefused
from tests.research_read_mcp.test_producer_launch import fixture


def setup(tmp_path, *, unsupported=False, excerpt_ok=True):
    config = fixture(tmp_path, rc=7)
    macro = Path(config["macro_release"])
    cli = macro / "scripts/ingest_research.py"
    text = cli.read_text().replace("import json,pathlib,sys,tempfile", "import json,pathlib,sys,tempfile,sqlite3")
    text = text.replace(" (p.parent/'observed.json')", " p.write_bytes(b'synthetic-original-journal')\n w=p.with_name(p.name+'.workspace');w.mkdir()\n c=sqlite3.connect(w/'corpus.sqlite');c.execute('PRAGMA user_version=1');c.close()\n (p.parent/'observed.json')")
    text += "\ndef _public_mirror_bytes(raw):\n d=json.loads(raw);d.pop('producer_generation');return json.dumps(d).encode()\n"
    cli.write_text(text)
    entries = {
        "engine/__init__.py": "",
        "engine/research_vault/__init__.py": "",
        "engine/research_vault/producer_generation.py": "GENERATION_FIELD='producer_generation'\nCORPUS_MAX_BYTES=1048576\n",
        "engine/research_vault/generation_recovery.py": (
            "from pathlib import Path\n"
            "def inspect_settled_publication(path, **kw):\n"
            " assert Path(path).name=='journal.jsonl'\n"
            " assert kw['original_capture_sha256']=='c'*64\n"
            " assert (Path(path).parent/'parent-observed-wait').read_text()=='waited'\n"
            + (" raise ValueError('SYNTHETIC_UNKNOWN_EFFECT')\n" if unsupported else " return {}\n")),
        "engine/research_vault/r2_store.py": (
            "from pathlib import Path\n"
            "def build_store(*,single_attempt_writes):\n"
            " assert single_attempt_writes is True\n"
            f" Path({str(tmp_path / 'store-constructed')!r}).write_text('yes')\n"
            " return object()\n"),
        "engine/research_vault/generation_continuation.py": (
            "import hashlib,json\nfrom pathlib import Path\n"
            "def _continue_after_original_exit(store,path,**kw):\n"
            " p=Path(path);raw=(p.with_name(p.name+'.workspace')/'corpus.sqlite').read_bytes()\n"
            " doc={'items':[{'id':'synthetic-report'}],'producer_generation':{'corpus_sha256':hashlib.sha256(raw).hexdigest()}}\n"
            " (p.parent/'continuation-core-called').write_text(kw['expected_identity']['run'])\n"
            " return {'continuation_capture_sha256':'d'*64,'catalog_bytes':json.dumps(doc).encode()}\n"),
        "engine/research_vault/excerpt.py": (
            "import json\n"
            "def snapshot(connection,ids):\n return {'synthetic-report':['public-safe synthetic excerpt']}\n"
            "def write_repo_snapshot(excerpts,path):\n"
            + (" path.write_text(json.dumps({'schema':1,'excerpts':excerpts}));return True\n"
               if excerpt_ok else " return False\n")),
    }
    for name, content in entries.items():
        path = macro / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    manifest_path = Path(config["manifest_path"])
    manifest = json.loads(manifest_path.read_bytes())
    manifest["members"]["macro"] = [
        {"path": str(p.relative_to(macro)), "bytes": p.stat().st_size,
         "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
        for p in macro.rglob("*") if p.is_file()]
    raw = json.dumps(manifest).encode()
    manifest_path.write_bytes(raw)
    config["manifest_sha256"] = hashlib.sha256(raw).hexdigest()
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config))
    path.chmod(0o600)
    return config, path


def observe_actual_wait(monkeypatch, config, *, mutate_source=False):
    original_popen = launch.subprocess.Popen
    observed = []
    class Child:
        def __init__(self, *args, **kwargs):
            self.child = original_popen(*args, **kwargs)
            self.stdout = self.child.stdout
            self.ordinal = len(observed)
            observed.append(["started"])
        def wait(self):
            rc = self.child.wait()
            observed[self.ordinal].append("waited")
            if self.ordinal == 0:
                run = Path(config["retention_root"]) / "macro-123-1"
                (run / "parent-observed-wait").write_text("waited")
                if mutate_source:
                    (Path(config["macro_release"]) / "engine/research_vault/r2_store.py").write_text("raise AssertionError('CHANGED')\n")
            return rc
    monkeypatch.setattr(launch.subprocess, "Popen", Child)
    return observed


@pytest.mark.parametrize("mode", ["success", "unsupported", "source_changed", "mirror_refused"])
def test_actual_original_parent_commissions_one_tail_after_wait(tmp_path, monkeypatch, capsys, mode):
    monkeypatch.delenv("RESEARCH_LOCAL_STORE", raising=False)
    config, path = setup(tmp_path, unsupported=mode == "unsupported", excerpt_ok=mode != "mirror_refused")
    observed = observe_actual_wait(monkeypatch, config, mutate_source=mode == "source_changed")
    rc = launch.main(["--config", str(path), "--run-id", "123", "--attempt", "1", "--execute"])
    output = capsys.readouterr().out
    result = json.loads(output)
    assert result["exit_code"] == 7  # Never rewrite the actual original outcome.
    assert observed == [["started", "waited"], ["started", "waited"]]
    assert "PRIVATE_SYNTHETIC_BODY" not in output
    assert "synthetic-original-journal" not in output
    assert rc == (0 if mode == "success" else 1)
    run = Path(config["retention_root"]) / "macro-123-1"
    assert (run / "journal.jsonl").read_bytes() == b"synthetic-original-journal"
    assert (run / "continuation-output.log").stat().st_mode & 0o777 == 0o600
    assert result["recovery_authorized"] is False  # Saved receipt never grants reentry.
    if mode in {"unsupported", "source_changed"}:
        assert not (tmp_path / "store-constructed").exists()
        assert not (run / "continuation-core-called").exists()
    else:
        assert (run / "continuation-core-called").read_text() == "github:mastermindx-market-intelligence/macro:123:1"
        assert result["continuation"]["continuation_capture_sha256"] == "d" * 64
    if mode == "success":
        public = Path(config["public_checkout"]) / "data/research_vault"
        assert "producer_generation" not in json.loads((public / "catalog.json").read_bytes())
        assert (public / "excerpts.json").is_file()
    with pytest.raises(RuntimeRefused):
        launch.execute(config, "123", "1")
    assert len(observed) == 2
