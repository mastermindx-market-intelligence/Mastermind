//! Closed data selectors only. Authentication stays in the incumbent native owner.
use serde_json::Value;
fn exact(v: &Value, keys: &[&str]) -> bool {
    v.as_object().is_some_and(|o| o.len()==keys.len() && keys.iter().all(|k| o.contains_key(*k)))
}
fn hex(v: &Value,n:usize)->bool { v.as_str().is_some_and(|s|s.len()==n && s.bytes().all(|b|b.is_ascii_digit() || (b'a'..=b'f').contains(&b))) }
fn id(v: &Value)->bool { v.as_str().is_some_and(|s| !s.is_empty() && s.len()<=128 && s.as_bytes()[0].is_ascii_alphanumeric() && s.bytes().all(|b|b.is_ascii_alphanumeric() || b"_.:-".contains(&b))) }
pub fn route(operation:&str)->Result<&'static str,String> { match operation {
    "submit"=>Ok("/os/executive/project-planning/submit"),"status"=>Ok("/os/executive/project-planning/status"),
    "result"=>Ok("/os/executive/project-planning/result"),"consume"=>Ok("/os/executive/project-planning/consume"),
    "prepare_proposal"=>Ok("/os/executive/project-planning/prepare_proposal"),
    _=>Err("PROJECT_PLANNING_INPUT_INVALID".into()) } }
pub fn operation(path:&str)->Option<&'static str> { ["submit","status","result","consume","prepare_proposal"].into_iter().find(|o|route(o).ok()==Some(path)) }
pub fn validate(operation:&str,value:&Value)->Result<Value,String> {
    let invalid=||"PROJECT_PLANNING_INPUT_INVALID".to_owned();
    route(operation)?;
    let keys:&[&str]=match operation {
        "submit"=>&["operation_key","work_ref","stage","project_source","publication","private_request","grounding"],
        "prepare_proposal"=>&["operation_key","work_ref","proposal_request"],
        "consume"=>&["operation_key","work_ref","attempt_id","result_digest","consumption_operation_key"],
        _=>&["operation_key","work_ref"] };
    if !exact(value,keys) || !id(&value["operation_key"]) {return Err(invalid())}
    let work=value["work_ref"].as_str().and_then(|w|w.strip_prefix("WS:")).ok_or_else(invalid)?;
    if work.is_empty() || work.len()>128 || !work.as_bytes()[0].is_ascii_alphanumeric() || !work.bytes().all(|b|b.is_ascii_alphanumeric() || b"._-".contains(&b)) {return Err(invalid())}
    if operation=="submit" {
        let s=&value["project_source"];let p=&value["publication"];let g=&value["grounding"];
        if !matches!(value["stage"].as_str(),Some("clarify"|"plan")) || !value["private_request"].as_str().is_some_and(|s| !s.trim().is_empty() && s.len()<=32768)
            || !exact(s,&["repository","commit","path","content_sha256","request_sha256"]) || s["repository"]!="macro" || !hex(&s["commit"],40)
            || s["path"]!=format!("agentos/workstreams/WS-{work}.md") || !hex(&s["content_sha256"],64) || !hex(&s["request_sha256"],64)
            || !exact(p,&["request_id","principal_scope","event_id","receipt_sha256"]) || !hex(&p["principal_scope"],64) || !hex(&p["receipt_sha256"],64)
            || !p["event_id"].as_u64().is_some_and(|n| n>0 && n<=9_007_199_254_740_991)
            || !p["request_id"].as_str().and_then(|s|s.strip_prefix("mmos-project-create-")).is_some_and(|s|hex(&Value::String(s.into()),40))
            || !exact(g,&["mastermind_sha","macro_sha"]) || !hex(&g["mastermind_sha"],40) || !hex(&g["macro_sha"],40) {return Err(invalid())}
    }
    if operation=="prepare_proposal" {
        let p=&value["proposal_request"];let b=&p["base_source"];let s=&p["selection"];
        if !exact(p,&["schema","request_id","work_ref","expected_commit","expected_adoption","base_source","selection","result_digest"])
            || p["schema"]!="mastermind.project_plan_proposal_request.v1" || p["work_ref"]!=value["work_ref"]
            || !p["request_id"].as_str().and_then(|x|x.strip_prefix("mmos-project-plan-proposal-")).is_some_and(|x|hex(&Value::String(x.into()),40))
            || !hex(&p["expected_commit"],40) || !hex(&p["result_digest"],64)
            || !(p["expected_adoption"].is_null() || p["expected_adoption"].as_str().is_some_and(|x|x.starts_with("DEC:") && x.len()<=256 && x[4..].bytes().all(|b|b.is_ascii_uppercase()||b.is_ascii_digit()||b==b'-')))
            || !exact(s,&["work_ref","job_id","attempt_id"]) || s["work_ref"]!=value["work_ref"] || !id(&s["job_id"]) || !id(&s["attempt_id"])
            || !exact(b,&["repository","commit","path","content_sha256"]) || b["repository"]!="mastermindx-market-intelligence/macro" || !hex(&b["commit"],40)||!hex(&b["content_sha256"],64)
            || !b["path"].as_str().is_some_and(|x| x.len()<=512 && !x.contains("..") && !x.contains('\\') && (x.starts_with("agentos/workstreams/WS-")||x.starts_with("research/project-plans/")) && x.ends_with(".md")) {return Err(invalid())}
    }
    if operation=="consume" && (!id(&value["attempt_id"]) || !hex(&value["result_digest"],64) || !id(&value["consumption_operation_key"])) {return Err(invalid())}
    if serde_json::to_vec(value).map_err(|_|invalid())?.len()>57344 {return Err(invalid())}
    Ok(value.clone())
}
#[cfg(test)] mod tests {
    use super::*;
    #[test] fn closed_routes_and_rootless_original_read() {
        let request=serde_json::json!({"operation_key":"original","work_ref":"WS:EXAMPLE"});
        for op in ["status","result"] {assert_eq!(validate(op,&request).unwrap(),request)}
        assert!(route("../submit").is_err());assert!(operation("https://other/submit").is_none());
        let mut bad=request;bad["job_id"]=Value::String("JOB-made-up".into());assert!(validate("status",&bad).is_err());
    }
}
