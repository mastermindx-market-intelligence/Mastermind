//! Local-user Hermes attachment; not Executive admission or a public loopback proxy.
//! The host guards current sign-in and never gives native tickets to the renderer.
use super::{AppHandle, Manager, NativeAuth, Resource, Result, Value};
use std::sync::Mutex;
#[path = "../hermes_native/core.rs"]
mod core;
const BRIDGE: &str = include_str!("../hermes_native/bridge.py");
const SCHEMA: &str = "mastermind.hermes_native_view.v1";
static IN_FLIGHT: Mutex<()> = Mutex::new(());

// One disposable view pipe, independent of foreground send/Stop. This is not
// session state: cancellation kills only our read helper, never the native turn.
struct Observation {
    active: Option<(String, std::sync::Arc<std::sync::atomic::AtomicBool>)>,
    cancelled_before_start: Option<String>,
}
static OBSERVATION: Mutex<Observation> = Mutex::new(Observation { active: None, cancelled_before_start: None });

fn validate(request: &Value) -> Result<bool> {
    let object = request.as_object().ok_or("REQUEST_INVALID")?;
    let operation = object.get("operation").and_then(Value::as_str).ok_or("REQUEST_INVALID")?;
    let keys: Vec<&str> = object.keys().map(String::as_str).collect();
    if !core::valid_fields(operation, &keys) { return Err("REQUEST_INVALID".into()); }
    for key in ["sessionId", "admissionId"] {
        if object.contains_key(key) && !object[key].as_str().is_some_and(core::valid_id) {
            return Err("REQUEST_INVALID".into());
        }
    }
    if object.contains_key("requestId") && !object["requestId"].as_str().is_some_and(core::valid_request_id) {
        return Err("REQUEST_INVALID".into());
    }
    if operation == "create" && !matches!(object["role"].as_str(), Some("meta-ceo" | "secretary")) {
        return Err("REQUEST_INVALID".into());
    }
    if operation == "send" && !object["text"].as_str().is_some_and(core::valid_prompt) {
        return Err("REQUEST_INVALID".into());
    }
    Ok(matches!(operation, "create" | "send" | "stop_send"))
}

// A rejected IPC call may clear a reservation only with this closed, original-
// invocation proof. Generic strings remain ambiguous after the renderer invokes.
fn no_send_error(request: &Value, generation: Option<u64>, code: &str) -> Value {
    let operation = request.get("operation").and_then(Value::as_str).unwrap_or("");
    let request_id = request.get("requestId").and_then(Value::as_str).unwrap_or("");
    if !matches!(operation, "create" | "send") || !core::valid_request_id(request_id)
        || generation.is_none() || operation == "send" && !request.get("sessionId")
            .and_then(Value::as_str).is_some_and(core::valid_id) {
        return Value::String(code.into());
    }
    let mut value = serde_json::json!({"schema":"mastermind.hermes_native_no_send.v1",
        "operation":operation,"requestId":request_id,"expectedAuthGeneration":generation.unwrap(),"code":code});
    if operation == "send" { value["sessionId"] = request["sessionId"].clone(); }
    value
}

#[derive(Debug)]
enum InvocationError { BeforeDispatch(String), AfterDispatch(String) }
impl From<&str> for InvocationError {
    fn from(code: &str) -> Self { Self::AfterDispatch(code.into()) }
}
impl From<String> for InvocationError {
    fn from(code: String) -> Self { Self::AfterDispatch(code) }
}
type InvocationResult = std::result::Result<Value, InvocationError>;

fn unavailable(mutating: bool, code: &'static str, request: &Value) -> Value {
    let operation = match request["operation"].as_str().unwrap_or("") {
        "recover_create" | "recover_send" => "recover", "stop_send" => "stop", operation => operation,
    };
    let mut value = serde_json::json!({"schema":SCHEMA,
        "state":if mutating || operation == "recover" {"EFFECT_UNKNOWN"} else {"UNAVAILABLE"},
        "capabilities":[], "delegation":"NOT_ENABLED", "retryAllowed":false, "code":code, "operation":operation});
    if request.get("requestId").is_some() { value["requestId"] = request["requestId"].clone(); }
    if matches!(request["operation"].as_str(), Some("send" | "recover_send" | "stop_send")) {
        value["requestSessionId"] = request["sessionId"].clone();
    }
    value
}

fn qualified_auth(app: &AppHandle, generation: Option<u64>, before_dispatch: bool) -> Result<u64> {
    let state = app.state::<NativeAuth>();
    let inner = state.lock()?;
    let current = inner.generation;
    if !core::release_allowed(generation.unwrap_or(current), current,
        inner.token(Resource::Acquisition).is_some(), inner.status().status == "signed_in") {
        return Err(if before_dispatch { "NATIVE_AUTH_NOT_DISPATCHED" } else { "AUTHENTICATION_CHANGED" }.into());
    }
    Ok(current)
}

// Validate the entire nonprivate proof before an auth race can hide the full
// response. No session, receipt, runtime or unvalidated extra field may bypass
// the renderer's decoder by being promoted to a before-dispatch error.
fn valid_no_send(value: &Value, request: &Value) -> bool {
    let Some(object) = value.as_object() else { return false; };
    let operation = request["operation"].as_str().unwrap_or("");
    let mut keys = vec!["schema", "state", "operation", "requestId", "capabilities", "delegation", "retryAllowed", "code"];
    if operation == "send" { keys.push("requestSessionId"); }
    matches!(operation, "create" | "send") && object.len() == keys.len()
        && keys.iter().all(|key| object.contains_key(*key))
        && value["schema"] == SCHEMA && value["state"] == "NOT_SENT"
        && value["operation"] == operation && value["requestId"] == request["requestId"]
        && request["requestId"].as_str().is_some_and(core::valid_request_id)
        && (operation != "send" || value["requestSessionId"] == request["sessionId"])
        && value["capabilities"] == serde_json::json!(["native_chat", "native_history", "admission_recovery"])
        && value["delegation"] == "NOT_ENABLED" && value["retryAllowed"] == false
        && value["code"] == "NATIVE_NOT_SENT"
}

fn release_result(result: InvocationResult, authentication: Result<u64>, request: &Value,
                  expected_generation: u64) -> std::result::Result<Value, Value> {
    let mut value = match result {
        Ok(value) => value,
        Err(InvocationError::BeforeDispatch(code)) => return Err(no_send_error(request, Some(expected_generation), &code)),
        Err(InvocationError::AfterDispatch(code)) => return Err(Value::String(code)),
    };
    let generation = match authentication {
        Ok(generation) if generation == expected_generation => generation,
        Ok(_) => return Err(Value::String("AUTHENTICATION_CHANGED".into())),
        Err(code) => {
            if code == "AUTHENTICATION_CHANGED" && valid_no_send(&value, request) {
                return Err(no_send_error(request, Some(expected_generation), "NATIVE_AUTH_NOT_DISPATCHED"));
            }
            return Err(Value::String(code));
        }
    };
    value["authGeneration"] = generation.into();
    Ok(value)
}

#[cfg(unix)]
fn trusted_path(path: &std::path::Path, home: &std::path::Path, file: bool) -> Result<()> {
    use std::os::unix::fs::MetadataExt;
    let uid = unsafe { libc::geteuid() };
    let relative = path.strip_prefix(home).map_err(|_| "NATIVE_INSTALL_UNAVAILABLE")?;
    let mut cursor = home.to_path_buf();
    let home_meta = std::fs::symlink_metadata(home).map_err(|_| "NATIVE_INSTALL_UNAVAILABLE")?;
    if !home_meta.is_dir() || home_meta.uid() != uid || home_meta.mode() & 0o022 != 0 {
        return Err("NATIVE_INSTALL_UNAVAILABLE".into());
    }
    for part in relative.components() {
        if !matches!(part, std::path::Component::Normal(_)) { return Err("NATIVE_INSTALL_UNAVAILABLE".into()); }
        cursor.push(part);
        let info = std::fs::symlink_metadata(&cursor).map_err(|_| "NATIVE_INSTALL_UNAVAILABLE")?;
        if info.file_type().is_symlink() || info.uid() != uid || info.mode() & 0o022 != 0
            || (cursor != path && !info.is_dir())
            || (cursor == path && if file { !info.is_file() } else { !info.is_dir() }) {
            return Err("NATIVE_INSTALL_UNAVAILABLE".into());
        }
    }
    Ok(())
}

#[cfg(unix)]
fn spawn_helper(app: &AppHandle, request: &Value, generation: u64)
    -> Result<(std::process::Child, Vec<u8>)> {
    use std::{io::Read, process::{Command, Stdio}};
    qualified_auth(&app, Some(generation), true)?;
    let home = app.path().home_dir().map_err(|_| "NATIVE_INSTALL_UNAVAILABLE")?;
    if home.canonicalize().map_err(|_| "NATIVE_INSTALL_UNAVAILABLE")? != home {
        return Err("NATIVE_INSTALL_UNAVAILABLE".into());
    }
    let root = home.join(".hermes/hermes-agent");
    let launcher = root.join(".hermes/bin/hermes");
    trusted_path(&launcher, &home, true)?;
    let source = std::fs::File::open(&launcher).map_err(|_| "NATIVE_INSTALL_UNAVAILABLE")?;
    let mut launcher_text = String::new();
    source.take(65537).read_to_string(&mut launcher_text).map_err(|_| "NATIVE_INSTALL_UNAVAILABLE")?;
    if launcher_text.len() > 65536 { return Err("NATIVE_INSTALL_UNAVAILABLE".into()); }
    let selected = core::launcher_python(&home, &launcher_text)?;
    trusted_path(selected.parent().ok_or("NATIVE_INSTALL_UNAVAILABLE")?, &home, false)?;
    // The upstream immutable Python distribution uses python3 -> python3.14.
    // Resolve only that fixed installed reference, then execute the checked target.
    let python = selected.canonicalize().map_err(|_| "NATIVE_INSTALL_UNAVAILABLE")?;
    if !python.starts_with(home.join(".hermes/tools")) { return Err("NATIVE_INSTALL_UNAVAILABLE".into()); }
    trusted_path(&python, &home, true)?;
    let bytes = serde_json::to_vec(&request).map_err(|_| "REQUEST_INVALID")?;
    if bytes.len() > 65536 { return Err("REQUEST_INVALID".into()); }
    // Hold the existing auth mutex only over spawn: sign-out cannot win between the
    // final authority check and this one local effect. No bearer leaves its owner.
    let state = app.state::<NativeAuth>();
    let inner = state.lock()?;
    if !core::release_allowed(generation, inner.generation, inner.token(Resource::Acquisition).is_some(),
        inner.status().status == "signed_in") { return Err("NATIVE_AUTH_NOT_DISPATCHED".into()); }
    let child = Command::new(python).args(["-I", "-B", "-c", BRIDGE])
        .env_clear().env("HOME", &home).env("PATH", "/usr/bin:/bin:/opt/homebrew/bin")
        .env("LANG", "en_US.UTF-8").current_dir(&home)
        .stdin(Stdio::piped()).stdout(Stdio::piped()).stderr(Stdio::null()).spawn();
    drop(inner);
    let child = child.map_err(|_| "NATIVE_CLIENT_NOT_STARTED")?;
    Ok((child, bytes))
}

#[cfg(unix)]
fn run_local(app: AppHandle, request: Value, generation: u64, mutating: bool) -> InvocationResult {
    use std::{io::{Read, Write}, thread, time::{Duration, Instant}};
    // A foreground client is bounded, not another scheduler. A concurrent invocation is not queued.
    // This closure contains every fallible step before a child can receive bytes.
    // After spawn, errors use AfterDispatch even if IO may have failed immediately.
    let prepared = (|| -> Result<_> {
    let single = IN_FLIGHT.try_lock().map_err(|_| "NATIVE_BUSY")?;
    let (child, bytes) = spawn_helper(&app, &request, generation)?;
    Ok((single, child, bytes))
    })();
    let (_single, mut child, bytes) = prepared.map_err(InvocationError::BeforeDispatch)?;
    let mut input = child.stdin.take().ok_or("NATIVE_PIPE_UNAVAILABLE")?;
    let output = child.stdout.take().ok_or("NATIVE_PIPE_UNAVAILABLE")?;
    // Separate pipe IO from the deadline so a blocked input or oversized output cannot
    // hang the host. The helper starts no children; killing it closes these two pipes.
    let writer = thread::spawn(move || input.write_all(&bytes));
    let reader = thread::spawn(move || {
        let mut bytes = Vec::new();
        output.take(1_048_577).read_to_end(&mut bytes).map(|_| bytes)
    });
    let deadline = Instant::now() + Duration::from_secs(30);
    let mut timed_out = false;
    let status = loop {
        match child.try_wait() {
            Ok(Some(status)) => break Some(status),
            Ok(None) if Instant::now() < deadline => thread::sleep(Duration::from_millis(25)),
            _ => {
                timed_out = true;
                let _ = child.kill();
                break child.wait().ok();
            }
        }
    };
    let wrote = matches!(writer.join(), Ok(Ok(())));
    let output = reader.join().ok().and_then(std::result::Result::ok);
    if timed_out || !wrote || !status.is_some_and(|status| status.success()) {
        return Ok(unavailable(mutating, "NATIVE_CLIENT_INTERRUPTED", &request));
    }
    let output = match output { Some(bytes) if bytes.len() <= 1_048_576 => bytes,
        _ => return Ok(unavailable(mutating, "NATIVE_RESPONSE_TOO_LARGE", &request)) };
    let value: Value = match serde_json::from_slice(&output) { Ok(value) => value,
        Err(_) => return Ok(unavailable(mutating, "NATIVE_RESPONSE_INVALID", &request)) };
    if value.get("schema").and_then(Value::as_str) != Some(SCHEMA)
        || value.get("retryAllowed").and_then(Value::as_bool) != Some(false)
        || value.get("delegation").and_then(Value::as_str) != Some("NOT_ENABLED") {
        return Ok(unavailable(mutating, "NATIVE_RESPONSE_INVALID", &request));
    }
    Ok(value)
}

#[cfg(not(unix))]
fn run_local(_app: AppHandle, _request: Value, _generation: u64, _mutating: bool) -> InvocationResult {
    Err(InvocationError::BeforeDispatch("NATIVE_PLATFORM_UNAVAILABLE".into()))
}

#[tauri::command]
pub async fn hermes_native(app: AppHandle, request: Value, expected_auth_generation: Option<u64>)
    -> std::result::Result<Value, Value> {
    let mutating = validate(&request).map_err(|code| no_send_error(&request, expected_auth_generation, &code))?;
    let generation = qualified_auth(&app, expected_auth_generation, true)
        .map_err(|code| no_send_error(&request, expected_auth_generation, &code))?;
    if !core::dispatch_generation_allowed(expected_auth_generation, generation, mutating) {
        return Err(no_send_error(&request, expected_auth_generation, "NATIVE_AUTH_NOT_DISPATCHED"));
    }
    let check = app.clone();
    let original = request.clone();
    let result = tauri::async_runtime::spawn_blocking(move || run_local(app, request, generation, mutating))
        .await.map_err(|_| Value::String("NATIVE_CLIENT_UNAVAILABLE".into()))?;
    release_result(result, qualified_auth(&check, Some(generation), false), &original, generation)
}

fn validate_observation(request: &Value) -> Result<()> {
    let object = request.as_object().ok_or("REQUEST_INVALID")?;
    let fields = ["operation", "sessionId", "admissionId", "authorityEpoch"];
    if object.len() != fields.len() || fields.iter().any(|key| !object.contains_key(*key))
        || request["operation"] != "observe"
        || !request["sessionId"].as_str().is_some_and(core::valid_id)
        || !request["admissionId"].as_str().is_some_and(core::valid_id)
        || !request["authorityEpoch"].as_u64().is_some_and(|n| n > 0 && n <= 9_007_199_254_740_991) {
        return Err("REQUEST_INVALID".into());
    }
    Ok(())
}

fn valid_stream_frame(value: &Value, request: &Value) -> bool {
    let Some(object) = value.as_object() else { return false; };
    let fields = ["schema", "sessionId", "admissionId", "authorityEpoch", "executionGeneration",
        "replayEpoch", "sequence", "state", "text", "activity", "code"];
    object.len() == fields.len() && fields.iter().all(|key| object.contains_key(*key))
        && value["schema"] == "mastermind.hermes_native_stream.v1"
        && value["sessionId"] == request["sessionId"] && value["admissionId"] == request["admissionId"]
        && value["authorityEpoch"] == request["authorityEpoch"]
        && value["replayEpoch"].as_str().is_some_and(core::valid_id)
        && value["sequence"].as_u64().is_some_and(|n| n <= 9_007_199_254_740_991)
        && (value["executionGeneration"].is_null() || value["executionGeneration"].as_u64().is_some_and(|n| n <= 9_007_199_254_740_991))
        && matches!(value["state"].as_str(), Some("live" | "complete" | "interrupted"))
        && matches!(value["activity"].as_str(), Some("working" | "responding" | "tool"))
        && value["text"].as_str().is_some_and(|s| s.len() <= 262_144)
        && (value["code"].is_null() || value["code"].as_str().is_some_and(|s|
            s.starts_with("NATIVE_STREAM_") && s.len() < 100 && s.bytes().all(|b| b.is_ascii_uppercase() || b == b'_')))
}

#[cfg(unix)]
fn run_observation(app: AppHandle, request: Value, generation: u64,
    cancelled: std::sync::Arc<std::sync::atomic::AtomicBool>, channel: tauri::ipc::Channel<Value>) -> Result<()> {
    use std::{io::{BufRead, BufReader, Read, Write}, sync::{atomic::Ordering, mpsc}, thread, time::{Duration, Instant}};
    if cancelled.load(Ordering::Acquire) { return Ok(()); }
    let (mut child, bytes) = spawn_helper(&app, &request, generation)?;
    let result = (|| -> Result<()> {
        let mut input = child.stdin.take().ok_or("NATIVE_STREAM_INTERRUPTED")?;
        let output = child.stdout.take().ok_or("NATIVE_STREAM_INTERRUPTED")?;
        input.write_all(&bytes).map_err(|_| "NATIVE_STREAM_INTERRUPTED")?;
        drop(input);
        let (sender, receiver) = mpsc::sync_channel::<Vec<u8>>(4);
        let reader = thread::spawn(move || {
            let mut pipe = BufReader::new(output);
            loop {
                let mut line = Vec::new();
                match (&mut pipe).take(300_001).read_until(b'\n', &mut line) {
                    Ok(n) if n > 0 && n <= 300_000 && line.last() == Some(&b'\n') => {
                        if sender.send(line).is_err() { break; }
                    },
                    _ => break,
                }
            }
        });
        let deadline = Instant::now() + Duration::from_secs(610);
        let mut total = 0usize;
        let observed = (|| -> Result<()> {
            loop {
                if cancelled.load(Ordering::Acquire) { return Ok(()); }
                qualified_auth(&app, Some(generation), false)?;
                if Instant::now() >= deadline { return Err("NATIVE_STREAM_INTERRUPTED".into()); }
                match receiver.recv_timeout(Duration::from_millis(50)) {
                    Ok(bytes) => {
                        total += bytes.len();
                        if total > 16_777_216 { return Err("NATIVE_STREAM_TOO_LARGE".into()); }
                        let mut value: Value = serde_json::from_slice(&bytes).map_err(|_| "NATIVE_STREAM_INVALID")?;
                        if !valid_stream_frame(&value, &request) { return Err("NATIVE_STREAM_INVALID".into()); }
                        let done = value["state"] != "live";
                        value["authGeneration"] = generation.into();
                        // Lock over each release, so sign-out cannot race a private
                        // frame after the final authority check. No bearer crosses.
                        let state = app.state::<NativeAuth>();
                        let inner = state.lock()?;
                        if !core::release_allowed(generation, inner.generation,
                            inner.token(Resource::Acquisition).is_some(), inner.status().status == "signed_in") {
                            return Err("AUTHENTICATION_CHANGED".into());
                        }
                        channel.send(value).map_err(|_| "NATIVE_STREAM_INTERRUPTED")?;
                        drop(inner);
                        if done { return Ok(()); }
                    },
                    Err(mpsc::RecvTimeoutError::Timeout) => {},
                    Err(mpsc::RecvTimeoutError::Disconnected) => return Err("NATIVE_STREAM_INTERRUPTED".into()),
                }
            }
        })();
        // Closing this pipe does not cancel the Hermes admission. The existing
        // original-request Stop command is the sole route to prompt.cancel.
        drop(receiver);
        let _ = child.kill(); let _ = child.wait(); let _ = reader.join();
        observed
    })();
    let _ = child.kill(); let _ = child.wait();
    result
}

#[cfg(not(unix))]
fn run_observation(_app: AppHandle, _request: Value, _generation: u64,
    _cancelled: std::sync::Arc<std::sync::atomic::AtomicBool>, _channel: tauri::ipc::Channel<Value>) -> Result<()> {
    Err("NATIVE_PLATFORM_UNAVAILABLE".into())
}

#[tauri::command]
pub async fn hermes_native_observe(app: AppHandle, request: Value, observer_id: String,
    expected_auth_generation: u64, on_event: tauri::ipc::Channel<Value>) -> Result<()> {
    use std::sync::{Arc, atomic::{AtomicBool, Ordering}};
    validate_observation(&request)?;
    if !core::valid_request_id(&observer_id) { return Err("REQUEST_INVALID".into()); }
    let generation = qualified_auth(&app, Some(expected_auth_generation), true)?;
    let cancelled = Arc::new(AtomicBool::new(false));
    {
        let mut owner = OBSERVATION.lock().map_err(|_| "NATIVE_STREAM_UNAVAILABLE")?;
        if owner.cancelled_before_start.as_ref() == Some(&observer_id) { return Ok(()); }
        if let Some((_, previous)) = owner.active.take() { previous.store(true, Ordering::Release); }
        owner.active = Some((observer_id.clone(), cancelled.clone()));
    }
    let result = tauri::async_runtime::spawn_blocking(move || run_observation(app, request, generation, cancelled, on_event))
        .await.map_err(|_| "NATIVE_STREAM_UNAVAILABLE".to_string());
    let mut owner = OBSERVATION.lock().map_err(|_| "NATIVE_STREAM_UNAVAILABLE")?;
    if owner.active.as_ref().is_some_and(|(id, _)| id == &observer_id) { owner.active = None; }
    result?
}

#[tauri::command]
pub fn hermes_native_unobserve(observer_id: String) -> Result<()> {
    use std::sync::atomic::Ordering;
    if !core::valid_request_id(&observer_id) { return Err("REQUEST_INVALID".into()); }
    let mut owner = OBSERVATION.lock().map_err(|_| "NATIVE_STREAM_UNAVAILABLE")?;
    // A bounded tombstone also closes the cancel-before-start race. This holds
    // only a random disposable view ID, with no session or request payload.
    owner.cancelled_before_start = Some(observer_id.clone());
    if let Some((id, cancelled)) = &owner.active {
        if id == &observer_id { cancelled.store(true, Ordering::Release); }
    }
    Ok(())
}

#[cfg(test)]
mod native_tests {
    use super::*;
    #[test]
    fn request_and_authority_keys_are_closed_before_process_creation() {
        assert_eq!(validate(&serde_json::json!({"operation":"status"})).unwrap(), false);
        assert!(validate(&serde_json::json!({"operation":"status","url":"http://attacker"})).is_err());
        assert!(validate(&serde_json::json!({"operation":"create","role":"secretary","requestId":"a".repeat(32)})).unwrap());
        assert!(validate(&serde_json::json!({"operation":"send","sessionId":"one","requestId":"a".repeat(32),"text":"original\n 文本"})).unwrap());
        assert!(validate(&serde_json::json!({"operation":"send","sessionId":"../other","requestId":"a".repeat(32),"text":"original"})).is_err());
    }
    #[test]
    fn stop_is_mutating_and_retains_original_binding_on_interruption() {
        let request = serde_json::json!({"operation":"stop_send","sessionId":"original","requestId":"a".repeat(32)});
        assert!(validate(&request).unwrap());
        let value = unavailable(true, "NATIVE_CLIENT_INTERRUPTED", &request);
        assert_eq!(value["operation"], "stop");
        assert_eq!(value["state"], "EFFECT_UNKNOWN");
        assert_eq!(value["requestId"], request["requestId"]);
        assert_eq!(value["requestSessionId"], "original");
        assert!(no_send_error(&request, Some(9), "NATIVE_AUTH_NOT_DISPATCHED").is_string());
    }
    #[test]
    fn auth_races_require_complete_original_no_send_proof() {
        let request = serde_json::json!({"operation":"send","sessionId":"original","requestId":"a".repeat(32),"text":"text"});
        let changed = || Err("AUTHENTICATION_CHANGED".into());
        let proof = serde_json::json!({"schema":SCHEMA,"state":"NOT_SENT","operation":"send",
            "requestId":"a".repeat(32),"requestSessionId":"original",
            "capabilities":["native_chat","native_history","admission_recovery"],
            "delegation":"NOT_ENABLED","retryAllowed":false,"code":"NATIVE_NOT_SENT"});
        let expected = no_send_error(&request, Some(9), "NATIVE_AUTH_NOT_DISPATCHED");
        assert_eq!(release_result(Err(InvocationError::BeforeDispatch("NATIVE_AUTH_NOT_DISPATCHED".into())), changed(), &request, 9).unwrap_err(), expected);
        assert_eq!(release_result(Ok(proof.clone()), changed(), &request, 9).unwrap_err(), expected);
        for key in ["capabilities", "requestId", "requestSessionId", "code"] {
            let mut bad = proof.clone(); bad.as_object_mut().unwrap().remove(key);
            assert_eq!(release_result(Ok(bad), changed(), &request, 9).unwrap_err(), "AUTHENTICATION_CHANGED");
        }
        for (key, value) in [("requestId", serde_json::json!("b".repeat(32))),
            ("requestSessionId", serde_json::json!("crossed")), ("receipt", serde_json::json!({"id":"crossed"})),
            ("capabilities", serde_json::json!(["unqualified"])), ("operation", serde_json::json!("create")),
            ("state", serde_json::json!("ADMITTED"))] {
            let mut bad = proof.clone(); bad[key] = value;
            assert_eq!(release_result(Ok(bad), changed(), &request, 9).unwrap_err(), "AUTHENTICATION_CHANGED");
        }
        assert_eq!(release_result(Err(InvocationError::AfterDispatch("AUTHENTICATION_CHANGED".into())), changed(), &request, 9).unwrap_err(), "AUTHENTICATION_CHANGED");
        assert_eq!(release_result(Ok(proof), Ok(9), &request, 9).unwrap()["authGeneration"], 9);
    }

    #[test]
    fn interrupted_modification_cannot_claim_absence_or_retry() {
        let value = unavailable(true, "NATIVE_CLIENT_INTERRUPTED", &serde_json::json!({"operation":"send"}));
        assert_eq!(value["state"], "EFFECT_UNKNOWN");
        assert_eq!(value["retryAllowed"], false);
        assert_eq!(value["delegation"], "NOT_ENABLED");
        assert_eq!(unavailable(false, "NATIVE_CLIENT_INTERRUPTED", &serde_json::json!({"operation":"read"}))["state"], "UNAVAILABLE");
    }
}
