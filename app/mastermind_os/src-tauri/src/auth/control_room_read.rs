//! Fixed incumbent Control Room inventory READ; no census or action runs here.
//! The authenticated Workspace owner remains the source and permission authority.
use super::{AppHandle, Manager, NativeAuth, Resource, Result, Url, Value, Duration,
    ORIGIN, bounded_json, ensure_native_token};
use std::future::Future;

const PATH: &str = "/workspace/control-room/state/current";
const CAP: usize = 2_000_000;
const FIELDS: [&str; 7] = ["control_room", "capabilities", "live_builds_active",
    "composed_at", "refresh_in_flight", "state_refresh_error", "source_validity"];

fn target() -> Result<Url> {
    Url::parse(&format!("{ORIGIN}{PATH}")).map_err(|_| "REQUEST_INVALID".into())
}
fn body(value: Value) -> Result<Value> {
    let object = value.as_object().ok_or("RESPONSE_INVALID")?;
    if object.len() != FIELDS.len() + usize::from(object.contains_key("cross_plane"))
        || !FIELDS.iter().all(|key| object.contains_key(*key))
        || value["control_room"].get("schema").and_then(Value::as_str)
            != Some("mastermind.chairman_control_room.v1")
        || !value["capabilities"].is_object() || !value["source_validity"].is_object()
        || !value["live_builds_active"].is_boolean() || !value["refresh_in_flight"].is_boolean()
        || !(value["composed_at"].is_null() || value["composed_at"].is_string())
        || !(value["state_refresh_error"].is_null() || value["state_refresh_error"].is_string()) {
        return Err("RESPONSE_INVALID".into());
    }
    if !value["state_refresh_error"].is_null() {
        return Err("CONTROL_ROOM_REFRESH_FAILED".into());
    }
    // The shared Host decoder checks the entire bounded navigation projection.
    // A census observation is not host eligibility, liveness or action authority.
    Ok(value)
}

// Private dispatch seam: the real command and inert HTTP qualification share
// exactly this fixed target, native token/currentness and bounded body path.
async fn read_with_dispatch<D, F>(state: &NativeAuth, generation: u64, dispatch: D) -> Result<Value>
where D: FnOnce(reqwest::Request) -> F,
      F: Future<Output = std::result::Result<reqwest::Response, reqwest::Error>> {
    let request = {
        let inner = state.lock()?;
        if !inner.release_allowed(generation, Resource::Acquisition) {
            return Err("AUTHENTICATION_CHANGED".into());
        }
        let token = inner.token(Resource::Acquisition).ok_or("AUTHENTICATION_REQUIRED")?;
        state.http.get(target()?).bearer_auth(&token.value)
            .header("Accept", "application/json").header("Cache-Control", "no-store")
            .timeout(Duration::from_secs(30)).build().map_err(|_| "REQUEST_INVALID")?
    };
    let response = dispatch(request).await.map_err(|_| "SOURCE_UNAVAILABLE")?;
    let result = bounded_json(response, CAP).await.and_then(body);
    if !state.lock()?.release_allowed(generation, Resource::Acquisition) {
        return Err("AUTHENTICATION_CHANGED".into());
    }
    result
}

#[tauri::command]
pub async fn read_control_room_state(app: AppHandle) -> Result<Value> {
    let state = app.state::<NativeAuth>();
    let (_, generation) = ensure_native_token(&app, Resource::Acquisition).await?;
    read_with_dispatch(&state, generation, |request| state.http.execute(request)).await
}

#[cfg(test)]
mod tests {
    use super::*;
    use super::super::{Inner, Token};
    use std::cell::Cell;
    use std::time::{Instant, SystemTime};

    fn fixture() -> Value {
        serde_json::from_str(include_str!("../../../src/fixtures/native-wire/control-room-state-source.json")).unwrap()
    }
    fn source_body() -> Value { fixture()["samples"][0]["response"]["body"].clone() }
    fn state(value: &str) -> NativeAuth {
        let state = NativeAuth::new().unwrap();
        let mut inner = Inner::new(None);
        inner.acquisition = Some(Token { value: value.into(),
            expires: Instant::now()+Duration::from_secs(60),
            wall_expires: SystemTime::now()+Duration::from_secs(60), executive_send:false });
        *state.lock().unwrap() = inner;
        state
    }
    fn response(status: u16, content_type: &str, body: String) -> reqwest::Response {
        tauri::http::Response::builder().status(status).header("Content-Type",content_type)
            .body(body).unwrap().into()
    }
    fn call(state: &NativeAuth, status:u16, value:Value) -> Result<Value> {
        let generation=state.lock().unwrap().generation;
        tauri::async_runtime::block_on(read_with_dispatch(state,generation,|request| {
            assert_eq!(request.method(),reqwest::Method::GET);
            assert_eq!(request.url().as_str(),format!("{ORIGIN}{PATH}"));
            assert!(request.url().query().is_none() && request.body().is_none());
            assert_eq!(request.headers()["accept"],"application/json");
            assert_eq!(request.headers()["cache-control"],"no-store");
            assert!(request.headers().contains_key("authorization"));
            std::future::ready(Ok(response(status,"application/json",value.to_string())))
        }))
    }
    #[test]
    fn source_issued_inventory_uses_fixed_read_and_preserves_body() {
        let value=source_body();
        let got=call(&state("inert-native-token"),200,value.clone()).unwrap();
        assert_eq!(got,value);
        assert_eq!(got["capabilities"]["codex"]["state"],"NOT_INSTALLED");
        assert_eq!(got["capabilities"]["aionui"]["state"],"UNSUPPORTED");
        // Programs and inventory are from one source, not fabricated live hosts.
        assert_eq!(got["control_room"],fixture()["samples"][1]["response"]["body"]["control_room"]);
    }
    #[test]
    fn absence_denied_and_foreign_bodies_never_become_inventory() {
        for (status,expected) in [(401,"AUTHENTICATION_REQUIRED"),(403,"ACCESS_REFUSED"),
            (404,"SELECTION_UNAVAILABLE"),(503,"SOURCE_UNAVAILABLE")] {
            assert_eq!(call(&state("inert-native-token"),status,source_body()).unwrap_err(),expected);
        }
        let mut extra=source_body();extra["host_ref"]="caller-supplied".into();
        assert_eq!(call(&state("inert-native-token"),200,extra).unwrap_err(),"RESPONSE_INVALID");
        let mut foreign=source_body();foreign["control_room"]["schema"]="foreign.v1".into();
        assert_eq!(call(&state("inert-native-token"),200,foreign).unwrap_err(),"RESPONSE_INVALID");
        let mut failed=source_body();failed["state_refresh_error"]="private error".into();
        assert_eq!(call(&state("inert-native-token"),200,failed).unwrap_err(),"CONTROL_ROOM_REFRESH_FAILED");
    }
    #[test]
    fn missing_expired_or_wrong_resource_refuses_before_dispatch() {
        for case in 0..4 {
            let state=state("inert-native-token");
            { let mut inner=state.lock().unwrap();
              match case {0=>inner.acquisition=None,
                1=>inner.acquisition.as_mut().unwrap().expires=Instant::now()-Duration::from_secs(1),
                2=>inner.acquisition.as_mut().unwrap().wall_expires=SystemTime::now()-Duration::from_secs(1),
                _=>{inner.content=inner.acquisition.take();} }
            }
            let calls=Cell::new(0);
            let result=tauri::async_runtime::block_on(read_with_dispatch(&state,0,|_| {
                calls.set(calls.get()+1);
                std::future::ready(Ok(response(200,"application/json",source_body().to_string())))
            }));
            assert_eq!(calls.get(),0);assert_eq!(result.unwrap_err(),"AUTHENTICATION_CHANGED");
        }
    }
    #[test]
    fn late_rotation_revocation_and_wall_expiry_withhold_body() {
        for case in 0..3 {
            let state=state("inert-native-token");let calls=Cell::new(0);
            let result=tauri::async_runtime::block_on(read_with_dispatch(&state,0,|_| {
                calls.set(calls.get()+1);
                {let mut inner=state.lock().unwrap();match case {
                    0=>inner.generation+=1,1=>inner.acquisition=None,
                    _=>inner.acquisition.as_mut().unwrap().wall_expires=SystemTime::now()-Duration::from_secs(1),
                }}
                std::future::ready(Ok(response(200,"application/json",source_body().to_string())))
            }));
            assert_eq!(calls.get(),1);assert_eq!(result.unwrap_err(),"AUTHENTICATION_CHANGED");
        }
    }
    #[test]
    fn bounded_json_content_type_and_size_stay_enforced() {
        for (kind,expected) in [("text/plain","RESPONSE_INVALID"),("application/json","RESPONSE_BOUND")] {
            let state=state("inert-native-token");
            let result=tauri::async_runtime::block_on(read_with_dispatch(&state,0,|_| {
                std::future::ready(Ok(response(200,kind,"x".repeat(CAP+1))))
            }));
            // The existing reader rejects declared size before MIME; a bad-MIME
            // small body is separately checked below.
            assert!(result.is_err(),"bounded body escaped");
            if kind=="application/json" {assert_eq!(result.unwrap_err(),expected);}
        }
        let state=state("inert-native-token");
        let result=tauri::async_runtime::block_on(read_with_dispatch(&state,0,|_| {
            std::future::ready(Ok(response(200,"text/plain",source_body().to_string())))
        }));assert_eq!(result.unwrap_err(),"RESPONSE_INVALID");
    }

    #[test]
    #[ignore = "opt-in one same-run signed HTTP fixture; no installed origin request"]
    fn same_run_signed_http_fixture_bridge() {
        let origin=std::env::var("MM_AT09_FIXTURE_ORIGIN").unwrap();
        let mapped=Url::parse(&origin).unwrap();
        assert_eq!(mapped.scheme(),"http");assert_eq!(mapped.host_str(),Some("127.0.0.1"));
        assert!(mapped.port().is_some() && mapped.query().is_none() && mapped.path()=="/");
        let token=std::env::var("MM_AT09_FIXTURE_TOKEN").unwrap();
        let test_http=reqwest::Client::builder().no_proxy()
            .redirect(reqwest::redirect::Policy::none()).timeout(Duration::from_secs(10)).build().unwrap();
        let mut outcomes=Vec::new();
        for expected in ["AVAILABLE","SOURCE_UNAVAILABLE","ACCESS_REFUSED","SOURCE_UNAVAILABLE"] {
            let state=state(&token);
            let value=tauri::async_runtime::block_on(read_with_dispatch(&state,0,|mut request| {
                // Inspect the actual production request before the test-only
                // loopback mapping. The native command accepts no origin/selector.
                assert_eq!(request.url().as_str(),format!("{ORIGIN}{PATH}"));
                assert_eq!(request.method(),reqwest::Method::GET);
                assert!(request.body().is_none() && request.url().query().is_none());
                assert!(request.headers().contains_key("authorization"));
                assert_eq!(request.headers()["accept"],"application/json");
                assert_eq!(request.headers()["cache-control"],"no-store");
                *request.url_mut()=mapped.join(PATH).unwrap();
                request.headers_mut().insert(reqwest::header::HOST,
                    reqwest::header::HeaderValue::from_static("mcp.mastermind-x.com"));
                test_http.execute(request)
            }));
            match value {
                Ok(body)=>{assert_eq!(expected,"AVAILABLE");outcomes.push(serde_json::json!({"state":"AVAILABLE","body":body}));},
                Err(reason)=>{assert_eq!(reason,expected);outcomes.push(serde_json::json!({"state":"UNAVAILABLE","reason":reason}));},
            }
        }
        let output=std::env::var("MM_AT09_NATIVE_RETURN").unwrap();
        std::fs::write(output,serde_json::to_vec(&serde_json::json!({
            "schema":"mastermind.at09_native_http_result.v1","origin":ORIGIN,"path":PATH,
            "method":"GET","selector":null,"outcomes":outcomes,
            "premise":"fixed production request dispatched only through owned loopback test transport"
        })).unwrap()).unwrap();
    }

}
