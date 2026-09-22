//! The native client owns OAuth transactions and bearer tokens. The webview
//! receives fixed read results and sanitized state, never credential material.
use base64::{engine::general_purpose::URL_SAFE_NO_PAD, Engine};
use rand::{rngs::OsRng, RngCore};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use sha2::{Digest, Sha256};
use std::{
    sync::Mutex,
    time::{Duration, Instant},
};
use tauri::{AppHandle, Emitter, Manager};
use tauri_plugin_opener::OpenerExt;
use url::Url;

const ISSUER: &str = "https://dev-eo0jf8us5mup7wd5.us.auth0.com/";
const CALLBACK: &str = "com.mastermind.os://oauth/callback";
const ORIGIN: &str = "https://mcp.mastermind-x.com";
const TRANSACTION_TTL: Duration = Duration::from_secs(300);
const HTTP_TIMEOUT: Duration = Duration::from_secs(30);
const MAX_RESPONSE: usize = 2_000_000;
type Result<T> = std::result::Result<T, String>;

#[derive(Clone, Copy, PartialEq, Eq, Debug)]
enum Resource {
    Acquisition,
    Content,
}
impl Resource {
    fn audience(self) -> &'static str {
        match self {
            Self::Acquisition => "https://mcp.mastermind-x.com/workspace/read",
            Self::Content => "https://mcp.mastermind-x.com/workspace/window/current",
        }
    }
    fn scope(self) -> &'static str {
        match self {
            Self::Acquisition => "mastermind.workspace.read",
            Self::Content => "mastermind.workspace.content.read",
        }
    }
}

#[derive(Clone, Serialize)]
pub struct AuthStatus {
    status: &'static str,
    reason: Option<&'static str>,
    acquisition: bool,
    content: bool,
}
struct Token {
    value: String,
    expires: Instant,
}
struct Pending {
    state: String,
    verifier: String,
    resource: Resource,
    expires: Instant,
    generation: u64,
}
struct Inner {
    client_id: Option<String>,
    generation: u64,
    pending: Option<Pending>,
    exchanging: bool,
    acquisition: Option<Token>,
    content: Option<Token>,
    reason: Option<&'static str>,
}
impl Inner {
    fn new(client: Option<&str>) -> Self {
        let client_id = client
            .filter(|s| {
                !s.is_empty()
                    && s.len() <= 128
                    && s.bytes()
                        .all(|b| b.is_ascii_alphanumeric() || b"_-".contains(&b))
            })
            .map(str::to_owned);
        Self {
            client_id,
            generation: 0,
            pending: None,
            exchanging: false,
            acquisition: None,
            content: None,
            reason: None,
        }
    }
    fn token(&self, resource: Resource) -> Option<&Token> {
        match resource {
            Resource::Acquisition => self.acquisition.as_ref(),
            Resource::Content => self.content.as_ref(),
        }
        .filter(|t| t.expires > Instant::now())
    }
    fn status(&self) -> AuthStatus {
        let acquisition = self.token(Resource::Acquisition).is_some();
        let content = self.token(Resource::Content).is_some();
        AuthStatus {
            status: if self.client_id.is_none() {
                "unconfigured"
            } else if self.pending.is_some() || self.exchanging {
                "signing_in"
            } else if self.reason.is_some() {
                "error"
            } else if acquisition || content {
                "signed_in"
            } else {
                "signed_out"
            },
            reason: if self.client_id.is_none() {
                Some("NATIVE_CLIENT_ID_MISSING")
            } else {
                self.reason
            },
            acquisition,
            content,
        }
    }
    fn invalidate(&mut self) {
        self.generation = self.generation.wrapping_add(1);
        self.pending = None;
        self.exchanging = false;
        self.acquisition = None;
        self.content = None;
        self.reason = None;
    }
    fn transaction(&mut self, resource: Resource) -> Result<String> {
        let client = self
            .client_id
            .as_deref()
            .ok_or("NATIVE_CLIENT_ID_MISSING")?;
        let state = random_secret();
        let verifier = random_secret();
        let url = authorization_url(client, resource, &state, &verifier);
        self.pending = Some(Pending {
            state,
            verifier,
            resource,
            expires: Instant::now() + TRANSACTION_TTL,
            generation: self.generation,
        });
        Ok(url)
    }
    fn consume(&mut self, callback: &str) -> Result<(Pending, String, String)> {
        // Malformed or unrelated callbacks cannot cancel another transaction.
        let (state, code, error) = parse_callback(callback)?;
        let pending = self.pending.as_ref().ok_or("AUTH_CALLBACK_UNEXPECTED")?;
        if state != pending.state {
            return Err("AUTH_STATE_MISMATCH".into());
        }
        let pending = self.pending.take().ok_or("AUTH_CALLBACK_UNEXPECTED")?;
        if pending.expires <= Instant::now() || pending.generation != self.generation {
            self.reason = Some("AUTH_TRANSACTION_EXPIRED");
            return Err("AUTH_TRANSACTION_EXPIRED".into());
        }
        if error {
            self.reason = Some("AUTHORIZATION_REFUSED");
            return Err("AUTHORIZATION_REFUSED".into());
        }
        self.exchanging = true;
        Ok((
            pending,
            code.ok_or("AUTH_CALLBACK_INVALID")?,
            self.client_id.clone().ok_or("NATIVE_CLIENT_ID_MISSING")?,
        ))
    }
    fn release_allowed(&self, generation: u64, resource: Resource) -> bool {
        self.generation == generation && self.token(resource).is_some()
    }
    fn finish_exchange(
        &mut self,
        generation: u64,
        resource: Resource,
        token: Result<Token>,
    ) -> Option<String> {
        if self.generation != generation || !self.exchanging {
            return None;
        }
        self.exchanging = false;
        match token {
            Ok(token) if resource == Resource::Acquisition => {
                self.acquisition = Some(token);
                self.reason = None;
                self.transaction(Resource::Content).ok()
            }
            Ok(token) => {
                self.content = Some(token);
                self.reason = None;
                None
            }
            Err(_) => {
                self.reason = Some("TOKEN_EXCHANGE_FAILED");
                None
            }
        }
    }
}

pub struct NativeAuth {
    inner: Mutex<Inner>,
    http: reqwest::Client,
}
impl NativeAuth {
    pub fn new() -> Result<Self> {
        let http = reqwest::Client::builder()
            .https_only(true)
            .redirect(reqwest::redirect::Policy::none())
            .timeout(HTTP_TIMEOUT)
            .build()
            .map_err(|_| "HTTP_CONFIGURATION_INVALID")?;
        Ok(Self {
            inner: Mutex::new(Inner::new(option_env!("MM_NATIVE_CLIENT_ID"))),
            http,
        })
    }
    fn lock(&self) -> Result<std::sync::MutexGuard<'_, Inner>> {
        self.inner
            .lock()
            .map_err(|_| "AUTH_STATE_UNAVAILABLE".into())
    }
}
fn random_secret() -> String {
    let mut bytes = [0u8; 32];
    OsRng.fill_bytes(&mut bytes);
    URL_SAFE_NO_PAD.encode(bytes)
}
fn authorization_url(client: &str, resource: Resource, state: &str, verifier: &str) -> String {
    let mut url = Url::parse(&format!("{ISSUER}authorize")).expect("fixed issuer");
    url.query_pairs_mut().extend_pairs([
        ("response_type", "code"),
        ("client_id", client),
        ("redirect_uri", CALLBACK),
        ("audience", resource.audience()),
        ("scope", resource.scope()),
        ("state", state),
        ("code_challenge_method", "S256"),
        (
            "code_challenge",
            &URL_SAFE_NO_PAD.encode(Sha256::digest(verifier.as_bytes())),
        ),
    ]);
    url.into()
}
fn parse_callback(raw: &str) -> Result<(String, Option<String>, bool)> {
    if raw.len() > 8192 {
        return Err("AUTH_CALLBACK_INVALID".into());
    }
    let url = Url::parse(raw).map_err(|_| "AUTH_CALLBACK_INVALID")?;
    if url.scheme() != "com.mastermind.os"
        || url.host_str() != Some("oauth")
        || url.path() != "/callback"
        || url.port().is_some()
        || !url.username().is_empty()
        || url.password().is_some()
        || url.fragment().is_some()
    {
        return Err("AUTH_CALLBACK_INVALID".into());
    }
    let mut params = std::collections::BTreeMap::new();
    for (k, v) in url.query_pairs() {
        if !["state", "code", "error", "error_description", "iss"].contains(&k.as_ref())
            || params.insert(k.into_owned(), v.into_owned()).is_some()
        {
            return Err("AUTH_CALLBACK_INVALID".into());
        }
    }
    if params.get("iss").is_some_and(|v| v != ISSUER) {
        return Err("AUTH_ISSUER_MISMATCH".into());
    }
    let state = params
        .remove("state")
        .filter(|s| !s.is_empty() && s.len() <= 128)
        .ok_or("AUTH_CALLBACK_INVALID")?;
    let code = params
        .remove("code")
        .filter(|s| !s.is_empty() && s.len() <= 4096);
    let error = params.contains_key("error");
    if code.is_some() == error {
        return Err("AUTH_CALLBACK_INVALID".into());
    }
    Ok((state, code, error))
}
fn emit(app: &AppHandle) {
    if let Ok(inner) = app.state::<NativeAuth>().lock() {
        let _ = app.emit("mastermind-auth-state", inner.status());
    }
}
fn open_transaction(app: &AppHandle, url: String, generation: u64) -> Result<()> {
    {
        let state = app.state::<NativeAuth>();
        let mut inner = state.lock()?;
        // Serialize browser handoff with logout and replacement transactions.
        if inner.generation != generation || inner.pending.is_none() {
            return Err("AUTHENTICATION_CHANGED".into());
        }
        if app.opener().open_url(url, None::<&str>).is_err() {
            inner.pending = None;
            inner.reason = Some("AUTH_BROWSER_UNAVAILABLE");
            drop(inner);
            emit(app);
            return Err("AUTH_BROWSER_UNAVAILABLE".into());
        }
    }
    let app = app.clone();
    tauri::async_runtime::spawn(async move {
        tokio::time::sleep(TRANSACTION_TTL).await;
        let state = app.state::<NativeAuth>();
        if let Ok(mut inner) = state.lock() {
            if inner.generation == generation
                && inner
                    .pending
                    .as_ref()
                    .is_some_and(|p| p.expires <= Instant::now())
            {
                inner.pending = None;
                inner.reason = Some("AUTH_TRANSACTION_EXPIRED");
            }
        }
        emit(&app);
    });
    Ok(())
}
#[tauri::command]
pub fn auth_status(state: tauri::State<'_, NativeAuth>) -> Result<AuthStatus> {
    Ok(state.lock()?.status())
}
#[tauri::command]
pub fn sign_out(app: AppHandle) -> Result<AuthStatus> {
    let state = app.state::<NativeAuth>();
    let mut inner = state.lock()?;
    inner.invalidate();
    let status = inner.status();
    drop(inner);
    emit(&app);
    Ok(status)
}
#[tauri::command]
pub fn sign_in(app: AppHandle) -> Result<AuthStatus> {
    let state = app.state::<NativeAuth>();
    let mut inner = state.lock()?;
    if inner.client_id.is_none() {
        return Ok(inner.status());
    }
    inner.invalidate();
    let url = inner.transaction(Resource::Acquisition)?;
    let generation = inner.generation;
    drop(inner);
    emit(&app);
    open_transaction(&app, url, generation)?;
    let result = state.lock()?.status();
    Ok(result)
}
async fn bounded_json(response: reqwest::Response, cap: usize) -> Result<Value> {
    if !response.status().is_success() {
        return Err(match response.status().as_u16() {
            401 => "AUTHENTICATION_REQUIRED",
            403 => "ACCESS_REFUSED",
            404 => "SELECTION_UNAVAILABLE",
            _ => "SOURCE_UNAVAILABLE",
        }
        .into());
    }
    read_json_body(response, cap).await
}

/// Body half of the bounded read: JSON content type, declared and streamed
/// length caps, then parse. No status handling, so the single allowed typed
/// 503 body can flow through it under the same exact cap.
async fn read_json_body(mut response: reqwest::Response, cap: usize) -> Result<Value> {
    if response.content_length().is_some_and(|n| n > cap as u64) {
        return Err("RESPONSE_BOUND".into());
    }
    if !response
        .headers()
        .get(reqwest::header::CONTENT_TYPE)
        .and_then(|v| v.to_str().ok())
        .is_some_and(|v| {
            v.split(';')
                .next()
                .is_some_and(|v| v.trim() == "application/json")
        })
    {
        return Err("RESPONSE_INVALID".into());
    }
    let mut bytes = Vec::new();
    while let Some(chunk) = response.chunk().await.map_err(|_| "SOURCE_UNAVAILABLE")? {
        if bytes.len().saturating_add(chunk.len()) > cap {
            return Err("RESPONSE_BOUND".into());
        }
        bytes.extend_from_slice(&chunk);
    }
    serde_json::from_slice(&bytes).map_err(|_| "RESPONSE_INVALID".into())
}
fn parse_token(value: Value, resource: Resource) -> Result<Token> {
    let object = value.as_object().ok_or("TOKEN_RESPONSE_INVALID")?;
    let token = object
        .get("access_token")
        .and_then(Value::as_str)
        .filter(|s| !s.is_empty() && s.len() <= 16384 && s.bytes().all(|b| b.is_ascii_graphic()))
        .ok_or("TOKEN_RESPONSE_INVALID")?;
    if !object
        .get("token_type")
        .and_then(Value::as_str)
        .is_some_and(|s| s.eq_ignore_ascii_case("Bearer"))
        || object
            .get("scope")
            .is_some_and(|s| s.as_str() != Some(resource.scope()))
    {
        return Err("TOKEN_RESPONSE_INVALID".into());
    }
    let seconds = object
        .get("expires_in")
        .and_then(Value::as_u64)
        .filter(|n| *n > 0 && *n <= 604800)
        .ok_or("TOKEN_RESPONSE_INVALID")?;
    Ok(Token {
        value: token.into(),
        expires: Instant::now() + Duration::from_secs(seconds),
    })
}
pub async fn callback(app: AppHandle, raw: String) {
    let state = app.state::<NativeAuth>();
    let transaction = match state.lock().and_then(|mut inner| inner.consume(&raw)) {
        Ok(t) => t,
        Err(_) => {
            emit(&app);
            return;
        }
    };
    let (pending, code, client) = transaction;
    let response = state
        .http
        .post(format!("{ISSUER}oauth/token"))
        .form(&[
            ("grant_type", "authorization_code"),
            ("client_id", client.as_str()),
            ("code", code.as_str()),
            ("redirect_uri", CALLBACK),
            ("code_verifier", pending.verifier.as_str()),
        ])
        .send()
        .await;
    let token = match response {
        Ok(r) => bounded_json(r, 32768)
            .await
            .and_then(|v| parse_token(v, pending.resource)),
        Err(_) => Err("TOKEN_EXCHANGE_FAILED".into()),
    };
    let expires = token.as_ref().ok().map(|token| token.expires);
    let mut inner = match state.lock() {
        Ok(i) => i,
        Err(_) => return,
    };
    let next = inner.finish_exchange(pending.generation, pending.resource, token);
    drop(inner);
    emit(&app);
    if let Some(expires) = expires {
        let expiry_app = app.clone();
        let generation = pending.generation;
        tauri::async_runtime::spawn(async move {
            tokio::time::sleep_until(tokio::time::Instant::from_std(expires)).await;
            let current = expiry_app
                .state::<NativeAuth>()
                .lock()
                .is_ok_and(|inner| inner.generation == generation);
            if current {
                emit(&expiry_app);
            }
        });
    }
    if let Some(url) = next {
        let _ = open_transaction(&app, url, pending.generation);
    }
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub struct MissionSelection {
    work_ref: String,
    root_job_id: String,
}
impl MissionSelection {
    fn validate(&self) -> Result<()> {
        fn id(s: &str, prefix: &str, suffix_limit: usize, punctuation: &[u8]) -> bool {
            s.strip_prefix(prefix).is_some_and(|rest| {
                !rest.is_empty()
                    && rest.len() <= suffix_limit
                    && rest.as_bytes()[0].is_ascii_alphanumeric()
                    && rest
                        .bytes()
                        .all(|b| b.is_ascii_alphanumeric() || punctuation.contains(&b))
            })
        }
        if id(&self.work_ref, "WS:", 128, b"_.-") && id(&self.root_job_id, "JOB-", 251, b"_.:-") {
            Ok(())
        } else {
            Err("SELECTION_INVALID".into())
        }
    }
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ResultSelection {
    work_ref: String,
    root_job_id: String,
    job_id: String,
    attempt_id: String,
    result_envelope_digest: String,
}
fn validate_workspace_pair(work_ref: &str, root_job_id: &str) -> Result<()> {
    let work = work_ref.strip_prefix("WS:").ok_or("SELECTION_INVALID")?;
    let job = root_job_id.strip_prefix("JOB-").ok_or("SELECTION_INVALID")?;
    if !(2..=64).contains(&work.len())
        || !(work.as_bytes()[0].is_ascii_uppercase() || work.as_bytes()[0].is_ascii_digit())
        || !work.bytes().all(|b| b.is_ascii_alphanumeric() || b"_.-".contains(&b))
        || !(1..=9).contains(&job.len()) || !job.bytes().all(|b| b.is_ascii_digit()) {
        return Err("SELECTION_INVALID".into());
    }
    Ok(())
}
fn lowercase_hex(value: &str, size: usize) -> bool {
    value.len() == size && value.bytes().all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
}
impl ResultSelection {
    fn validate(&self) -> Result<()> {
        validate_workspace_pair(&self.work_ref, &self.root_job_id)?;
        validate_workspace_pair(&self.work_ref, &self.job_id)?;
        if !self.attempt_id.strip_prefix("ATT-").is_some_and(|value| lowercase_hex(value, 32))
            || !lowercase_hex(&self.result_envelope_digest, 64) {
            return Err("SELECTION_INVALID".into());
        }
        Ok(())
    }
}

const RESULT_RESPONSE_CAP: usize = 16_384;
const MISSION_V3_RESPONSE_CAP: usize = 2_000_000;
const RESULT_MISSION_V3_PATH: &str = "/workspace/mission/v3/current";
const RESULT_DETAIL_PATH: &str = "/workspace/result/current";
const MISSION_V3_SCHEMA: &str = "mastermind.mission_workspace.v3";
const RESULT_SCHEMA: &str = "mastermind.workspace_role_result.v1";
async fn read(
    app: AppHandle,
    resource: Resource,
    path: &str,
    schema: &str,
    selection: Option<MissionSelection>,
) -> Result<Value> {
    let mut url = Url::parse(&format!("{ORIGIN}{path}")).map_err(|_| "REQUEST_INVALID")?;
    if let Some(selection) = selection {
        selection.validate()?;
        url.query_pairs_mut()
            .append_pair("work_ref", &selection.work_ref)
            .append_pair("root_job_id", &selection.root_job_id);
    }
    let state = app.state::<NativeAuth>();
    let (token, generation) = {
        let inner = state.lock()?;
        (
            inner
                .token(resource)
                .ok_or("AUTHENTICATION_REQUIRED")?
                .value
                .clone(),
            inner.generation,
        )
    };
    let response = state
        .http
        .get(url)
        .bearer_auth(token)
        .header("Accept", "application/json")
        .header("Cache-Control", "no-store")
        .send()
        .await
        .map_err(|_| "SOURCE_UNAVAILABLE")?;
    let result = bounded_json(response, MAX_RESPONSE).await;
    if !state.lock()?.release_allowed(generation, resource) {
        return Err("AUTHENTICATION_CHANGED".into());
    }
    let value = result?;
    if !value.is_object() || value.get("schema").and_then(Value::as_str) != Some(schema) {
        return Err("RESPONSE_INVALID".into());
    }
    // The shared frontend decoder validates the full closed DTO before rendering.
    Ok(value)
}
#[tauri::command]
pub async fn read_programs(app: AppHandle) -> Result<Value> {
    read(
        app,
        Resource::Acquisition,
        "/workspace/programs/current",
        "mastermind.workspace_programs.v1",
        None,
    )
    .await
}
#[tauri::command]
pub async fn read_mission(app: AppHandle, selection: MissionSelection) -> Result<Value> {
    read(
        app,
        Resource::Acquisition,
        "/workspace/mission/current",
        "mastermind.mission_workspace.v2",
        Some(selection),
    )
    .await
}
#[tauri::command]
pub async fn read_mission_v3(app: AppHandle, selection: MissionSelection) -> Result<Value> {
    let mut url =
        Url::parse(&format!("{ORIGIN}{RESULT_MISSION_V3_PATH}")).map_err(|_| "REQUEST_INVALID")?;
    validate_workspace_pair(&selection.work_ref, &selection.root_job_id)?;
    url.query_pairs_mut()
        .append_pair("work_ref", &selection.work_ref)
        .append_pair("root_job_id", &selection.root_job_id);
    let state = app.state::<NativeAuth>();
    let (token, generation) = {
        let inner = state.lock()?;
        (
            inner
                .token(Resource::Acquisition)
                .ok_or("AUTHENTICATION_REQUIRED")?
                .value
                .clone(),
            inner.generation,
        )
    };
    let response = state
        .http
        .get(url)
        .bearer_auth(token)
        .header("Accept", "application/json")
        .header("Cache-Control", "no-store")
        .send()
        .await
        .map_err(|_| "SOURCE_UNAVAILABLE")?;
    let result = bounded_json(response, MISSION_V3_RESPONSE_CAP).await;
    if !state
        .lock()?
        .release_allowed(generation, Resource::Acquisition)
    {
        return Err("AUTHENTICATION_CHANGED".into());
    }
    let value = result?;
    if !value.is_object() || value.get("schema").and_then(Value::as_str) != Some(MISSION_V3_SCHEMA) {
        return Err("RESPONSE_INVALID".into());
    }
    Ok(value)
}
#[tauri::command]
pub async fn read_result(app: AppHandle, selection: ResultSelection) -> Result<Value> {
    let mut url = Url::parse(&format!("{ORIGIN}{RESULT_DETAIL_PATH}"))
        .map_err(|_| "REQUEST_INVALID")?;
    selection.validate()?;
    url.query_pairs_mut()
        .append_pair("work_ref", &selection.work_ref)
        .append_pair("root_job_id", &selection.root_job_id)
        .append_pair("job_id", &selection.job_id)
        .append_pair("attempt_id", &selection.attempt_id)
        .append_pair("result_envelope_digest", &selection.result_envelope_digest);
    let state = app.state::<NativeAuth>();
    let (token, generation) = {
        let inner = state.lock()?;
        (
            inner
                .token(Resource::Acquisition)
                .ok_or("AUTHENTICATION_REQUIRED")?
                .value
                .clone(),
            inner.generation,
        )
    };
    let response = state
        .http
        .get(url)
        .bearer_auth(token)
        .header("Accept", "application/json")
        .header("Cache-Control", "no-store")
        .send()
        .await
        .map_err(|_| "SOURCE_UNAVAILABLE")?;
    // The fixed result route is the one route allowed to surface a typed
    // error body: a 503 whose body parses under the exact 16KiB cap and is
    // the closed unavailable envelope with a null result. 401/403 and every
    // other non-OK status keep the established refusal in bounded_json.
    let result = if response.status().as_u16() == 503 {
        read_json_body(response, RESULT_RESPONSE_CAP)
            .await
            .and_then(|v| {
                if !v.is_object()
                    || v.get("schema").and_then(Value::as_str) != Some(RESULT_SCHEMA)
                    || v.get("availability").and_then(Value::as_str) != Some("UNAVAILABLE")
                    || !v.get("result").map(|r| r.is_null()).unwrap_or(false)
                {
                    Err("RESPONSE_INVALID".into())
                } else {
                    Ok(v)
                }
            })
    } else {
        bounded_json(response, RESULT_RESPONSE_CAP).await
    };
    if !state
        .lock()?
        .release_allowed(generation, Resource::Acquisition)
    {
        return Err("AUTHENTICATION_CHANGED".into());
    }
    let value = result?;
    if !value.is_object() || value.get("schema").and_then(Value::as_str) != Some(RESULT_SCHEMA) {
        return Err("RESPONSE_INVALID".into());
    }
    Ok(value)
}
#[tauri::command]
pub async fn read_current_window(app: AppHandle) -> Result<Value> {
    read(
        app,
        Resource::Content,
        "/workspace/window/current",
        "mastermind.workspace.window_read_candidate.v1",
        None,
    )
    .await
}

#[cfg(test)]
mod tests {
    use super::*;
    fn inner() -> Inner {
        Inner::new(Some("public-client"))
    }
    fn callback_url(state: &str) -> String {
        format!("{CALLBACK}?state={state}&code=test-code")
    }
    fn token(value: &str) -> Token {
        Token {
            value: value.into(),
            expires: Instant::now() + Duration::from_secs(60),
        }
    }
    #[test]
    fn actual_transaction_completion_keeps_resources_separate() {
        let mut i = inner();
        i.transaction(Resource::Acquisition).unwrap();
        let s = i.pending.as_ref().unwrap().state.clone();
        let (p, _, _) = i.consume(&callback_url(&s)).unwrap();
        let next = i
            .finish_exchange(p.generation, p.resource, Ok(token("acquisition")))
            .unwrap();
        assert!(next.contains("mastermind.workspace.content.read"));
        assert!(i.status().acquisition);
        assert!(!i.status().content);
        let s = i.pending.as_ref().unwrap().state.clone();
        let (p, _, _) = i.consume(&callback_url(&s)).unwrap();
        assert!(i
            .finish_exchange(p.generation, p.resource, Ok(token("content")))
            .is_none());
        assert_eq!(i.token(Resource::Acquisition).unwrap().value, "acquisition");
        assert_eq!(i.token(Resource::Content).unwrap().value, "content");
        assert_eq!(i.status().status, "signed_in");
    }
    #[test]
    fn late_token_exchange_cannot_restore_signed_out_session() {
        let mut i = inner();
        i.transaction(Resource::Acquisition).unwrap();
        let s = i.pending.as_ref().unwrap().state.clone();
        let (p, _, _) = i.consume(&callback_url(&s)).unwrap();
        i.invalidate();
        assert!(i
            .finish_exchange(p.generation, p.resource, Ok(token("late")))
            .is_none());
        assert!(!i.status().acquisition);
        assert!(i.pending.is_none());
        assert_eq!(i.status().status, "signed_out");
    }
    #[test]
    fn content_exchange_failure_preserves_independent_acquisition() {
        let mut i = inner();
        i.acquisition = Some(token("acquisition"));
        i.transaction(Resource::Content).unwrap();
        let s = i.pending.as_ref().unwrap().state.clone();
        let (p, _, _) = i.consume(&callback_url(&s)).unwrap();
        i.finish_exchange(p.generation, p.resource, Err("failure".into()));
        assert!(i.status().acquisition);
        assert!(!i.status().content);
        assert_eq!(i.status().status, "error");
    }
    #[test]
    fn missing_config_never_constructs_transaction() {
        let mut i = Inner::new(None);
        assert_eq!(i.status().status, "unconfigured");
        assert!(i.transaction(Resource::Acquisition).is_err());
    }
    #[test]
    fn native_client_identity_uses_the_closed_shared_grammar() {
        for invalid in [
            "",
            "invalid client",
            "client/slash",
            "client.dot",
            "client:colon",
            "client\nnewline",
        ] {
            assert_eq!(Inner::new(Some(invalid)).status().status, "unconfigured");
        }
        assert_eq!(
            Inner::new(Some(&"a".repeat(129))).status().status,
            "unconfigured"
        );
        assert_eq!(
            Inner::new(Some(&"a".repeat(128))).status().status,
            "signed_out"
        );
        assert_eq!(
            Inner::new(Some("tpc_A1_-valid")).status().status,
            "signed_out"
        );
    }
    #[test]
    fn separate_authorizations_have_exact_custom_scope_and_s256() {
        for resource in [Resource::Acquisition, Resource::Content] {
            let url =
                Url::parse(&authorization_url("client", resource, "state", "verifier")).unwrap();
            let pairs: std::collections::BTreeMap<_, _> = url.query_pairs().collect();
            assert_eq!(pairs["audience"], resource.audience());
            assert_eq!(pairs["scope"], resource.scope());
            assert_eq!(pairs["code_challenge_method"], "S256");
            assert_eq!(pairs["redirect_uri"], CALLBACK);
            assert_eq!(
                pairs["code_challenge"],
                URL_SAFE_NO_PAD.encode(Sha256::digest(b"verifier"))
            );
        }
    }
    #[test]
    fn callback_exactness_and_duplicates() {
        for url in [
            "com.mastermind.os://oauth/other?state=x&code=y",
            "https://oauth/callback?state=x&code=y",
            "com.mastermind.os://oauth/callback?state=x&state=x&code=y",
            "com.mastermind.os://oauth/callback?state=x&code=y#x",
            "com.mastermind.os://oauth/callback?state=x&code=y&iss=https://other.example/",
        ] {
            assert!(parse_callback(url).is_err());
        }
    }
    #[test]
    fn wrong_state_does_not_consume_but_valid_state_is_one_use() {
        let mut i = inner();
        i.transaction(Resource::Acquisition).unwrap();
        let s = i.pending.as_ref().unwrap().state.clone();
        assert!(i.consume(&callback_url("wrong")).is_err());
        assert!(i.pending.is_some());
        assert!(i.consume(&callback_url(&s)).is_ok());
        assert!(i.consume(&callback_url(&s)).is_err());
    }
    #[test]
    fn expired_callback_consumed_without_exchange() {
        let mut i = inner();
        i.transaction(Resource::Acquisition).unwrap();
        let p = i.pending.as_mut().unwrap();
        p.expires = Instant::now();
        let s = p.state.clone();
        assert!(i.consume(&callback_url(&s)).is_err());
        assert!(!i.exchanging);
        assert!(i.pending.is_none());
    }
    #[test]
    fn logout_fences_old_exchange_and_read_and_both_tokens() {
        let mut i = inner();
        i.acquisition = Some(Token {
            value: "secret".into(),
            expires: Instant::now() + Duration::from_secs(60),
        });
        let generation = i.generation;
        assert!(i.release_allowed(generation, Resource::Acquisition));
        i.invalidate();
        assert!(!i.release_allowed(generation, Resource::Acquisition));
        assert!(i.acquisition.is_none());
        assert_eq!(i.status().status, "signed_out");
        assert_ne!(i.generation, generation);
    }
    #[test]
    fn selection_is_closed_and_validated() {
        assert!(serde_json::from_value::<MissionSelection>(
            serde_json::json!({"work_ref":"WS:X","root_job_id":"JOB-x","url":"https://other"})
        )
        .is_err());
        assert!(MissionSelection {
            work_ref: "WS:X".into(),
            root_job_id: "../other".into()
        }
        .validate()
        .is_err());
    }
    #[test]
    fn token_response_is_bound_and_expiring() {
        let good = serde_json::json!({"access_token":"secret","token_type":"Bearer","expires_in":60,"scope":"mastermind.workspace.read"});
        assert!(parse_token(good.clone(), Resource::Acquisition).is_ok());
        assert!(parse_token(good, Resource::Content).is_err());
        for seconds in [0, -1, 604801] {
            assert!(parse_token(serde_json::json!({"access_token":"secret","token_type":"Bearer","expires_in":seconds}),Resource::Acquisition).is_err());
        }
    }
    #[test]
    fn structured_result_selectors_use_exact_new_contract() {
        let valid = serde_json::json!({"work_ref":"WS:AB", "root_job_id":"JOB-1", "job_id":"JOB-2", "attempt_id":format!("ATT-{}", "a".repeat(32)), "result_envelope_digest":"b".repeat(64)});
        assert!(serde_json::from_value::<ResultSelection>(valid.clone()).unwrap().validate().is_ok());
        for (key, value) in [("work_ref", "WS:aB"), ("work_ref", "WS:A"), ("root_job_id", "JOB-x"), ("job_id", "JOB-1234567890"), ("attempt_id", "ATT-gggggggggggggggggggggggggggggggg"), ("attempt_id", "ATT-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA")] {
            let mut candidate = valid.clone(); candidate[key] = value.into();
            assert!(serde_json::from_value::<ResultSelection>(candidate).unwrap().validate().is_err(), "{key}: {value}");
        }
        let mut extra = valid; extra["url"] = "https://other.example".into();
        assert!(serde_json::from_value::<ResultSelection>(extra).is_err());
    }

}
