//! Fixed project execution selectors; private credentials remain in NativeAuth.
use serde_json::Value;
fn exact(v: &Value, keys: &[&str]) -> bool {
    v.as_object().is_some_and(|o| o.len() == keys.len() && keys.iter().all(|k| o.contains_key(*k)))
}
fn hex(v: &Value, n: usize) -> bool {
    v.as_str().is_some_and(|s| s.len() == n && s.bytes().all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b)))
}
fn work(v: &Value) -> Option<&str> {
    let s = v.as_str()?.strip_prefix("WS:")?;
    if s.len() < 2 || s.len() > 64 || s.split('-').any(|x| x.is_empty() ||
        !x.bytes().all(|b| b.is_ascii_uppercase() || b.is_ascii_digit())) { None } else { Some(s) }
}
fn relative(s: &str) -> bool {
    !s.is_empty() && s.len() <= 512 && !s.contains(['\\','\0','\r','\n']) &&
        s.split('/').all(|x| !x.is_empty() && !matches!(x,"."|".."|".git"))
}
fn source(v: &Value) -> bool {
    exact(v,&["repository","commit","path","content_sha256"]) &&
    matches!(v["repository"].as_str(),Some("mastermindx-market-intelligence/macro"|"mastermindx-market-intelligence/Mastermind")) &&
    hex(&v["commit"],40) && hex(&v["content_sha256"],64) &&
    v["path"].as_str().is_some_and(|s| relative(s) && s.ends_with(".md"))
}
pub fn route(operation: &str) -> Result<&'static str,String> {
    match operation {
        "preview" => Ok("/os/executive/project-execution/preview"),
        "submit" => Ok("/os/executive/project-execution/submit"),
        "status" => Ok("/os/executive/project-execution/status"),
        _ => Err("PROJECT_EXECUTION_INPUT_INVALID".into()),
    }
}
pub fn operation(path: &str) -> Option<&'static str> {
    ["preview","submit","status"].into_iter().find(|o| route(o).ok() == Some(path))
}
/// Completion evidence only. Runtime independently binds this to the actual prior run.
pub fn validate_previous_run(v: &Value) -> Result<Value, String> {
    let valid = exact(v, &["schema", "root_job_id", "root_event_id", "root_event_sha256",
        "project_execution_source_sha256", "input_fingerprint_sha256", "attempt_id",
        "result_envelope_sha256", "terminal_receipt_sha256"]) &&
        v["schema"] == "mastermind.project_execution_parent.v1" &&
        v["root_job_id"].as_str().and_then(|s| s.strip_prefix("JOB-"))
            .is_some_and(|s| !s.is_empty() && s.bytes().all(|b| b.is_ascii_digit())) &&
        v["root_event_id"].as_u64().is_some_and(|n| n > 0 && n < (1u64 << 53)) &&
        v["attempt_id"].as_str().is_some_and(|s| !s.is_empty() && s.chars().count() <= 128 &&
            s.chars().all(|c| (c as u32) >= 32)) &&
        ["root_event_sha256", "project_execution_source_sha256", "input_fingerprint_sha256",
            "result_envelope_sha256", "terminal_receipt_sha256"].into_iter().all(|key| hex(&v[key], 64));
    if !valid { return Err("PROJECT_EXECUTION_INPUT_INVALID".into()); }
    Ok(v.clone())
}
pub fn validate(operation: &str, v: &Value) -> Result<Value,String> {
    let invalid = || "PROJECT_EXECUTION_INPUT_INVALID".to_owned();
    route(operation)?;
    let mut keys = vec!["operation_key","work_ref"];
    if operation != "status" {
        keys.push("expected_context");
        if let Some(previous) = v.get("previous_run") {
            keys.push("previous_run");
            validate_previous_run(previous)?;
        }
    }
    if operation == "submit" {
        keys.extend(["context_sha256","execution_binding_sha256","execution_profile","objective","handoff_text","continuation_mode"]);
        for key in ["allowed_write_paths","validation"] {
            if v.get(key).is_some() { keys.push(key); }
        }
    }
    let work = work(&v["work_ref"]).ok_or_else(invalid)?;
    let prefix = if operation == "preview" { "mmos-project-preview-" } else { "mmos-project-execute-" };
    if !exact(v,&keys) || !v["operation_key"].as_str().and_then(|s|s.strip_prefix(prefix))
        .is_some_and(|s|hex(&Value::String(s.into()),40)) { return Err(invalid()); }
    if operation != "status" {
        let c = &v["expected_context"];
        if !exact(c,&["record_source","adoption","adoption_decision_source"]) || !source(&c["record_source"]) ||
            c["record_source"]["repository"] != "mastermindx-market-intelligence/macro" ||
            c["record_source"]["path"] != format!("agentos/workstreams/WS-{work}.md") { return Err(invalid()); }
        let adoption = &c["adoption"];
        match adoption["state"].as_str() {
            None if adoption.is_null() && c["adoption_decision_source"].is_null() => {},
            Some("UNAVAILABLE") if exact(adoption,&["state","reason"]) &&
                matches!(adoption["reason"].as_str(),Some("SOURCE_UNAVAILABLE"|"NOT_DECLARED"|"LINEAGE_INVALID"|"PROPOSAL_MISMATCH"|"CONTENT_OVER_BUDGET")) &&
                c["adoption_decision_source"].is_null() => {},
            Some("AVAILABLE") => {
                let decision = adoption["decision_ref"].as_str().and_then(|s|s.strip_prefix("DEC:")).ok_or_else(invalid)?;
                if decision.is_empty() || decision.split('-').any(|x|x.is_empty() ||
                    !x.bytes().all(|b|b.is_ascii_uppercase() || b.is_ascii_digit())) ||
                    !exact(adoption,&["state","decision_ref","adopted_source","display_revision","matches_authored_record"]) ||
                    !source(&adoption["adopted_source"]) || !adoption["matches_authored_record"].is_boolean() ||
                    !(adoption["display_revision"].is_null() || adoption["display_revision"].as_str().is_some_and(|s|!s.trim().is_empty() && s.chars().count()<=128)) ||
                    !source(&c["adoption_decision_source"]) ||
                    c["adoption_decision_source"]["repository"] != "mastermindx-market-intelligence/macro" ||
                    c["adoption_decision_source"]["path"] != format!("agentos/decisions/DEC-{decision}.md") {return Err(invalid());}
            },
            _ => return Err(invalid()),
        }
    }
    if operation == "submit" {
        if !hex(&v["context_sha256"],64) || !hex(&v["execution_binding_sha256"],64) ||
            !matches!(v["continuation_mode"].as_str(),Some("DURABLE"|"ATTENDED")) ||
            !matches!(v["execution_profile"].as_str(),Some("research_only"|"bounded_code_change")) ||
            !v["objective"].as_str().is_some_and(|s|!s.trim().is_empty() && !s.contains('\0') && s.chars().count()<=4000) ||
            !(v["handoff_text"].is_null() || v["handoff_text"].as_str().is_some_and(|s|s.len()<=32768 && !s.contains('\0'))) {return Err(invalid());}
        if let Some(paths) = v.get("allowed_write_paths") {
            if !paths.as_array().is_some_and(|xs| xs.len()<=16 && xs.iter().all(|x|x.as_str().is_some_and(|s|
                s.len()<=256 && relative(s) && !s.contains(['*','?'])))) {return Err(invalid());}
        }
        if let Some(validation) = v.get("validation") {
            if !validation.as_object().is_some_and(|o|o.keys().all(|k|matches!(k.as_str(),"pytest_targets"|"compileall_paths"|"git_diff_check"))) {return Err(invalid());}
            for key in ["pytest_targets","compileall_paths"] {
                if let Some(targets) = validation.get(key) {
                    if !targets.as_array().is_some_and(|xs|xs.len()<=8 && xs.iter().all(|x|x.as_str()
                        .is_some_and(|s| !s.trim().is_empty() && s.len()<=256))) {return Err(invalid());}
                }
            }
            if validation.get("git_diff_check").is_some_and(|x| !x.is_boolean()) {return Err(invalid());}
        }
        let writes = v["allowed_write_paths"].as_array().is_some_and(|x|!x.is_empty());
        let checks = v["validation"]["git_diff_check"] == true ||
            ["pytest_targets","compileall_paths"].iter().any(|key|v["validation"][key].as_array().is_some_and(|x|!x.is_empty()));
        if if v["execution_profile"] == "bounded_code_change" { !writes || !checks } else { writes || checks } {return Err(invalid());}
    }
    if serde_json::to_vec(v).map_err(|_|invalid())?.len() > 57344 {return Err(invalid());}
    Ok(v.clone())
}
pub fn is_refusal(v: &Value, operation: &str) -> bool {
    exact(v,&["schema","operation","ok","data","error"]) &&
    v["schema"]=="mastermind.project_execution_private_result.v1" && v["operation"]==operation &&
    v["ok"]==false && v["data"].is_null() && exact(&v["error"],&["code","message"]) &&
    v["error"]["code"].is_string() && v["error"]["message"].is_string()
}
#[cfg(test)] mod tests {
    use super::*;
    fn submit() -> Value { serde_json::json!({
        "operation_key":format!("mmos-project-execute-{}","a".repeat(40)),"work_ref":"WS:NEW-PROJECT",
        "expected_context":{"record_source":{"repository":"mastermindx-market-intelligence/macro","commit":"b".repeat(40),
            "path":"agentos/workstreams/WS-NEW-PROJECT.md","content_sha256":"c".repeat(64)},"adoption":null,"adoption_decision_source":null},
        "context_sha256":"d".repeat(64),"execution_binding_sha256":"e".repeat(64),
        "execution_profile":"bounded_code_change","objective":"Complete the project","handoff_text":"Original handoff","continuation_mode":"DURABLE",
        "allowed_write_paths":["app/example"],"validation":{"git_diff_check":true}
    }) }
    fn previous_run() -> Value {
        serde_json::json!({
            "schema": "mastermind.project_execution_parent.v1", "root_job_id": "JOB-123",
            "root_event_id": 42, "root_event_sha256": "a".repeat(64),
            "project_execution_source_sha256": "b".repeat(64), "input_fingerprint_sha256": "c".repeat(64),
            "attempt_id": "ATTEMPT-123", "result_envelope_sha256": "d".repeat(64),
            "terminal_receipt_sha256": "e".repeat(64)
        })
    }
    #[test] fn previous_run_is_optional_exact_evidence_only_on_preview_and_submit() {
        let mut value = submit(); value["previous_run"] = previous_run();
        assert_eq!(validate("submit", &value).unwrap(), value);
        let preview = serde_json::json!({
            "operation_key": format!("mmos-project-preview-{}", "a".repeat(40)),
            "work_ref": value["work_ref"], "expected_context": value["expected_context"],
            "previous_run": previous_run()
        });
        assert_eq!(validate("preview", &preview).unwrap(), preview);
        let status = serde_json::json!({
            "operation_key": value["operation_key"], "work_ref": value["work_ref"], "previous_run": previous_run()
        });
        assert!(validate("status", &status).is_err());
        value["previous_run"] = Value::Null;
        assert!(validate("submit", &value).is_err());
    }
    #[test] fn malformed_previous_run_does_not_become_an_execution_selector() {
        for (key, bad) in [
            ("root_job_id", serde_json::json!("JOB-foreign")),
            ("root_event_id", serde_json::json!(0)),
            ("root_event_id", serde_json::json!(true)),
            ("root_event_id", serde_json::json!(9007199254740992u64)),
            ("attempt_id", serde_json::json!("ATTEMPT\nforeign")),
            ("attempt_id", serde_json::json!("x".repeat(129))),
            ("result_envelope_sha256", serde_json::json!("F".repeat(64))),
            ("terminal_receipt_sha256", serde_json::json!("short")),
        ] {
            let mut value = previous_run(); value[key] = bad;
            assert!(validate_previous_run(&value).is_err());
        }
        let mut value = previous_run(); value["work_ref"] = "WS:FORGED".into();
        assert!(validate_previous_run(&value).is_err());
        let mut value = previous_run(); value.as_object_mut().unwrap().remove("input_fingerprint_sha256");
        assert!(validate_previous_run(&value).is_err());
    }
    #[test] fn exact_routes_and_original_status() {
        assert!(route("../submit").is_err()); assert!(operation("/os/executive/submit").is_none());
        let mut value=serde_json::json!({"operation_key":format!("mmos-project-execute-{}","a".repeat(40)),"work_ref":"WS:NEW-PROJECT"});
        assert!(validate("status",&value).is_ok());
        value["job_id"]="JOB-invented".into(); assert!(validate("status",&value).is_err());
    }
    #[test] fn closed_requested_scope_and_source() {
        let value=submit(); assert!(validate("submit",&value).is_ok());
        for path in ["../outside","/absolute",".git/config","app/*"] {
            let mut bad=value.clone();bad["allowed_write_paths"]=serde_json::json!([path]);assert!(validate("submit",&bad).is_err());
        }
        let mut bad=value.clone();bad["expected_context"]["record_source"]["path"]="agentos/workstreams/WS-OTHER.md".into();
        assert!(validate("submit",&bad).is_err());
        let mut bad=value.clone();bad["validation"]=serde_json::json!({});assert!(validate("submit",&bad).is_err());
        let mut bad=value;bad["endpoint"]="https://foreign".into();assert!(validate("submit",&bad).is_err());
    }
}
