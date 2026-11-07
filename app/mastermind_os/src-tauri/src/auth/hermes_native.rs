//! Local-user Hermes attachment; not Executive admission or a public loopback proxy.
//! The host guards current sign-in and never gives native tickets to the renderer.
use super::{AppHandle, Manager, NativeAuth, Resource, Result, Value};
use std::sync::Mutex;
#[path = "../hermes_native/core.rs"]
mod core;
const BRIDGE: &str = include_str!("../hermes_native/bridge.py");
const SCHEMA: &str = "mastermind.hermes_native_view.v1";
static IN_FLIGHT: Mutex<()> = Mutex::new(());

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
    Ok(matches!(operation, "create" | "send"))
}

fn unavailable(mutating: bool, code: &'static str) -> Value {
    serde_json::json!({"schema":SCHEMA, "state":if mutating {"EFFECT_UNKNOWN"} else {"UNAVAILABLE"},
        "capabilities":[], "delegation":"NOT_ENABLED", "retryAllowed":false, "code":code})
}

fn qualified_auth(app: &AppHandle, generation: Option<u64>) -> Result<u64> {
    let state = app.state::<NativeAuth>();
    let inner = state.lock()?;
    let current = inner.generation;
    if !core::release_allowed(generation.unwrap_or(current), current,
        inner.token(Resource::Acquisition).is_some(), inner.status().status == "signed_in") {
        return Err("AUTHENTICATION_CHANGED".into());
    }
    Ok(current)
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
fn run_local(app: AppHandle, request: Value, generation: u64, mutating: bool) -> Result<Value> {
    use std::{io::{Read, Write}, process::{Command, Stdio}, thread, time::{Duration, Instant}};
    // A foreground client is bounded, not another scheduler. A concurrent invocation is not queued.
    let _single = IN_FLIGHT.try_lock().map_err(|_| "NATIVE_BUSY")?;
    qualified_auth(&app, Some(generation))?;
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
        inner.status().status == "signed_in") { return Err("AUTHENTICATION_CHANGED".into()); }
    let child = Command::new(python).args(["-I", "-B", "-c", BRIDGE])
        .env_clear().env("HOME", &home).env("PATH", "/usr/bin:/bin:/opt/homebrew/bin")
        .env("LANG", "en_US.UTF-8").current_dir(&home)
        .stdin(Stdio::piped()).stdout(Stdio::piped()).stderr(Stdio::null()).spawn();
    drop(inner);
    let mut child = child.map_err(|_| "NATIVE_CLIENT_NOT_STARTED")?;
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
    qualified_auth(&app, Some(generation))?;
    if timed_out || !wrote || !status.is_some_and(|status| status.success()) {
        return Ok(unavailable(mutating, "NATIVE_CLIENT_INTERRUPTED"));
    }
    let output = match output { Some(bytes) if bytes.len() <= 1_048_576 => bytes,
        _ => return Ok(unavailable(mutating, "NATIVE_RESPONSE_TOO_LARGE")) };
    let mut value: Value = match serde_json::from_slice(&output) { Ok(value) => value,
        Err(_) => return Ok(unavailable(mutating, "NATIVE_RESPONSE_INVALID")) };
    if value.get("schema").and_then(Value::as_str) != Some(SCHEMA)
        || value.get("retryAllowed").and_then(Value::as_bool) != Some(false)
        || value.get("delegation").and_then(Value::as_str) != Some("NOT_ENABLED") {
        return Ok(unavailable(mutating, "NATIVE_RESPONSE_INVALID"));
    }
    value["authGeneration"] = generation.into();
    Ok(value)
}

#[cfg(not(unix))]
fn run_local(_app: AppHandle, _request: Value, _generation: u64, _mutating: bool) -> Result<Value> {
    Err("NATIVE_PLATFORM_UNAVAILABLE".into())
}

#[tauri::command]
pub async fn hermes_native(app: AppHandle, request: Value, expected_auth_generation: Option<u64>) -> Result<Value> {
    let mutating = validate(&request)?;
    let generation = qualified_auth(&app, expected_auth_generation)?;
    // A durable reservation may outlive a sign-in change before this invocation.
    // Mutations must carry the generation observed before reserving that pointer.
    if !core::dispatch_generation_allowed(expected_auth_generation, generation, mutating) {
        return Err("AUTHENTICATION_CHANGED".into());
    }
    let check = app.clone();
    let result = tauri::async_runtime::spawn_blocking(move || run_local(app, request, generation, mutating))
        .await.map_err(|_| "NATIVE_CLIENT_UNAVAILABLE")?;
    qualified_auth(&check, Some(generation))?;
    let mut value = result?;
    value["authGeneration"] = generation.into();
    Ok(value)
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
    fn interrupted_modification_cannot_claim_absence_or_retry() {
        let value = unavailable(true, "NATIVE_CLIENT_INTERRUPTED");
        assert_eq!(value["state"], "EFFECT_UNKNOWN");
        assert_eq!(value["retryAllowed"], false);
        assert_eq!(value["delegation"], "NOT_ENABLED");
        assert_eq!(unavailable(false, "NATIVE_CLIENT_INTERRUPTED")["state"], "UNAVAILABLE");
    }
}
