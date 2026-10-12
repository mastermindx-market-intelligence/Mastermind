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
const EXECUTIVE_SCOPE: &str = "mastermind.executive.read mastermind.executive.intent.submit";
const EXECUTIVE_REQUEST_CAP: usize = 65_536;
const EXECUTIVE_RESPONSE_CAP: usize = 262_144;
const MAX_SAFE_GENERATION: u64 = (1_u64 << 53) - 1;

fn executive_resource(value: &str) -> Option<String> {
    let url = Url::parse(value).ok()?;
    if url.scheme() != "https" || url.host_str().is_none() || !url.username().is_empty()
        || url.password().is_some() || url.query().is_some() || url.fragment().is_some()
        || url.as_str() != value { return None; }
    Some(value.to_owned())
}
#[derive(Clone, Copy, Serialize)]
pub struct ExecutiveAuthStatus { generation: u64, available: bool }

type Result<T> = std::result::Result<T, String>;

#[derive(Clone, Copy, PartialEq, Eq, Debug)]
enum Resource {
    Acquisition,
    Content,
    Executive,
}
impl Resource {
    fn audience(self) -> &'static str {
        match self {
            Self::Acquisition => "https://mcp.mastermind-x.com/workspace/read",
            Self::Content => "https://mcp.mastermind-x.com/workspace/window/current",
            Self::Executive => option_env!("MM_EXECUTIVE_RESOURCE").unwrap_or(""),
        }
    }
    fn scope(self) -> &'static str {
        match self {
            Self::Acquisition => "mastermind.workspace.read",
            Self::Content => "mastermind.workspace.content.read",
            Self::Executive => EXECUTIVE_SCOPE,
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
    executive_resource: Option<String>,
    executive_generation: u64,
    executive: Option<Token>,
    generation: u64,
    pending: Option<Pending>,
    exchanging: bool,
    acquisition: Option<Token>,
    content: Option<Token>,
    reason: Option<&'static str>,
}
impl Inner {
    fn new(client: Option<&str>) -> Self {
        Self::with_executive_resource(client, option_env!("MM_EXECUTIVE_RESOURCE"))
    }
    fn with_executive_resource(client: Option<&str>, resource: Option<&str>) -> Self {
        let client_id = client
            .filter(|value| crate::native_client::validate_native_client_id(value).is_ok())
            .map(str::to_owned);
        Self {
            client_id,
            executive_resource: resource.and_then(executive_resource),
            executive_generation: 0,
            executive: None,
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
            Resource::Executive => self.executive.as_ref().filter(|_| self.executive_resource.is_some()),
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
    // Overflow permanently disables this optional capability; generations never wrap/reuse.
    fn advance_executive(&mut self) -> bool {
        match self.executive_generation.checked_add(1).filter(|n| *n <= MAX_SAFE_GENERATION) {
            Some(next) => { self.executive_generation = next; true }
            None => { self.executive = None; self.executive_resource = None; false }
        }
    }
    fn clear_executive(&mut self) {
        self.executive = None;
        self.advance_executive();
    }
    fn expire_executive(&mut self) {
        if self.executive.as_ref().is_some_and(|t| t.expires <= Instant::now()) {
            self.clear_executive();
        }
    }
    fn executive_status(&mut self) -> ExecutiveAuthStatus {
        self.expire_executive();
        ExecutiveAuthStatus { generation: self.executive_generation,
            available: self.token(Resource::Executive).is_some() }
    }
    fn fail_transaction(&mut self, resource: Resource, reason: &'static str) {
        if resource == Resource::Executive { self.clear_executive(); }
        else { self.reason = Some(reason); }
    }
    fn invalidate(&mut self) {
        self.generation = self.generation.wrapping_add(1);
        self.clear_executive();
        self.pending = None;
        self.exchanging = false;
        self.acquisition = None;
        self.content = None;
        self.reason = None;
    }
    fn transaction(&mut self, resource: Resource) -> Result<String> {
        if resource == Resource::Executive {
            if self.executive_resource.is_none() { return Err("EXECUTIVE_UNCONFIGURED".into()); }
            self.clear_executive();
            if self.executive_resource.is_none() { return Err("EXECUTIVE_UNCONFIGURED".into()); }
        }
        let client = self
            .client_id
            .as_deref()
            .ok_or("NATIVE_CLIENT_ID_MISSING")?;
        let state = random_secret();
        let verifier = random_secret();
        let url = if resource == Resource::Executive {
            authorization_url_for_audience(client, resource, self.executive_resource.as_deref().ok_or("EXECUTIVE_UNCONFIGURED")?, &state, &verifier)
        } else { authorization_url(client, resource, &state, &verifier) };
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
            self.fail_transaction(pending.resource, "AUTH_TRANSACTION_EXPIRED");
            return Err("AUTH_TRANSACTION_EXPIRED".into());
        }
        if error {
            self.fail_transaction(pending.resource, "AUTHORIZATION_REFUSED");
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
            Ok(token) if resource == Resource::Content => {
                self.content = Some(token);
                self.reason = None;
                if self.executive_resource.is_some() { self.transaction(Resource::Executive).ok() } else { None }
            }
            Ok(token) => {
                if self.executive_resource.is_some() && self.advance_executive() {
                    self.executive = Some(token);
                }
                None
            }
            Err(_) => {
                self.fail_transaction(resource, "TOKEN_EXCHANGE_FAILED");
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
    authorization_url_for_audience(client, resource, resource.audience(), state, verifier)
}
fn authorization_url_for_audience(client: &str, resource: Resource, audience: &str, state: &str, verifier: &str) -> String {
    let mut url = Url::parse(&format!("{ISSUER}authorize")).expect("fixed issuer");
    url.query_pairs_mut().extend_pairs([
        ("response_type", "code"),
        ("client_id", client),
        ("redirect_uri", CALLBACK),
        ("audience", audience),
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
    if let Ok(mut inner) = app.state::<NativeAuth>().lock() {
        let executive = inner.executive_status();
        let _ = app.emit("mastermind-auth-state", inner.status());
        let _ = app.emit("mastermind-executive-auth-state", executive);
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
            let resource = inner.pending.take().ok_or("AUTHENTICATION_CHANGED")?.resource;
            inner.fail_transaction(resource, "AUTH_BROWSER_UNAVAILABLE");
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
                if let Some(pending) = inner.pending.take() {
                    inner.fail_transaction(pending.resource, "AUTH_TRANSACTION_EXPIRED");
                }
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
    if resource == Resource::Executive {
        let scopes = object.get("scope").and_then(Value::as_str).ok_or("TOKEN_RESPONSE_INVALID")?;
        let mut scopes: Vec<_> = scopes.split_whitespace().collect();
        scopes.sort_unstable();
        if scopes != ["mastermind.executive.intent.submit", "mastermind.executive.read"] {
            return Err("TOKEN_RESPONSE_INVALID".into());
        }
    }
    let token = object
        .get("access_token")
        .and_then(Value::as_str)
        .filter(|s| !s.is_empty() && s.len() <= 16384 && s.bytes().all(|b| b.is_ascii_graphic()))
        .ok_or("TOKEN_RESPONSE_INVALID")?;
    if !object
        .get("token_type")
        .and_then(Value::as_str)
        .is_some_and(|s| s.eq_ignore_ascii_case("Bearer"))
        || (resource != Resource::Executive && object
            .get("scope")
            .is_some_and(|s| s.as_str() != Some(resource.scope())))
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
const WORK_PATH: &str = "/workspace/work/current";
const MISSION_V3_SCHEMA: &str = "mastermind.mission_workspace.v3";
const RESULT_SCHEMA: &str = "mastermind.workspace_role_result.v1";
const WORK_SCHEMA: &str = "mastermind.workspace_work_queue.v1";

fn typed_unavailable(value: Value, schema: &str, require_null_result: bool) -> Result<Value> {
    if !value.is_object()
        || value.get("schema").and_then(Value::as_str) != Some(schema)
        || value.get("availability").and_then(Value::as_str) != Some("UNAVAILABLE")
        || (require_null_result && !value.get("result").map(|r| r.is_null()).unwrap_or(false))
    {
        Err("RESPONSE_INVALID".into())
    } else {
        Ok(value)
    }
}
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
pub async fn read_work(app: AppHandle) -> Result<Value> {
    let url = Url::parse(&format!("{ORIGIN}{WORK_PATH}")).map_err(|_| "REQUEST_INVALID")?;
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
    let result = if response.status().as_u16() == 503 {
        read_json_body(response, MAX_RESPONSE)
            .await
            .and_then(|value| typed_unavailable(value, WORK_SCHEMA, false))
    } else {
        bounded_json(response, MAX_RESPONSE).await
    };
    if !state
        .lock()?
        .release_allowed(generation, Resource::Acquisition)
    {
        return Err("AUTHENTICATION_CHANGED".into());
    }
    let value = result?;
    if !value.is_object() || value.get("schema").and_then(Value::as_str) != Some(WORK_SCHEMA) {
        return Err("RESPONSE_INVALID".into());
    }
    Ok(value)
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
    // Result and Work each admit only their own fixed typed-503 schema.
    // Result keeps the exact 16KiB cap plus null-result rule; Work uses the
    // public response cap and its Work schema. 401/403 and every other
    // non-OK status keep the established refusal in bounded_json.
    let result = if response.status().as_u16() == 503 {
        read_json_body(response, RESULT_RESPONSE_CAP)
            .await
            .and_then(|value| typed_unavailable(value, RESULT_SCHEMA, true))
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
const WINDOW_SCHEMA_V1: &str = "mastermind.workspace.window_read_candidate.v1";
const WINDOW_SCHEMA_V2: &str = "mastermind.workspace.window_read_candidate.v2";
fn allowed_window_schema(schema: &str) -> bool {
    schema == WINDOW_SCHEMA_V1 || schema == WINDOW_SCHEMA_V2
}
async fn read_current_window_document(app: AppHandle) -> Result<Value> {
    let url = Url::parse(&format!("{ORIGIN}/workspace/window/current")).map_err(|_| "REQUEST_INVALID")?;
    let state = app.state::<NativeAuth>();
    let (token, generation) = {
        let inner = state.lock()?;
        (
            inner
                .token(Resource::Content)
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
    if !state.lock()?.release_allowed(generation, Resource::Content) {
        return Err("AUTHENTICATION_CHANGED".into());
    }
    let value = result?;
    let schema = value.get("schema").and_then(Value::as_str).unwrap_or("");
    if !value.is_object() || !allowed_window_schema(schema) {
        return Err("RESPONSE_INVALID".into());
    }
    Ok(value)
}
#[tauri::command]
pub async fn read_current_window(app: AppHandle) -> Result<Value> {
    read_current_window_document(app).await
}

fn executive_guard(inner: &mut Inner, generation: u64, token_expires: Instant) -> Result<()> {
    inner.expire_executive();
    if inner.executive_generation == generation &&
        inner.token(Resource::Executive).is_some_and(|t| t.expires == token_expires) {
        Ok(())
    } else { Err("EXECUTIVE_AUTH_CHANGED".into()) }
}
fn executive_body(body: &Value) -> Result<Vec<u8>> {
    let serialized = serde_json::to_vec(body).map_err(|_| "REQUEST_INVALID".to_owned())?;
    if serialized.len() > EXECUTIVE_REQUEST_CAP {
        return Err("REQUEST_BOUND".into());
    }
    Ok(serialized)
}
async fn executive_post(app: AppHandle, path: &'static str, body: Value) -> Result<Value> {
    let serialized = executive_body(&body)?;
    let state = app.state::<NativeAuth>();
    let (token, token_expires, generation) = {
        let inner = state.lock()?;
        let token = inner.token(Resource::Executive).ok_or("EXECUTIVE_AUTH_REQUIRED")?;
        (
            token.value.clone(),
            token.expires,
            inner.executive_generation,
        )
    };
    let url = Url::parse(&format!("{ORIGIN}{path}")).map_err(|_| "REQUEST_INVALID".to_owned())?;
    if url.origin().ascii_serialization() != ORIGIN {
        return Err("REQUEST_INVALID".into());
    }
    let response = state
        .http
        .post(url)
        .bearer_auth(token)
        .header("Accept", "application/json")
        .header("Cache-Control", "no-store")
        .header(reqwest::header::CONTENT_TYPE, "application/json")
        .body(serialized)
        .send()
        .await
        .map_err(|_| "EXECUTIVE_TRANSPORT_UNAVAILABLE".to_owned())?;
    { executive_guard(&mut *state.lock()?, generation, token_expires)?; }
    let status = response.status();
    let result = if status.is_success() {
        read_json_body(response, EXECUTIVE_RESPONSE_CAP).await
    } else {
        Err(match status.as_u16() {
            401 => "EXECUTIVE_AUTH_REQUIRED",
            403 => "EXECUTIVE_ACCESS_REFUSED",
            _ => "EXECUTIVE_TRANSPORT_UNAVAILABLE",
        }
        .into())
    };
    {
        let mut inner = state.lock()?;
        executive_guard(&mut inner, generation, token_expires)?;
    }
    result
}
#[tauri::command]
pub fn executive_auth_status(state: tauri::State<'_, NativeAuth>) -> Result<ExecutiveAuthStatus> {
    Ok(state.lock()?.executive_status())
}
#[tauri::command]
pub async fn executive_context(app: AppHandle) -> Result<Value> {
    let result = executive_post(app.clone(), "/os/executive/context", serde_json::json!({})).await;
    if result.is_err() {
        emit(&app);
    }
    result
}
#[tauri::command]
pub async fn executive_submit(app: AppHandle, arguments: Value) -> Result<Value> {
    let result = executive_post(
        app.clone(),
        "/os/executive/submit",
        serde_json::json!({ "arguments": arguments }),
    )
    .await;
    if result.is_err() {
        emit(&app);
    }
    result
}
#[tauri::command]
pub async fn executive_status(app: AppHandle, intent_id: String) -> Result<Value> {
    let result = executive_post(
        app.clone(),
        "/os/executive/status",
        serde_json::json!({ "arguments": { "intent_id": intent_id } }),
    )
    .await;
    if result.is_err() {
        emit(&app);
    }
    result
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
    fn native_client_identity_constructor_is_wired_to_shared_validator() {
        let source = include_str!("auth.rs");
        let constructor = source
            .split_once("fn new(client: Option<&str>) -> Self {")
            .and_then(|(_, rest)| rest.split_once("\n    fn token"))
            .map(|(body, _)| body)
            .expect("Inner::new source must remain present");
        assert!(constructor.contains("crate::native_client::validate_native_client_id"));
        assert!(!constructor.contains("is_ascii_alphanumeric"));
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
    fn current_window_allowlist_is_exactly_v1_and_v2() {
        assert!(allowed_window_schema(
            "mastermind.workspace.window_read_candidate.v1"
        ));
        assert!(allowed_window_schema(
            "mastermind.workspace.window_read_candidate.v2"
        ));
        assert!(!allowed_window_schema(
            "mastermind.workspace.window_read_candidate.v3"
        ));
        assert!(!allowed_window_schema(
            "mastermind.workspace.recorded_read_candidate.v1"
        ));
        assert!(!allowed_window_schema("mastermind.mission_workspace.v3"));
        assert!(!allowed_window_schema(""));
    }
    #[test]
    fn typed_unavailable_is_schema_specific_and_result_keeps_null_result_rule() {
        let work = serde_json::json!({
            "schema": WORK_SCHEMA,
            "availability": "UNAVAILABLE",
            "reason_codes": ["projection_refused"],
        });
        assert!(typed_unavailable(work.clone(), WORK_SCHEMA, false).is_ok());

        let mut available = work.clone();
        available["availability"] = "AVAILABLE".into();
        assert!(typed_unavailable(available, WORK_SCHEMA, false).is_err());

        let mut wrong = work.clone();
        wrong["schema"] = RESULT_SCHEMA.into();
        assert!(typed_unavailable(wrong, WORK_SCHEMA, false).is_err());

        let result = serde_json::json!({
            "schema": RESULT_SCHEMA,
            "availability": "UNAVAILABLE",
            "result": null,
        });
        assert!(typed_unavailable(result.clone(), RESULT_SCHEMA, true).is_ok());
        let mut non_null = result;
        non_null["result"] = serde_json::json!({});
        assert!(typed_unavailable(non_null, RESULT_SCHEMA, true).is_err());
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

    fn executive_inner() -> Inner {
        Inner::with_executive_resource(Some("public-client"), Some("https://fixture.invalid/executive"))
    }
    fn complete_resource(i: &mut Inner, resource: Resource) -> Option<String> {
        let pending = i.pending.as_ref().unwrap();
        assert_eq!(pending.resource, resource);
        let raw = callback_url(&pending.state);
        let (p, _, _) = i.consume(&raw).unwrap();
        i.finish_exchange(p.generation, p.resource, Ok(token("fixture-private-token")))
    }
    fn at_executive_pending() -> Inner {
        let mut i = executive_inner();
        i.transaction(Resource::Acquisition).unwrap();
        complete_resource(&mut i, Resource::Acquisition).unwrap();
        complete_resource(&mut i, Resource::Content).unwrap();
        i
    }
    #[test]
    fn executive_is_third_distinct_pkce_in_the_existing_chain() {
        let mut i = executive_inner();
        let mut url = Some(i.transaction(Resource::Acquisition).unwrap());
        let mut states = std::collections::BTreeSet::new();
        let mut verifiers = std::collections::BTreeSet::new();
        for resource in [Resource::Acquisition, Resource::Content, Resource::Executive] {
            let parsed = Url::parse(url.as_ref().unwrap()).unwrap();
            let pairs: std::collections::BTreeMap<_, _> = parsed.query_pairs().into_owned().collect();
            let pending = i.pending.as_ref().unwrap();
            assert!(states.insert(pending.state.clone()));
            assert!(verifiers.insert(pending.verifier.clone()));
            assert_eq!(pairs["client_id"], "public-client");
            assert_eq!(pairs["redirect_uri"], CALLBACK);
            assert_eq!(pairs["scope"], resource.scope());
            assert_eq!(pairs["code_challenge_method"], "S256");
            assert_eq!(pairs["code_challenge"], URL_SAFE_NO_PAD.encode(Sha256::digest(pending.verifier.as_bytes())));
            assert_eq!(pairs["audience"], if resource == Resource::Executive {
                "https://fixture.invalid/executive"
            } else { resource.audience() });
            url = complete_resource(&mut i, resource);
        }
        assert!(url.is_none());
        assert!(i.token(Resource::Acquisition).is_some());
        assert!(i.token(Resource::Content).is_some());
        assert!(i.executive_status().available);
        assert_eq!(i.status().status, "signed_in");
    }
    #[test]
    fn executive_denial_and_exchange_failure_preserve_workspace_tokens() {
        for denied in [true, false] {
            let mut i = at_executive_pending();
            let generation = i.executive_generation;
            let state = i.pending.as_ref().unwrap().state.clone();
            if denied {
                assert!(i.consume(&format!("{CALLBACK}?state={state}&error=access_denied")).is_err());
            } else {
                let (p, _, _) = i.consume(&callback_url(&state)).unwrap();
                assert!(i.finish_exchange(p.generation, p.resource, Err("fixture".into())).is_none());
            }
            assert!(i.token(Resource::Acquisition).is_some());
            assert!(i.token(Resource::Content).is_some());
            assert_eq!(i.status().status, "signed_in");
            assert!(i.reason.is_none());
            assert!(!i.executive_status().available);
            assert!(i.executive_generation > generation);
        }
    }
    #[test]
    fn signout_fences_pending_and_delayed_executive_exchange() {
        for exchanging in [false, true] {
            let mut i = at_executive_pending();
            let state = i.pending.as_ref().unwrap().state.clone();
            let old = i.executive_generation;
            let consumed = if exchanging { Some(i.consume(&callback_url(&state)).unwrap().0) } else { None };
            i.invalidate();
            assert!(i.executive_generation > old);
            if let Some(p) = consumed {
                assert!(i.finish_exchange(p.generation, p.resource, Ok(token("late"))).is_none());
            } else { assert!(i.consume(&callback_url(&state)).is_err()); }
            assert!(!i.executive_status().available);
            assert_eq!(i.status().status, "signed_out");
        }
    }
    #[test]
    fn executive_expiry_and_reinstall_fence_old_results_without_changing_workspace_generation() {
        let mut i = at_executive_pending();
        complete_resource(&mut i, Resource::Executive);
        let first_generation = i.executive_generation;
        let first_expiry = i.executive.as_ref().unwrap().expires;
        let workspace_generation = i.generation;
        assert!(executive_guard(&mut i, first_generation, first_expiry).is_ok());
        i.transaction(Resource::Executive).unwrap();
        complete_resource(&mut i, Resource::Executive);
        assert!(executive_guard(&mut i, first_generation, first_expiry).is_err());
        let generation = i.executive_generation;
        i.executive.as_mut().unwrap().expires = Instant::now() - Duration::from_secs(1);
        let expiry = i.executive.as_ref().unwrap().expires;
        assert!(executive_guard(&mut i, generation, expiry).is_err());
        assert!(i.executive_generation > generation);
        assert_eq!(i.generation, workspace_generation);
        assert!(i.token(Resource::Acquisition).is_some());
        assert!(i.token(Resource::Content).is_some());
        assert!(!i.executive_status().available);
    }
    #[test]
    fn executive_generation_overflow_permanently_disables_without_reuse() {
        let mut i = executive_inner();
        i.executive_generation = MAX_SAFE_GENERATION;
        i.executive = Some(token("old"));
        i.invalidate();
        assert_eq!(i.executive_generation, MAX_SAFE_GENERATION);
        assert!(!i.executive_status().available);
        assert!(i.transaction(Resource::Executive).is_err());
        i.invalidate();
        assert_eq!(i.executive_generation, MAX_SAFE_GENERATION);
    }
    #[test]
    fn executive_resource_defaults_off_and_rejects_noncanonical_or_credential_urls() {
        for resource in [None, Some(""), Some("http://fixture.invalid/x"),
            Some("https://u:p@fixture.invalid/x"), Some("https://fixture.invalid/x?q=1"),
            Some("https://fixture.invalid/x#x"), Some(" https://fixture.invalid/x"),
            Some("https://fixture.invalid")] {
            let mut i = Inner::with_executive_resource(Some("public-client"), resource);
            assert!(!i.executive_status().available);
            assert!(i.transaction(Resource::Executive).is_err());
            assert!(i.transaction(Resource::Acquisition).is_ok());
        }
    }
    #[test]
    fn executive_scope_is_an_exact_set_and_never_accepts_duplicates() {
        for scope in [EXECUTIVE_SCOPE, "mastermind.executive.intent.submit mastermind.executive.read"] {
            assert!(parse_token(serde_json::json!({"access_token":"opaque", "token_type":"Bearer",
                "expires_in":60, "scope":scope}), Resource::Executive).is_ok());
        }
        for scope in [Value::Null, Value::String("mastermind.executive.read".into()),
            Value::String(format!("{EXECUTIVE_SCOPE} extra")), Value::String(format!("{EXECUTIVE_SCOPE} mastermind.executive.read"))] {
            assert!(parse_token(serde_json::json!({"access_token":"opaque", "token_type":"Bearer",
                "expires_in":60, "scope":scope}), Resource::Executive).is_err());
        }
    }
    #[test]
    fn executive_request_cap_counts_actual_encoded_bytes() {
        assert!(executive_body(&serde_json::json!({"arguments":{"goal":"x".repeat(65_000)}})).is_ok());
        assert!(executive_body(&serde_json::json!({"arguments":{"goal":"é".repeat(33_000)}})).is_err());
    }

}
