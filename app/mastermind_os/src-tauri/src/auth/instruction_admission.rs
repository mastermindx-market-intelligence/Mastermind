//! Fixed instruction reads/action. Existing auth owner retains every bearer.
use super::{AppHandle,Manager,NativeAuth,Resource,Result,Url,Value,Duration,Deserialize,Serialize,
    ProjectPlanSelection,lowercase_hex,ORIGIN,ensure_native_token,read_json_body,bounded_json};

#[derive(Clone,Deserialize,Serialize)]
#[serde(deny_unknown_fields)]
pub struct InstructionSelection {work_ref:String,instruction_ref:String}
impl InstructionSelection {
    fn validate(&self)->Result<()> {
        ProjectPlanSelection{work_ref:self.work_ref.clone()}.validate()?;
        let key=self.instruction_ref.strip_prefix("INS:").ok_or("REQUEST_INVALID")?;
        if !(2..=64).contains(&key.len()) || !key.split('-').all(|part|!part.is_empty()&&part.bytes().all(|c|c.is_ascii_uppercase()||c.is_ascii_digit())) {return Err("REQUEST_INVALID".into());}
        Ok(())
    }
}
#[derive(Deserialize,Serialize)]
#[serde(deny_unknown_fields)]
pub struct InstructionSource {repository:String,commit:String,path:String,content_sha256:String}
impl InstructionSource {
    fn validate(&self,work_ref:&str)->Result<()> {
        if self.repository!="mastermindx-market-intelligence/macro" || !lowercase_hex(&self.commit,40)
            || !lowercase_hex(&self.content_sha256,64) || self.path!=format!("agentos/workstreams/WS-{}.md",&work_ref[3..]) {return Err("REQUEST_INVALID".into());}
        Ok(())
    }
}
#[derive(Deserialize,Serialize)]
#[serde(deny_unknown_fields)]
pub struct InstructionPauseRequest {selection:InstructionSelection,command_id:String,expected_revision:String,expected_source:InstructionSource}
#[derive(Deserialize,Serialize)]
#[serde(deny_unknown_fields)]
pub struct InstructionStatusRequest {selection:InstructionSelection,command_id:String}
#[derive(Clone,Copy,PartialEq,Eq)]
enum Mode {Content,Current,Pause,Status}
fn command(value:&str)->Result<()> {
    if !value.strip_prefix("mmos-instruction-pause-").is_some_and(|suffix|lowercase_hex(suffix,40)) {return Err("REQUEST_INVALID".into());}
    Ok(())
}
fn target(mode:Mode,selection:&Value,command_id:Option<&str>)->Result<Url> {
    let work=selection.get("work_ref").and_then(Value::as_str).ok_or("REQUEST_INVALID")?;
    if mode==Mode::Content {
        serde_json::from_value::<ProjectPlanSelection>(selection.clone()).map_err(|_|"REQUEST_INVALID")?.validate()?;
    } else {serde_json::from_value::<InstructionSelection>(selection.clone()).map_err(|_|"REQUEST_INVALID")?.validate()?;}
    let path=match mode {Mode::Content=>"/workspace/project-instructions/current",Mode::Current=>"/workspace/instruction-admission/current",Mode::Pause=>"/workspace/instruction-admission/pause",Mode::Status=>"/workspace/instruction-admission/operation"};
    let mut url=Url::parse(&format!("{ORIGIN}{path}")).map_err(|_|"REQUEST_INVALID")?;
    if mode!=Mode::Pause {
        url.query_pairs_mut().append_pair("work_ref",work);
        if mode!=Mode::Content {url.query_pairs_mut().append_pair("instruction_ref",selection.get("instruction_ref").and_then(Value::as_str).ok_or("REQUEST_INVALID")?);}
    }
    if matches!(mode,Mode::Pause|Mode::Status) {
        let id=command_id.ok_or("REQUEST_INVALID")?;command(id)?;
        if mode==Mode::Status {url.query_pairs_mut().append_pair("command_id",id);}
    } else if command_id.is_some() {return Err("REQUEST_INVALID".into());}
    Ok(url)
}
fn header(value:&Value,mode:Mode,selection:&Value,command_id:Option<&str>)->bool {
    let schema=match mode {Mode::Content=>"mastermind.workspace_project_instructions.v2",Mode::Current=>"mastermind.workspace_instruction_admission_control.v1",Mode::Pause=>"mastermind.workspace_instruction_admission_action_result.v1",Mode::Status=>"mastermind.workspace_instruction_admission_status_result.v1"};
    let mut expected=selection.clone();if let Some(id)=command_id {expected["command_id"]=Value::String(id.into());}
    value.get("schema").and_then(Value::as_str)==Some(schema)&&value.get("selection")==Some(&expected)
}
async fn exchange(app:AppHandle,mode:Mode,selection:Value,command_id:Option<String>,body:Option<Value>)->Result<Value> {
    let url=target(mode,&selection,command_id.as_deref())?;
    if (mode==Mode::Pause)!=body.is_some() {return Err("REQUEST_INVALID".into());}
    let encoded=body.map(|value|serde_json::to_vec(&value).map_err(|_|"REQUEST_INVALID".to_owned())).transpose()?;
    if encoded.as_ref().is_some_and(|value|value.len()>16_384) {return Err("REQUEST_BOUND".into());}
    let state=app.state::<NativeAuth>();let before=state.lock()?.generation;
    let (token,generation)=ensure_native_token(&app,Resource::Acquisition).await?;
    if before!=generation||!state.lock()?.release_allowed(generation,Resource::Acquisition) {return Err("AUTHENTICATION_CHANGED".into());}
    let request=if let Some(bytes)=encoded {state.http.post(url).header("Content-Type","application/json").body(bytes)} else {state.http.get(url)};
    let response=request.bearer_auth(token).header("Accept","application/json").header("Cache-Control","no-store").timeout(Duration::from_secs(60)).send().await.map_err(|_|"SOURCE_UNAVAILABLE")?;
    let result=if response.status().as_u16()==503 {read_json_body(response,32_768).await} else {bounded_json(response,32_768).await};
    if !state.lock()?.release_allowed(generation,Resource::Acquisition) {return Err("AUTHENTICATION_CHANGED".into());}
    let value=result?;if !header(&value,mode,&selection,command_id.as_deref()) {return Err("RESPONSE_INVALID".into());}
    // Full typed host decoder validates every returned body before publication.
    Ok(value)
}
#[tauri::command]
pub async fn read_project_instructions(app:AppHandle,selection:ProjectPlanSelection)->Result<Value> {
    selection.validate()?;exchange(app,Mode::Content,serde_json::json!({"work_ref":selection.work_ref}),None,None).await
}
#[tauri::command]
pub async fn read_instruction_admission_control(app:AppHandle,selection:InstructionSelection)->Result<Value> {
    selection.validate()?;exchange(app,Mode::Current,serde_json::to_value(selection).map_err(|_|"REQUEST_INVALID")?,None,None).await
}
#[tauri::command]
pub async fn pause_instruction_admission(app:AppHandle,request:InstructionPauseRequest)->Result<Value> {
    request.selection.validate()?;command(&request.command_id)?;request.expected_source.validate(&request.selection.work_ref)?;
    if !lowercase_hex(&request.expected_revision,64) {return Err("REQUEST_INVALID".into());}
    let body=serde_json::to_value(&request).map_err(|_|"REQUEST_INVALID")?;
    exchange(app,Mode::Pause,serde_json::to_value(request.selection).map_err(|_|"REQUEST_INVALID")?,Some(request.command_id),Some(body)).await
}
#[tauri::command]
pub async fn read_instruction_admission_operation(app:AppHandle,request:InstructionStatusRequest)->Result<Value> {
    request.selection.validate()?;command(&request.command_id)?;
    exchange(app,Mode::Status,serde_json::to_value(request.selection).map_err(|_|"REQUEST_INVALID")?,Some(request.command_id),None).await
}

#[cfg(test)]
mod instruction_transport_tests {
    use super::*;
    #[test]
    fn exact_fixed_paths_and_namespaces() {
        let selected=serde_json::json!({"work_ref":"WS:ONE","instruction_ref":"INS:DAILY-ONE"});let id=format!("mmos-instruction-pause-{}","a".repeat(40));
        let pause=target(Mode::Pause,&selected,Some(&id)).unwrap();assert_eq!(pause.path(),"/workspace/instruction-admission/pause");assert!(pause.query().is_none());
        let status=target(Mode::Status,&selected,Some(&id)).unwrap();assert_eq!(status.path(),"/workspace/instruction-admission/operation");assert_eq!(status.query_pairs().count(),3);
        assert_eq!(target(Mode::Content,&serde_json::json!({"work_ref":"WS:ONE"}),None).unwrap().path(),"/workspace/project-instructions/current");
        for bad in [id.clone()+"\n",format!("mmos-project-pause-{}","a".repeat(40)),"mmos-instruction-pause-a".into()] {assert!(command(&bad).is_err());}
        assert!(target(Mode::Current,&selected,Some(&id)).is_err());
    }
    #[test]
    fn closed_selection_and_source_cannot_carry_authority_or_foreign_paths() {
        for value in [serde_json::json!({"work_ref":"WS:ONE","instruction_ref":"INS:DAILY-ONE","principal":"forged"}),serde_json::json!({"work_ref":"WS:ONE","instruction_ref":"INS:BAD\n"}),serde_json::json!({"work_ref":"WS:ONE","instruction_ref":"INS:BAD--REF"}),serde_json::json!({"work_ref":"WS:ONE","instruction_ref":null})] {assert!(target(Mode::Current,&value,None).is_err());}
        let mut source=InstructionSource{repository:"mastermindx-market-intelligence/macro".into(),commit:"a".repeat(40),path:"agentos/workstreams/WS-ONE.md".into(),content_sha256:"b".repeat(64)};assert!(source.validate("WS:ONE").is_ok());source.path="/private/input".into();assert!(source.validate("WS:ONE").is_err());
    }
    #[test]
    fn foreign_or_extra_response_selection_is_withheld() {
        let selected=serde_json::json!({"work_ref":"WS:ONE","instruction_ref":"INS:DAILY-ONE"});let id=format!("mmos-instruction-pause-{}","a".repeat(40));
        let mut value=serde_json::json!({"schema":"mastermind.workspace_instruction_admission_status_result.v1","selection":{"work_ref":"WS:ONE","instruction_ref":"INS:DAILY-ONE","command_id":id}});
        assert!(header(&value,Mode::Status,&selected,Some(&id)));value["selection"]["instruction_ref"]=Value::String("INS:OTHER".into());assert!(!header(&value,Mode::Status,&selected,Some(&id)));
        let project=serde_json::json!({"work_ref":"WS:ONE"});
        let mut content=serde_json::json!({"schema":"mastermind.workspace_project_instructions.v2","selection":project});
        assert!(header(&content,Mode::Content,&project,None));
        content["schema"]=Value::String("mastermind.workspace_project_instructions.v1".into());assert!(!header(&content,Mode::Content,&project,None));
    }
}
