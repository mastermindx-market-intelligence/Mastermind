//! One fixed Acquisition READ; the typed host validates the entire public body.
use super::{AppHandle,Manager,NativeAuth,Resource,Result,Url,Value,Duration,
    ProjectPlanSelection,ORIGIN,ensure_native_token,read_json_body,bounded_json};
fn target(selection:&ProjectPlanSelection)->Result<Url>{
    selection.validate()?;
    let mut url=Url::parse(&format!("{ORIGIN}/workspace/project-access/current")).map_err(|_|"REQUEST_INVALID")?;
    url.query_pairs_mut().append_pair("work_ref",&selection.work_ref);Ok(url)
}
fn header(body:&Value,selection:&ProjectPlanSelection)->bool{
    matches!(body.get("schema").and_then(Value::as_str),Some("mastermind.workspace_project_access.v1"|"mastermind.workspace_project_access.v2"))
        &&body.get("selection")==Some(&serde_json::json!({"work_ref":selection.work_ref}))
}
#[tauri::command]
pub async fn read_project_access(app:AppHandle,selection:ProjectPlanSelection)->Result<Value>{
    let url=target(&selection)?;
    let state=app.state::<NativeAuth>();let before=state.lock()?.generation;
    let(token,generation)=ensure_native_token(&app,Resource::Acquisition).await?;
    if before!=generation||!state.lock()?.release_allowed(generation,Resource::Acquisition){return Err("AUTHENTICATION_CHANGED".into());}
    let response=state.http.get(url).bearer_auth(token).header("Accept","application/json").header("Cache-Control","no-store")
        .timeout(Duration::from_secs(30)).send().await.map_err(|_|"SOURCE_UNAVAILABLE")?;
    let result=if response.status().as_u16()==503{read_json_body(response,16_384).await}else{bounded_json(response,16_384).await};
    if !state.lock()?.release_allowed(generation,Resource::Acquisition){return Err("AUTHENTICATION_CHANGED".into());}
    let body=result?;if !header(&body,&selection){return Err("RESPONSE_INVALID".into());}Ok(body)
}
#[cfg(test)]
mod project_access_tests{
    use super::*;
    #[test]
    fn fixed_read_selection_and_exact_header(){
        let selection:ProjectPlanSelection=serde_json::from_value(serde_json::json!({"work_ref":"WS:ONE"})).unwrap();
        let url=target(&selection).unwrap();assert_eq!(url.origin().ascii_serialization(),ORIGIN);
        assert_eq!(url.path(),"/workspace/project-access/current");assert_eq!(url.query_pairs().collect::<Vec<_>>(),vec![("work_ref".into(),"WS:ONE".into())]);
        assert!(serde_json::from_value::<ProjectPlanSelection>(serde_json::json!({"work_ref":"WS:ONE","principal":"forged"})).is_err());
        let mut body=serde_json::json!({"schema":"mastermind.workspace_project_access.v1","selection":{"work_ref":"WS:ONE"}});assert!(header(&body,&selection));
        body["schema"]=Value::String("mastermind.workspace_project_access.v2".into());assert!(header(&body,&selection));
        body["schema"]=Value::String("mastermind.workspace_project_access.v3".into());assert!(!header(&body,&selection));
        body["schema"]=Value::String("mastermind.workspace_project_access.v2".into());body["selection"]["work_ref"]=Value::String("WS:OTHER".into());assert!(!header(&body,&selection));
        body["selection"]=serde_json::json!({"work_ref":"WS:ONE","root_job_id":"JOB-FOREIGN"});assert!(!header(&body,&selection));
    }
}
