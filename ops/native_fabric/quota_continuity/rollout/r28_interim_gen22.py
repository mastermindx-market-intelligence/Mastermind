#!/usr/bin/env python3
"""Source-only gen22+R28 staging; publication/selection remains with native_generation."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import native_generation as g

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[3]
BASE="ac9acf0daf5a438934f3862afa02039734aa100812d4e040eda5966388817c3b"
SEQ=22
BASE_PICK="9bbb96c8da84e38bbd802fdd373a0e8ba386395abc5a80bc8628b49d5afd8174"
R28="4008caca8c6a0e2145e7cb90965740ce24445e3300a8e3693d7a96130df236df"
FUSED="4311200ae485ffd19b2560434e46c0c01899fbb58f0793c198292dba6004503b"
TARGET="854dd5456c005f6385daecb6e93658025d59f94e496dd5f9374d7896d06eed87"
PIN="fbb0c69818edeb4217cdc1b2f353df2f00cd70fc"
SRC="ops/native_fabric/quota_continuity/candidate/pick.py"
EXT=(Path.home()/".claude/projects/-Users-chriswong-Documents-Cluade-Macro-Dashboard"
     /"handoff_kits/meta-ceo-b-2026-09-08/ext")
MANIFEST=HERE/"r28_interim_gen22_manifest.json"
PROVENANCE=HERE/"r28_interim_gen22_provenance.json"
HUNKS=(
 (b'    "operator", "reviewer", "adjudicate", "decompose", "audit", "repair",',
  b'    "operator", "reviewer", "review", "adjudicate", "decompose", "audit", "repair",'),
 (b'    if is_execute_class(tc, doc) or tc in LABOR_CLASSES_R30:\n'
  b'        return _pick_execute(',
  b'    # Independent review/audit remain judgment even when legacy execute_classes includes them.\n'
  b'    # Preserve explicit-pool gates above; do not score implicit reviewers into Qwen.\n'
  b'    if tc not in {"review", "audit"} and (is_execute_class(tc, doc) or tc in LABOR_CLASSES_R30):\n'
  b'        return _pick_execute('),
)

def digest(raw):
    return hashlib.sha256(raw).hexdigest()

def fail(message):
    raise ValueError("R28_INTERIM_REFUSED:"+message)

def contract():
    manifest=g.manifest_files(g.unique_json(g.regular_bytes(MANIFEST,65536)))
    actual=g.unique_json(g.regular_bytes(PROVENANCE,65536))
    expected={
      "schema":"mastermind.fabric_native_r28_gen22_interim_provenance.v1",
      "status":"SOURCE_ONLY_NOT_PUBLISHED_NOT_SELECTED",
      "protected_source_commit":PIN,"protected_source_pr":1797,
      "protected_review_picker_sha256":R28,
      "baseline_source":"EXACT_VERIFIED_EXISTING_IMMUTABLE_SELECTED_GENERATION",
      "baseline_generation":BASE,"baseline_sequence":22,
      "baseline_pick_sha256":BASE_PICK,"changed_member":"ext/pick.py",
      "changed_member_sha256":FUSED,"unchanged_members":94,"member_count":95,
      "proposed_generation":TARGET,"stable_ext":str(EXT),
      "native_publisher":"existing native_generation.py publish/select; never this staging helper",
      "live_effects_authorized":False,
    }
    if actual!=expected or len(manifest)!=95 or manifest.get("ext/pick.py")!=FUSED:
        fail("SOURCE_MANIFEST_OR_PROVENANCE_CHANGED")
    return manifest

def reviewed_source():
    try:
        source=subprocess.check_output(["git","-C",str(REPO),"show",PIN+":"+SRC],timeout=15)
    except (OSError,subprocess.TimeoutExpired,subprocess.CalledProcessError):
        fail("PROTECTED_MERGED_SOURCE_UNAVAILABLE")
    if source!=g.regular_bytes(REPO/SRC) or digest(source)!=R28:
        fail("PROTECTED_MERGED_SOURCE_DRIFT")
    return source

def fuse(baseline,merged):
    if digest(baseline)!=BASE_PICK or digest(merged)!=R28:
        fail("BASE_OR_REVIEWED_PICKER_CHANGED")
    result=baseline
    for old,new in HUNKS:
        # Three bare execute predicates exist; replace ONLY the exact callsite.
        if result.count(old)!=1 or merged.count(new)!=1:
            fail("PROTECTED_TWO_HUNK_SHAPE_CHANGED")
        result=result.replace(old,new,1)
    if digest(result)!=FUSED:
        fail("EXACT_FUSED_PICKER_DIGEST_CHANGED")
    compile(result,"ext/pick.py","exec")
    return result

def compatible(base,proposed):
    if (len(base)!=95 or set(base)!=set(proposed) or base.get("ext/pick.py")!=BASE_PICK
        or any(base[k]!=proposed[k] for k in base if k!="ext/pick.py")):
        fail("NON_PICKER_MEMBER_DRIFT")
    descriptor=g.descriptor(proposed,str(EXT))
    if g.digest(g.canonical(descriptor))!=TARGET:
        fail("GENERATION_IDENTITY_CHANGED")

def staging_output(out,store):
    out=out.absolute()
    kit=store.parent
    if (os.path.lexists(out) or out==Path("/") or out==kit
        or out.is_relative_to(kit) or kit.is_relative_to(out)
        or out==REPO or out.is_relative_to(REPO)
        or not out.parent.is_dir() or out.parent.is_symlink()
        or out.parent.resolve(strict=True)!=out.parent):
        fail("FRESH_EXTERNAL_STAGE_REQUIRED")
    return out

def stage(store,out):
    proposed=contract()
    protected=reviewed_source()
    store=g.check_store(store)
    pointer=g.current(store)
    if pointer is None or pointer["generation"]!=BASE or pointer["sequence"]!=SEQ:
        fail("SELECTED_CURRENT_NOT_SEQ22")
    base_root,meta=g.verify(store,BASE)
    if meta["stable_ext"]!=str(EXT):
        fail("STABLE_EXT_CHANGED")
    compatible(meta["files"],proposed)
    out=staging_output(out,store)
    picker=fuse(g.regular_bytes(base_root/"ext/pick.py"),protected)
    out.mkdir(mode=0o700)
    source=out/"native-code-stage"
    (source/"ext").mkdir(parents=True,mode=0o700)
    for rel,want in sorted(proposed.items()):
        raw=picker if rel=="ext/pick.py" else g.regular_bytes(base_root/rel)
        if digest(raw)!=want:
            fail("STAGE_MEMBER_DIGEST_REFUSED:"+rel)
        target=source/rel
        target.parent.mkdir(mode=0o700,exist_ok=True)
        with target.open("xb") as fp:
            fp.write(raw);fp.flush();os.fsync(fp.fileno())
        if digest(g.regular_bytes(target))!=want:
            fail("STAGE_READBACK_REFUSED:"+rel)
    (out/"native-manifest.json").write_text(json.dumps(proposed,sort_keys=True,indent=2)+"\n")
    result={"schema":"mastermind.fabric_native_r28_gen22_stage.v1",
            "state":"STAGED_ONLY_NOT_PUBLISHED_NOT_SELECTED",
            "protected_commit":PIN,"base_generation":BASE,"base_sequence":SEQ,
            "candidate_generation":TARGET,"manifest_members":95,
            "changed_members":["ext/pick.py"],"runtime_effects":False}
    (out/"STAGE_RECEIPT.json").write_text(json.dumps(result,sort_keys=True,indent=2)+"\n")
    g.verify(store,BASE)
    if g.current(store)!=pointer:
        fail("CURRENT_CHANGED_DURING_STAGING")
    return result

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    try:
        print(json.dumps(stage(args.store,args.output),sort_keys=True))
        return 0
    except (OSError,ValueError,SyntaxError) as exc:
        print("R28_INTERIM_STAGE_REFUSED:"+str(exc)[:260],file=sys.stderr)
        return 78

if __name__=="__main__":
    raise SystemExit(main())
