//! Fixed selected-work recorded physical-host READ. No telemetry acquisition.
use super::{AppHandle, Manager, NativeAuth, Resource, Result, Url, Value, Duration,
    RetainedActivitySelection, ORIGIN, ensure_native_token, read_json_body, bounded_json};
const PATH: &str = "/workspace/resources/host-observation/current";
const SCHEMA: &str = "mastermind.workspace_host_observation_result.v1";
fn target(selection: &RetainedActivitySelection) -> Result<Url> {
    selection.validate()?;
    let mut url = Url::parse(&format!("{ORIGIN}{PATH}")).map_err(|_| "REQUEST_INVALID")?;
    url.query_pairs_mut().append_pair("work_ref", &selection.work_ref)
        .append_pair("root_job_id", &selection.root_job_id).append_pair("job_id", &selection.job_id)
        .append_pair("attempt_id", &selection.attempt_id);
    Ok(url)
}
fn header(body: &Value, selection: &RetainedActivitySelection) -> bool {
    body.get("schema").and_then(Value::as_str) == Some(SCHEMA)
        && body.get("selection") == Some(&serde_json::json!({"work_ref":selection.work_ref,
            "root_job_id":selection.root_job_id,"job_id":selection.job_id,"attempt_id":selection.attempt_id}))
}
#[tauri::command]
pub async fn read_host_observation(app: AppHandle, selection: RetainedActivitySelection) -> Result<Value> {
    let url = target(&selection)?;
    let state = app.state::<NativeAuth>();
    let before = state.lock()?.generation;
    let (token, generation) = ensure_native_token(&app, Resource::Acquisition).await?;
    if before != generation || !state.lock()?.release_allowed(generation, Resource::Acquisition) {
        return Err("AUTHENTICATION_CHANGED".into());
    }
    let response = state.http.get(url).bearer_auth(token).header("Accept", "application/json")
        .header("Cache-Control", "no-store").timeout(Duration::from_secs(30)).send().await.map_err(|_| "SOURCE_UNAVAILABLE")?;
    let result = if response.status().as_u16() == 503 { read_json_body(response, 16_384).await }
        else { bounded_json(response, 16_384).await };
    if !state.lock()?.release_allowed(generation, Resource::Acquisition) { return Err("AUTHENTICATION_CHANGED".into()); }
    let body = result?;
    if !header(&body, &selection) { return Err("RESPONSE_INVALID".into()); }
    // The Host wrapper validates the complete closed body before display.
    Ok(body)
}
#[cfg(test)]
mod host_observation_tests {
    use super::*;
    #[test]
    fn fixed_host_observation_selection_header_and_origin() {
        let selected = serde_json::json!({"work_ref":"WS:ONE","root_job_id":"JOB-1","job_id":"JOB-2","attempt_id":format!("ATT-{}","a".repeat(32))});
        let selection: RetainedActivitySelection = serde_json::from_value(selected.clone()).unwrap();
        let url = target(&selection).unwrap();
        assert_eq!(url.origin().ascii_serialization(), ORIGIN); assert_eq!(url.path(), PATH);
        assert_eq!(url.query_pairs().count(), 4);
        let mut body = serde_json::json!({"schema":SCHEMA,"selection":selected});
        assert!(header(&body, &selection)); body["selection"]["root_job_id"] = Value::String("JOB-9".into()); assert!(!header(&body, &selection));
        body["selection"] = selected.clone(); body["schema"] = Value::String("mastermind.native_host_capacity_read/v1".into()); assert!(!header(&body, &selection));
        let mut foreign = selected.clone(); foreign["host_ref"] = Value::String("supplied".into());
        assert!(serde_json::from_value::<RetainedActivitySelection>(foreign).is_err());
        let mut bad = selected; bad["job_id"] = Value::String("JOB-1".into());
        assert!(target(&serde_json::from_value::<RetainedActivitySelection>(bad).unwrap()).is_err());
    }
}
