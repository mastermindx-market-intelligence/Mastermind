"""Strict content only; authored source never implies a Runtime instruction gate."""
import copy
import hashlib
import pytest
from common import workspace_project_instructions_contract as wire
from common.executive_workspace_contract import canonical

SELECTED={"work_ref":"WS:PROJECT-ONE"}
SOURCE={"repository":"mastermindx-market-intelligence/macro","commit":"a"*40,"path":"agentos/workstreams/WS-PROJECT-ONE.md","content_sha256":"b"*64}

def body(rows=None, declaration="SUPPLIED"):
    return {"schema":wire.BODY_SCHEMA,"selection":dict(SELECTED),"availability":"AVAILABLE","source":dict(SOURCE),
        "declaration":declaration,"instructions":[] if rows is None else rows,"reason_codes":[]}


def test_public_recovery_identity_is_versioned_and_does_not_change_canonical_content_contract():
    identity={'principal_scope':'f'*64};private=body();public=wire.public_body(private,recovery_identity=identity)
    assert public['schema']==wire.PUBLIC_BODY_SCHEMA and public['recovery_identity']==identity
    assert wire.validate_public_body(public,SELECTED)==public and wire.validate_body(private,SELECTED)==private
    with pytest.raises(ValueError):wire.validate_body(public,SELECTED)
    with pytest.raises(ValueError):wire.validate_public_body({**private,'recovery_identity':identity},SELECTED)
    for forged in [None,{'principal_scope':'f'*64,'permission':True},{'principal_scope':'f'*64+'\n'}]:
        with pytest.raises(ValueError):wire.public_body(private,recovery_identity=forged)


def test_unavailable_public_content_never_retains_recovery_identity():
    public=wire.public_body(wire.unavailable(SELECTED['work_ref']),recovery_identity={'principal_scope':'f'*64})
    assert public['recovery_identity'] is None
    with pytest.raises(ValueError):wire.validate_public_body({**public,'recovery_identity':{'principal_scope':'f'*64}},SELECTED)


def test_added_recovery_metadata_cannot_expand_the_existing_utf8_ceiling():
    rows=[wire.authored_instruction({'instruction_ref':f'INS:ITEM-{i}','text':'x'*3900}) for i in range(8)]
    value=body(rows);size=len(canonical({'ok':True,'result':value}))+1
    delta=32740-size
    assert 0<delta<196
    rows[-1]=wire.authored_instruction({'instruction_ref':rows[-1]['instruction_ref'],'text':'x'*(3900+delta)})
    assert wire.validate_body(body(rows),SELECTED)
    with pytest.raises(ValueError):wire.public_body(body(rows),recovery_identity={'principal_scope':'f'*64})


def test_absent_explicit_empty_and_unavailable_are_distinct_and_detached():
    absent=body(declaration="NOT_DECLARED");empty=body();unavailable=wire.unavailable(SELECTED["work_ref"])
    assert wire.validate_body(absent,SELECTED)!=wire.validate_body(empty,SELECTED)
    assert unavailable["availability"]=="UNAVAILABLE" and unavailable["instructions"] is None
    row=wire.authored_instruction({"instruction_ref":"INS:DAILY-ONE","text":"  保留文字\nGoal 🎯  "})
    assert row["revision"]==hashlib.sha256(canonical({"instruction_ref":row["instruction_ref"],"text":row["text"]})).hexdigest()
    value=body([row]);detached=wire.validate_body(value,SELECTED);value["instructions"][0]["text"]="edited"
    assert detached["instructions"][0]["text"]=="  保留文字\nGoal 🎯  "
    assert not {"state","active","permission","title","observed_at"}&set(row)


@pytest.mark.parametrize("field,bad",[("instruction_ref","INS:A"),("instruction_ref","INS:DAILY-ONE\n"),("instruction_ref","INS:lower"),
    ("text"," \t\n"),("text","\x00private"),("text","\x7f"),("text","x"*4097),("text","\ud800"),("text",True)])
def test_bad_authored_identity_and_text_fail_closed(field,bad):
    value={"instruction_ref":"INS:DAILY-ONE","text":"Do bounded work"};value[field]=bad
    with pytest.raises(ValueError,match="^source_unavailable$"):wire.authored_instruction(value)


@pytest.mark.parametrize("mutate",[
    lambda x:x.update(active=True),lambda x:x["source"].update(commit="A"*40),
    lambda x:x["source"].update(path="agentos/workstreams/WS-FOREIGN.md"),
    lambda x:x["source"].update(content_sha256="b"*64+"\n"),
    lambda x:x["selection"].update(work_ref="WS:FOREIGN"),
    lambda x:x.update(reason_codes=["SOURCE_UNAVAILABLE"]),
    lambda x:x.update(declaration="ACTIVE"),lambda x:x.update(instructions=None),
    lambda x:x.update(instructions=[wire.authored_instruction({"instruction_ref":"INS:ONE","text":"Do work"})]*2),
    lambda x:x.update(instructions=[{**wire.authored_instruction({"instruction_ref":"INS:ONE","text":"Do work"}),"revision":"a"*64}]),
    lambda x:x.update(declaration="NOT_DECLARED",instructions=[wire.authored_instruction({"instruction_ref":"INS:ONE","text":"Do work"})]),
])
def test_owner_body_never_accepts_foreign_partial_or_unproven_facts(mutate):
    value=body();mutate(value)
    with pytest.raises(ValueError,match="^source_unavailable$"):wire.validate_body(value,SELECTED)


def test_whole_utf8_envelope_is_refused_instead_of_truncated():
    rows=[wire.authored_instruction({"instruction_ref":f"INS:ITEM-{n}","text":"漢"*4096}) for n in range(3)]
    with pytest.raises(ValueError,match="^source_unavailable$"):wire.validate_body(body(rows),SELECTED)
    assert wire.validate_body(body(rows[:1]),SELECTED)["instructions"]==rows[:1]


@pytest.mark.parametrize("reason",sorted(wire.REASONS))
def test_unavailable_withholds_all_content(reason):
    value=wire.unavailable(SELECTED["work_ref"],reason)
    assert value["source"] is value["declaration"] is value["instructions"] is None
    value["instructions"]=[]
    with pytest.raises(ValueError):wire.validate_body(value,SELECTED)
