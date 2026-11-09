"""Closed one-account event enrollment within the incumbent MCP update transaction."""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from ops.executive_os import mcp_component_update as m
from test_mcp_component_update import (
    FakeHost, Crash, NEW_RELEASE, PRIOR_CONFIG, PRIOR_PLIST,
    prior_mcp_document, mcp_bytes,
)


def chris(subject="1"*64, **overrides):
    value={
        "armed":True,
        "subject_digest":subject,
        "workspace_id":"T0BRD2AQXQV",
        "channel_id":"C0BSBM78V1N",
        "relay_bot_user_id":"U0BT71H4FQE",
        "owner_slack_user_id":"U0BRET6191C",
        "not_before_ts":"1794017500.000001",
    }
    value.update(overrides)
    return value


def input_pair(tmp_path, config=None):
    filename=tmp_path/"chris.json"
    data=(json.dumps(chris() if config is None else config,
          sort_keys=True,separators=(",",":"))+"\n").encode()
    filename.write_bytes(data)
    filename.chmod(0o600)
    return str(filename),hashlib.sha256(data).hexdigest()


def planned(host,path,digest):
    return m.plan(host,release_sha=NEW_RELEASE,set_public=False,
                  canary_input=path,canary_sha256=digest)


def test_existing_original_source_only_mcp_update_unchanged():
    host=FakeHost()
    before=m.plan(host,release_sha=NEW_RELEASE,set_public=False)
    assert before["ok"] and "chris_dot_enrollment_sha256" not in before["plan"]
    candidate=m.compile_candidate(PRIOR_CONFIG,PRIOR_PLIST,
        release_sha=NEW_RELEASE,set_public_mcp_resource=False)
    output=json.loads(candidate.config_after)
    assert "dot_canary" not in output and "reply_events_armed" not in output
    assert not host.log and not host.events


def test_original_root_input_to_original_marker_and_single_installed_grant(tmp_path):
    path,digest=input_pair(tmp_path)
    host=FakeHost()
    receipt=planned(host,path,digest)
    assert receipt["outcome"]=="PLANNED"
    assert receipt["plan"]["chris_dot_enrollment_sha256"]==m.digest(m.canonical(chris()))
    assert "subject_digest" not in json.dumps(receipt["plan"])
    assert not host.log and host.config==PRIOR_CONFIG
    installed=m.apply(host,release_sha=NEW_RELEASE,set_public=False,
        plan_sha256=receipt["plan_sha256"],canary_input=path,canary_sha256=digest)
    assert installed["outcome"]=="COMPLETE"
    config=json.loads(host.config)
    assert config["dot_canary"]==chris()
    assert config["reply_events_armed"] is True
    assert config["policies"]==prior_mcp_document()["policies"]
    assert host.count("stop_service")==host.count("start_service")==1
    assert host.marker is None
    data=list(host.receipts.values())
    assert len(data)==1
    assert data[0]["chris_dot_enrollment_sha256"]==receipt["plan"]["chris_dot_enrollment_sha256"]
    assert "subject_digest" not in json.dumps(data[0])


@pytest.mark.parametrize("updates",[
    {"workspace_id":"T0BWRONG0000"},
    {"channel_id":"C0BWRONG0000"},
    {"relay_bot_user_id":"U0BWRONG0000"},
    {"owner_slack_user_id":"U0BWRONG0000"},
    {"subject_digest":"invalid"},
    {"not_before_ts":"invalid"},
    {"armed":False},
    {"unexpected":True},
])
def test_foreign_chris_identity_or_invalid_source_refuses_before_effect(tmp_path,updates):
    path,digest=input_pair(tmp_path,chris(**updates))
    host=FakeHost()
    with pytest.raises((m.UpdateRefused,ValueError)):
        planned(host,path,digest)
    assert host.log==[] and host.config==PRIOR_CONFIG and host.marker is None


def test_add_only_enrollment_refuses_overwriting_a_current_grant(tmp_path):
    path,digest=input_pair(tmp_path)
    host=FakeHost(config=mcp_bytes(prior_mcp_document(
        reply_events_armed=True,dot_canary=chris())))
    with pytest.raises(m.UpdateRefused):
        planned(host,path,digest)
    assert not host.log


def test_wrong_byte_digest_and_changed_input_fail_closed(tmp_path):
    path,digest=input_pair(tmp_path)
    host=FakeHost()
    with pytest.raises(m.UpdateRefused):
        planned(host,path,"f"*64 if digest!="f"*64 else "e"*64)
    first=planned(host,path,digest)
    Path(path).write_text(json.dumps(chris(subject="2"*64)))
    with pytest.raises(m.UpdateRefused):
        m.apply(host,release_sha=NEW_RELEASE,set_public=False,
                plan_sha256=first["plan_sha256"],
                canary_input=path,canary_sha256=digest)
    assert host.log==[]


def test_stop_effect_unknown_recovers_original_grant_without_reopening_input(tmp_path):
    path,digest=input_pair(tmp_path)
    host=FakeHost()
    first=planned(host,path,digest)
    def interrupt(_): raise Crash("after original stop")
    host.hooks[("stop_service",1)]=interrupt
    with pytest.raises(Crash):
        m.apply(host,release_sha=NEW_RELEASE,set_public=False,
                plan_sha256=first["plan_sha256"],
                canary_input=path,canary_sha256=digest)
    assert host.count("stop_service")==1
    assert host.marker["chris_dot_enrollment"]==chris()
    Path(path).unlink()
    host.hooks.clear()
    source_reads=host.events.count("read_selected_child_input")
    recovered=m.reconcile(host,release_sha=NEW_RELEASE)
    assert recovered["outcome"]=="COMPLETE"
    assert host.events.count("read_selected_child_input")==source_reads
    assert host.count("stop_service")==1
    assert json.loads(host.config)["dot_canary"]==chris()


def test_malformed_frozen_grant_cannot_continue_a_partial_effect(tmp_path):
    path,digest=input_pair(tmp_path)
    host=FakeHost()
    first=planned(host,path,digest)
    host.hooks[("stop_service",1)]=lambda _: (_ for _ in ()).throw(Crash("stop"))
    with pytest.raises(Crash):
        m.apply(host,release_sha=NEW_RELEASE,set_public=False,
                plan_sha256=first["plan_sha256"],
                canary_input=path,canary_sha256=digest)
    host.hooks.clear()
    host.marker["chris_dot_enrollment"]["subject_digest"]="wrong"
    with pytest.raises(m.TransactionEffectUnknown):
        m.reconcile(host,release_sha=NEW_RELEASE)
    assert host.count("stop_service")==1 and host.marker is not None


@pytest.mark.parametrize("arguments",[
    ["plan","--release-sha",NEW_RELEASE,
     "--chris-dot-canary-input","/full/path"],
    ["apply","--release-sha",NEW_RELEASE,
     "--plan-sha256","a"*64,"--chris-dot-canary-sha256","b"*64],
    ["reconcile","--release-sha",NEW_RELEASE,
     "--chris-dot-canary-input","/full/path","--chris-dot-canary-sha256","a"*64],
    ["plan","--release-sha",NEW_RELEASE,
     "--chris-dot-canary-input","/../bad","--chris-dot-canary-sha256","a"*64],
    ["plan","--release-sha",NEW_RELEASE,
     "--chris-dot-canary-input","/full/path","--chris-dot-canary-sha256","invalid"],
])
def test_no_partial_or_reconciliation_account_override(arguments):
    with pytest.raises(m.UsageError):
        m.parse_arguments(arguments)


def test_same_mcp_command_line_dispatches_only_original_transaction(tmp_path,capsys):
    path,digest=input_pair(tmp_path)
    host=FakeHost()
    args=["plan","--release-sha",NEW_RELEASE,
          "--chris-dot-canary-input",path,"--chris-dot-canary-sha256",digest]
    assert m.main(args,host=host)==0
    approved=json.loads(capsys.readouterr().out)
    args=["apply","--release-sha",NEW_RELEASE,
          "--plan-sha256",approved["plan_sha256"],
          "--chris-dot-canary-input",path,"--chris-dot-canary-sha256",digest]
    assert m.main(args,host=host)==0
    assert json.loads(capsys.readouterr().out)["outcome"]=="COMPLETE"


def test_original_service_control_accepts_only_the_exact_chris_pair():
    source=(Path(__file__).resolve().parents[1] /
            "ops/executive_os/service-control.sh").read_text()
    start=source.index("mcp_component_args() {")
    end=source.index("\n}\n",start)+2
    function=source[start:end]
    path="/trusted/chris-account-grant.json"
    sha="a"*64
    prefix='''set -e
valid_component_input_path() { [[ "$1" == /* && "$1" != *".."* ]]; }
''' + function + "\n"
    requested=["plan-mcp-component","--expected-sha",NEW_RELEASE,
               "--chris-dot-canary-input",path,
               "--chris-dot-canary-sha256",sha]
    command=prefix+"mcp_component_args "+ " ".join(requested)+"\n"
    result=subprocess.run(["/bin/bash","-c",command],
                          capture_output=True,text=True)
    assert result.returncode==0,result.stderr
    array_expansion=chr(36)+"{MCP_COMPONENT_ARGV[@]}"
    output=subprocess.run(["/bin/bash","-c",command+
                           'printf "%s\\n" "'+array_expansion+'"\n'],
                          capture_output=True,text=True)
    assert output.returncode==0,output.stderr
    assert output.stdout.splitlines()==[
        "plan","--release-sha",NEW_RELEASE,
        "--chris-dot-canary-input",path,"--chris-dot-canary-sha256",sha]
    for bad in (requested[:-2],requested[:3]+requested[5:],
                ["reconcile-mcp-component","--expected-sha",NEW_RELEASE,
                 "--chris-dot-canary-input",path,
                 "--chris-dot-canary-sha256",sha],
                requested+["--owner-slack-user-id","UFOREIGN"]):
        denied=subprocess.run(["/bin/bash","-c",prefix+
                               "mcp_component_args "+" ".join(bad)+"\n"],
                              capture_output=True,text=True)
        assert denied.returncode!=0
