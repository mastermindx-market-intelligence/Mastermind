//! Fixed READ selectors only. Authentication and source ownership stay in the
//! incumbent Executive transport and private reader, never in these DTOs.
use serde_json::Value;

const INVALID: &str = "REQUEST_INVALID";
const ROUTES: [(&str, &str); 6] = [
    ("/os/executive/session/conversations", "catalogue"),
    ("/os/executive/session/conversation-read", "read"),
    ("/os/executive/session/fresh-conversations", "fresh_references"),
    ("/os/executive/session/fresh-conversation-read", "fresh_read"),
    ("/os/executive/session/project-executions", "execution_references"),
    ("/os/executive/session/project-execution-read", "execution_read"),
];
pub fn operation(path: &str) -> Option<&'static str> {
    ROUTES.iter().find(|(p, _)| *p == path).map(|(_, op)| *op)
}
pub fn path(op: &str) -> Option<&'static str> {
    ROUTES.iter().find(|(_, operation)| *operation == op).map(|(p, _)| *p)
}
fn exact(value: &Value, keys: &[&str]) -> bool {
    value.as_object().is_some_and(|o| o.len() == keys.len() && keys.iter().all(|k| o.contains_key(*k)))
}
fn text(value: &Value, key: &str, check: impl FnOnce(&str) -> bool) -> bool {
    value.get(key).and_then(Value::as_str).is_some_and(check)
}
fn hex(s: &str) -> bool {
    s.len() == 64 && s.bytes().all(|c| c.is_ascii_digit() || (b'a'..=b'f').contains(&c))
}
fn tagged_hex(s: &str, prefix: &str) -> bool {
    s.strip_prefix(prefix).is_some_and(hex)
}
fn work(s: &str, fresh: bool) -> bool {
    let Some(body) = s.strip_prefix("WS:") else { return false };
    if fresh {
        (1..=69).contains(&body.len()) && body.as_bytes()[0].is_ascii_alphanumeric()
            && body.bytes().all(|c| c.is_ascii_alphanumeric() || matches!(c,b'.'|b'_'|b'-'))
    } else {
        (2..=64).contains(&body.len()) && body.split('-').all(|part|
            !part.is_empty() && part.bytes().all(|c| c.is_ascii_uppercase() || c.is_ascii_digit()))
    }
}
pub fn validate(op: &str, value: &Value) -> Result<(), String> {
    let valid = match op {
        "catalogue" => value.as_object().is_some_and(|o|
            o.contains_key("work_ref") && o.keys().all(|k| matches!(k.as_str(),"work_ref"|"cursor")))
            && text(value,"work_ref",|s|work(s,false))
            && value.get("cursor").is_none_or(|v| v.is_null() || v.as_str().is_some_and(|s|
                (1..=2048).contains(&s.len()) && s.bytes().all(|c|c.is_ascii_alphanumeric() || matches!(c,b'_'|b'='|b'-')))),
        "read" => exact(value,&["work_ref","conversation_ref","revision","requests"])
            && text(value,"work_ref",|s|work(s,false))
            && text(value,"conversation_ref",|s|tagged_hex(s,"conversation-"))
            && text(value,"revision",hex)
            && value["requests"].as_array().is_some_and(|rows| {
                let mut seen = std::collections::HashSet::new();
                (1..=4).contains(&rows.len()) && rows.iter().all(|row|
                    exact(row,&["read_ref","request_revision"])
                    && text(row,"request_revision",hex)
                    && text(row,"read_ref",|s|tagged_hex(s,"session-reply-") && seen.insert(s.to_owned())))
            }),
        "execution_references" => exact(value,&["work_ref"]) && text(value,"work_ref",|s|work(s,false)),
        "execution_read" => exact(value,&["schema","work_ref","root_job_id","root_event_id",
            "root_event_sha256","project_execution_source_sha256","principal_scope_sha256"])
            && value["schema"].as_str()==Some("mastermind.project_execution_reference.v1")
            && text(value,"work_ref",|s|work(s,false))
            && text(value,"root_job_id",|s| s.len()<=256 && s.strip_prefix("JOB-").is_some_and(|id|
                !id.is_empty() && id.bytes().all(|c|c.is_ascii_digit())))
            && value["root_event_id"].as_u64().is_some_and(|n|(1..=9_007_199_254_740_991).contains(&n))
            && text(value,"root_event_sha256",hex) && text(value,"project_execution_source_sha256",hex)
            && text(value,"principal_scope_sha256",hex),
        "fresh_references" => exact(value,&["work_ref"]) && text(value,"work_ref",|s|work(s,true)),
        "fresh_read" => exact(value,&["schema","work_ref","root_job_id","root_event_id","root_event_sha256","principal_scope_sha256"])
            && value["schema"].as_str()==Some("mastermind.fresh_conversation_reference.v1")
            && text(value,"work_ref",|s|work(s,true))
            && text(value,"root_job_id",|s| s.len()<=256 && s.strip_prefix("JOB-").is_some_and(|id|
                !id.is_empty() && id.bytes().all(|c|c.is_ascii_digit())))
            && value["root_event_id"].as_u64().is_some_and(|n|(1..=9_007_199_254_740_991).contains(&n))
            && text(value,"root_event_sha256",hex) && text(value,"principal_scope_sha256",hex),
        _ => false,
    };
    if valid && serde_json::to_vec(value).is_ok_and(|bytes|bytes.len()<=4096) {Ok(())}
    else {Err(INVALID.into())}
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;
    fn reference() -> Value {json!({"schema":"mastermind.fresh_conversation_reference.v1",
        "work_ref":"WS:project.a_1", "root_job_id":"JOB-12", "root_event_id":1,
        "root_event_sha256":"a".repeat(64),"principal_scope_sha256":"b".repeat(64)})}
    fn read() -> Value {json!({"work_ref":"WS:AB-CD", "conversation_ref":format!("conversation-{}","a".repeat(64)),
        "revision":"b".repeat(64), "requests":[{"read_ref":format!("session-reply-{}","c".repeat(64)),"request_revision":"d".repeat(64)}]})}
    #[test] fn fixed_routes_and_closed_selectors() {
        for (route,op) in ROUTES {assert_eq!(operation(route),Some(op));assert_eq!(path(op),Some(route));
            assert!(operation(&(route.to_owned()+"/extra")).is_none());}
        for (op,value) in [("catalogue",json!({"work_ref":"WS:AB"})),("read",read()),
            ("fresh_references",json!({"work_ref":"WS:a"})),("fresh_read",reference())] {
            assert!(validate(op,&value).is_ok());let mut extra=value.clone();extra["target"]="foreign".into();
            assert_eq!(validate(op,&extra),Err(INVALID.into()));
        }
        assert!(validate("submit",&json!({})).is_err());
    }
    #[test] fn catalogue_legacy_grammar_and_cursor_bounds() {
        for work_ref in ["WS:A","WS:ab","WS:-AB","WS:AB-","WS:AB--CD","WS:AB.CD"] {
            assert!(validate("catalogue",&json!({"work_ref":work_ref})).is_err());
        }
        for cursor in [Value::Null,json!("A_=-"),json!("x".repeat(2048))] {
            assert!(validate("catalogue",&json!({"work_ref":"WS:AB","cursor":cursor})).is_ok());
        }
        for cursor in [json!(""),json!("a/"),json!("x".repeat(2049)),json!(1)] {
            assert!(validate("catalogue",&json!({"work_ref":"WS:AB","cursor":cursor})).is_err());
        }
    }
    #[test] fn requests_are_bounded_unique_exact_and_hash_qualified() {
        let mut value=read();let row=value["requests"][0].clone();
        value["requests"]=json!([row.clone(),row]);assert!(validate("read",&value).is_err());
        value["requests"]=json!([]);assert!(validate("read",&value).is_err());
        value=read();value["requests"][0]["request_revision"]="A".repeat(64).into();assert!(validate("read",&value).is_err());
        value=read();value["requests"][0]["extra"]=true.into();assert!(validate("read",&value).is_err());
    }

    fn execution_reference() -> Value {json!({
        "schema":"mastermind.project_execution_reference.v1","work_ref":"WS:PROJECT-ONE",
        "root_job_id":"JOB-123","root_event_id":42,"root_event_sha256":"a".repeat(64),
        "project_execution_source_sha256":"b".repeat(64),"principal_scope_sha256":"c".repeat(64)
    })}
    #[test] fn project_execution_reads_are_closed_and_preserve_original_reference() {
        assert_eq!(path("execution_references"), Some("/os/executive/session/project-executions"));
        assert_eq!(path("execution_read"), Some("/os/executive/session/project-execution-read"));
        assert!(validate("execution_references", &json!({"work_ref":"WS:PROJECT-ONE"})).is_ok());
        assert!(validate("execution_read", &execution_reference()).is_ok());
        for extra in ["cursor","operation_key","target_ref","principal","send"] {
            let mut value=execution_reference(); value[extra]=json!("not-a-read-selector");
            assert!(validate("execution_read", &value).is_err());
        }
        assert!(validate("fresh_read", &execution_reference()).is_err());
        assert!(validate("execution_read", &reference()).is_err());
        assert!(validate("execution_references", &json!({"work_ref":"WS:PROJECT-ONE","cursor":null})).is_err());
    }
    #[test] fn project_execution_read_refuses_foreign_reference_shape_before_dispatch() {
        for (key,bad) in [
            ("work_ref",json!("WS:project.a_1")),
            ("root_job_id",json!("JOB-fabric")),
            ("root_event_id",json!(true)),
            ("root_event_id",json!(0)),
            ("root_event_id",json!(1.0)),
            ("root_event_id",json!(9_007_199_254_740_992u64)),
            ("root_event_sha256",json!("A".repeat(64))),
            ("project_execution_source_sha256",json!("short")),
            ("principal_scope_sha256",Value::Null),
        ] {
            let mut value=execution_reference(); value[key]=bad;
            assert!(validate("execution_read", &value).is_err());
        }
        let mut value=execution_reference();value.as_object_mut().unwrap().remove("project_execution_source_sha256");
        assert!(validate("execution_read", &value).is_err());
        for work_ref in ["WS:A","WS:ab","WS:AB--CD","WS:AB.CD"] {
            assert!(validate("execution_references", &json!({"work_ref":work_ref})).is_err());
        }
    }

    #[test] fn fresh_reference_int53_and_closed_immutable_identity() {
        for id in [json!(0),json!(-1),json!(1.0),json!(true),json!(9_007_199_254_740_992u64)] {
            let mut value=reference();value["root_event_id"]=id;assert!(validate("fresh_read",&value).is_err());
        }
        let mut value=reference();value["root_event_id"]=json!(9_007_199_254_740_991u64);assert!(validate("fresh_read",&value).is_ok());
        for id in ["JOB-x","JOB-","foreign","JOB-1/2"] {
            let mut value=reference();value["root_job_id"]=id.into();assert!(validate("fresh_read",&value).is_err());
        }
        let mut value=reference();value["operation_key"]="original".into();assert!(validate("fresh_read",&value).is_err());
    }
}
