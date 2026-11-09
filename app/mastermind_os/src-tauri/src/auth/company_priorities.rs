//! One zero-selector authored company READ. Never acquires/refreshes a grant.
use super::*;
const PATH:&str="/os/executive/company-priorities";
const CAP:usize=65_536;
fn body(value:Value)->Result<Value>{
 let o=value.as_object().ok_or("RESPONSE_INVALID")?;
 let keys=["schema","source","owner_context","authority","as_of","company_phase","north_star","priorities","phase_review_criteria"];
 if o.len()!=keys.len()||keys.iter().any(|k|!o.contains_key(*k))||value["schema"]!="mastermind.company_priorities.v1"||value["authority"]!="advisory_and_orientation_only"||value["source"]["owner"]!="STRATEGIC_STATE"||value["source"]["path"]!="config/strategic_state.yml"||!value["source"]["revision"].as_str().is_some_and(|v|v.len()==40&&v.bytes().all(|c|c.is_ascii_digit()||(b'a'..=b'f').contains(&c)))||!value["north_star"].is_array()||!value["priorities"].is_array()||!value["phase_review_criteria"].is_object(){return Err("RESPONSE_INVALID".into())}
 let exact=|v:&Value,keys:&[&str]|v.as_object().is_some_and(|o|o.len()==keys.len()&&keys.iter().all(|k|o.contains_key(*k)));
 let text=|v:&Value|v.as_str().is_some_and(|s|!s.trim().is_empty()&&s.chars().count()<=8192);
 let texts=|v:&Value,max:usize|v.as_array().is_some_and(|a|!a.is_empty()&&a.len()<=max&&a.iter().all(&text));
 if !exact(&value["source"],&["owner","revision","path","observed_at"])||!text(&value["source"]["observed_at"])||!exact(&value["owner_context"],&["principal_scope","verified_expiry"])||!value["owner_context"]["principal_scope"].as_str().is_some_and(|s|s.len()==64&&s.bytes().all(|c|c.is_ascii_digit()||(b'a'..=b'f').contains(&c)))||!value["owner_context"]["verified_expiry"].as_u64().is_some_and(|x|x<=9_007_199_254_740_991)||!text(&value["as_of"])||!text(&value["company_phase"])||!texts(&value["north_star"],32){return Err("RESPONSE_INVALID".into())}
 let rows=value["priorities"].as_array().ok_or("RESPONSE_INVALID")?;if rows.is_empty()||rows.len()>128{return Err("RESPONSE_INVALID".into())}
 let mut ids=std::collections::HashSet::new();for p in rows {if !exact(p,&["id","department","objective","status"])||!text(&p["id"])||!ids.insert(p["id"].as_str().unwrap_or(""))||!text(&p["department"])||!text(&p["objective"])||!matches!(p["status"].as_str(),Some("active"|"paused"|"achieved"|"retired")){return Err("RESPONSE_INVALID".into())}}
 let gates=value["phase_review_criteria"].as_object().ok_or("RESPONSE_INVALID")?;if gates.is_empty()||gates.len()>16{return Err("RESPONSE_INVALID".into())}
 for (name,g) in gates {if name.is_empty()||name.len()>64||!name.bytes().all(|c|c.is_ascii_uppercase()||c.is_ascii_digit()||c==b'_')||!exact(g,&["purpose","criteria","on_pass"])||!text(&g["purpose"])||!text(&g["on_pass"])||!texts(&g["criteria"],32){return Err("RESPONSE_INVALID".into())}}
 Ok(value)
}
async fn read_with_dispatch<D,F>(state:&NativeAuth,dispatch:D)->Result<Value>
where D:FnOnce(reqwest::Request)->F,F:std::future::Future<Output=std::result::Result<reqwest::Response,reqwest::Error>>{
 let (request,generation,expiry)={let mut inner=state.lock()?;inner.expire_executive();let token=inner.token(Resource::Executive).ok_or("EXECUTIVE_AUTH_REQUIRED")?;
  (state.http.post(format!("{ORIGIN}{PATH}")).bearer_auth(&token.value).header("Accept","application/json").header("Cache-Control","no-store").header("Content-Type","application/json").body("{}").timeout(HTTP_TIMEOUT).build().map_err(|_|"REQUEST_INVALID")?,inner.executive_generation,token.expires)};
 let response=dispatch(request).await.map_err(|_|"SOURCE_UNAVAILABLE")?;
 executive_guard(&mut *state.lock()?,generation,expiry)?;
 let result=bounded_json(response,CAP).await.and_then(body);
 executive_guard(&mut *state.lock()?,generation,expiry)?;
 result
}
#[tauri::command]
pub async fn read_company_priorities(app:AppHandle)->Result<Value>{let state=app.state::<NativeAuth>();read_with_dispatch(&state,|request|state.http.execute(request)).await}
#[cfg(test)]
mod tests {
 use super::*;use std::cell::Cell;
 fn vector()->Value{serde_json::from_str::<Value>(include_str!("../../../src/fixtures/office-company-priorities-source.json")).unwrap()["response"].clone()}
 fn state()->NativeAuth{let state=NativeAuth::new().unwrap();let mut i=Inner::with_executive_resource(None,Some("https://executive.example.invalid/mcp"));i.executive=Some(Token{value:"inert-current-read-token".into(),expires:Instant::now()+Duration::from_secs(60),wall_expires:SystemTime::now()+Duration::from_secs(60),executive_send:false});*state.lock().unwrap()=i;state}
 fn response(v:Value)->reqwest::Response{tauri::http::Response::builder().status(200).header("Content-Type","application/json").body(v.to_string()).unwrap().into()}
 #[test]fn actual_signed_source_body_fixed_read_needs_no_send_or_workspace(){
  let state=state();let expected=vector();let got=tauri::async_runtime::block_on(read_with_dispatch(&state,|r|{assert_eq!(r.method(),reqwest::Method::POST);assert_eq!(r.url().as_str(),format!("{ORIGIN}{PATH}"));assert_eq!(r.body().unwrap().as_bytes().unwrap(),b"{}");assert!(r.headers().contains_key("authorization"));assert!(!r.headers().contains_key("X-Mastermind-Workspace-Authorization"));std::future::ready(Ok(response(expected.clone())))})).unwrap();assert_eq!(got,expected);
 }
 #[test]fn unavailable_expired_and_late_epoch_withhold_before_or_after_fixed_read(){
  for late in [false,true]{let state=state();if !late{state.lock().unwrap().executive=None;}let calls=Cell::new(0);let result=tauri::async_runtime::block_on(read_with_dispatch(&state,|_|{calls.set(calls.get()+1);state.lock().unwrap().clear_executive();std::future::ready(Ok(response(vector())))}));assert!(result.is_err());assert_eq!(calls.get(),usize::from(late));}
  let state=state();state.lock().unwrap().executive.as_mut().unwrap().wall_expires=SystemTime::now()-Duration::from_secs(1);let calls=Cell::new(0);assert!(tauri::async_runtime::block_on(read_with_dispatch(&state,|_|{calls.set(1);std::future::ready(Ok(response(vector())))})).is_err());assert_eq!(calls.get(),0);
 }
 #[test]fn foreign_authority_partial_or_widened_frames_never_become_company_facts(){
  let mut foreign=vector();foreign["authority"]="execute".into();assert!(body(foreign).is_err());let mut partial=vector();partial["phase_review_criteria"]=serde_json::json!({});assert!(body(partial).is_err());let mut added=vector();added["permission"]=true.into();assert!(body(added).is_err());let mut p=vector();p["priorities"][0]["ready"]=true.into();assert!(body(p).is_err());
 }
}
