//! The native client owns OAuth transactions and bearer tokens. The webview
//! receives fixed read results and sanitized state, never credential material.
pub mod host_observation;
pub mod hermes_native;
pub mod control_room_read;
pub mod company_priorities;
mod draft_continuity;
mod transport_diagnostics;
use transport_diagnostics::{ExecutiveObservation, ExecutiveReason, ProgramsRead};
pub mod native_draft_identity;
pub mod authorization_continuation;
#[cfg(test)]
mod draft_recovery_tests;
use base64::{engine::general_purpose::URL_SAFE_NO_PAD, Engine};
use rand::{rngs::OsRng, RngCore};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use sha2::{Digest, Sha256};
use std::{
    sync::Mutex,
    time::{Duration, Instant, SystemTime},
};
use tauri::{AppHandle, Emitter, Manager};
use tauri_plugin_opener::OpenerExt;
pub mod instruction_admission;
pub mod project_access;
use url::Url;

const ISSUER: &str = "https://dev-eo0jf8us5mup7wd5.us.auth0.com/";
const CALLBACK: &str = "com.mastermind.os://oauth/callback";
const ORIGIN: &str = "https://mcp.mastermind-x.com";
const TRANSACTION_TTL: Duration = Duration::from_secs(300);
const HTTP_TIMEOUT: Duration = Duration::from_secs(30);
// Source preparation <=120s followed by the existing <=300s foreground owner.
// This is only a transport ceiling, never execution or retry authority.
const EXECUTIVE_FOREGROUND_TIMEOUT: Duration = Duration::from_secs(430);
const MAX_RESPONSE: usize = 2_000_000;
const EXECUTIVE_SCOPE: &str = "mastermind.executive.read mastermind.executive.intent.submit";
const EXECUTIVE_REQUEST_CAP: usize = 65_536;
const EXECUTIVE_RESPONSE_CAP: usize = 262_144;
const DIRECT_NATIVE_REQUEST_CAP: usize = 4096;
const DIRECT_NATIVE_RESPONSE_CAP: usize = 24_576;
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
    fn persistent(self) -> bool {
        self != Self::Executive && crate::native_refresh::enabled()
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
    // A sleeping Mac need not advance Instant. Check actual wall expiry too.
    wall_expires: SystemTime,
    // Derived from the exact validated Executive grant; stays in the native owner.
    executive_send: bool,
}
struct Pending {
    state: String,
    verifier: String,
    resource: Resource,
    expires: Instant,
    generation: u64,
    continuation: Option<authorization_continuation::ContentContinuation>,
}
struct Inner {
    draft_continuity: draft_continuity::DraftContinuity,
    client_id: Option<String>,
    executive_resource: Option<String>,
    executive_generation: u64,
    executive_changed: tokio::sync::watch::Sender<()>,
    executive: Option<Token>,
    executive_reason: ExecutiveReason,
    programs_sequence: u64,
    programs_read: ProgramsRead,
    generation: u64,
    pending: Option<Pending>,
    exchanging: bool,
    acquisition: Option<Token>,
    content: Option<Token>,
    reason: Option<&'static str>,
    restoring: bool,
    content_timeout: Option<authorization_continuation::ContentTimeout>,
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
            draft_continuity: draft_continuity::DraftContinuity::new(draft_owner_instance()),
            client_id,
            executive_resource: resource.and_then(executive_resource),
            executive_generation: 0,
            executive_changed: tokio::sync::watch::channel(()).0,
            executive: None,
            executive_reason: ExecutiveReason::NotEstablished,
            programs_sequence: 0,
            programs_read: ProgramsRead::default(),
            generation: 0,
            pending: None,
            exchanging: false,
            acquisition: None,
            content: None,
            reason: None,
            restoring: false,
            content_timeout: None,
        }
    }
    fn token(&self, resource: Resource) -> Option<&Token> {
        self.stored_token(resource)
            .filter(|t| t.expires > Instant::now() && t.wall_expires > SystemTime::now())
    }
    fn stored_token(&self, resource: Resource) -> Option<&Token> {
        match resource {
            Resource::Acquisition => self.acquisition.as_ref(),
            Resource::Content => self.content.as_ref(),
            Resource::Executive => self.executive.as_ref().filter(|_| self.executive_resource.is_some()),
        }
    }
    fn status(&self) -> AuthStatus {
        let acquisition = self.token(Resource::Acquisition).is_some();
        let content = self.token(Resource::Content).is_some();
        let expired = self.acquisition.as_ref().is_some_and(|_| !acquisition)
            || self.content.as_ref().is_some_and(|_| !content);
        AuthStatus {
            status: if self.client_id.is_none() {
                "unconfigured"
            } else if self.pending.is_some() || self.exchanging || self.restoring {
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
                self.reason.or_else(|| {
                    if matches!(self.draft_continuity.snapshot(None).phase, draft_continuity::Phase::Withdrawn) {
                        Some("USER_SIGNED_OUT")
                    } else if expired { Some("NATIVE_TOKEN_EXPIRED") } else { None }
                })
            },
            acquisition,
            content,
        }
    }
    // Overflow permanently disables this optional capability; generations never wrap/reuse.
    fn advance_executive(&mut self) -> bool {
        // Wake a pending foreground transport so its actual HTTP request is
        // dropped on logout/renewal. The generation remains the authority.
        self.executive_changed.send_replace(());
        match self.executive_generation.checked_add(1).filter(|n| *n <= MAX_SAFE_GENERATION) {
            Some(next) => { self.executive_generation = next; true }
            None => { self.executive = None; self.executive_resource = None; self.executive_reason = ExecutiveReason::GenerationExhausted; false }
        }
    }
    fn clear_executive(&mut self) {
        self.executive = None;
        if self.advance_executive() { self.executive_reason = ExecutiveReason::NotEstablished; }
    }
    fn expire_executive(&mut self) {
        if self.executive.as_ref().is_some_and(|t| t.expires <= Instant::now()) {
            self.clear_executive();
            if self.executive_resource.is_some() { self.executive_reason = ExecutiveReason::Expired; }
        }
    }
    fn executive_status(&mut self) -> ExecutiveAuthStatus {
        self.expire_executive();
        ExecutiveAuthStatus { generation: self.executive_generation,
            available: self.token(Resource::Executive).is_some() }
    }
    fn executive_observation(&mut self) -> ExecutiveObservation {
        let status = self.executive_status();
        let configured = self.executive_resource.is_some();
        let reason = if status.available { ExecutiveReason::Available }
            else if self.executive_reason == ExecutiveReason::GenerationExhausted { ExecutiveReason::GenerationExhausted }
            else if !configured { ExecutiveReason::Unconfigured }
            else if self.executive.is_some() { ExecutiveReason::Expired }
            else { self.executive_reason };
        ExecutiveObservation { schema: "mastermind.native_executive_status.v1",
            generation: status.generation, available: status.available, configured, reason,
            programs_read: self.programs_read }
    }
    fn begin_programs_observation(&mut self) -> Option<(u64, u64)> {
        let Some(next) = self.programs_sequence.checked_add(1) else {
            self.programs_read = ProgramsRead::default(); return None;
        };
        self.programs_sequence = next; self.programs_read = ProgramsRead::pending();
        Some((self.generation, next))
    }
    fn finish_programs_observation(&mut self, ticket: Option<(u64, u64)>, observed: ProgramsRead) {
        if ticket == Some((self.generation, self.programs_sequence)) { self.programs_read = observed; }
    }
    fn fail_transaction(&mut self, resource: Resource, reason: &'static str) {
        if resource == Resource::Executive {
            self.clear_executive();
            if self.executive_resource.is_some() { self.executive_reason = ExecutiveReason::failure(reason); }
        } else { self.reason = Some(reason); }
    }
    fn invalidate(&mut self) {
        self.invalidate_auth();
        self.draft_continuity.logout();
    }
    fn begin_reauthentication(&mut self) {
        self.invalidate_auth();
        self.draft_continuity.begin_reauthentication();
    }
    fn invalidate_auth(&mut self) {
        self.generation = self.generation.wrapping_add(1);
        self.programs_sequence = 0; self.programs_read = ProgramsRead::default();
        self.clear_executive();
        self.pending = None;
        self.exchanging = false;
        self.restoring = false;
        self.acquisition = None;
        self.content = None;
        self.reason = None;
        self.content_timeout = None;
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
        if resource == Resource::Executive { self.executive_reason = ExecutiveReason::Authorizing; }
        self.pending = Some(Pending {
            state,
            verifier,
            resource,
            expires: Instant::now() + TRANSACTION_TTL,
            generation: self.generation,
            continuation: None,
        });
        Ok(url)
    }
    fn initial_sign_in_transaction(&mut self) -> Result<String> {
        // Request a fresh login UI on explicit Sign in so an unrelated browser
        // SSO session can be changed. This hint is not identity
        // proof; the normal trusted issuer and resource checks still apply.
        // Only this initial handoff requests it. Chained grants keep SSO.
        let url = self.transaction(Resource::Acquisition)?;
        Ok(format!("{url}&prompt=login"))
    }
    fn expire_transaction(&mut self, generation: u64, expires: Instant, now: Instant) -> bool {
        // A completed or replaced transaction's timer must not announce a new
        // auth boundary. Only the exact original pending deadline can expire.
        if self.generation != generation
            || !self.pending.as_ref().is_some_and(|pending|
                pending.generation == generation && pending.expires == expires && expires <= now)
        {
            return false;
        }
        let Some(pending) = self.pending.take() else { return false; };
        self.fail_transaction(pending.resource, "AUTH_TRANSACTION_EXPIRED");
        self.remember_content_timeout(&pending);
        true
    }
    fn consume(&mut self, callback: &str) -> Result<(Pending, String, String)> {
        // Malformed or unrelated callbacks cannot cancel another transaction.
        let (state, code, error) = parse_callback(callback)?;
        if error && self.observe_timed_out_refusal(&state) { return Err("AUTHORIZATION_REFUSED".into()); }
        let pending = self.pending.as_ref().ok_or("AUTH_CALLBACK_UNEXPECTED")?;
        if state != pending.state {
            return Err("AUTH_STATE_MISMATCH".into());
        }
        let pending = self.pending.take().ok_or("AUTH_CALLBACK_UNEXPECTED")?;
        if pending.expires <= Instant::now() || pending.generation != self.generation {
            self.fail_transaction(pending.resource, "AUTH_TRANSACTION_EXPIRED");
            if !error { self.remember_content_timeout(&pending); }
            return Err("AUTH_TRANSACTION_EXPIRED".into());
        }
        if error {
            self.fail_transaction(pending.resource, "AUTHORIZATION_REFUSED");
            return Err("AUTHORIZATION_REFUSED".into());
        }
        self.exchanging = true;
        self.continuation_exchange_guard(&pending)?;
        if pending.resource == Resource::Executive { self.executive_reason = ExecutiveReason::Exchanging; }
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
                self.draft_continuity.unqualified();
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
                    self.executive_reason = ExecutiveReason::Available;
                }
                None
            }
            Err(error) => {
                // Only the dedicated public enum may retain a closed cause.
                // Raw token/provider/error material is never stored or emitted.
                self.fail_transaction(resource, "TOKEN_EXCHANGE_FAILED");
                if resource == Resource::Executive && self.executive_resource.is_some() {
                    self.executive_reason = ExecutiveReason::failure(&error);
                }
                None
            }
        }
    }
}

pub struct NativeAuth {
    inner: Mutex<Inner>,
    http: reqwest::Client,
    // Keychain writes and logout use the same lock. A late rotating response
    // cannot recreate a credential after a generation-changing logout.
    keychain_lock: Mutex<()>,
    refresh_locks: [tokio::sync::Mutex<()>; 2],
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
            keychain_lock: Mutex::new(()),
            refresh_locks: [tokio::sync::Mutex::new(()), tokio::sync::Mutex::new(())],
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
fn draft_owner_instance() -> String {
    let mut bytes = [0u8; 16];
    OsRng.fill_bytes(&mut bytes);
    bytes.iter().map(|byte| format!("{byte:02x}")).collect()
}
fn authorization_url(client: &str, resource: Resource, state: &str, verifier: &str) -> String {
    authorization_url_for_audience(client, resource, resource.audience(), state, verifier)
}
fn authorization_url_for_audience(client: &str, resource: Resource, audience: &str, state: &str, verifier: &str) -> String {
    let mut url = Url::parse(&format!("{ISSUER}authorize")).expect("fixed issuer");
    let scope = if resource.persistent() {
        format!("{} offline_access", resource.scope())
    } else {
        resource.scope().to_owned()
    };
    url.query_pairs_mut().extend_pairs([
        ("response_type", "code"),
        ("client_id", client),
        ("redirect_uri", CALLBACK),
        ("audience", audience),
        ("scope", scope.as_str()),
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
    let expires = {
        let state = app.state::<NativeAuth>();
        let mut inner = state.lock()?;
        // Serialize browser handoff with logout and replacement transactions.
        if inner.generation != generation || inner.pending.is_none() {
            return Err("AUTHENTICATION_CHANGED".into());
        }
        if !inner.continuation_handoff_current() {
            let resource = inner.pending.take().ok_or("AUTHENTICATION_CHANGED")?.resource;
            inner.fail_transaction(resource, "AUTHENTICATION_CHANGED");
            drop(inner);
            emit(app);
            return Err("AUTHENTICATION_CHANGED".into());
        }
        if app.opener().open_url(url, None::<&str>).is_err() {
            let resource = inner.pending.take().ok_or("AUTHENTICATION_CHANGED")?.resource;
            inner.fail_transaction(resource, "AUTH_BROWSER_UNAVAILABLE");
            drop(inner);
            emit(app);
            return Err("AUTH_BROWSER_UNAVAILABLE".into());
        }
        inner.pending.as_ref().ok_or("AUTHENTICATION_CHANGED")?.expires
    };
    let app = app.clone();
    tauri::async_runtime::spawn(async move {
        tokio::time::sleep(TRANSACTION_TTL).await;
        let state = app.state::<NativeAuth>();
        let expired = state.lock().map(|mut inner|
            inner.expire_transaction(generation, expires, Instant::now())).unwrap_or(false);
        if expired { emit(&app); }
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
    let _keychain = match state.keychain_lock.lock() {
        Ok(guard) => guard,
        Err(_) => {
            // Explicit logout withdraws in-memory authority and privacy
            // continuity even when platform credential cleanup is unavailable.
            state.lock()?.invalidate();
            emit(&app);
            return Err("KEYCHAIN_UNAVAILABLE".into());
        }
    };
    let mut inner = state.lock()?;
    inner.invalidate();
    let client = inner.client_id.clone();
    let mut failure = None;
    if crate::native_refresh::enabled() {
        if let Some(client) = client {
            for resource in [Resource::Acquisition, Resource::Content] {
                if let Err(error) = crate::native_refresh::delete(&client, resource.audience()) {
                    failure = Some(error);
                }
            }
        }
    }
    if failure.is_some() { inner.reason = Some("KEYCHAIN_DELETE_FAILED"); }
    let status = inner.status();
    drop(inner);
    drop(_keychain);
    emit(&app);
    if failure.is_some() { return Err("KEYCHAIN_DELETE_FAILED".into()); }
    Ok(status)
}
#[tauri::command]
pub fn sign_in(app: AppHandle) -> Result<AuthStatus> {
    let state = app.state::<NativeAuth>();
    let _keychain = state.keychain_lock.lock().map_err(|_| "KEYCHAIN_UNAVAILABLE")?;
    let mut inner = state.lock()?;
    if inner.client_id.is_none() {
        return Ok(inner.status());
    }
    inner.begin_reauthentication();
    if crate::native_refresh::enabled() {
        let client = inner.client_id.as_deref().ok_or("NATIVE_CLIENT_ID_MISSING")?;
        for resource in [Resource::Acquisition, Resource::Content] {
            crate::native_refresh::delete(client, resource.audience())?;
        }
    }
    let url = inner.initial_sign_in_transaction()?;
    let generation = inner.generation;
    drop(inner);
    drop(_keychain);
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
    let executive_send = if resource == Resource::Executive {
        let scopes = object.get("scope").and_then(Value::as_str).ok_or("TOKEN_RESPONSE_INVALID")?;
        let mut scopes: Vec<_> = scopes.split_whitespace().collect();
        scopes.sort_unstable();
        if scopes != ["mastermind.executive.intent.submit", "mastermind.executive.read"] && scopes != ["mastermind.executive.read"] {
            return Err("TOKEN_RESPONSE_INVALID".into());
        }
        scopes == ["mastermind.executive.intent.submit", "mastermind.executive.read"]
    } else {
        false
    };
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
            .is_some_and(|s| {
                let Some(actual) = s.as_str() else { return true; };
                let mut scopes: Vec<_> = actual.split_whitespace().collect();
                scopes.sort_unstable();
                let mut expected = vec![resource.scope()];
                if resource.persistent() { expected.push("offline_access"); }
                expected.sort_unstable();
                scopes != expected && scopes != [resource.scope()]
            }))
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
        wall_expires: SystemTime::now() + Duration::from_secs(seconds),
        executive_send,
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
    // A continuation cannot exchange a fresh code against an expired or
    // replaced retained Acquisition grant. Rejoin again immediately before
    // constructing the request, after consume's own continuation fence.
    if pending.continuation.is_some() && state.lock()
        .and_then(|mut inner| inner.continuation_exchange_guard(&pending)).is_err() {
        emit(&app);
        return;
    }
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
        Ok(r) => bounded_json(r, 32768).await.and_then(|v| {
            let access = parse_token(v.clone(), pending.resource)?;
            if pending.continuation.is_none() && pending.resource.persistent() {
                let refresh = v.get("refresh_token").and_then(Value::as_str)
                    .filter(|s| crate::native_refresh::valid_refresh(s))
                    .ok_or("REFRESH_TOKEN_NOT_ISSUED")?;
                let _keychain = state.keychain_lock.lock()
                    .map_err(|_| "KEYCHAIN_UNAVAILABLE")?;
                let inner = state.lock()?;
                if inner.generation != pending.generation || !inner.exchanging {
                    return Err("AUTHENTICATION_CHANGED".into());
                }
                crate::native_refresh::save(&client, pending.resource.audience(), refresh)?;
            }
            Ok(access)
        }),
        Err(_) => Err("TOKEN_EXCHANGE_FAILED".into()),
    };
    if let Some(witness) = pending.continuation.as_ref() {
        authorization_continuation::finish_callback(&app, &pending, witness, token).await;
        return;
    }
    let expiry = token.as_ref().ok().map(|token| (token.expires, token.wall_expires));
    let mut inner = match state.lock() {
        Ok(i) => i,
        Err(_) => return,
    };
    let next = inner.finish_exchange(pending.generation, pending.resource, token);
    drop(inner);
    emit(&app);
    if let Some((expires, wall_expires)) = expiry {
        schedule_expiration(app.clone(), pending.resource, expires, wall_expires, pending.generation);
    }
    if let Some(url) = next {
        let _ = open_transaction(&app, url, pending.generation);
    }
}

// Auth0 can report a revoked/expired/rotated grant on any of these exact
// statuses; never keep a permanent ambiguous Keychain marker for a definitive
// invalid_grant. Other errors or malformed responses remain ambiguous.
fn terminal_invalid_grant(status: u16, body: &Value) -> bool {
    matches!(status, 400 | 401 | 403) &&
    body.get("error").and_then(Value::as_str) == Some("invalid_grant")
}

/// Resume an existing, per-resource rotating Auth0 grant. No credential is
/// exposed through a Tauri command. The per-resource Tokio lock prevents
/// concurrent replay, including timer expiry racing with a workspace read.
async fn refresh_one(app: &AppHandle, resource: Resource) -> Result<()> {
    if !resource.persistent() { return Err("AUTHENTICATION_REQUIRED".into()); }
    let state = app.state::<NativeAuth>();
    let slot = match resource {
        Resource::Acquisition => 0,
        Resource::Content => 1,
        Resource::Executive => return Err("AUTHENTICATION_REQUIRED".into()),
    };
    let _singleflight = state.refresh_locks[slot].lock().await;
    let (client, generation) = {
        let inner = state.lock()?;
        if inner.token(resource).is_some_and(|t|
            t.expires > Instant::now() + Duration::from_secs(45) &&
            t.wall_expires > SystemTime::now() + Duration::from_secs(45)) { return Ok(()); }
        (inner.client_id.clone().ok_or("NATIVE_CLIENT_ID_MISSING")?, inner.generation)
    };
    let old = {
        let _keychain = state.keychain_lock.lock().map_err(|_| "KEYCHAIN_UNAVAILABLE")?;
        crate::native_refresh::load(&client, resource.audience())?
            .ok_or("AUTHENTICATION_REQUIRED")?
    };
    {
        let _keychain = state.keychain_lock.lock().map_err(|_| "KEYCHAIN_UNAVAILABLE")?;
        let inner = state.lock()?;
        if inner.generation != generation { return Err("AUTHENTICATION_CHANGED".into()); }
        crate::native_refresh::begin_rotation(&client, resource.audience(), &old)?;
    }
    // Once begin_rotation succeeds, the outcome must be assumed ambiguous if the
    // response fails. The Keychain marker prohibits replay on the next restart.
    let response = state.http.post(format!("{ISSUER}oauth/token"))
        .form(&[
            ("grant_type", "refresh_token"),
            ("client_id", client.as_str()),
            ("refresh_token", old.as_str()),
        ])
        .send().await;
    let response = match response {
        Ok(response) => response,
        Err(error) if error.is_connect() => {
            // reqwest classified the failure as a pre-transmission connection
            // error: Auth0 never received this grant. Permit an online retry,
            // but only after deleting our *exact* Keychain pending item.
            let _keychain = state.keychain_lock.lock().map_err(|_| "KEYCHAIN_UNAVAILABLE")?;
            let inner = state.lock()?;
            if inner.generation != generation { return Err("AUTHENTICATION_CHANGED".into()); }
            crate::native_refresh::rollback_untransmitted(&client, resource.audience(), &old)?;
            return Err("NETWORK_UNAVAILABLE".into());
        }
        Err(_) => return Err("REFRESH_OUTCOME_UNCONFIRMED".into()),
    };
    if !response.status().is_success() {
        let status = response.status().as_u16();
        let invalid_grant = if matches!(status, 400 | 401 | 403) {
            read_json_body(response, 32768).await.ok().is_some_and(|body|
                terminal_invalid_grant(status, &body))
        } else { false };
        if invalid_grant {
            let _keychain = state.keychain_lock.lock().map_err(|_| "KEYCHAIN_UNAVAILABLE")?;
            let mut inner = state.lock()?;
            if inner.generation != generation { return Err("AUTHENTICATION_CHANGED".into()); }
            // This response is terminal only for the exact grant this process
            // sent. The generation fence above is process-local: another
            // instance's explicit sign-out or fresh sign-in may have replaced
            // the stored credential and marker after begin_rotation. Qualified
            // cleanup mutates only items it can still prove hold the old
            // grant, so a newer login and its rotation marker survive a stale
            // response; a superseded account is not treated as signed out.
            let cleanup = crate::native_refresh::delete_stale(&client, resource.audience(), &old)?;
            match cleanup {
                crate::native_refresh::StaleGrantCleanup::Superseded => {
                    drop(inner); drop(_keychain); emit(app);
                    return Err("AUTHENTICATION_CHANGED".into());
                }
                crate::native_refresh::StaleGrantCleanup::RemovedStaleGrant
                | crate::native_refresh::StaleGrantCleanup::AlreadyAbsent => {
                    match resource {
                        Resource::Acquisition => inner.acquisition = None,
                        Resource::Content => inner.content = None,
                        Resource::Executive => (),
                    }
                }
            }
            drop(inner); drop(_keychain); emit(app);
            return Err("AUTHENTICATION_REQUIRED".into());
        }
        return Err("REFRESH_OUTCOME_UNCONFIRMED".into());
    }
    let decoded = read_json_body(response, 32768).await
        .map_err(|_| "REFRESH_OUTCOME_UNCONFIRMED")?;
    let access = parse_token(decoded.clone(), resource)
        .map_err(|_| "REFRESH_OUTCOME_UNCONFIRMED")?;
    let next = decoded.get("refresh_token").and_then(Value::as_str)
        .filter(|s| crate::native_refresh::valid_refresh(s))
        .ok_or("REFRESH_OUTCOME_UNCONFIRMED")?;
    let expires = access.expires;
    let wall_expires = access.wall_expires;
    {
        let _keychain = state.keychain_lock.lock().map_err(|_| "KEYCHAIN_UNAVAILABLE")?;
        let mut inner = state.lock()?;
        if inner.generation != generation { return Err("AUTHENTICATION_CHANGED".into()); }
        crate::native_refresh::finish_rotation(&client, resource.audience(), &old, next)?;
        match resource {
            Resource::Acquisition => {
                inner.acquisition = Some(access);
                inner.draft_continuity.unqualified();
            },
            Resource::Content => inner.content = Some(access),
            Resource::Executive => return Err("AUTHENTICATION_REQUIRED".into()),
        }
        inner.reason = None;
    }
    emit(app);
    schedule_expiration(app.clone(), resource, expires, wall_expires, generation);
    Ok(())
}

/// Resource read paths may transparently restore a previously authorized
/// native grant, but cannot bootstrap a new user identity or widen scopes.
async fn ensure_native_token(app: &AppHandle, resource: Resource) -> Result<(String, u64)> {
    let state = app.state::<NativeAuth>();
    let needs_refresh = {
        let inner = state.lock()?;
        inner.token(resource).is_none()
    };
    if needs_refresh && resource.persistent() {
        refresh_one(app, resource).await?;
    }
    let inner = state.lock()?;
    let token = inner.token(resource).ok_or("AUTHENTICATION_REQUIRED")?;
    Ok((token.value.clone(), inner.generation))
}

// Refresh while the credential is inside refresh_one's 45-second threshold.
// Scheduling 60 seconds before expiry silently made refresh_one return early
// without ever creating the next timer, so idle sessions still expired.
fn native_refresh_deadline(expires: Instant, now: Instant) -> Instant {
    let early = expires.checked_sub(Duration::from_secs(35)).unwrap_or(expires);
    let floor = now + Duration::from_secs(10);
    if early < floor { floor } else { early }
}
fn original_expiry_current(inner: &Inner, resource: Resource, expires: Instant,
    wall_expires: SystemTime, generation: u64) -> bool {
    inner.generation == generation && inner.stored_token(resource)
        .is_some_and(|token| token.expires == expires && token.wall_expires == wall_expires)
}
fn original_expiry_due(inner: &Inner, resource: Resource, expires: Instant,
    wall_expires: SystemTime, generation: u64, now: Instant, wall: SystemTime) -> bool {
    original_expiry_current(inner, resource, expires, wall_expires, generation)
        && (now >= expires || wall >= wall_expires)
}
fn schedule_expiration(app: AppHandle, resource: Resource, expires: Instant, wall_expires: SystemTime, generation: u64) {
    tauri::async_runtime::spawn(async move {
        let target = if resource.persistent() {
            native_refresh_deadline(expires, Instant::now())
        } else { expires };
        let wall_target = if resource.persistent() {
            wall_expires.checked_sub(Duration::from_secs(35)).unwrap_or(wall_expires)
        } else { wall_expires };
        // Wake/sleep-safe periodic deadline observation. Monotonic-only Tokio
        // timers can remain behind the real Auth0 expiry after laptop sleep.
        loop {
            let now = Instant::now();
            if now >= target || SystemTime::now() >= wall_target { break; }
            tokio::time::sleep((target - now).min(Duration::from_secs(30))).await;
        }
        let unchanged = app.state::<NativeAuth>().lock().is_ok_and(|inner|
            inner.generation == generation);
        if !unchanged { return; }
        if resource.persistent() {
            // A network/rotation failure does not replay an ambiguous token;
            // a later explicit sign-in remains available.
            let _ = refresh_one(&app, resource).await;
        }
        // An early refresh failure may leave the old token valid at this
        // point. The same original deadline owner must still report its real
        // expiry; it never retries refresh, creates another timer or extends
        // the token. A replacement grant/logout retires this old deadline.
        loop {
            let state = app.state::<NativeAuth>();
            let due = match state.lock() {
                Ok(inner) => {
                    if !original_expiry_current(&inner, resource, expires, wall_expires, generation) { return; }
                    original_expiry_due(&inner, resource, expires, wall_expires, generation, Instant::now(), SystemTime::now())
                },
                Err(_) => return,
            };
            if due { break; }
            let remaining = expires.saturating_duration_since(Instant::now());
            tokio::time::sleep(remaining.min(Duration::from_secs(30))).await;
        }
        emit(&app);
    });
}

/// Startup reads the platform Keychain on the native owner only. The frontend
/// sees a signing_in state, not any refresh/access credentials.
pub fn start_restore(app: AppHandle) {
    if !crate::native_refresh::enabled() { return; }
    if let Ok(mut inner) = app.state::<NativeAuth>().lock() {
        if inner.client_id.is_none() { return; }
        inner.restoring = true;
    } else { return; }
    emit(&app);
    tauri::async_runtime::spawn(async move {
        for resource in [Resource::Acquisition, Resource::Content] {
            let _ = refresh_one(&app, resource).await;
        }
        if let Ok(mut inner) = app.state::<NativeAuth>().lock() {
            inner.restoring = false;
        }
        emit(&app);
    });
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
pub struct SessionSelection {
    work_ref: String,
    root_job_id: String,
    /// The closed target kind of the selected session. An absent kind keeps
    /// the incumbent fabric target; no other kind is admitted.
    #[serde(default, deserialize_with = "deserialize_session_target_kind")]
    target_kind: Option<String>,
}
fn deserialize_session_target_kind<'de, D>(
    deserializer: D,
) -> std::result::Result<Option<String>, D::Error>
where
    D: serde::Deserializer<'de>,
{
    // Only omission uses the default. Explicit null is not legacy Fabric.
    String::deserialize(deserializer).map(Some)
}
impl SessionSelection {
    fn validate(&self) -> Result<()> {
        MissionSelection {
            work_ref: self.work_ref.clone(),
            root_job_id: self.root_job_id.clone(),
        }
        .validate()?;
        match self.target_kind.as_deref() {
            None => Ok(()),
            Some("fabric_attempt") | Some("hermes_secretary") | Some("hermes_meta") => Ok(()),
            Some(_) => Err("SELECTION_INVALID".into()),
        }
    }
    /// The exact wire selection. The legacy pair is carried verbatim; an
    /// explicit kind adds the one closed key and nothing else.
    fn wire(&self) -> Value {
        let mut selection = serde_json::json!({
            "work_ref": self.work_ref, "root_job_id": self.root_job_id
        });
        if let Some(kind) = &self.target_kind {
            selection["target_kind"] = Value::String(kind.to_owned());
        }
        selection
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
const MISSION_RESULT_RESPONSE_CAP: usize = 2_000_000;
const MISSION_RESULT_PATH: &str = "/workspace/mission-result/current";
const MISSION_RESULT_SCHEMA: &str = "mastermind.workspace_mission_result.v1";
const RESULT_MISSION_V3_PATH: &str = "/workspace/mission/v3/current";
const RESULT_DETAIL_PATH: &str = "/workspace/result/current";
const PLAN_DETAIL_PATH: &str = "/workspace/plan/current";
const PLAN_RESPONSE_CAP: usize = 16_384;
const PLAN_SCHEMA: &str = "mastermind.workspace_admitted_execution_plan.v1";
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
// Header compatibility is deliberately fixed to this one zero-selector read.
// The shared frontend decoder still validates the entire versioned DTO.
fn workspace_read_body(value: Value, path: &str, schema: &str) -> Result<Value> {
    let actual = value.get("schema").and_then(Value::as_str);
    let programs_v2 = path == "/workspace/programs/current"
        && schema == "mastermind.workspace_programs.v1"
        && actual == Some("mastermind.workspace_programs.v2");
    if !value.is_object() || (actual != Some(schema) && !programs_v2) {
        return Err("RESPONSE_INVALID".into());
    }
    Ok(value)
}
fn finish_programs_observation(state: &NativeAuth, ticket: Option<(u64, u64)>, observed: ProgramsRead) {
    // Optional observability never adds a fallible gate to the real read.
    if let Ok(mut inner) = state.lock() { inner.finish_programs_observation(ticket, observed); }
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
    let observation = if resource == Resource::Acquisition && path == "/workspace/programs/current" {
        state.lock().ok().and_then(|mut inner| inner.begin_programs_observation())
    } else { None };
    let (token, generation) = match ensure_native_token(&app, resource).await {
        Ok(value) => value,
        Err(error) => {
            finish_programs_observation(&state, observation, ProgramsRead::auth_unavailable());
            return Err(error);
        }
    };
    let response = match state.http.get(url).bearer_auth(token)
        .header("Accept", "application/json").header("Cache-Control", "no-store")
        .send().await {
        Ok(response) => response,
        Err(error) => {
            finish_programs_observation(&state, observation, ProgramsRead::network(error.is_timeout()));
            return Err("SOURCE_UNAVAILABLE".into());
        }
    };
    let status = response.status().as_u16();
    let result = bounded_json(response, MAX_RESPONSE).await;
    if !state.lock()?.release_allowed(generation, resource) {
        finish_programs_observation(&state, observation, ProgramsRead::auth_unavailable());
        return Err("AUTHENTICATION_CHANGED".into());
    }
    let result = result.and_then(|value| workspace_read_body(value, path, schema));
    finish_programs_observation(&state, observation,
        ProgramsRead::response(status, result.as_ref().err().map(String::as_str)));
    result
}
#[tauri::command]
pub async fn read_byok_roles(app: AppHandle) -> Result<Value> {
    let url = Url::parse(&format!("{ORIGIN}/workspace/byok/roles/current"))
        .map_err(|_| "REQUEST_INVALID")?;
    let state = app.state::<NativeAuth>();
    let (token, generation) = ensure_native_token(&app, Resource::Acquisition).await?;
    let response = state.http.get(url).bearer_auth(token)
        .header("Accept", "application/json").header("Cache-Control", "no-store")
        .send().await.map_err(|_| "SOURCE_UNAVAILABLE")?;
    let result = bounded_json(response, 8192).await;
    if !state.lock()?.release_allowed(generation, Resource::Acquisition) {
        return Err("AUTHENTICATION_CHANGED".into());
    }
    let value = result?;
    if !value.is_object() || value.get("schema").and_then(Value::as_str)
        != Some("mastermind.workspace_byok_roles.v1") {
        return Err("RESPONSE_INVALID".into());
    }
    // Both native and web release through the same closed frontend decoder.
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
    let (token, generation) = ensure_native_token(&app, Resource::Acquisition).await?;
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
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ProjectPlanSelection {
    work_ref: String,
}
impl ProjectPlanSelection {
    fn validate(&self) -> Result<()> {
        let work = self.work_ref.strip_prefix("WS:").ok_or("SELECTION_INVALID")?;
        if !(2..=64).contains(&work.len()) || work.split('-').any(|part|
            part.is_empty() || !part.bytes().all(|b| b.is_ascii_uppercase() || b.is_ascii_digit())) {
            return Err("SELECTION_INVALID".into());
        }
        Ok(())
    }
}
const PROJECT_PLAN_PATH: &str = "/workspace/project-plan/current";
const PROJECT_PLAN_SCHEMA: &str = "mastermind.workspace_project_plan.v1";
const PROJECT_PLAN_SCHEMA_V2: &str = "mastermind.workspace_project_plan.v2";
const PROJECT_PLAN_RESPONSE_CAP: usize = 131_072;
fn project_plan_target(selection: &ProjectPlanSelection) -> Result<Url> {
    selection.validate()?;
    let mut url = Url::parse(&format!("{ORIGIN}{PROJECT_PLAN_PATH}")).map_err(|_| "REQUEST_INVALID")?;
    url.query_pairs_mut().append_pair("work_ref", &selection.work_ref);
    Ok(url)
}
fn project_plan_header_matches(value: &Value, selection: &ProjectPlanSelection) -> bool {
    matches!(value.get("schema").and_then(Value::as_str),
        Some(PROJECT_PLAN_SCHEMA) | Some(PROJECT_PLAN_SCHEMA_V2))
        && value.get("selection").and_then(|s| s.get("work_ref")).and_then(Value::as_str) == Some(selection.work_ref.as_str())
}
#[tauri::command]
pub async fn read_project_plan(app: AppHandle, selection: ProjectPlanSelection) -> Result<Value> {
    let url = project_plan_target(&selection)?;
    let state = app.state::<NativeAuth>();
    let (token, generation) = ensure_native_token(&app, Resource::Acquisition).await?;
    let response = state.http.get(url).bearer_auth(token)
        .header("Accept", "application/json").header("Cache-Control", "no-store")
        .send().await.map_err(|_| "SOURCE_UNAVAILABLE")?;
    let result = if response.status().as_u16() == 503 {
        read_json_body(response, PROJECT_PLAN_RESPONSE_CAP).await
            .and_then(|value| typed_unavailable(value, PROJECT_PLAN_SCHEMA, false))
    } else {
        bounded_json(response, PROJECT_PLAN_RESPONSE_CAP).await
    };
    if !state.lock()?.release_allowed(generation, Resource::Acquisition) {
        return Err("AUTHENTICATION_CHANGED".into());
    }
    let value = result?;
    if !project_plan_header_matches(&value, &selection) {
        return Err("RESPONSE_INVALID".into());
    }
    // The existing host performs the sole full closed-body decode before display.
    Ok(value)
}

const PROJECT_ARCHIVE_PATH: &str = "/workspace/projects/archive/current";
const PROJECT_ARCHIVE_SCHEMA: &str = "mastermind.workspace_project_archive.v1";
const PROJECT_ARCHIVE_RESPONSE_CAP: usize = 262_144;
fn project_archive_target() -> Result<Url> {
    Url::parse(&format!("{ORIGIN}{PROJECT_ARCHIVE_PATH}")).map_err(|_| "REQUEST_INVALID".into())
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ProjectArchiveCursor {
    after_work_ref: String,
    catalogue_digest: String,
}
fn project_archive_page_target(cursor: &ProjectArchiveCursor) -> Result<Url> {
    ProjectPlanSelection { work_ref: cursor.after_work_ref.clone() }.validate()?;
    if cursor.catalogue_digest.len() != 64 || !cursor.catalogue_digest.bytes().all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b)) {
        return Err("REQUEST_INVALID".into());
    }
    let mut url = project_archive_target()?;
    url.query_pairs_mut().append_pair("after_work_ref", &cursor.after_work_ref)
        .append_pair("catalogue_digest", &cursor.catalogue_digest);
    Ok(url)
}
#[tauri::command]
pub async fn read_project_archive(app: AppHandle) -> Result<Value> {
    let target = project_archive_target()?;
    read_project_archive_at(app, target).await
}
#[tauri::command]
pub async fn read_project_archive_page(app: AppHandle, cursor: ProjectArchiveCursor) -> Result<Value> {
    let target = project_archive_page_target(&cursor)?;
    read_project_archive_at(app, target).await
}
async fn read_project_archive_at(app: AppHandle, target: Url) -> Result<Value> {
    let state = app.state::<NativeAuth>();
    let (token, generation) = ensure_native_token(&app, Resource::Acquisition).await?;
    let response = state.http.get(target).bearer_auth(token)
        .header("Accept", "application/json").header("Cache-Control", "no-store")
        .send().await.map_err(|_| "SOURCE_UNAVAILABLE")?;
    let result = if response.status().as_u16() == 503 {
        read_json_body(response, PROJECT_ARCHIVE_RESPONSE_CAP).await
            .and_then(|value| typed_unavailable(value, PROJECT_ARCHIVE_SCHEMA, false))
    } else {
        bounded_json(response, PROJECT_ARCHIVE_RESPONSE_CAP).await
    };
    if !state.lock()?.release_allowed(generation, Resource::Acquisition) {
        return Err("AUTHENTICATION_CHANGED".into());
    }
    let value = result?;
    if value.get("schema").and_then(Value::as_str) != Some(PROJECT_ARCHIVE_SCHEMA) {
        return Err("RESPONSE_INVALID".into());
    }
    // The existing host performs the full closed-body decode before display.
    Ok(value)
}

const PROJECT_DIRECTION_PATH: &str = "/workspace/project-direction/current";
const PROJECT_DIRECTION_SCHEMA: &str = "mastermind.workspace_project_direction.v1";
const PROJECT_DIRECTION_RESPONSE_CAP: usize = 65_536;
fn project_direction_target(selection: &ProjectPlanSelection) -> Result<Url> {
    selection.validate()?;
    let mut url = Url::parse(&format!("{ORIGIN}{PROJECT_DIRECTION_PATH}")).map_err(|_| "REQUEST_INVALID")?;
    url.query_pairs_mut().append_pair("work_ref", &selection.work_ref);
    Ok(url)
}
fn project_direction_header_matches(value: &Value, selection: &ProjectPlanSelection) -> bool {
    value.get("schema").and_then(Value::as_str) == Some(PROJECT_DIRECTION_SCHEMA)
        && value.get("selection").and_then(|s| s.get("work_ref")).and_then(Value::as_str) == Some(selection.work_ref.as_str())
}
#[tauri::command]
pub async fn read_project_direction(app: AppHandle, selection: ProjectPlanSelection) -> Result<Value> {
    let url = project_direction_target(&selection)?;
    let state = app.state::<NativeAuth>();
    let (token, generation) = ensure_native_token(&app, Resource::Acquisition).await?;
    let response = state.http.get(url).bearer_auth(token)
        .header("Accept", "application/json").header("Cache-Control", "no-store")
        .send().await.map_err(|_| "SOURCE_UNAVAILABLE")?;
    let result = if response.status().as_u16() == 503 {
        read_json_body(response, PROJECT_DIRECTION_RESPONSE_CAP).await
            .and_then(|value| typed_unavailable(value, PROJECT_DIRECTION_SCHEMA, false))
    } else {
        bounded_json(response, PROJECT_DIRECTION_RESPONSE_CAP).await
    };
    if !state.lock()?.release_allowed(generation, Resource::Acquisition) {
        return Err("AUTHENTICATION_CHANGED".into());
    }
    let value = result?;
    if !project_direction_header_matches(&value, &selection) {
        return Err("RESPONSE_INVALID".into());
    }
    // Full closed-body validation remains in the existing host decode boundary.
    Ok(value)
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ProjectKnowledgeSourceSelection {
    work_ref: String,
    source_ref: String,
    expected_revision: String,
}
impl ProjectKnowledgeSourceSelection {
    fn validate(&self) -> Result<()> {
        ProjectPlanSelection { work_ref: self.work_ref.clone() }.validate()?;
        let digest = self.source_ref.strip_prefix("project-file.v1.")
            .or_else(|| self.source_ref.strip_prefix("project-record.v1.")).ok_or("SELECTION_INVALID")?;
        if digest.len() != 64 || !digest.bytes().all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
            || self.expected_revision.len() != 40
            || !self.expected_revision.bytes().all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b)) {
            return Err("SELECTION_INVALID".into());
        }
        Ok(())
    }
}
#[derive(Clone, Copy)]
enum ProjectKnowledgeReadKind { Catalogue, Memory, Source }
impl ProjectKnowledgeReadKind {
    fn path(self) -> &'static str { match self {
        Self::Catalogue => "/workspace/project-knowledge/current",
        Self::Memory => "/workspace/project-memory/current",
        Self::Source => "/workspace/project-source/current",
    }}
    fn schema(self) -> &'static str { match self {
        Self::Catalogue => "mastermind.workspace_project_knowledge.v1",
        Self::Memory => "mastermind.workspace_project_preference.v1",
        Self::Source => "mastermind.workspace_project_source.v1",
    }}
}
fn project_knowledge_target(kind: ProjectKnowledgeReadKind, work_ref: &str,
        source: Option<(&str, &str)>) -> Result<Url> {
    ProjectPlanSelection { work_ref: work_ref.to_owned() }.validate()?;
    if matches!(kind, ProjectKnowledgeReadKind::Source) != source.is_some() {
        return Err("SELECTION_INVALID".into());
    }
    let mut url = Url::parse(&format!("{ORIGIN}{}",kind.path())).map_err(|_| "REQUEST_INVALID")?;
    url.query_pairs_mut().append_pair("work_ref",work_ref);
    if let Some((source_ref,revision)) = source {
        ProjectKnowledgeSourceSelection {work_ref:work_ref.to_owned(),source_ref:source_ref.to_owned(),expected_revision:revision.to_owned()}.validate()?;
        url.query_pairs_mut().append_pair("source_ref",source_ref).append_pair("expected_revision",revision);
    }
    Ok(url)
}
async fn project_knowledge_read(app: AppHandle, kind: ProjectKnowledgeReadKind,
        work_ref: String, source: Option<(String,String)>) -> Result<Value> {
    let url = project_knowledge_target(kind,&work_ref,source.as_ref().map(|(a,b)|(a.as_str(),b.as_str())))?;
    let state=app.state::<NativeAuth>();
    let (token,generation)=ensure_native_token(&app,Resource::Acquisition).await?;
    let response=state.http.get(url).bearer_auth(token).header("Accept","application/json")
        .header("Cache-Control","no-store").send().await.map_err(|_| "SOURCE_UNAVAILABLE")?;
    let result=if response.status().as_u16()==503 {
        read_json_body(response,131_072).await.and_then(|value|typed_unavailable(value,kind.schema(),false))
    } else { bounded_json(response,131_072).await };
    if !state.lock()?.release_allowed(generation,Resource::Acquisition) {return Err("AUTHENTICATION_CHANGED".into());}
    let value=result?;
    let selected=value.get("selection").and_then(Value::as_object).ok_or("RESPONSE_INVALID")?;
    let expected_count=if source.is_some(){2}else{1};
    if value.get("schema").and_then(Value::as_str)!=Some(kind.schema()) || selected.len()!=expected_count
        || selected.get("work_ref").and_then(Value::as_str)!=Some(work_ref.as_str()) {
        return Err("RESPONSE_INVALID".into());
    }
    if let Some((source_ref,revision))=source {
        if selected.get("source_ref").and_then(Value::as_str)!=Some(source_ref.as_str())
            || (value.get("availability").and_then(Value::as_str)==Some("AVAILABLE")
                && value.get("source").and_then(|v|v.get("revision")).and_then(Value::as_str)!=Some(revision.as_str())) {
            return Err("RESPONSE_INVALID".into());
        }
    }
    Ok(value)
}
#[tauri::command]
pub async fn read_project_knowledge_catalogue(app:AppHandle,selection:ProjectPlanSelection)->Result<Value>{
    project_knowledge_read(app,ProjectKnowledgeReadKind::Catalogue,selection.work_ref,None).await
}
#[tauri::command]
pub async fn read_project_knowledge_memory(app:AppHandle,selection:ProjectPlanSelection)->Result<Value>{
    project_knowledge_read(app,ProjectKnowledgeReadKind::Memory,selection.work_ref,None).await
}
#[tauri::command]
pub async fn read_project_knowledge_source(app:AppHandle,selection:ProjectKnowledgeSourceSelection)->Result<Value>{
    selection.validate()?;
    project_knowledge_read(app,ProjectKnowledgeReadKind::Source,selection.work_ref,Some((selection.source_ref,selection.expected_revision))).await
}

const PROJECT_JOURNAL_PATH: &str = "/workspace/project-journal/current";
const PROJECT_JOURNAL_SCHEMA: &str = "mastermind.workspace_project_journal.v1";
const PROJECT_JOURNAL_RESPONSE_CAP: usize = 131_072;
fn project_journal_target(selection: &ProjectPlanSelection) -> Result<Url> {
    selection.validate()?;
    let mut url = Url::parse(&format!("{ORIGIN}{PROJECT_JOURNAL_PATH}")).map_err(|_| "REQUEST_INVALID")?;
    url.query_pairs_mut().append_pair("work_ref", &selection.work_ref);
    Ok(url)
}
#[tauri::command]
pub async fn read_project_journal(app: AppHandle, selection: ProjectPlanSelection) -> Result<Value> {
    let url = project_journal_target(&selection)?;
    let state = app.state::<NativeAuth>();
    let (token, generation) = ensure_native_token(&app, Resource::Acquisition).await?;
    let response = state.http.get(url).bearer_auth(token)
        .header("Accept", "application/json").header("Cache-Control", "no-store")
        .send().await.map_err(|_| "SOURCE_UNAVAILABLE")?;
    let result = if response.status().as_u16() == 503 {
        read_json_body(response, PROJECT_JOURNAL_RESPONSE_CAP).await
            .and_then(|value| typed_unavailable(value, PROJECT_JOURNAL_SCHEMA, false))
    } else {
        bounded_json(response, PROJECT_JOURNAL_RESPONSE_CAP).await
    };
    if !state.lock()?.release_allowed(generation, Resource::Acquisition) {
        return Err("AUTHENTICATION_CHANGED".into());
    }
    let value = result?;
    if value.get("schema").and_then(Value::as_str) != Some(PROJECT_JOURNAL_SCHEMA)
        || value.get("selection").and_then(|s| s.get("work_ref")).and_then(Value::as_str) != Some(selection.work_ref.as_str()) {
        return Err("RESPONSE_INVALID".into());
    }
    // The existing host performs the sole full closed-body decode before display.
    Ok(value)
}


// Project admission uses a dedicated fixed action/status surface. These selectors
// carry no principal, grant, path or mutation authority from the webview.
#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ProjectAdmissionSelection {
    work_ref: String,
    #[serde(default, skip_serializing_if = "Option::is_none", deserialize_with = "admission_optional_root")]
    root_job_id: Option<String>,
}
fn admission_optional_root<'de, D: serde::Deserializer<'de>>(d: D) -> std::result::Result<Option<String>, D::Error> {
    String::deserialize(d).map(Some)
}
impl ProjectAdmissionSelection {
    fn validate(&self) -> Result<()> {
        ProjectPlanSelection { work_ref: self.work_ref.clone() }.validate()?;
        if let Some(root) = &self.root_job_id { validate_workspace_pair(&self.work_ref, root)?; }
        Ok(())
    }
}
#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ProjectAdmissionPauseRequest { selection: ProjectAdmissionSelection, command_id: String }
#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ProjectAdmissionPauseToken { event_id: u64, receipt_digest: String }
#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ProjectAdmissionResumeRequest {
    selection: ProjectAdmissionSelection, command_id: String, pause_token: ProjectAdmissionPauseToken,
}
#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ProjectAdmissionStatusRequest { selection: ProjectAdmissionSelection, command_id: String, kind: String }
#[derive(Clone, Copy, PartialEq, Eq)]
enum ProjectAdmissionMode { Current, Pause, Resume, PauseStatus, ResumeStatus }
fn project_admission_command(command: &str, resume: bool) -> Result<()> {
    let prefix = if resume { "mmos-project-resume-" } else { "mmos-project-pause-" };
    if !command.strip_prefix(prefix).is_some_and(|suffix| lowercase_hex(suffix, 40)) {
        return Err("REQUEST_INVALID".into());
    }
    Ok(())
}
fn project_admission_target(mode: ProjectAdmissionMode, selection: &ProjectAdmissionSelection, command: Option<&str>) -> Result<Url> {
    selection.validate()?;
    let path = match mode {
        ProjectAdmissionMode::Current => "current", ProjectAdmissionMode::Pause => "pause",
        ProjectAdmissionMode::Resume => "resume", _ => "operation",
    };
    let mut url = Url::parse(&format!("{ORIGIN}/workspace/project-admission/{path}")).map_err(|_| "REQUEST_INVALID")?;
    if mode == ProjectAdmissionMode::Current || matches!(mode, ProjectAdmissionMode::PauseStatus | ProjectAdmissionMode::ResumeStatus) {
        url.query_pairs_mut().append_pair("work_ref", &selection.work_ref);
        if let Some(root) = &selection.root_job_id { url.query_pairs_mut().append_pair("root_job_id", root); }
    }
    if mode != ProjectAdmissionMode::Current {
        let command = command.ok_or("REQUEST_INVALID")?;
        let resume = matches!(mode, ProjectAdmissionMode::Resume | ProjectAdmissionMode::ResumeStatus);
        project_admission_command(command, resume)?;
        if matches!(mode, ProjectAdmissionMode::PauseStatus | ProjectAdmissionMode::ResumeStatus) {
            url.query_pairs_mut().append_pair("command_id", command)
                .append_pair("kind", if resume { "project_resume" } else { "project_pause" });
        }
    } else if command.is_some() { return Err("REQUEST_INVALID".into()); }
    Ok(url)
}
fn project_admission_header_matches(value: &Value, mode: ProjectAdmissionMode, selection: &ProjectAdmissionSelection, command: Option<&str>) -> bool {
    let schema = match mode {
        ProjectAdmissionMode::Current => "mastermind.workspace_project_admission_control.v1",
        ProjectAdmissionMode::Pause => "mastermind.workspace_project_admission_action_result.v1",
        ProjectAdmissionMode::Resume => "mastermind.workspace_project_resumption_action_result.v1",
        ProjectAdmissionMode::PauseStatus => "mastermind.workspace_project_admission_status_result.v1",
        ProjectAdmissionMode::ResumeStatus => "mastermind.workspace_project_resumption_status_result.v1",
    };
    let Ok(mut expected) = serde_json::to_value(selection) else { return false; };
    if let Some(command) = command { expected["command_id"] = Value::String(command.into()); }
    value.get("schema").and_then(Value::as_str) == Some(schema) && value.get("selection") == Some(&expected)
}
async fn project_admission_exchange(app: AppHandle, mode: ProjectAdmissionMode, selection: ProjectAdmissionSelection, command: Option<String>, body: Option<Value>) -> Result<Value> {
    let url = project_admission_target(mode, &selection, command.as_deref())?;
    let action = matches!(mode, ProjectAdmissionMode::Pause | ProjectAdmissionMode::Resume);
    if action != body.is_some() { return Err("REQUEST_INVALID".into()); }
    let encoded = body.map(|body| serde_json::to_vec(&body).map_err(|_| "REQUEST_INVALID".to_owned())).transpose()?;
    if encoded.as_ref().is_some_and(|v| v.len() > 16_384) { return Err("REQUEST_BOUND".into()); }
    let state = app.state::<NativeAuth>();
    let before = state.lock()?.generation;
    let (token, generation) = ensure_native_token(&app, Resource::Acquisition).await?;
    // Authentication may change while token acquisition awaits; no action may
    // cross that identity change, even if the replacement user is signed in.
    if before != generation || !state.lock()?.release_allowed(generation, Resource::Acquisition) {
        return Err("AUTHENTICATION_CHANGED".into());
    }
    let mut request = if let Some(bytes) = encoded {
        state.http.post(url).header("Content-Type", "application/json").body(bytes)
    } else { state.http.get(url) };
    request = request.bearer_auth(token).header("Accept", "application/json")
        .header("Cache-Control", "no-store").timeout(Duration::from_secs(60));
    let response = request.send().await.map_err(|_| "SOURCE_UNAVAILABLE")?;
    let result = if response.status().as_u16() == 503 {
        read_json_body(response, 32_768).await
    } else { bounded_json(response, 32_768).await };
    if !state.lock()?.release_allowed(generation, Resource::Acquisition) { return Err("AUTHENTICATION_CHANGED".into()); }
    let value = result?;
    if !project_admission_header_matches(&value, mode, &selection, command.as_deref()) { return Err("RESPONSE_INVALID".into()); }
    // The typed host decodes the full current document; the incumbent finite
    // port decodes every action/status receipt before controller publication.
    Ok(value)
}
#[tauri::command]
pub async fn read_project_admission_control(app: AppHandle, selection: ProjectAdmissionSelection) -> Result<Value> {
    project_admission_exchange(app, ProjectAdmissionMode::Current, selection, None, None).await
}
#[tauri::command]
pub async fn pause_project_admission(app: AppHandle, request: ProjectAdmissionPauseRequest) -> Result<Value> {
    project_admission_command(&request.command_id, false)?;
    let body = serde_json::to_value(&request).map_err(|_| "REQUEST_INVALID")?;
    project_admission_exchange(app, ProjectAdmissionMode::Pause, request.selection, Some(request.command_id), Some(body)).await
}
#[tauri::command]
pub async fn resume_project_admission(app: AppHandle, request: ProjectAdmissionResumeRequest) -> Result<Value> {
    project_admission_command(&request.command_id, true)?;
    if request.pause_token.event_id == 0 || request.pause_token.event_id > MAX_SAFE_GENERATION
        || !lowercase_hex(&request.pause_token.receipt_digest, 64) { return Err("REQUEST_INVALID".into()); }
    let body = serde_json::to_value(&request).map_err(|_| "REQUEST_INVALID")?;
    project_admission_exchange(app, ProjectAdmissionMode::Resume, request.selection, Some(request.command_id), Some(body)).await
}
#[tauri::command]
pub async fn read_project_admission_operation(app: AppHandle, request: ProjectAdmissionStatusRequest) -> Result<Value> {
    let mode = match request.kind.as_str() { "project_pause" => ProjectAdmissionMode::PauseStatus,
        "project_resume" => ProjectAdmissionMode::ResumeStatus, _ => return Err("REQUEST_INVALID".into()) };
    project_admission_exchange(app, mode, request.selection, Some(request.command_id), None).await
}


#[cfg(test)]
mod project_admission_transport_tests {
    use super::*;
    fn selection() -> ProjectAdmissionSelection { ProjectAdmissionSelection { work_ref: "WS:PROJECT-ONE".into(), root_job_id: None } }
    #[test]
    fn fixed_targets_and_exact_original_namespaces() {
        let selection = selection();
        let pause = format!("mmos-project-pause-{}", "a".repeat(40));
        let resume = format!("mmos-project-resume-{}", "b".repeat(40));
        let current = project_admission_target(ProjectAdmissionMode::Current, &selection, None).unwrap();
        assert_eq!(current.as_str(), "https://mcp.mastermind-x.com/workspace/project-admission/current?work_ref=WS%3APROJECT-ONE");
        let status = project_admission_target(ProjectAdmissionMode::ResumeStatus, &selection, Some(&resume)).unwrap();
        assert_eq!(status.path(), "/workspace/project-admission/operation");
        assert!(status.query_pairs().any(|(k,v)| k == "kind" && v == "project_resume"));
        let mutation = project_admission_target(ProjectAdmissionMode::Pause, &selection, Some(&pause)).unwrap();
        assert_eq!(mutation.path(), "/workspace/project-admission/pause"); assert_eq!(mutation.query(), None);
        assert!(project_admission_target(ProjectAdmissionMode::Pause, &selection, Some(&resume)).is_err());
        assert!(project_admission_target(ProjectAdmissionMode::ResumeStatus, &selection, Some(&pause)).is_err());
        assert!(project_admission_target(ProjectAdmissionMode::Current, &selection, Some(&pause)).is_err());
        for command in [pause.clone()+"\n", pause.to_uppercase(), "mmos-project-pause-a".into()] { assert!(project_admission_command(&command, false).is_err()); }
    }
    #[test]
    fn closed_selectors_and_requests_reject_private_or_foreign_fields() {
        for bad in [serde_json::json!({"work_ref":"WS:PROJECT-ONE","root_job_id":null}),
            serde_json::json!({"work_ref":"WS:PROJECT-ONE","principal":"caller"}),
            serde_json::json!({"work_ref":"WS:PROJECT-ONE","root_job_id":1})] {
            assert!(serde_json::from_value::<ProjectAdmissionSelection>(bad).is_err());
        }
        for bad in ["WS:x", "WS:PROJECT--ONE", "WS:PROJECT_ONE", "WS:PROJECT-ONE\n"] {
            let selected = ProjectAdmissionSelection { work_ref:bad.into(), root_job_id:None };
            assert!(project_admission_target(ProjectAdmissionMode::Current,&selected,None).is_err());
        }
        let mut selected=selection();
        for root in ["JOB-0", "JOB-0001", "JOB-999999999"] { selected.root_job_id=Some(root.into()); assert!(selected.validate().is_ok()); }
        for root in ["JOB-", "JOB-1000000000", "JOB-1\n", "JOB-other"] { selected.root_job_id=Some(root.into()); assert!(selected.validate().is_err()); }
        let pause = serde_json::json!({"selection":{"work_ref":"WS:PROJECT-ONE"},"command_id":format!("mmos-project-pause-{}","a".repeat(40))});
        assert!(serde_json::from_value::<ProjectAdmissionPauseRequest>(pause.clone()).is_ok());
        for field in ["url","actor","permission_digest","pause_token","kind"] { let mut v=pause.clone(); v[field]=Value::String("private".into()); assert!(serde_json::from_value::<ProjectAdmissionPauseRequest>(v).is_err()); }
        assert!(serde_json::from_value::<ProjectAdmissionPauseToken>(serde_json::json!({"event_id":1,"receipt_digest":"a".repeat(64),"extra":true})).is_err());
    }
    #[test]
    fn response_header_withholds_other_originals_and_scope() {
        let selection=selection(); let command=format!("mmos-project-pause-{}","a".repeat(40));
        let mut value=serde_json::json!({"schema":"mastermind.workspace_project_admission_status_result.v1","selection":{"work_ref":"WS:PROJECT-ONE","command_id":command}});
        assert!(project_admission_header_matches(&value,ProjectAdmissionMode::PauseStatus,&selection,Some(&command)));
        assert!(!project_admission_header_matches(&value,ProjectAdmissionMode::ResumeStatus,&selection,Some(&command)));
        value["selection"]["root_job_id"]=Value::String("JOB-1".into());
        assert!(!project_admission_header_matches(&value,ProjectAdmissionMode::PauseStatus,&selection,Some(&command)));
        value["selection"].as_object_mut().unwrap().remove("root_job_id");
        value["selection"]["command_id"]=Value::String(format!("mmos-project-pause-{}","b".repeat(40)));
        assert!(!project_admission_header_matches(&value,ProjectAdmissionMode::PauseStatus,&selection,Some(&command)));
    }
}

const PROJECT_SESSION_PATH: &str = "/workspace/project-session/current";
const PROJECT_SESSION_SCHEMA: &str = "mastermind.workspace_project_session_association.v1";
const PROJECT_SESSION_RESPONSE_CAP: usize = 16_384;

#[derive(Debug, Clone, serde::Deserialize)]
#[serde(deny_unknown_fields)]
pub struct SourceOperationContextSelection {
    action: String,
    work_ref: Option<String>,
}
fn source_operation_context_target(selection: &SourceOperationContextSelection) -> Result<Url> {
    if !matches!(selection.action.as_str(), "publish_project_proposal" | "ADOPT_PLAN" | "ACCEPT_DIRECTION"
        | "add_project_file" | "set_project_communication_preference" | "correct_project_discovery") {
        return Err("SELECTION_INVALID".into());
    }
    if let Some(work) = &selection.work_ref {
        ProjectPlanSelection { work_ref: work.clone() }.validate()?;
    } else if selection.action != "publish_project_proposal" {
        return Err("SELECTION_INVALID".into());
    }
    let mut url = Url::parse(&format!("{ORIGIN}/workspace/source-operation/context"))
        .map_err(|_| "REQUEST_INVALID")?;
    url.query_pairs_mut().append_pair("action", &selection.action);
    if let Some(work) = &selection.work_ref {
        url.query_pairs_mut().append_pair("work_ref", work);
    }
    Ok(url)
}
#[tauri::command]
pub async fn read_source_operation_context(app: AppHandle, selection: SourceOperationContextSelection) -> Result<Value> {
    let url = source_operation_context_target(&selection)?;
    let state = app.state::<NativeAuth>();
    let (token, generation) = ensure_native_token(&app, Resource::Acquisition).await?;
    let response = state.http.get(url).bearer_auth(token)
        .header("Accept", "application/json").header("Cache-Control", "no-store")
        .send().await.map_err(|_| "SOURCE_UNAVAILABLE")?;
    let result = bounded_json(response, 4096).await;
    if !state.lock()?.release_allowed(generation, Resource::Acquisition) {
        return Err("AUTHENTICATION_CHANGED".into());
    }
    let value = result?;
    if value.get("schema").and_then(Value::as_str) != Some("mastermind.workspace_source_operation_context.v1")
        || value.get("selection").and_then(|s| s.get("action")).and_then(Value::as_str) != Some(selection.action.as_str())
        || value.get("selection").and_then(|s| s.get("work_ref")).and_then(Value::as_str) != selection.work_ref.as_deref() {
        return Err("RESPONSE_INVALID".into());
    }
    Ok(value)
}
const SOURCE_OPERATION_CAP: usize = 32_768;
const PROJECT_FILE_PREPARE_CAP: usize = 98_304;
fn source_operation_keys(value: &Value, keys: &[&str]) -> Result<()> {
    let object = value.as_object().ok_or("REQUEST_INVALID")?;
    if object.len() != keys.len() || keys.iter().any(|key| !object.contains_key(*key)) {
        return Err("REQUEST_INVALID".into());
    }
    Ok(())
}
fn source_operation_hex(value: Option<&str>, length: usize) -> bool {
    value.is_some_and(|s| {
        s.len() == length
            && s.bytes()
                .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
    })
}
fn source_operation_identity(request: &Value) -> Result<(&str, &str, &str)> {
    let action = request
        .get("action")
        .and_then(Value::as_str)
        .ok_or("REQUEST_INVALID")?;
    let prefix = match action {
        "publish_project_proposal" => "mmos-project-create-",
        "ADOPT_PLAN" => "mmos-project-adopt-",
        "ACCEPT_DIRECTION" => "mmos-direction-accept-",
        "add_project_file" => "mmos-project-file-add-",
        "set_project_communication_preference" => "mmos-project-preference-set-",
        "correct_project_discovery" => "mmos-project-discovery-correct-",
        _ => return Err("REQUEST_INVALID".into()),
    };
    let id = request
        .get("request_id")
        .and_then(Value::as_str)
        .ok_or("REQUEST_INVALID")?;
    if !id
        .strip_prefix(prefix)
        .is_some_and(|tail| source_operation_hex(Some(tail), 40))
    {
        return Err("REQUEST_INVALID".into());
    }
    let work = request
        .get("work_ref")
        .and_then(Value::as_str)
        .ok_or("REQUEST_INVALID")?;
    ProjectPlanSelection {
        work_ref: work.to_owned(),
    }
    .validate()?;
    Ok((action, id, work))
}
fn source_discovery_ref(value: Option<&str>) -> bool {
    value.and_then(|s| s.strip_prefix("DSC:")).is_some_and(|key| {
        (2..=64).contains(&key.len()) && key.split('-').all(|part| !part.is_empty()
            && part.bytes().all(|b| b.is_ascii_uppercase() || b.is_ascii_digit()))
    })
}
fn source_correction_text(value: &Value, limit: usize, empty: bool) -> bool {
    value.as_str().is_some_and(|s| s.len() <= limit && (!s.trim().is_empty() || (empty && s.is_empty()))
        && !s.chars().any(|c| (c < '\u{20}' && !matches!(c, '\n' | '\r' | '\t')) || ('\u{7f}'..='\u{9f}').contains(&c)))
}
fn source_correction_date(value: &Value) -> bool {
    let Some(s) = value.as_str() else { return false; };
    let b = s.as_bytes();
    if b.len() != 10 || b[4] != b'-' || b[7] != b'-'
        || b.iter().enumerate().any(|(i,c)| i != 4 && i != 7 && !c.is_ascii_digit()) { return false; }
    let year: u32 = s[..4].parse().unwrap_or(0);
    let month: usize = s[5..7].parse().unwrap_or(0);
    let day: u32 = s[8..].parse().unwrap_or(0);
    let days = [31, if year % 4 == 0 && (year % 100 != 0 || year % 400 == 0) {29} else {28},31,30,31,30,31,31,30,31,30,31];
    year > 0 && (1..=12).contains(&month) && day > 0 && day <= days[month - 1]
}
fn source_discovery_correction_request(value: &Value) -> Result<()> {
    source_operation_keys(value, &["schema","request_id","work_ref","source_commit","base_revision",
        "discovery_ref","expected_discovery_revision","correction_reason","replacement"])?;
    if value["schema"].as_str() != Some("mastermind.project_discovery_correct_request.v1")
        || !source_operation_hex(value["source_commit"].as_str(),40)
        || !source_operation_hex(value["base_revision"].as_str(),64)
        || !source_operation_hex(value["expected_discovery_revision"].as_str(),64)
        || !source_discovery_ref(value["discovery_ref"].as_str())
        || !source_correction_text(&value["correction_reason"],2048,false)
        || serde_json::to_vec(value).map_err(|_| "REQUEST_INVALID")?.len() > 24_576 {
        return Err("REQUEST_INVALID".into());
    }
    let r = &value["replacement"];
    source_operation_keys(r, &["claim","falsifier","so_what","kind","confidence","verified_at","verified_by","expires","body_utf8","evidence"])?;
    if ["claim","falsifier","so_what","verified_by"].iter().any(|key| !source_correction_text(&r[*key],2048,false))
        || !source_correction_text(&r["body_utf8"],8192,true)
        || !matches!(r["kind"].as_str(),Some("architecture"|"data"|"landmine"|"dead_code"|"constraint"|"runtime"))
        || !matches!(r["confidence"].as_str(),Some("verified"|"probable"|"suspected"))
        || !source_correction_date(&r["verified_at"])
        || (!r["expires"].is_null() && (!source_correction_date(&r["expires"]) || r["expires"].as_str() < r["verified_at"].as_str()))
        || serde_json::to_vec(r).map_err(|_| "REQUEST_INVALID")?.len() > 16_384 {
        return Err("REQUEST_INVALID".into());
    }
    let evidence = r["evidence"].as_array().ok_or("REQUEST_INVALID")?;
    if !(1..=8).contains(&evidence.len()) || evidence.iter().enumerate().any(|(i,item)|
        !source_correction_text(item,1024,false) || evidence[..i].contains(item)) {return Err("REQUEST_INVALID".into());}
    Ok(())
}
fn source_operation_target(kind: &str, request: &Value) -> Result<Url> {
    let file_prepare = kind == "prepare" && request.get("action").and_then(Value::as_str) == Some("add_project_file");
    let request_cap = if file_prepare { PROJECT_FILE_PREPARE_CAP } else { SOURCE_OPERATION_CAP };
    if serde_json::to_vec(request)
        .map_err(|_| "REQUEST_INVALID")?
        .len()
        > request_cap
    {
        return Err("REQUEST_INVALID".into());
    }
    if kind == "options" {
        source_operation_keys(request,&["action"])?;
        if request.get("action").and_then(Value::as_str)!=Some("publish_project_proposal") {return Err("REQUEST_INVALID".into());}
    } else if kind == "prepare" {
        source_operation_keys(request, &["action", "request"])?;
        let inner = request
            .get("request")
            .filter(|v| v.is_object())
            .ok_or("REQUEST_INVALID")?;
        if file_prepare {
            source_operation_keys(inner, &["schema", "request_id", "work_ref", "source_commit", "base_revision", "file"])?;
            let file = inner.get("file").ok_or("REQUEST_INVALID")?;
            source_operation_keys(file, &["display_name", "media_type", "content_utf8"])?;
            let name = file.get("display_name").and_then(Value::as_str).ok_or("REQUEST_INVALID")?;
            let content = file.get("content_utf8").and_then(Value::as_str).ok_or("REQUEST_INVALID")?;
            let (stem, suffix) = name.rsplit_once('.').ok_or("REQUEST_INVALID")?;
            let media = if suffix.eq_ignore_ascii_case("md") { "text/markdown" } else if suffix.eq_ignore_ascii_case("txt") { "text/plain" } else { return Err("REQUEST_INVALID".into()); };
            if inner.get("schema").and_then(Value::as_str) != Some("mastermind.project_file_add_request.v1")
                || !source_operation_hex(inner.get("source_commit").and_then(Value::as_str), 40)
                || !source_operation_hex(inner.get("base_revision").and_then(Value::as_str), 64)
                || name.is_empty() || name.len() > 128 || stem.is_empty()
                || name.chars().any(|c| c < '\u{20}' || ('\u{7f}'..='\u{9f}').contains(&c) || c == '/' || c == '\\')
                || content.len() > 32_768
                || content.chars().any(|c| (c < '\u{20}' && !matches!(c, '\n' | '\r' | '\t')) || ('\u{7f}'..='\u{9f}').contains(&c))
                || file.get("media_type").and_then(Value::as_str) != Some(media) {
                return Err("REQUEST_INVALID".into());
            }
        }
        let action = request
            .get("action")
            .and_then(Value::as_str)
            .ok_or("REQUEST_INVALID")?;
        if action == "correct_project_discovery" {source_discovery_correction_request(inner)?;}
        let work = inner.get("work_ref").and_then(Value::as_str);
        source_operation_context_target(&SourceOperationContextSelection {
            action: action.to_owned(),
            work_ref: work.map(str::to_owned),
        })?;
        let prefix = match action {
            "publish_project_proposal" => "mmos-project-create-",
            "ADOPT_PLAN" => "mmos-project-adopt-",
            "ACCEPT_DIRECTION" => "mmos-direction-accept-",
            "add_project_file" => "mmos-project-file-add-",
            "set_project_communication_preference" => "mmos-project-preference-set-",
            "correct_project_discovery" => "mmos-project-discovery-correct-",
            _ => return Err("REQUEST_INVALID".into()),
        };
        if !inner
            .get("request_id")
            .and_then(Value::as_str)
            .and_then(|id| id.strip_prefix(prefix))
            .is_some_and(|tail| source_operation_hex(Some(tail), 40))
        {
            return Err("REQUEST_INVALID".into());
        }
    } else if kind == "submit" {
        source_operation_keys(
            request,
            &["action", "request_id", "work_ref", "preview_witness"],
        )?;
        source_operation_identity(request)?;
        let witness = request.get("preview_witness").ok_or("REQUEST_INVALID")?;
        source_operation_keys(witness, &["original_input", "recipe_fingerprint_sha256"])?;
        let input = witness.get("original_input").ok_or("REQUEST_INVALID")?;
        source_operation_keys(
            input,
            &["schema", "input_ref", "artifact_sha256", "payload_sha256"],
        )?;
        if input.get("schema").and_then(Value::as_str)
            != Some("mastermind.terminal_original_input_reference.v1")
            || !input
                .get("input_ref")
                .and_then(Value::as_str)
                .and_then(|r| r.strip_prefix("terminal-input:"))
                .is_some_and(|tail| source_operation_hex(Some(tail), 64))
            || !source_operation_hex(input.get("artifact_sha256").and_then(Value::as_str), 64)
            || !source_operation_hex(input.get("payload_sha256").and_then(Value::as_str), 64)
            || !source_operation_hex(
                witness
                    .get("recipe_fingerprint_sha256")
                    .and_then(Value::as_str),
                64,
            )
        {
            return Err("REQUEST_INVALID".into());
        }
    } else if kind == "advance" {
        source_operation_keys(
            request,
            &[
                "schema",
                "action",
                "request_id",
                "work_ref",
                "phase_receipt_digest",
            ],
        )?;
        let (action, _, _) = source_operation_identity(request)?;
        if action != "ADOPT_PLAN"
            || request.get("schema").and_then(Value::as_str)
                != Some("mastermind.workspace_source_operation_advance.v1")
            || !source_operation_hex(
                request.get("phase_receipt_digest").and_then(Value::as_str),
                64,
            )
        {
            return Err("REQUEST_INVALID".into());
        }
    } else if kind == "read" && request.get("action").and_then(Value::as_str)==Some("publish_project_proposal") && request.get("work_ref").is_some_and(Value::is_null) {
        source_operation_keys(request,&["schema","action","request_id","work_ref"])?;
        let id=request.get("request_id").and_then(Value::as_str).and_then(|s|s.strip_prefix("mmos-project-create-")).ok_or("REQUEST_INVALID")?;
        if !source_operation_hex(Some(id),40) || request.get("schema").and_then(Value::as_str)!=Some("mastermind.workspace_source_operation_lookup.v1") {return Err("REQUEST_INVALID".into());}
    } else if kind == "read" || kind == "reconcile" {
        let (action, _, _) = source_operation_identity(request)?;
        if action == "correct_project_discovery" {
            source_operation_keys(request, &["action","request_id","work_ref","source_commit","base_revision","request_sha256","discovery_ref","expected_discovery_revision"])?;
            if !source_operation_hex(request["source_commit"].as_str(),40)
                || !source_operation_hex(request["base_revision"].as_str(),64)
                || !source_operation_hex(request["request_sha256"].as_str(),64)
                || !source_operation_hex(request["expected_discovery_revision"].as_str(),64)
                || !source_discovery_ref(request["discovery_ref"].as_str()) {return Err("REQUEST_INVALID".into());}
        } else if matches!(action, "add_project_file" | "set_project_communication_preference") {
            source_operation_keys(request, &["action", "request_id", "work_ref", "source_commit", "base_revision", "request_sha256", "expected_preference_revision"])?;
            let preference = request.get("expected_preference_revision").ok_or("REQUEST_INVALID")?;
            if !source_operation_hex(request.get("source_commit").and_then(Value::as_str), 40)
                || !source_operation_hex(request.get("base_revision").and_then(Value::as_str), 64)
                || !source_operation_hex(request.get("request_sha256").and_then(Value::as_str), 64)
                || (!preference.is_null() && !source_operation_hex(preference.as_str(), 64))
                || (action == "add_project_file" && !preference.is_null()) {
                return Err("REQUEST_INVALID".into());
            }
        } else {
            source_operation_keys(request, &["schema", "action", "request_id", "work_ref"])?;
            if request.get("schema").and_then(Value::as_str) != Some("mastermind.workspace_source_operation_lookup.v1") {
                return Err("REQUEST_INVALID".into());
            }
        }
    } else {
        return Err("REQUEST_INVALID".into());
    }
    let suffix = if kind == "read" { "operation" } else { kind };
    let mut url = Url::parse(&format!("{ORIGIN}/workspace/source-operation/{suffix}"))
        .map_err(|_| "REQUEST_INVALID")?;
    if kind == "options" {url.query_pairs_mut().append_pair("action","publish_project_proposal");}
    if kind == "read" {
        let (action,id,work) = if request.get("action").and_then(Value::as_str)==Some("publish_project_proposal") && request.get("work_ref").is_some_and(Value::is_null) {
            ("publish_project_proposal",request["request_id"].as_str().ok_or("REQUEST_INVALID")?,"null")
        } else { source_operation_identity(request)? };
        url.query_pairs_mut()
            .append_pair("action", action)
            .append_pair("request_id", id)
            .append_pair("work_ref", work);
        if action == "correct_project_discovery" {
            for field in ["source_commit","base_revision","request_sha256","discovery_ref","expected_discovery_revision"] {
                url.query_pairs_mut().append_pair(field,request[field].as_str().ok_or("REQUEST_INVALID")?);
            }
        }
        if matches!(action, "add_project_file" | "set_project_communication_preference") {
            for field in ["source_commit", "base_revision", "request_sha256", "expected_preference_revision"] {
                // The fixed HTTP owner decodes only literal null for the
                // nullable preference preimage; POST keeps actual JSON null.
                let value = request.get(field).ok_or("REQUEST_INVALID")?;
                url.query_pairs_mut().append_pair(field, if value.is_null() { "null" } else { value.as_str().ok_or("REQUEST_INVALID")? });
            }
        }
    }
    Ok(url)
}
async fn source_operation_exchange(app: AppHandle, kind: &str, request: Value) -> Result<Value> {
    let url = source_operation_target(kind, &request)?;
    let state = app.state::<NativeAuth>();
    let (token, generation) = ensure_native_token(&app, Resource::Acquisition).await?;
    let mut call = state
        .http
        .request(
            if kind == "read" || kind == "options" {
                reqwest::Method::GET
            } else {
                reqwest::Method::POST
            },
            url,
        )
        .bearer_auth(token)
        .header("Accept", "application/json")
        .header("Cache-Control", "no-store");
    if kind != "read" && kind != "options" {
        call = call.json(&request);
    }
    let response = call.send().await.map_err(|_| "SOURCE_UNAVAILABLE")?;
    let result = bounded_json(response, SOURCE_OPERATION_CAP).await;
    if !state
        .lock()?
        .release_allowed(generation, Resource::Acquisition)
    {
        return Err("AUTHENTICATION_CHANGED".into());
    }
    source_operation_body(result?, kind, &request)
}
fn source_operation_body(value: Value, kind: &str, request: &Value) -> Result<Value> {
    if kind == "options" {
        if value.get("schema").and_then(Value::as_str)!=Some("mastermind.project_creation_options.v1") {return Err("RESPONSE_INVALID".into());}
        return Ok(value);
    }
    let source = if kind == "prepare" {
        request.get("request").ok_or("REQUEST_INVALID")?
    } else {
        &request
    };
    let schema = if kind == "prepare" {
        "mastermind.workspace_source_operation_preview.v1"
    } else {
        "mastermind.workspace_source_operation_status.v1"
    };
    if value.get("schema").and_then(Value::as_str) != Some(schema)
        || value.get("selection").and_then(|v| v.get("action")) != request.get("action")
        || value.get("selection").and_then(|v| v.get("request_id")) != source.get("request_id")
        || (source.get("work_ref").is_some_and(|v| !v.is_null())
            && value.get("selection").and_then(|v| v.get("work_ref")) != source.get("work_ref"))
    {
        return Err("RESPONSE_INVALID".into());
    }
    Ok(value)
}
#[tauri::command]
pub async fn source_operation_options(app: AppHandle, request: Value) -> Result<Value> {
    source_operation_exchange(app, "options", request).await
}
#[tauri::command]
pub async fn source_operation_prepare(app: AppHandle, request: Value) -> Result<Value> {
    source_operation_exchange(app, "prepare", request).await
}
#[tauri::command]
pub async fn source_operation_read(app: AppHandle, request: Value) -> Result<Value> {
    source_operation_exchange(app, "read", request).await
}
#[tauri::command]
pub async fn source_operation_submit(app: AppHandle, request: Value) -> Result<Value> {
    source_operation_exchange(app, "submit", request).await
}
#[tauri::command]
pub async fn source_operation_reconcile(app: AppHandle, request: Value) -> Result<Value> {
    source_operation_exchange(app, "reconcile", request).await
}
#[tauri::command]
pub async fn source_operation_advance(app: AppHandle, request: Value) -> Result<Value> {
    source_operation_exchange(app, "advance", request).await
}

fn project_session_target(selection: &MissionSelection) -> Result<Url> {
    selection.validate()?;
    let key = selection.work_ref.strip_prefix("WS:").ok_or("SELECTION_INVALID")?;
    let root = selection.root_job_id.strip_prefix("JOB-").ok_or("SELECTION_INVALID")?;
    if !(2..=64).contains(&key.len()) || key.starts_with('-') || key.ends_with('-') || key.contains("--")
        || !key.bytes().all(|b| b.is_ascii_uppercase() || b.is_ascii_digit() || b == b'-')
        || root.is_empty() || root.len() > 9 || !root.bytes().all(|b| b.is_ascii_digit()) {
        return Err("SELECTION_INVALID".into());
    }
    let mut url = Url::parse(&format!("{ORIGIN}{PROJECT_SESSION_PATH}")).map_err(|_| "REQUEST_INVALID")?;
    url.query_pairs_mut().append_pair("work_ref", &selection.work_ref).append_pair("root_job_id", &selection.root_job_id);
    Ok(url)
}
#[tauri::command]
pub async fn read_project_session(app: AppHandle, selection: MissionSelection) -> Result<Value> {
    let url = project_session_target(&selection)?;
    let state = app.state::<NativeAuth>();
    let (token, generation) = ensure_native_token(&app, Resource::Acquisition).await?;
    let response = state.http.get(url).bearer_auth(token)
        .header("Accept", "application/json").header("Cache-Control", "no-store")
        .send().await.map_err(|_| "SOURCE_UNAVAILABLE")?;
    let result = if response.status().as_u16() == 503 {
        read_json_body(response, PROJECT_SESSION_RESPONSE_CAP).await
            .and_then(|value| typed_unavailable(value, PROJECT_SESSION_SCHEMA, false))
    } else {
        bounded_json(response, PROJECT_SESSION_RESPONSE_CAP).await
    };
    if !state.lock()?.release_allowed(generation, Resource::Acquisition) {
        return Err("AUTHENTICATION_CHANGED".into());
    }
    let value = result?;
    if value.get("schema").and_then(Value::as_str) != Some(PROJECT_SESSION_SCHEMA)
        || value.get("selection").and_then(|s| s.get("work_ref")).and_then(Value::as_str) != Some(selection.work_ref.as_str())
        || value.get("selection").and_then(|s| s.get("root_job_id")).and_then(Value::as_str) != Some(selection.root_job_id.as_str()) {
        return Err("RESPONSE_INVALID".into());
    }
    // The existing host performs the sole full closed-body decode before display.
    Ok(value)
}

const AUTONOMY_POLICY_PATH: &str = "/workspace/autonomy/current";
const AUTONOMY_POLICY_SCHEMA: &str = "mastermind.workspace_autonomy_read_result.v1";
const AUTONOMY_POLICY_RESPONSE_CAP: usize = 32_768;
fn autonomy_policy_target(selection: &MissionSelection) -> Result<Url> {
    validate_workspace_pair(&selection.work_ref, &selection.root_job_id)?;
    let mut url = Url::parse(&format!("{ORIGIN}{AUTONOMY_POLICY_PATH}")).map_err(|_| "REQUEST_INVALID")?;
    url.query_pairs_mut().append_pair("work_ref", &selection.work_ref)
        .append_pair("root_job_id", &selection.root_job_id);
    Ok(url)
}
#[tauri::command]
pub async fn read_autonomy_policy(app: AppHandle, selection: MissionSelection) -> Result<Value> {
    let url = autonomy_policy_target(&selection)?;
    let state = app.state::<NativeAuth>();
    let (token, generation) = ensure_native_token(&app, Resource::Acquisition).await?;
    let response = state.http.get(url).bearer_auth(token)
        .header("Accept", "application/json").header("Cache-Control", "no-store")
        .send().await.map_err(|_| "SOURCE_UNAVAILABLE")?;
    let result = if response.status().as_u16() == 503 {
        read_json_body(response, AUTONOMY_POLICY_RESPONSE_CAP).await
            .and_then(|value| typed_unavailable(value, AUTONOMY_POLICY_SCHEMA, false))
    } else {
        bounded_json(response, AUTONOMY_POLICY_RESPONSE_CAP).await
    };
    if !state.lock()?.release_allowed(generation, Resource::Acquisition) {
        return Err("AUTHENTICATION_CHANGED".into());
    }
    let value = result?;
    if value.get("schema").and_then(Value::as_str) != Some(AUTONOMY_POLICY_SCHEMA)
        || value.get("selection").and_then(|s| s.get("work_ref")).and_then(Value::as_str) != Some(selection.work_ref.as_str())
        || value.get("selection").and_then(|s| s.get("root_job_id")).and_then(Value::as_str) != Some(selection.root_job_id.as_str()) {
        return Err("RESPONSE_INVALID".into());
    }
    // Full closed-body validation remains in the existing host before display.
    Ok(value)
}

#[tauri::command]
pub async fn read_admitted_plan(app: AppHandle, selection: MissionSelection) -> Result<Value> {
    // Original Workspace selection grammar is narrower than legacy Mission selection.
    validate_workspace_pair(&selection.work_ref, &selection.root_job_id)?;
    let mut url = Url::parse(&format!("{ORIGIN}{PLAN_DETAIL_PATH}"))
        .map_err(|_| "REQUEST_INVALID")?;
    url.query_pairs_mut()
        .append_pair("work_ref", &selection.work_ref)
        .append_pair("root_job_id", &selection.root_job_id);
    let state = app.state::<NativeAuth>();
    let (token, generation) = ensure_native_token(&app, Resource::Acquisition).await?;
    let response = state.http.get(url).bearer_auth(token)
        .header("Accept", "application/json")
        .header("Cache-Control", "no-store")
        .send().await.map_err(|_| "SOURCE_UNAVAILABLE")?;
    let result = if response.status().as_u16() == 503 {
        read_json_body(response, PLAN_RESPONSE_CAP).await
            .and_then(|value| typed_unavailable(value, PLAN_SCHEMA, false))
    } else {
        bounded_json(response, PLAN_RESPONSE_CAP).await
    };
    // A completed HTTP request is not publication permission after identity rotation.
    if !state.lock()?.release_allowed(generation, Resource::Acquisition) {
        return Err("AUTHENTICATION_CHANGED".into());
    }
    let value = result?;
    if value.get("schema").and_then(Value::as_str) != Some(PLAN_SCHEMA) {
        return Err("RESPONSE_INVALID".into());
    }
    // Exact fields, source observation, availability, and selectors are decoded in
    // the existing frontend Plan consumer; no private response fields are projected.
    Ok(value)
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub struct FabricStatusSelection {
    root_id: String,
    run_id: String,
}
impl FabricStatusSelection {
    fn validate(&self) -> Result<()> {
        let root = self.root_id.strip_prefix("JOB-").ok_or("SELECTION_INVALID")?;
        if root.is_empty() || root.len() > 9 || !root.bytes().all(|b| b.is_ascii_digit())
            || !self.run_id.strip_prefix("ATT-").is_some_and(|v| lowercase_hex(v, 32)) {
            return Err("SELECTION_INVALID".into());
        }
        Ok(())
    }
}
fn fabric_read_target(selection: Option<&FabricStatusSelection>) -> Result<(Url, &'static str, usize)> {
    let (path, schema, cap) = if selection.is_some() {
        ("/workspace/fabric/status/current", "mastermind.fabric_task_status.v1", 16_384)
    } else {
        ("/workspace/fabric/catalog/current", "mastermind.attended_fabric_catalog.v1", 65_536)
    };
    let mut url = Url::parse(&format!("{ORIGIN}{path}")).map_err(|_| "REQUEST_INVALID")?;
    if let Some(selected) = selection {
        selected.validate()?;
        url.query_pairs_mut().append_pair("root_id", &selected.root_id)
            .append_pair("run_id", &selected.run_id);
    }
    Ok((url, schema, cap))
}
async fn read_fabric(app: AppHandle, selection: Option<FabricStatusSelection>) -> Result<Value> {
    let (url, schema, cap) = fabric_read_target(selection.as_ref())?;
    let state = app.state::<NativeAuth>();
    let (token, generation) = ensure_native_token(&app, Resource::Acquisition).await?;
    let response = state.http.get(url).bearer_auth(token)
        .header("Accept", "application/json").header("Cache-Control", "no-store")
        .send().await.map_err(|_| "SOURCE_UNAVAILABLE")?;
    // Unavailable/error bodies cannot become successful run observations.
    let result = bounded_json(response, cap).await;
    if !state.lock()?.release_allowed(generation, Resource::Acquisition) {
        return Err("AUTHENTICATION_CHANGED".into());
    }
    let value = result?;
    if value.get("schema").and_then(Value::as_str) != Some(schema) {
        return Err("RESPONSE_INVALID".into());
    }
    // The same strict frontend decoders retain only approved metadata and
    // enforce exact-run browser scope; no machine-local credential is used.
    Ok(value)
}
#[tauri::command]
pub async fn read_fabric_catalog(app: AppHandle) -> Result<Value> {
    read_fabric(app, None).await
}
#[tauri::command]
pub async fn read_fabric_status(app: AppHandle, selection: FabricStatusSelection) -> Result<Value> {
    read_fabric(app, Some(selection)).await
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub struct RetainedActivitySelection {
    work_ref: String,
    root_job_id: String,
    job_id: String,
    attempt_id: String,
}
impl RetainedActivitySelection {
    fn validate(&self) -> Result<()> {
        validate_workspace_pair(&self.work_ref, &self.root_job_id)?;
        validate_workspace_pair(&self.work_ref, &self.job_id)?;
        if self.job_id == self.root_job_id
            || !self.attempt_id.strip_prefix("ATT-")
                .is_some_and(|v| lowercase_hex(v, 32)) {
            return Err("SELECTION_INVALID".into());
        }
        Ok(())
    }
}
const MODEL_CONFIGURATION_PATH: &str = "/workspace/resources/models/current";
const MODEL_CONFIGURATION_SCHEMA: &str = "mastermind.workspace_model_configuration.v1";
const MODEL_CONFIGURATION_CAP: usize = 278_528;

/// Fixed current-capacity read through the existing Workspace identity.
/// The native caller cannot supply a URL, account, provider or source path.
#[tauri::command]
pub async fn read_capacity_fabric(app: AppHandle) -> Result<Value> {
    const SCHEMA: &str = "mastermind.workspace_capacity_fabric.v1";
    const CAP: usize = 262_144;
    let url = Url::parse(&format!("{ORIGIN}/workspace/resources/fabric/current"))
        .map_err(|_| "REQUEST_INVALID")?;
    let state = app.state::<NativeAuth>();
    let (token, generation) = ensure_native_token(&app, Resource::Acquisition).await?;
    let response = state.http.get(url).bearer_auth(token)
        .header("Accept", "application/json")
        .header("Cache-Control", "no-store")
        .send().await.map_err(|_| "SOURCE_UNAVAILABLE")?;
    let result = if response.status().as_u16() == 503 {
        read_json_body(response, CAP).await
            .and_then(|value| typed_unavailable(value, SCHEMA, false))
    } else {
        bounded_json(response, CAP).await
    };
    if !state.lock()?.release_allowed(generation, Resource::Acquisition) {
        return Err("AUTHENTICATION_CHANGED".into());
    }
    let value = result?;
    if value.get("schema").and_then(Value::as_str) != Some(SCHEMA) {
        return Err("RESPONSE_INVALID".into());
    }
    Ok(value)
}

/// Fixed read of configured routing through the existing Workspace identity.
/// No caller URL, policy path, model activation, credentials or mutation.
#[tauri::command]
pub async fn read_model_configuration(app: AppHandle) -> Result<Value> {
    let url = Url::parse(&format!("{ORIGIN}{MODEL_CONFIGURATION_PATH}"))
        .map_err(|_| "REQUEST_INVALID")?;
    let state = app.state::<NativeAuth>();
    let (token, generation) = ensure_native_token(&app, Resource::Acquisition).await?;
    let response = state.http.get(url).bearer_auth(token)
        .header("Accept", "application/json")
        .header("Cache-Control", "no-store")
        .send().await.map_err(|_| "SOURCE_UNAVAILABLE")?;
    let result = if response.status().as_u16() == 503 {
        read_json_body(response, MODEL_CONFIGURATION_CAP).await
            .and_then(|value| typed_unavailable(value, MODEL_CONFIGURATION_SCHEMA, false))
    } else {
        bounded_json(response, MODEL_CONFIGURATION_CAP).await
    };
    if !state.lock()?.release_allowed(generation, Resource::Acquisition) {
        return Err("AUTHENTICATION_CHANGED".into());
    }
    let value = result?;
    if value.get("schema").and_then(Value::as_str) != Some(MODEL_CONFIGURATION_SCHEMA) {
        return Err("RESPONSE_INVALID".into());
    }
    Ok(value)
}

const RESOURCE_CAPACITY_PATH: &str = "/workspace/resources/capacity/current";
const RESOURCE_CAPACITY_SCHEMA: &str = "mastermind.workspace_resource_capacity_result.v1";
const RESOURCE_CAPACITY_CAP: usize = 16_384;

/// Same fixed public Workspace acquisition bearer and owner-issued generation
/// fence as admitted plan; never pass private keys, native Fabric run IDs or
/// raw Event rows into the webview. A 503 must keep the closed typed schema.
#[tauri::command]
pub async fn read_resource_capacity(app: AppHandle, selection: RetainedActivitySelection) -> Result<Value> {
    selection.validate()?;
    let mut url = Url::parse(&format!("{ORIGIN}{RESOURCE_CAPACITY_PATH}"))
        .map_err(|_| "REQUEST_INVALID")?;
    url.query_pairs_mut()
        .append_pair("work_ref", &selection.work_ref)
        .append_pair("root_job_id", &selection.root_job_id)
        .append_pair("job_id", &selection.job_id)
        .append_pair("attempt_id", &selection.attempt_id);
    let state = app.state::<NativeAuth>();
    let (token, generation) = ensure_native_token(&app, Resource::Acquisition).await?;
    let response = state.http.get(url).bearer_auth(token)
        .header("Accept", "application/json")
        .header("Cache-Control", "no-store")
        .send().await.map_err(|_| "SOURCE_UNAVAILABLE")?;
    let result = if response.status().as_u16() == 503 {
        read_json_body(response, RESOURCE_CAPACITY_CAP).await
            .and_then(|value| typed_unavailable(value, RESOURCE_CAPACITY_SCHEMA, false))
    } else {
        bounded_json(response, RESOURCE_CAPACITY_CAP).await
    };
    if !state.lock()?.release_allowed(generation, Resource::Acquisition) {
        return Err("AUTHENTICATION_CHANGED".into());
    }
    let value = result?;
    if value.get("schema").and_then(Value::as_str) != Some(RESOURCE_CAPACITY_SCHEMA) {
        return Err("RESPONSE_INVALID".into());
    }
    // The existing host's strict DTO decoder removes unrecognized fields.
    Ok(value)
}

const RETAINED_ACTIVITY_PATH: &str = "/workspace/operator/activity/current";
const RETAINED_ACTIVITY_SCHEMA: &str = "mastermind.workspace_retained_activity.v1";
const RETAINED_ACTIVITY_CAP: usize = 16_384;

/// Same fixed public Workspace acquisition bearer and owner-issued generation
/// fence as admitted plan; never pass private keys, native Fabric run IDs or
/// raw Event rows into the webview. A 503 must keep the closed typed schema.
#[tauri::command]
pub async fn read_retained_activity(app: AppHandle, selection: RetainedActivitySelection) -> Result<Value> {
    selection.validate()?;
    let mut url = Url::parse(&format!("{ORIGIN}{RETAINED_ACTIVITY_PATH}"))
        .map_err(|_| "REQUEST_INVALID")?;
    url.query_pairs_mut()
        .append_pair("work_ref", &selection.work_ref)
        .append_pair("root_job_id", &selection.root_job_id)
        .append_pair("job_id", &selection.job_id)
        .append_pair("attempt_id", &selection.attempt_id);
    let state = app.state::<NativeAuth>();
    let (token, generation) = ensure_native_token(&app, Resource::Acquisition).await?;
    let response = state.http.get(url).bearer_auth(token)
        .header("Accept", "application/json")
        .header("Cache-Control", "no-store")
        .send().await.map_err(|_| "SOURCE_UNAVAILABLE")?;
    let result = if response.status().as_u16() == 503 {
        read_json_body(response, RETAINED_ACTIVITY_CAP).await
            .and_then(|value| typed_unavailable(value, RETAINED_ACTIVITY_SCHEMA, false))
    } else {
        bounded_json(response, RETAINED_ACTIVITY_CAP).await
    };
    if !state.lock()?.release_allowed(generation, Resource::Acquisition) {
        return Err("AUTHENTICATION_CHANGED".into());
    }
    let value = result?;
    if value.get("schema").and_then(Value::as_str) != Some(RETAINED_ACTIVITY_SCHEMA) {
        return Err("RESPONSE_INVALID".into());
    }
    // The existing host's strict DTO decoder removes unrecognized fields.
    Ok(value)
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ResultReferencesSelection {
    work_ref: String,
    root_job_id: String,
}
impl ResultReferencesSelection {
    fn validate(&self) -> Result<()> {
        validate_workspace_pair(&self.work_ref, &self.root_job_id)
    }
}
const RESULT_REFERENCES_PATH: &str = "/workspace/result-references/current";
const RESULT_REFERENCES_SCHEMA: &str = "mastermind.workspace_result_references.v1";
const RESULT_REFERENCES_CAP: usize = PLAN_RESPONSE_CAP;

/// Same fixed public Workspace acquisition bearer, origin, no-store headers,
/// 16KiB cap and owner-issued generation fence as retained activity. A 503
/// must keep this route's closed typed schema; 401/403/404 and every other
/// non-OK status keep the established refusal in bounded_json. Read-only:
/// no consume, no ACK, no change to the frozen five-tuple Result read.
#[tauri::command]
pub async fn read_result_references(
    app: AppHandle,
    selection: ResultReferencesSelection,
) -> Result<Value> {
    selection.validate()?;
    let mut url = Url::parse(&format!("{ORIGIN}{RESULT_REFERENCES_PATH}"))
        .map_err(|_| "REQUEST_INVALID")?;
    url.query_pairs_mut()
        .append_pair("work_ref", &selection.work_ref)
        .append_pair("root_job_id", &selection.root_job_id);
    let state = app.state::<NativeAuth>();
    let (token, generation) = ensure_native_token(&app, Resource::Acquisition).await?;
    let response = state.http.get(url).bearer_auth(token)
        .header("Accept", "application/json")
        .header("Cache-Control", "no-store")
        .send().await.map_err(|_| "SOURCE_UNAVAILABLE")?;
    let result = if response.status().as_u16() == 503 {
        read_json_body(response, RESULT_REFERENCES_CAP).await
            .and_then(|value| typed_unavailable(value, RESULT_REFERENCES_SCHEMA, false))
    } else {
        bounded_json(response, RESULT_REFERENCES_CAP).await
    };
    // A completed HTTP request is not publication permission after identity rotation.
    if !state.lock()?.release_allowed(generation, Resource::Acquisition) {
        return Err("AUTHENTICATION_CHANGED".into());
    }
    let value = result?;
    if value.get("schema").and_then(Value::as_str) != Some(RESULT_REFERENCES_SCHEMA) {
        return Err("RESPONSE_INVALID".into());
    }
    // The existing host's strict DTO decoder removes unrecognized fields.
    Ok(value)
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
    let (token, generation) = ensure_native_token(&app, Resource::Acquisition).await?;
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
    let (token, generation) = ensure_native_token(&app, Resource::Acquisition).await?;
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
fn mission_result_url(selection: &ResultSelection) -> Result<Url> {
    selection.validate()?;
    let mut url = Url::parse(&format!("{ORIGIN}{MISSION_RESULT_PATH}"))
        .map_err(|_| "REQUEST_INVALID")?;
    url.query_pairs_mut()
        .append_pair("work_ref", &selection.work_ref)
        .append_pair("root_job_id", &selection.root_job_id)
        .append_pair("job_id", &selection.job_id)
        .append_pair("attempt_id", &selection.attempt_id)
        .append_pair("result_envelope_digest", &selection.result_envelope_digest);
    Ok(url)
}

fn typed_mission_result_unavailable(value: Value) -> Result<Value> {
    let value = typed_unavailable(value, MISSION_RESULT_SCHEMA, false)?;
    if !value.get("mission").is_some_and(Value::is_null)
        || !value.get("role_result").is_some_and(Value::is_null)
    {
        return Err("RESPONSE_INVALID".into());
    }
    Ok(value)
}

#[tauri::command]
pub async fn read_mission_result(app: AppHandle, selection: ResultSelection) -> Result<Value> {
    let url = mission_result_url(&selection)?;
    let state = app.state::<NativeAuth>();
    let (token, generation) = ensure_native_token(&app, Resource::Acquisition).await?;
    let response = state
        .http
        .get(url)
        .bearer_auth(token)
        .header("Accept", "application/json")
        .header("Cache-Control", "no-store")
        .send()
        .await
        .map_err(|_| "SOURCE_UNAVAILABLE")?;
    // One acquisition and the received-byte cap apply to both nested documents.
    // The existing typed host still owns exact association and nested Result limits.
    let result = if response.status().as_u16() == 503 {
        read_json_body(response, MISSION_RESULT_RESPONSE_CAP)
            .await
            .and_then(typed_mission_result_unavailable)
    } else {
        bounded_json(response, MISSION_RESULT_RESPONSE_CAP).await
    };
    if !state.lock()?.release_allowed(generation, Resource::Acquisition) {
        return Err("AUTHENTICATION_CHANGED".into());
    }
    let value = result?;
    if !value.is_object()
        || value.get("schema").and_then(Value::as_str) != Some(MISSION_RESULT_SCHEMA)
    {
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
    let (token, generation) = ensure_native_token(&app, Resource::Content).await?;
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
fn direct_native_arguments(arguments: Value, consume: bool) -> Result<Value> {
    let object = arguments.as_object().ok_or("DIRECT_SELECTION_INVALID")?;
    let keys: &[&str] = if consume {
        &["work_ref", "job_id", "attempt_id", "result_digest", "operation_key"]
    } else { &["work_ref", "job_id", "attempt_id"] };
    if object.len() != keys.len() || keys.iter().any(|key| !object.contains_key(*key)) {
        return Err("DIRECT_SELECTION_INVALID".into());
    }
    let id = |value: &Value| value.as_str().is_some_and(|value| {
        !value.is_empty() && value.len() <= 128
            && value.as_bytes()[0].is_ascii_alphanumeric()
            && value.bytes().all(|byte| byte.is_ascii_alphanumeric() || b"._:-".contains(&byte))
    });
    if !object["work_ref"].as_str().is_some_and(|value| !value.is_empty()
        && value.trim() == value && value.chars().count() <= 512
        && !value.chars().any(char::is_control))
        || !id(&object["job_id"])
        || !(id(&object["attempt_id"]) || (!consume && object["attempt_id"].is_null())) {
        return Err("DIRECT_SELECTION_INVALID".into());
    }
    if consume && (!id(&object["operation_key"])
        || !object["result_digest"].as_str().is_some_and(|value| value.len() == 64
            && value.bytes().all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte)))) {
        return Err("DIRECT_SELECTION_INVALID".into());
    }
    if executive_body(&arguments)?.len() > DIRECT_NATIVE_REQUEST_CAP {
        return Err("REQUEST_BOUND".into());
    }
    Ok(arguments)
}
fn direct_native_correction_arguments(arguments: Value) -> Result<Value> {
    let object = arguments.as_object().ok_or("DIRECT_SELECTION_INVALID")?;
    let request = match object.get("operation").and_then(Value::as_str) {
        Some("inspect") => false, Some("request") => true,
        _ => return Err("DIRECT_SELECTION_INVALID".into()),
    };
    let keys: &[&str] = if request {
        &["operation", "work_ref", "job_id", "attempt_id", "fence_generation", "operation_key"]
    } else { &["operation", "work_ref", "job_id", "attempt_id"] };
    if object.len() != keys.len() || keys.iter().any(|key| !object.contains_key(*key)) {
        return Err("DIRECT_SELECTION_INVALID".into());
    }
    direct_native_arguments(serde_json::json!({"work_ref":object["work_ref"],
        "job_id":object["job_id"], "attempt_id":object["attempt_id"]}), false)?;
    if request && (object["attempt_id"].is_null()
        || !object["fence_generation"].as_u64().is_some_and(|value| value > 0 && value <= MAX_SAFE_GENERATION)
        || !object["operation_key"].as_str().is_some_and(|value| !value.is_empty() && value.len() <= 128
            && value.as_bytes()[0].is_ascii_alphanumeric()
            && value.bytes().all(|byte| byte.is_ascii_alphanumeric() || b"._:-".contains(&byte)))) {
        return Err("DIRECT_SELECTION_INVALID".into());
    }
    if executive_body(&arguments)?.len() > DIRECT_NATIVE_REQUEST_CAP { return Err("REQUEST_BOUND".into()); }
    Ok(arguments)
}
async fn executive_post(app: AppHandle, path: &'static str, body: Value) -> Result<Value> {
    let state = app.state::<NativeAuth>();
    executive_post_with_dispatch(&state, path, body, reqwest::RequestBuilder::send).await
}

// Production and tests share the authorization and transport-dispatch boundary.
async fn executive_post_with_dispatch<D, F>(
    state: &NativeAuth,
    path: &'static str,
    body: Value,
    dispatch: D,
) -> Result<Value>
where
    D: FnOnce(reqwest::RequestBuilder) -> F,
    F: std::future::Future<Output = std::result::Result<reqwest::Response, reqwest::Error>>,
{
    let foreground_research = path == "/os/executive/submit"
        && body.get("arguments").and_then(|v| v.get("execution_profile"))
            .and_then(Value::as_str) == Some("research_only");
    let planning=crate::project_planning::operation(path);
    let execution=crate::project_execution::operation(path);
    let fresh=crate::fresh_conversation::operation(path);
    let conversation_read=crate::project_conversations_read::operation(path);
    let session_send=path==crate::native_session_send::PATH;
    if session_send {
        if !body.as_object().is_some_and(|o|o.len()==1&&o.contains_key("arguments")){return Err("REQUEST_INVALID".into())}
        crate::native_session_send::validate(&body["arguments"])?;
    }
    if let Some(operation)=conversation_read {
        if !body.as_object().is_some_and(|o|o.len()==1 && o.contains_key("arguments")) {return Err("REQUEST_INVALID".into())}
        crate::project_conversations_read::validate(operation,&body["arguments"])?;
    }
    if let Some(operation)=fresh {
        if !body.as_object().is_some_and(|o|o.len()==1 && o.contains_key("arguments")) {return Err("REQUEST_INVALID".into())}
        crate::fresh_conversation::validate(operation,&body["arguments"])?;
    }
    if let Some(operation)=execution {
        if !body.as_object().is_some_and(|o|o.len()==1 && o.contains_key("arguments")) {return Err("REQUEST_INVALID".into())}
        crate::project_execution::validate(operation,&body["arguments"])?;
    }
    if let Some(operation)=planning {
        if !body.as_object().is_some_and(|o|o.len()==1 && o.contains_key("arguments")) {return Err("REQUEST_INVALID".into())}
        crate::project_planning::validate(operation,&body["arguments"])?;
    }
    // Validate the closed selectors at the shared boundary before dispatch,
    // including callers other than the public command wrappers.
    match path {
        "/os/executive/direct-native/result" => { direct_native_arguments(body.clone(), false)?; }
        "/os/executive/direct-native/consume" => { direct_native_arguments(body.clone(), true)?; }
        "/os/executive/direct-native/correction" => { direct_native_correction_arguments(body.clone())?; }
        _ => {}
    }
    let (token, token_expires, generation, changed, workspace) = {
        let inner = state.lock()?;
        let token = inner.token(Resource::Executive).ok_or("EXECUTIVE_AUTH_REQUIRED")?;
        match path {
            "/os/executive/context"
            | "/os/executive/status"
            | "/os/executive/session/context"
            | "/os/executive/session/history-context"
            | "/os/executive/session/reply"
            | "/os/executive/session/references"
            | "/os/executive/direct-native/result" => {}
            "/os/executive/direct-native/correction" => {
                if body.get("operation").and_then(Value::as_str) == Some("request") && !token.executive_send {
                    return Err("EXECUTIVE_SEND_SCOPE_REQUIRED".into());
                }
            }
            "/os/executive/submit" | "/os/executive/direct-native/consume" | "/os/executive/session/send" => {
                if !token.executive_send {
                    return Err("EXECUTIVE_SEND_SCOPE_REQUIRED".into());
                }
            }
            _ if conversation_read.is_some() => {}
            _ if planning.is_some() || execution.is_some() => {if !token.executive_send {return Err("EXECUTIVE_SEND_SCOPE_REQUIRED".into())}}
            // Every original fresh-conversation operation belongs to the
            // enrolled submit-policy principal. Pure project catalogue READ
            // is separately composed; it is never relabeled here.
            _ if fresh.is_some() => {if !token.executive_send {return Err("EXECUTIVE_SEND_SCOPE_REQUIRED".into())}}
            _ => return Err("REQUEST_INVALID".into()),
        }
        (
            token.value.clone(),
            token.expires,
            inner.executive_generation,
            inner.executive_changed.subscribe(),
            if planning.is_some() || execution.is_some() || matches!(fresh,Some("preview"|"create"|"consume"|"turn"|"turn_preview")) {let workspace=inner.token(Resource::Acquisition).ok_or("WORKSPACE_AUTH_REQUIRED")?;
                Some((workspace.value.clone(),inner.generation,workspace.expires))} else {None},
        )
    };
    let serialized = executive_body(&body)?;
    let direct = matches!(path, "/os/executive/direct-native/result" | "/os/executive/direct-native/consume"
        | "/os/executive/direct-native/correction");
    if direct && serialized.len() > DIRECT_NATIVE_REQUEST_CAP { return Err("REQUEST_BOUND".into()); }
    let url = Url::parse(&format!("{ORIGIN}{path}")).map_err(|_| "REQUEST_INVALID".to_owned())?;
    if url.origin().ascii_serialization() != ORIGIN {
        return Err("REQUEST_INVALID".into());
    }
    let mut request = state
        .http
        .post(url)
        .bearer_auth(token)
        .header("Accept", "application/json")
        .header("Cache-Control", "no-store")
        .header(reqwest::header::CONTENT_TYPE, "application/json")
        .body(serialized);
    if let Some((value,_,_))=&workspace {
        request=request.header("X-Mastermind-Workspace-Authorization",format!("Bearer {value}"));
    }
    if fresh.is_some() || execution.is_some() {
        request = request.timeout(Duration::from_secs(300));
    } else if foreground_research || planning.is_some() {
        request = request.timeout(EXECUTIVE_FOREGROUND_TIMEOUT);
    }
    let exchange = async {
        let response = dispatch(request)
            .await
            .map_err(|_| "EXECUTIVE_TRANSPORT_UNAVAILABLE".to_owned())?;
        { planning_auth_guard(&mut *state.lock()?,generation,token_expires,workspace.as_ref())?; }
        let status = response.status();
        let result = if status.is_success() {
            read_json_body(response, if direct { DIRECT_NATIVE_RESPONSE_CAP } else { EXECUTIVE_RESPONSE_CAP }).await
        } else if execution.is_some() && [400, 401, 403, 409, 503].contains(&status.as_u16()) {
            let value = read_json_body(response, EXECUTIVE_RESPONSE_CAP).await?;
            if crate::project_execution::is_refusal(&value, execution.unwrap()) { Ok(value) }
            else { Err("EXECUTIVE_TRANSPORT_UNAVAILABLE".into()) }
        } else if direct && [401, 403, 409, 503].contains(&status.as_u16()) {
            let value = read_json_body(response, DIRECT_NATIVE_RESPONSE_CAP).await?;
            if value.get("schema").and_then(Value::as_str) == Some("mastermind.direct_native_result_response.v1")
                && value.get("availability").and_then(Value::as_str) == Some("UNAVAILABLE") {
                Ok(value)
            } else { Err("EXECUTIVE_TRANSPORT_UNAVAILABLE".into()) }
        } else {
            Err(match status.as_u16() {
                401 => "EXECUTIVE_AUTH_REQUIRED",
                403 => "EXECUTIVE_ACCESS_REFUSED",
                _ => "EXECUTIVE_TRANSPORT_UNAVAILABLE",
            }.into())
        };
        { planning_auth_guard(&mut *state.lock()?,generation,token_expires,workspace.as_ref())?; }
        result
    };
    if foreground_research || direct || planning.is_some() || execution.is_some() || fresh.is_some() || session_send {
        executive_foreground_exchange(state, generation, token_expires, changed, workspace.as_ref(), exchange).await
    } else {
        exchange.await
    }
}

fn planning_auth_guard(inner:&mut Inner,generation:u64,expires:Instant,workspace:Option<&(String,u64,Instant)>)->Result<()> {
    executive_guard(inner,generation,expires)?;
    if let Some((value,epoch,deadline))=workspace {
        if inner.generation!=*epoch || !inner.token(Resource::Acquisition).is_some_and(|t|t.expires==*deadline && t.value==*value) {
            return Err("WORKSPACE_AUTH_CHANGED".into());
        }
    }
    Ok(())
}

async fn executive_foreground_exchange<T, F>(
    state: &NativeAuth, generation: u64, expires: Instant,
    mut changed: tokio::sync::watch::Receiver<()>, workspace:Option<&(String,u64,Instant)>, exchange: F,
) -> Result<T>
where F: std::future::Future<Output = Result<T>> {
    use std::{future::Future, task::Poll};
    let mut exchange = std::pin::pin!(exchange);
    let deadline=workspace.map(|(_,_,deadline)|expires.min(*deadline)).unwrap_or(expires);
    let mut expiry = std::pin::pin!(tokio::time::sleep_until(deadline.into()));
    let mut workspace_tick=tokio::time::interval(Duration::from_millis(25));
    let mut notification = std::pin::pin!(changed.changed());
    std::future::poll_fn(|cx| {
        if notification.as_mut().poll(cx).is_ready() || expiry.as_mut().poll(cx).is_ready() {
            return Poll::Ready(Err("EXECUTIVE_AUTH_CHANGED".into()));
        }
        if workspace.is_some() {let _=workspace_tick.poll_tick(cx);}
        if let Err(error) = state.lock().and_then(|mut inner| planning_auth_guard(&mut inner,generation,expires,workspace)) {
            return Poll::Ready(Err(error));
        }
        exchange.as_mut().poll(cx)
    }).await
}
#[tauri::command]
pub async fn executive_project_conversations_read(app:AppHandle,operation:String,arguments:Value)->Result<Value> {
    let path=crate::project_conversations_read::path(&operation).ok_or("REQUEST_INVALID")?;
    crate::project_conversations_read::validate(&operation,&arguments)?;
    let result=executive_post(app.clone(),path,serde_json::json!({"arguments":arguments})).await;
    if result.is_err(){emit(&app);}
    result
}
#[tauri::command]
pub async fn executive_fresh_conversation(app:AppHandle,operation:String,arguments:Value)->Result<Value> {
    let path=crate::fresh_conversation::path(&operation).ok_or("REQUEST_INVALID")?;
    crate::fresh_conversation::validate(&operation,&arguments)?;
    let result=executive_post(app.clone(),path,serde_json::json!({"arguments":arguments})).await;
    if result.is_err(){emit(&app);}
    result
}
#[tauri::command]
pub async fn executive_project_execution(app:AppHandle,operation:String,arguments:Value)->Result<Value> {
    let path=crate::project_execution::route(&operation)?;
    let arguments=crate::project_execution::validate(&operation,&arguments)?;
    executive_post(app,path,serde_json::json!({"arguments":arguments})).await
}
#[tauri::command]
pub async fn executive_project_planning(app:AppHandle,operation:String,arguments:Value)->Result<Value> {
    let path=crate::project_planning::route(&operation)?;
    let arguments=crate::project_planning::validate(&operation,&arguments)?;
    executive_post(app,path,serde_json::json!({"arguments":arguments})).await
}
#[tauri::command]
pub fn executive_auth_status(state: tauri::State<'_, NativeAuth>, diagnostics: Option<bool>) -> Result<Value> {
    let mut inner = state.lock()?;
    if diagnostics.unwrap_or(false) {
        serde_json::to_value(inner.executive_observation()).map_err(|_| "RESPONSE_INVALID".into())
    } else {
        serde_json::to_value(inner.executive_status()).map_err(|_| "RESPONSE_INVALID".into())
    }
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

#[tauri::command]
pub async fn executive_direct_native_result(app: AppHandle, arguments: Value) -> Result<Value> {
    let arguments = direct_native_arguments(arguments, false)?;
    let result = executive_post(app.clone(), "/os/executive/direct-native/result", arguments).await;
    if result.is_err() { emit(&app); }
    result
}
#[tauri::command]
pub async fn executive_direct_native_consume(app: AppHandle, arguments: Value) -> Result<Value> {
    let arguments = direct_native_arguments(arguments, true)?;
    let result = executive_post(app.clone(), "/os/executive/direct-native/consume", arguments).await;
    if result.is_err() { emit(&app); }
    result
}
#[tauri::command]
pub async fn executive_direct_correction(app: AppHandle, arguments: Value) -> Result<Value> {
    let arguments = direct_native_correction_arguments(arguments)?;
    let result = executive_post(app.clone(), "/os/executive/direct-native/correction", arguments).await;
    if result.is_err() { emit(&app); }
    result
}

// Read-only original-answer transport on the existing Executive token and
// generation. These commands do not originate or ACK a CONTINUE; in particular
// SEND now has its own closed command below. The separate
// original F2 review of executive_submit remains held and unmodified.
fn valid_original_operation_key(key: &str) -> bool {
    key.strip_prefix("session-continue-")
        .is_some_and(|suffix| lowercase_hex(suffix, 64))
}
fn valid_reference_cursor(cursor: &str) -> bool {
    !cursor.is_empty() && cursor.len() <= 2048 &&
        cursor.bytes().all(|b| b.is_ascii_alphanumeric() || b"_-=".contains(&b))
}
fn original_reference_args(
    selection: &MissionSelection, page_size: Option<u8>, cursor: Option<&str>,
) -> Result<Value> {
    selection.validate()?;
    let size = page_size.unwrap_or(16);
    if !(1..=32).contains(&size) ||
       cursor.is_some_and(|value| !valid_reference_cursor(value)) {
        return Err("SESSION_REFERENCES_INVALID".into());
    }
    let mut args = serde_json::json!({
        "work_ref": selection.work_ref, "root_job_id": selection.root_job_id,
        "page_size": size,
    });
    if let Some(cursor) = cursor {
        args["cursor"] = Value::String(cursor.to_owned());
    }
    Ok(args)
}
// Separate closed project-history selector. Never reinterpret an absent root
// as a current/latest root, and never widen the incumbent selected-root command.
fn project_original_reference_args(work_ref: &str, cursor: Option<&str>) -> Result<Value> {
    let work = work_ref.strip_prefix("WS:").ok_or("SESSION_REFERENCES_INVALID")?;
    if !(2..=64).contains(&work.len()) ||
        !(work.as_bytes()[0].is_ascii_uppercase() || work.as_bytes()[0].is_ascii_digit()) ||
        !work.bytes().all(|b| b.is_ascii_alphanumeric() || b"_.-".contains(&b)) {
        return Err("SESSION_REFERENCES_INVALID".into());
    }
    if cursor.is_some_and(|value| !valid_reference_cursor(value)) {
        return Err("SESSION_REFERENCES_INVALID".into());
    }
    let mut args = serde_json::json!({ "work_ref": work_ref, "page_size": 4 });
    if let Some(cursor) = cursor { args["cursor"] = Value::String(cursor.to_owned()); }
    Ok(args)
}
#[tauri::command]
pub async fn executive_project_session_references(
    app: AppHandle, work_ref: String, cursor: Option<String>,
) -> Result<Value> {
    let args = project_original_reference_args(&work_ref, cursor.as_deref())?;
    let result = executive_post(app.clone(), "/os/executive/session/references",
        serde_json::json!({ "arguments": args })).await;
    if result.is_err() { emit(&app); }
    result
}
/// One continuation through the incumbent Executive resource. No implicit
/// target, alternate origin, retries, login or Workspace authority is added.
#[tauri::command]
pub async fn executive_session_send(app:AppHandle,arguments:Value)->Result<Value>{
    let body=crate::native_session_send::body(arguments)?;
    let result=executive_post(app.clone(),crate::native_session_send::PATH,body).await;
    if result.is_err(){emit(&app);}
    result
}
#[tauri::command]
pub async fn executive_session_context(app: AppHandle, selection: SessionSelection) -> Result<Value> {
    selection.validate()?;
    // The Session context endpoint requires the selected variant directly,
    // whereas replies/references use the existing arguments envelope. This
    // stays a READ. The fixed SEND command validates Fabric, Secretary or Meta targets.
    let result = executive_post(app.clone(), "/os/executive/session/context",
        serde_json::json!({ "selection": selection.wire() })).await;
    if result.is_err() { emit(&app); }
    result
}
fn project_history_context_body(work_ref: String) -> Result<Value> {
    let selection = ProjectPlanSelection { work_ref };
    selection.validate()?;
    Ok(serde_json::json!({ "selection": { "work_ref": selection.work_ref } }))
}
#[tauri::command]
pub async fn executive_project_history_context(app: AppHandle, work_ref: String) -> Result<Value> {
    let body = project_history_context_body(work_ref)?;
    let result = executive_post(app.clone(), "/os/executive/session/history-context", body).await;
    if result.is_err() { emit(&app); }
    result
}
#[tauri::command]
pub async fn executive_session_reply(app: AppHandle, operation_key: String) -> Result<Value> {
    if !valid_original_operation_key(&operation_key) {
        return Err("SESSION_OPERATION_INVALID".into());
    }
    let result = executive_post(app.clone(), "/os/executive/session/reply",
        serde_json::json!({ "arguments": { "operation_key": operation_key } })).await;
    if result.is_err() { emit(&app); }
    result
}
#[tauri::command]
pub async fn executive_session_references(
    app: AppHandle, selection: MissionSelection, page_size: Option<u8>, cursor: Option<String>,
) -> Result<Value> {
    let args = original_reference_args(&selection, page_size, cursor.as_deref())?;
    let result = executive_post(app.clone(), "/os/executive/session/references",
        serde_json::json!({ "arguments": args })).await;
    if result.is_err() { emit(&app); }
    result
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn project_history_omits_root_and_fixes_four_reference_budget() {
        let args = project_original_reference_args("WS:ALPHA", Some("YQ==")).unwrap();
        assert_eq!(args, serde_json::json!({"work_ref":"WS:ALPHA","page_size":4,"cursor":"YQ=="}));
        assert!(args.get("root_job_id").is_none());
        assert_eq!(project_original_reference_args("WS:ALPHA", None).unwrap(),
            serde_json::json!({"work_ref":"WS:ALPHA","page_size":4}));
        for work in ["WS:A", "WS:lower", "WS:ALPHA\n", "WS:../private", "https://private"] {
            assert!(project_original_reference_args(work, None).is_err());
        }
        assert!(project_original_reference_args("WS:ALPHA", Some("abc/..")).is_err());
        assert!(project_original_reference_args("WS:ALPHA", Some(&"A".repeat(2049))).is_err());
    }
    #[test]
    fn native_original_reads_admit_only_closed_selection_operation_and_cursor() {
        let selected = MissionSelection { work_ref: "WS:ORIGINAL".into(), root_job_id: "JOB-1".into() };
        let args = original_reference_args(&selected, None, None).unwrap();
        assert_eq!(args["page_size"], 16);
        assert!(args.get("cursor").is_none());
        let args = original_reference_args(&selected, Some(32), Some("YWJjZA==")).unwrap();
        assert_eq!(args["cursor"], "YWJjZA==");
        assert!(original_reference_args(&selected, Some(0), None).is_err());
        assert!(original_reference_args(&selected, Some(33), None).is_err());
        assert!(original_reference_args(&selected, Some(16), Some("abc/..")).is_err());
        assert!(original_reference_args(&selected, None, Some(&"A".repeat(2049))).is_err());
        assert!(original_reference_args(&MissionSelection {
            work_ref: "WS:BAD?".into(), root_job_id: "JOB-1".into(),
        }, None, None).is_err());
        assert!(valid_original_operation_key(&format!("session-continue-{}", "a".repeat(64))));
        assert!(!valid_original_operation_key(&format!("session-continue-{}", "A".repeat(64))));
        assert!(!valid_original_operation_key("session-continue-invalid"));
    }
    #[test]
    fn autonomy_policy_read_is_one_fixed_selected_root_acquisition_target() {
        let selected: MissionSelection = serde_json::from_value(serde_json::json!({"work_ref":"WS:ONE","root_job_id":"JOB-1"})).unwrap();
        let url = autonomy_policy_target(&selected).unwrap();
        assert_eq!(url.origin().ascii_serialization(), ORIGIN);
        assert_eq!(url.path(), "/workspace/autonomy/current");
        assert_eq!(url.query_pairs().collect::<Vec<_>>(), vec![("work_ref".into(),"WS:ONE".into()),("root_job_id".into(),"JOB-1".into())]);
        assert_eq!(AUTONOMY_POLICY_RESPONSE_CAP, 32_768);
        for value in [
            serde_json::json!({"work_ref":"WS:ONE","root_job_id":"JOB-1","path":"/private"}),
            serde_json::json!({"work_ref":"WS:ONE","root_job_id":"JOB-1","account":"foreign"}),
            serde_json::json!({"work_ref":"WS:ONE"}),
        ] { assert!(serde_json::from_value::<MissionSelection>(value).is_err()); }
        for (work, root) in [("WS:ONE\n","JOB-1"),("WS:ONE","JOB-1\n"),("WS:lower","JOB-1"),("WS:ONE","JOB-latest")] {
            assert!(autonomy_policy_target(&MissionSelection {work_ref:work.into(),root_job_id:root.into()}).is_err());
        }
    }
    #[test]
    fn project_plan_read_is_one_fixed_rootless_acquisition_target() {
        let selection: ProjectPlanSelection = serde_json::from_value(serde_json::json!({"work_ref": "WS:PLAN-ONE"})).unwrap();
        let url = project_plan_target(&selection).unwrap();
        assert_eq!(url.path(), "/workspace/project-plan/current");
        assert_eq!(url.origin().ascii_serialization(), ORIGIN);
        assert_eq!(url.query_pairs().collect::<Vec<_>>(), vec![("work_ref".into(), "WS:PLAN-ONE".into())]);
        assert_eq!(PROJECT_PLAN_RESPONSE_CAP, 131_072);
        for key in ["root_job_id", "path", "commit", "resource", "operation"] {
            let mut value = serde_json::json!({"work_ref": "WS:PLAN-ONE"});
            value[key] = serde_json::json!("foreign");
            assert!(serde_json::from_value::<ProjectPlanSelection>(value).is_err());
        }
        for work in ["WS:A", "WS:plan", "WS:PLAN\n", "WS:PLAN/../../private", "WS:PLAN--ONE", "WS:-PLAN", "WS:PLAN-", "JOB-1", "WS:計画"] {
            assert!(project_plan_target(&ProjectPlanSelection { work_ref: work.into() }).is_err());
        }
    }
    #[test]
    fn project_plan_header_retains_v1_and_accepts_only_bound_v2() {
        let selection = ProjectPlanSelection { work_ref: "WS:PLAN-TEST".into() };
        for schema in [PROJECT_PLAN_SCHEMA, PROJECT_PLAN_SCHEMA_V2] {
            assert!(project_plan_header_matches(&serde_json::json!({"schema": schema,
                "selection": {"work_ref": "WS:PLAN-TEST"}}), &selection));
        }
        for value in [serde_json::json!({"schema": PROJECT_PLAN_SCHEMA_V2, "selection": {"work_ref": "WS:OTHER"}}),
            serde_json::json!({"schema": "mastermind.workspace_project_plan.v3", "selection": {"work_ref": "WS:PLAN-TEST"}}),
            serde_json::json!({"schema": PROJECT_PLAN_SCHEMA_V2})] {
            assert!(!project_plan_header_matches(&value, &selection));
        }
    }
    #[test]
    fn project_journal_read_is_one_fixed_rootless_acquisition_target() {
        let selection: ProjectPlanSelection = serde_json::from_value(serde_json::json!({"work_ref": "WS:PLAN-ONE"})).unwrap();
        let url = project_journal_target(&selection).unwrap();
        assert_eq!(url.path(), "/workspace/project-journal/current");
        assert_eq!(url.origin().ascii_serialization(), ORIGIN);
        assert_eq!(url.query_pairs().collect::<Vec<_>>(), vec![("work_ref".into(), "WS:PLAN-ONE".into())]);
        assert_eq!(PROJECT_JOURNAL_RESPONSE_CAP, 131_072);
        for key in ["root_job_id", "path", "commit", "resource", "operation"] {
            let mut value = serde_json::json!({"work_ref": "WS:PLAN-ONE"});
            value[key] = serde_json::json!("foreign");
            assert!(serde_json::from_value::<ProjectPlanSelection>(value).is_err());
        }
        for work in ["WS:A", "WS:plan", "WS:PLAN\n", "WS:PLAN/../../private", "WS:PLAN--ONE", "WS:-PLAN", "WS:PLAN-", "JOB-1", "WS:計画"] {
            assert!(project_journal_target(&ProjectPlanSelection { work_ref: work.into() }).is_err());
        }
    }
    fn inner() -> Inner {
        // This fixture covers the base two-resource flow independently of the
        // compiled optional Executive profile; enabled flows have explicit fixtures.
        Inner::with_executive_resource(Some("public-client"), None)
    }
    fn callback_url(state: &str) -> String {
        format!("{CALLBACK}?state={state}&code=test-code")
    }
    fn token(value: &str) -> Token {
        Token {
            value: value.into(),
            expires: Instant::now() + Duration::from_secs(60),
            wall_expires: SystemTime::now() + Duration::from_secs(60),
            executive_send: false,
        }
    }
    #[test]
    fn native_token_wall_expiry_fences_sleep_without_waiting_for_instant() {
        let mut inner = inner();
        let mut access = token("synthetic-but-private");
        assert!(access.expires > Instant::now());
        access.wall_expires = SystemTime::now() - Duration::from_secs(1);
        inner.acquisition = Some(access);
        assert!(inner.token(Resource::Acquisition).is_none());
        assert!(!inner.status().acquisition);
        assert_eq!(inner.status().status, "signed_out");
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
    fn completed_transaction_timers_do_not_announce_an_auth_change() {
        let mut i = Inner::with_executive_resource(Some("public-client"),
            Some("https://mcp.mastermind-x.com/os/executive"));
        i.transaction(Resource::Acquisition).unwrap();
        let mut deadlines = Vec::new();
        for resource in [Resource::Acquisition, Resource::Content, Resource::Executive] {
            let pending = i.pending.as_ref().unwrap();
            deadlines.push((pending.generation, pending.expires));
            let state = pending.state.clone();
            let (pending, _, _) = i.consume(&callback_url(&state)).unwrap();
            assert_eq!(pending.resource, resource);
            i.finish_exchange(pending.generation, resource, Ok(token("grant")));
        }
        let generation = i.generation;
        let executive_generation = i.executive_generation;
        for (timer_generation, expires) in deadlines {
            assert!(!i.expire_transaction(timer_generation, expires, expires));
        }
        assert_eq!(i.status().status, "signed_in");
        assert!(i.token(Resource::Acquisition).is_some());
        assert!(i.token(Resource::Content).is_some());
        assert!(i.token(Resource::Executive).is_some());
        assert_eq!(i.generation, generation);
        assert_eq!(i.executive_generation, executive_generation);
        assert!(i.pending.is_none());
        assert!(i.reason.is_none());
    }

    #[test]
    fn consumed_callback_timer_does_not_interrupt_exchange() {
        let mut i = inner();
        i.transaction(Resource::Acquisition).unwrap();
        let state = i.pending.as_ref().unwrap().state.clone();
        let (pending, _, _) = i.consume(&callback_url(&state)).unwrap();
        assert!(!i.expire_transaction(pending.generation, pending.expires, pending.expires));
        assert!(i.exchanging);
        assert!(i.reason.is_none());
        assert!(i.finish_exchange(pending.generation, pending.resource, Ok(token("grant"))).is_some());
        assert!(i.status().acquisition);
    }

    #[test]
    fn stale_transaction_timer_preserves_replacement_and_logout_generation() {
        let mut i = inner();
        i.transaction(Resource::Acquisition).unwrap();
        let generation = i.generation;
        let old_deadline = i.pending.as_ref().unwrap().expires;
        i.transaction(Resource::Content).unwrap();
        let replacement_deadline = old_deadline + Duration::from_secs(1);
        i.pending.as_mut().unwrap().expires = replacement_deadline;
        let replacement_state = i.pending.as_ref().unwrap().state.clone();
        assert!(!i.expire_transaction(generation, old_deadline, replacement_deadline));
        assert!(!i.expire_transaction(generation, replacement_deadline, old_deadline));
        assert_eq!(i.pending.as_ref().unwrap().state, replacement_state);
        assert_eq!(i.pending.as_ref().unwrap().resource, Resource::Content);
        i.invalidate();
        i.transaction(Resource::Acquisition).unwrap();
        let current_deadline = i.pending.as_ref().unwrap().expires;
        let current_state = i.pending.as_ref().unwrap().state.clone();
        assert!(!i.expire_transaction(generation, current_deadline, current_deadline));
        assert_eq!(i.pending.as_ref().unwrap().state, current_state);
        assert!(i.reason.is_none());
    }

    #[test]
    fn current_transaction_expires_once_with_resource_failure_isolation() {
        for resource in [Resource::Acquisition, Resource::Content, Resource::Executive] {
            let mut i = Inner::with_executive_resource(Some("public-client"),
                Some("https://mcp.mastermind-x.com/os/executive"));
            i.acquisition = Some(token("acquisition"));
            i.content = Some(token("content"));
            i.transaction(resource).unwrap();
            let expires = i.pending.as_ref().unwrap().expires;
            let generation = i.generation;
            assert!(i.expire_transaction(generation, expires, expires));
            assert!(!i.expire_transaction(generation, expires, expires));
            assert!(i.pending.is_none());
            assert!(!i.exchanging);
            assert!(i.status().acquisition);
            assert!(i.status().content);
            if resource == Resource::Executive {
                assert_eq!(i.status().status, "signed_in");
                assert!(i.reason.is_none());
                assert!(i.executive.is_none());
            } else {
                assert_eq!(i.reason, Some("AUTH_TRANSACTION_EXPIRED"));
                assert_eq!(i.status().status, "error");
            }
        }
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
    fn explicit_sign_in_requests_login_without_an_identity_hint() {
        let mut i = inner();
        let raw = i.initial_sign_in_transaction().unwrap();
        let url = Url::parse(&raw).unwrap();
        let pairs: Vec<_> = url.query_pairs().collect();
        let value = |key: &str| pairs.iter().find(|(k, _)| k == key).map(|(_, v)| v.as_ref());
        assert_eq!(value("prompt"), Some("login"));
        assert_eq!(pairs.iter().filter(|(k, _)| k == "prompt").count(), 1);
        assert_eq!(value("login_hint"), None);
        assert_eq!(url.origin().ascii_serialization(), ISSUER.trim_end_matches('/'));
        assert_eq!(url.path(), "/authorize");
        assert_eq!(value("client_id"), Some("public-client"));
        assert_eq!(value("redirect_uri"), Some(CALLBACK));
        assert_eq!(value("response_type"), Some("code"));
        assert_eq!(value("audience"), Some(Resource::Acquisition.audience()));
        let expected_scope = if Resource::Acquisition.persistent() {
            format!("{} offline_access", Resource::Acquisition.scope())
        } else { Resource::Acquisition.scope().to_owned() };
        assert_eq!(value("scope"), Some(expected_scope.as_str()));
        let pending = i.pending.as_ref().unwrap();
        assert_eq!(value("state"), Some(pending.state.as_str()));
        assert_eq!(value("code_challenge_method"), Some("S256"));
        let challenge = URL_SAFE_NO_PAD.encode(Sha256::digest(pending.verifier.as_bytes()));
        assert_eq!(value("code_challenge"), Some(challenge.as_str()));
    }
    #[test]
    fn explicit_sign_in_chained_grants_preserve_same_session_sso() {
        let mut i = Inner::with_executive_resource(Some("public-client"),
            Some("https://mcp.mastermind-x.com/os/executive"));
        i.initial_sign_in_transaction().unwrap();
        for (completed, next) in [(Resource::Acquisition, Resource::Content),
            (Resource::Content, Resource::Executive)] {
            let state = i.pending.as_ref().unwrap().state.clone();
            let (pending, _, _) = i.consume(&callback_url(&state)).unwrap();
            assert_eq!(pending.resource, completed);
            let raw = i.finish_exchange(pending.generation, pending.resource, Ok(token("grant"))).unwrap();
            let url = Url::parse(&raw).unwrap();
            let pairs: std::collections::BTreeMap<_, _> = url.query_pairs().collect();
            assert!(!pairs.contains_key("prompt"));
            assert!(!pairs.contains_key("login_hint"));
            assert_eq!(pairs["audience"], if next == Resource::Executive {
                i.executive_resource.as_deref().unwrap()
            } else { next.audience() });
            assert_eq!(pairs["redirect_uri"], CALLBACK);
            assert_eq!(pairs["code_challenge_method"], "S256");
            assert_eq!(i.pending.as_ref().unwrap().resource, next);
        }
        let state = i.pending.as_ref().unwrap().state.clone();
        let (pending, _, _) = i.consume(&callback_url(&state)).unwrap();
        assert!(i.finish_exchange(pending.generation, pending.resource, Ok(token("grant"))).is_none());
        assert!(i.token(Resource::Executive).is_some());
    }
    #[test]
    fn explicit_sign_in_without_a_client_stays_unconfigured() {
        let mut i = Inner::new(None);
        assert_eq!(i.initial_sign_in_transaction().unwrap_err(), "NATIVE_CLIENT_ID_MISSING");
        assert!(i.pending.is_none());
        assert_eq!(i.status().status, "unconfigured");
    }
    #[test]
    fn separate_authorizations_have_exact_custom_scope_and_s256() {
        for resource in [Resource::Acquisition, Resource::Content] {
            let url =
                Url::parse(&authorization_url("client", resource, "state", "verifier")).unwrap();
            let pairs: std::collections::BTreeMap<_, _> = url.query_pairs().collect();
            assert_eq!(pairs["audience"], resource.audience());
            assert_eq!(pairs["scope"], if resource.persistent() {
                format!("{} offline_access", resource.scope())
            } else { resource.scope().to_owned() });
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
            wall_expires: SystemTime::now() + Duration::from_secs(60),
            executive_send: false,
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
    fn mission_result_acquisition_uses_fixed_path_and_exact_selection() {
        let mut selection = ResultSelection {
            work_ref: "WS:AB".into(),
            root_job_id: "JOB-1".into(),
            job_id: "JOB-2".into(),
            attempt_id: format!("ATT-{}", "a".repeat(32)),
            result_envelope_digest: "b".repeat(64),
        };
        let url = mission_result_url(&selection).unwrap();
        assert_eq!(url.origin(), Url::parse(ORIGIN).unwrap().origin());
        assert_eq!(url.path(), "/workspace/mission-result/current");
        assert!(url.fragment().is_none());
        let pairs: std::collections::BTreeMap<_, _> = url.query_pairs().into_owned().collect();
        assert_eq!(pairs.len(), 5);
        assert_eq!(pairs.get("work_ref"), Some(&selection.work_ref));
        assert_eq!(pairs.get("root_job_id"), Some(&selection.root_job_id));
        assert_eq!(pairs.get("job_id"), Some(&selection.job_id));
        assert_eq!(pairs.get("attempt_id"), Some(&selection.attempt_id));
        assert_eq!(pairs.get("result_envelope_digest"), Some(&selection.result_envelope_digest));
        selection.job_id = "https://other.invalid".into();
        assert!(mission_result_url(&selection).is_err());
    }

    #[test]
    fn compound_unavailable_cannot_carry_a_mission_or_result() {
        let unavailable = serde_json::json!({
            "schema": MISSION_RESULT_SCHEMA,
            "availability": "UNAVAILABLE",
            "mission": null,
            "role_result": null,
        });
        assert!(typed_mission_result_unavailable(unavailable.clone()).is_ok());
        for name in ["mission", "role_result"] {
            let mut non_null = unavailable.clone();
            non_null[name] = serde_json::json!({});
            assert!(typed_mission_result_unavailable(non_null).is_err());
            let mut missing = unavailable.clone();
            missing.as_object_mut().unwrap().remove(name);
            assert!(typed_mission_result_unavailable(missing).is_err());
        }
        let mut wrong = unavailable.clone();
        wrong["schema"] = RESULT_SCHEMA.into();
        assert!(typed_mission_result_unavailable(wrong).is_err());
        let mut available = unavailable;
        available["availability"] = "AVAILABLE".into();
        assert!(typed_mission_result_unavailable(available).is_err());
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
            assert_eq!(pairs["scope"], if resource.persistent() {
                format!("{} offline_access", resource.scope())
            } else { resource.scope().to_owned() });
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
    fn native_diagnostic_status_preserves_regular_wire_and_workspace_authority() {
        let mut i = at_executive_pending();
        let workspace_generation = i.generation;
        let pending_state = i.pending.as_ref().unwrap().state.clone();
        let regular = serde_json::to_value(i.executive_status()).unwrap();
        assert_eq!(regular.as_object().unwrap().len(), 2);
        let observation = serde_json::to_value(i.executive_observation()).unwrap();
        assert_eq!(observation.as_object().unwrap().len(), 6);
        assert_eq!(observation["configured"], true);
        assert_eq!(observation["reason"], "AUTHORIZING");
        assert_eq!(i.generation, workspace_generation);
        assert_eq!(i.pending.as_ref().unwrap().state, pending_state);
        assert!(i.token(Resource::Acquisition).is_some() && i.token(Resource::Content).is_some());
        assert!(!i.executive_status().available);
        assert!(i.consume(&format!("{CALLBACK}?state={pending_state}&error=access_denied")).is_err());
        assert_eq!(serde_json::to_value(i.executive_observation()).unwrap()["reason"], "AUTHORIZATION_REFUSED");
        assert!(i.reason.is_none());
        assert_eq!(i.status().status, "signed_in");
        assert!(i.token(Resource::Acquisition).is_some() && i.token(Resource::Content).is_some());
    }
    #[test]
    fn native_diagnostic_status_reports_ready_expired_and_unconfigured_without_grant_inference() {
        let mut i = at_executive_pending();
        assert!(complete_resource(&mut i, Resource::Executive).is_none());
        assert_eq!(serde_json::to_value(i.executive_observation()).unwrap()["reason"], "AVAILABLE");
        i.executive.as_mut().unwrap().expires = Instant::now() - Duration::from_secs(1);
        let observed = serde_json::to_value(i.executive_observation()).unwrap();
        assert_eq!(observed["reason"], "EXPIRED");
        assert_eq!(observed["available"], false);
        assert!(i.token(Resource::Acquisition).is_some() && i.token(Resource::Content).is_some());
        i.executive_resource = None;
        assert_eq!(serde_json::to_value(i.executive_observation()).unwrap()["reason"], "UNCONFIGURED");
    }
    #[test]
    fn native_diagnostic_programs_observation_is_latest_same_generation_only() {
        let mut i = executive_inner();
        let first = i.begin_programs_observation();
        let second = i.begin_programs_observation();
        i.finish_programs_observation(first, ProgramsRead::response(503, None));
        assert_eq!(i.programs_read, ProgramsRead::pending());
        i.finish_programs_observation(second, ProgramsRead::response(200, None));
        assert_eq!(i.programs_read.phase, transport_diagnostics::ProgramsPhase::Ready);
        i.invalidate_auth();
        i.finish_programs_observation(second, ProgramsRead::response(503, None));
        assert_eq!(i.programs_read, ProgramsRead::default());
        i.programs_sequence = u64::MAX;
        assert_eq!(i.begin_programs_observation(), None);
        i.finish_programs_observation(None, ProgramsRead::response(503, None));
        assert_eq!(i.programs_read, ProgramsRead::default());
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
        for scope in [EXECUTIVE_SCOPE, "mastermind.executive.intent.submit mastermind.executive.read", "mastermind.executive.read"] {
            assert!(parse_token(serde_json::json!({"access_token":"opaque", "token_type":"Bearer",
                "expires_in":60, "scope":scope}), Resource::Executive).is_ok());
        }
        for scope in [Value::Null, Value::String("mastermind.executive.intent.submit".into()),
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

    fn parsed_native_executive_token(scope: &str) -> Token {
        parse_token(serde_json::json!({
            "access_token": "fixture-native-executive",
            "token_type": "Bearer",
            "expires_in": 60,
            "scope": scope,
        }), Resource::Executive).unwrap()
    }

    fn install_native_executive_token(inner: &mut Inner, scope: &str) {
        let pending_state = inner.pending.as_ref().unwrap().state.clone();
        let (pending, _, _) = inner.consume(&callback_url(&pending_state)).unwrap();
        inner.finish_exchange(pending.generation, pending.resource,
            Ok(parsed_native_executive_token(scope)));
    }

    fn native_executive_state(scope: &str) -> NativeAuth {
        let mut inner = at_executive_pending();
        install_native_executive_token(&mut inner, scope);
        let state = NativeAuth::new().unwrap();
        *state.lock().unwrap() = inner;
        state
    }

    fn native_fixture_response() -> reqwest::Response {
        tauri::http::Response::builder()
            .status(200)
            .header("Content-Type", "application/json")
            .body(r#"{"fixture":"native-dispatch"}"#.to_owned())
            .unwrap()
            .into()
    }

    #[test]
    fn native_diagnostic_wire_same_run_file_source_requests_and_responses_preserve_exact_bodies() {
        let fixture: Value = serde_json::from_str(include_str!("../../src/fixtures/native-wire/source-file-6cb8.json")).unwrap();
        for index in [3usize, 4, 5, 6, 8, 9, 10, 11, 12] {
            let sample = &fixture["samples"][index];
            let kind = sample["operation"].as_str().unwrap();
            let request = &sample["request"];
            let response = sample["response"].clone();
            let target = source_operation_target(kind, request).unwrap();
            assert_eq!(target.path(), format!("/workspace/source-operation/{}", if kind == "read" {"operation"} else {kind}));
            assert_eq!(source_operation_body(response.clone(), kind, request).unwrap(), response);
            let mut foreign = response.clone(); foreign["schema"] = "foreign.v1".into();
            assert!(source_operation_body(foreign, kind, request).is_err());
            let mut foreign = response; foreign["selection"]["request_id"] = "foreign".into();
            assert!(source_operation_body(foreign, kind, request).is_err());
            let mut foreign = request.clone(); foreign["principal_scope"] = "foreign".into();
            assert!(source_operation_target(kind, &foreign).is_err());
        }
        let sample = &fixture["samples"][2];
        assert!(source_operation_target("options", &sample["request"]).is_ok());
        assert_eq!(source_operation_body(sample["response"].clone(), "options", &sample["request"]).unwrap(), sample["response"]);
    }
    #[test]
    fn native_diagnostic_wire_same_run_planning_preserves_signed_producer_vectors() {
        let fixture: Value = serde_json::from_str(include_str!("../../src/fixtures/native-wire/source-file-6cb8.json")).unwrap();
        for index in [15usize,16] {
            let sample = &fixture["samples"][index];
            let operation = sample["operation"].as_str().unwrap();
            let arguments = &sample["request"]["arguments"];
            assert_eq!(crate::project_planning::validate(operation,arguments).unwrap(), *arguments);
            let path = crate::project_planning::route(operation).unwrap();
            let state = native_executive_state(EXECUTIVE_SCOPE);
            state.lock().unwrap().acquisition = Some(token("fixture-workspace"));
            let calls = std::cell::Cell::new(0);
            let body = serde_json::json!({"arguments":arguments});
            let result = tauri::async_runtime::block_on(executive_post_with_dispatch(&state, path, body.clone(), |builder| {
                calls.set(calls.get()+1);
                let request=builder.build().unwrap();
                assert_eq!(request.url().path(),path);
                assert_eq!(serde_json::from_slice::<Value>(request.body().unwrap().as_bytes().unwrap()).unwrap(),body);
                assert!(request.headers().contains_key("x-mastermind-workspace-authorization"));
                let encoded=serde_json::to_string(&sample["response"]).unwrap();
                async move {Ok(tauri::http::Response::builder().status(200).header("Content-Type","application/json").body(encoded).unwrap().into())}
            })).unwrap();
            assert_eq!(calls.get(),1);assert_eq!(result,sample["response"]);
            let mut foreign=arguments.clone();foreign["principal_scope"]="foreign".into();
            assert!(crate::project_planning::validate(operation,&foreign).is_err());
        }
    }
    #[test]
    fn native_diagnostic_wire_same_run_initial_and_attended_requests_dispatch_once_and_preserve_bodies() {
        let fixture: Value = serde_json::from_str(include_str!("../../src/fixtures/native-wire/fresh-attended-0f44.json")).unwrap();
        let initial = serde_json::json!({"work_ref":fixture["request"]["work_ref"],"operation_key":fixture["request"]["operation_key"]});
        let attended = &fixture["attended"];
        let cases = [
            ("preview", fixture["request"].clone(), fixture["preview"].clone()),
            ("create", fixture["create_request"].clone(), fixture["create"].clone()),
            ("status", initial.clone(), fixture["status"].clone()),
            ("read", initial, fixture["read"].clone()),
            ("consume", attended["consume_request"].clone(), attended["lost_consume"].clone()),
            ("consume_status", attended["consume_request"].clone(), attended["consume_status"].clone()),
            ("turn_preview", attended["turn_preview_request"].clone(), attended["turn_preview"].clone()),
            ("turn", attended["turn_request"].clone(), attended["turn"].clone()),
            ("turn_status", attended["turn_selection"].clone(), attended["status"].clone()),
            ("turn_read", attended["turn_selection"].clone(), attended["turn_read"].clone()),
        ];
        for (operation, arguments, response) in cases {
            crate::fresh_conversation::validate(operation, &arguments).unwrap();
            let path = crate::fresh_conversation::path(operation).unwrap();
            let state = native_executive_state(EXECUTIVE_SCOPE);
            state.lock().unwrap().acquisition = Some(token("fixture-workspace"));
            let calls = std::cell::Cell::new(0);
            let body = serde_json::json!({"arguments":arguments});
            let result = tauri::async_runtime::block_on(executive_post_with_dispatch(&state, path, body.clone(), |builder| {
                calls.set(calls.get() + 1);
                let request = builder.build().unwrap();
                assert_eq!(request.url().path(), path);
                assert_eq!(serde_json::from_slice::<Value>(request.body().unwrap().as_bytes().unwrap()).unwrap(), body);
                let encoded = serde_json::to_string(&response).unwrap();
                async move {Ok(tauri::http::Response::builder().status(200).header("Content-Type", "application/json").body(encoded).unwrap().into())}
            })).unwrap();
            assert_eq!(calls.get(), 1); assert_eq!(result, response);
            let mut foreign = arguments; foreign["principal_scope"] = "foreign".into();
            assert!(crate::fresh_conversation::validate(operation, &foreign).is_err());
        }
    }
    #[test]
    fn native_diagnostic_programs_header_preserves_actual_same_run_v1_v2_and_rejects_foreign() {
        let fixture: Value = serde_json::from_str(include_str!("../../src/fixtures/project-discovery-app-source.json")).unwrap();
        for key in ["programs_before", "programs"] {
            let raw = fixture[key].clone();
            let body = workspace_read_body(raw.clone(), "/workspace/programs/current", "mastermind.workspace_programs.v1").unwrap();
            assert_eq!(body, raw); // no source/row/clock/identity or DATA relabel
        }
        for header in ["mastermind.workspace_programs.v3", "foreign", "mastermind.workspace_work_queue.v1"] {
            let mut raw = fixture["programs"].clone(); raw["schema"] = header.into();
            assert_eq!(workspace_read_body(raw, "/workspace/programs/current", "mastermind.workspace_programs.v1").unwrap_err(), "RESPONSE_INVALID");
        }
        assert!(workspace_read_body(fixture["programs"].clone(), "/workspace/work/current", "mastermind.workspace_programs.v1").is_err());
        assert!(workspace_read_body(fixture["programs"].clone(), "/workspace/programs/current", "mastermind.workspace_work_queue.v1").is_err());
    }


    fn project_execution_read_reference() -> Value {
        serde_json::json!({
            "schema": "mastermind.project_execution_reference.v1", "work_ref": "WS:PROJECT-ONE",
            "root_job_id": "JOB-123", "root_event_id": 42, "root_event_sha256": "a".repeat(64),
            "project_execution_source_sha256": "b".repeat(64), "principal_scope_sha256": "c".repeat(64)
        })
    }

    #[test]
    fn project_conversations_read_execution_routes_use_only_read_only_executive_grant() {
        for operation in ["execution_references", "execution_read"] {
            let state = native_executive_state("mastermind.executive.read");
            state.lock().unwrap().acquisition = None;
            let path = crate::project_conversations_read::path(operation).unwrap();
            let args = if operation == "execution_references" {
                serde_json::json!({"work_ref": "WS:PROJECT-ONE"})
            } else { project_execution_read_reference() };
            let body = serde_json::json!({"arguments": args});
            let calls = std::cell::Cell::new(0);
            let result = tauri::async_runtime::block_on(executive_post_with_dispatch(&state, path, body.clone(), |builder| {
                calls.set(calls.get() + 1);
                let request = builder.build().unwrap();
                assert_eq!(request.url().as_str(), format!("{ORIGIN}{path}"));
                assert_eq!(request.headers()["authorization"], "Bearer fixture-native-executive");
                assert!(!request.headers().contains_key("x-mastermind-workspace-authorization"));
                assert_eq!(serde_json::from_slice::<Value>(request.body().unwrap().as_bytes().unwrap()).unwrap(), body);
                async { Ok(native_fixture_response()) }
            }));
            assert!(result.is_ok()); assert_eq!(calls.get(), 1);
            assert!(!state.lock().unwrap().token(Resource::Executive).unwrap().executive_send);
        }
    }

    #[test]
    fn project_conversations_read_execution_refuses_new_authority_and_invalid_identity_before_dispatch() {
        let state = native_executive_state("mastermind.executive.read");
        state.lock().unwrap().acquisition = None;
        let calls = std::cell::Cell::new(0);
        let mut extra = project_execution_read_reference(); extra["operation_key"] = "forged".into();
        let mut foreign = project_execution_read_reference(); foreign["project_execution_source_sha256"] = "short".into();
        for args in [extra, foreign] {
            let result = tauri::async_runtime::block_on(executive_post_with_dispatch(&state,
                "/os/executive/session/project-execution-read", serde_json::json!({"arguments": args}), |_| {
                    calls.set(calls.get() + 1); async { Ok(native_fixture_response()) }
                }));
            assert_eq!(result.unwrap_err(), "REQUEST_INVALID");
        }
        assert_eq!(calls.get(), 0);
    }

    #[test]
    fn project_conversations_read_execution_late_response_is_fenced_by_current_executive_generation() {
        let state = native_executive_state("mastermind.executive.read");
        state.lock().unwrap().acquisition = None;
        let calls = std::cell::Cell::new(0);
        let result = tauri::async_runtime::block_on(executive_post_with_dispatch(&state,
            "/os/executive/session/project-execution-read",
            serde_json::json!({"arguments": project_execution_read_reference()}), |_| async {
                calls.set(calls.get() + 1);
                state.lock().unwrap().executive_generation += 1;
                Ok(native_fixture_response())
            }));
        assert_eq!(result.unwrap_err(), "EXECUTIVE_AUTH_CHANGED"); assert_eq!(calls.get(), 1);
    }

    fn project_execution_arguments(operation: &str) -> Value {
        let mut value = serde_json::json!({
            "operation_key": format!("mmos-project-execute-{}", "a".repeat(40)), "work_ref": "WS:EXAMPLE"
        });
        if operation != "status" {
            value["expected_context"] = serde_json::json!({
                "record_source": {"repository": "mastermindx-market-intelligence/macro", "commit": "b".repeat(40),
                    "path": "agentos/workstreams/WS-EXAMPLE.md", "content_sha256": "c".repeat(64)},
                "adoption": null, "adoption_decision_source": null
            });
        }
        if operation == "preview" {
            value["operation_key"] = format!("mmos-project-preview-{}", "d".repeat(40)).into();
        }
        if operation == "submit" {
            value["context_sha256"] = "e".repeat(64).into();
            value["execution_binding_sha256"] = "f".repeat(64).into();
            value["execution_profile"] = "research_only".into();
            value["objective"] = "Finish the project".into();
            value["handoff_text"] = "Original private handoff".into();
            value["continuation_mode"] = "DURABLE".into();
        }
        value
    }

    #[test]
    fn project_execution_uses_fixed_routes_and_distinct_private_resource_tokens() {
        for operation in ["preview", "submit", "status"] {
            let state = native_executive_state(EXECUTIVE_SCOPE);
            state.lock().unwrap().acquisition = Some(token("fixture-workspace"));
            let path = crate::project_execution::route(operation).unwrap();
            let body = serde_json::json!({"arguments": project_execution_arguments(operation)});
            let calls = std::cell::Cell::new(0);
            let result = tauri::async_runtime::block_on(executive_post_with_dispatch(&state, path, body.clone(), |builder| {
                calls.set(calls.get() + 1);
                let request = builder.build().unwrap();
                assert_eq!(request.url().as_str(), format!("{ORIGIN}{path}"));
                assert_eq!(request.headers()["authorization"], "Bearer fixture-native-executive");
                assert_eq!(request.headers()["x-mastermind-workspace-authorization"], "Bearer fixture-workspace");
                assert_eq!(serde_json::from_slice::<Value>(request.body().unwrap().as_bytes().unwrap()).unwrap(), body);
                async { Ok(native_fixture_response()) }
            }));
            assert!(result.is_ok()); assert_eq!(calls.get(), 1);
        }
    }

    #[test]
    fn project_execution_requires_both_resources_and_send_scope_before_native_dispatch() {
        for (workspace, send) in [(false, true), (true, false), (true, true)] {
            let state = native_executive_state(if send { EXECUTIVE_SCOPE } else { "mastermind.executive.read" });
            state.lock().unwrap().acquisition = if workspace { Some(token("fixture-workspace")) } else { None };
            let calls = std::cell::Cell::new(0);
            let result = tauri::async_runtime::block_on(executive_post_with_dispatch(&state,
                "/os/executive/project-execution/submit",
                serde_json::json!({"arguments": project_execution_arguments("submit")}), |_| {
                    calls.set(calls.get() + 1); async { Ok(native_fixture_response()) }
                }));
            assert_eq!(calls.get(), usize::from(workspace && send));
            assert_eq!(result.is_ok(), workspace && send);
        }
    }

    #[test]
    fn project_execution_secondary_generation_and_expiry_fence_pending_response() {
        for change in ["generation", "remove", "expire"] {
            let state = native_executive_state(EXECUTIVE_SCOPE);
            state.lock().unwrap().acquisition = Some(token("fixture-workspace"));
            let calls = std::cell::Cell::new(0);
            let result = tauri::async_runtime::block_on(executive_post_with_dispatch(&state,
                "/os/executive/project-execution/submit",
                serde_json::json!({"arguments": project_execution_arguments("submit")}), |_| async {
                    calls.set(calls.get() + 1);
                    { let mut inner = state.lock().unwrap(); match change {
                        "generation" => inner.generation += 1,
                        "remove" => inner.acquisition = None,
                        _ => inner.acquisition.as_mut().unwrap().wall_expires = SystemTime::UNIX_EPOCH,
                    }}
                    Ok(native_fixture_response())
                }));
            assert_eq!(result.unwrap_err(), "WORKSPACE_AUTH_CHANGED");
            assert_eq!(calls.get(), 1);
        }
    }

    #[test]
    fn project_execution_rejects_extra_authority_and_oversize_handoff_before_dispatch() {
        let state = native_executive_state(EXECUTIVE_SCOPE);
        state.lock().unwrap().acquisition = Some(token("fixture-workspace"));
        let calls = std::cell::Cell::new(0);
        let mut forged = project_execution_arguments("submit"); forged["root_job_id"] = "JOB-forged".into();
        let mut oversized = project_execution_arguments("submit"); oversized["handoff_text"] = "界".repeat(10923).into();
        for args in [forged, oversized] {
            let result = tauri::async_runtime::block_on(executive_post_with_dispatch(&state,
                "/os/executive/project-execution/submit", serde_json::json!({"arguments": args}), |_| {
                    calls.set(calls.get() + 1); async { Ok(native_fixture_response()) }
                }));
            assert!(result.is_err());
        }
        assert_eq!(calls.get(), 0);
    }

    #[test]
    fn project_execution_preserves_typed_refusal_and_unknown_without_retry() {
        for (status, code) in [(403, "context_changed"), (409, "operation_conflict"), (503, "source_unavailable"), (202, "effect_unknown")] {
            let state = native_executive_state(EXECUTIVE_SCOPE);
            state.lock().unwrap().acquisition = Some(token("fixture-workspace"));
            let expected = serde_json::json!({
                "schema": "mastermind.project_execution_private_result.v1", "operation": "submit", "ok": false,
                "data": null, "error": {"code": code, "message": "Fixed refusal"}
            });
            let calls = std::cell::Cell::new(0);
            let result = tauri::async_runtime::block_on(executive_post_with_dispatch(&state,
                "/os/executive/project-execution/submit", serde_json::json!({"arguments": project_execution_arguments("submit")}), |_| {
                    calls.set(calls.get() + 1);
                    let encoded = serde_json::to_string(&expected).unwrap();
                    async move { Ok(tauri::http::Response::builder().status(status)
                        .header("Content-Type", "application/json").body(encoded).unwrap().into()) }
                })).unwrap();
            assert_eq!(result, expected); assert_eq!(calls.get(), 1);
        }
    }

    #[test]
    fn project_execution_refuses_mismatched_error_response_without_retry() {
        let state = native_executive_state(EXECUTIVE_SCOPE);
        state.lock().unwrap().acquisition = Some(token("fixture-workspace"));
        let calls = std::cell::Cell::new(0);
        let result = tauri::async_runtime::block_on(executive_post_with_dispatch(&state,
            "/os/executive/project-execution/submit", serde_json::json!({"arguments": project_execution_arguments("submit")}), |_| {
                calls.set(calls.get() + 1);
                async { Ok(tauri::http::Response::builder().status(403).header("Content-Type", "application/json")
                    .body(serde_json::json!({"schema": "mastermind.project_execution_private_result.v1",
                        "operation": "status", "ok": false, "data": null,
                        "error": {"code": "refused", "message": "Different operation"}}).to_string()).unwrap().into()) }
            }));
        assert_eq!(result.unwrap_err(), "EXECUTIVE_TRANSPORT_UNAVAILABLE"); assert_eq!(calls.get(), 1);
    }

    fn native_session_send_fixtures() -> Vec<Value> {
        [
            include_str!("../../src/fixtures/native-session-send-producer.json"),
            include_str!("../../src/fixtures/native-hermes-session-send-producer.json"),
        ].into_iter().map(|raw| serde_json::from_str(raw).unwrap()).collect()
    }

    #[test]
    fn native_session_send_actual_signed_body_uses_only_current_executive_resource() {
        for fixture in native_session_send_fixtures() {
            let state=native_executive_state(EXECUTIVE_SCOPE);
            {let mut i=state.lock().unwrap();i.acquisition=None;i.content=None;}
            let body=crate::native_session_send::body(fixture["arguments"].clone()).unwrap();
            let count=std::cell::Cell::new(0);
            let result=tauri::async_runtime::block_on(executive_post_with_dispatch(&state,crate::native_session_send::PATH,body.clone(),|builder|{
                count.set(count.get()+1);let request=builder.build().unwrap();
                assert_eq!(request.url().as_str(),format!("{ORIGIN}/os/executive/session/send"));
                assert_eq!(request.headers()["authorization"],"Bearer fixture-native-executive");
                assert!(!request.headers().contains_key("x-mastermind-workspace-authorization"));
                assert_eq!(serde_json::from_slice::<Value>(request.body().unwrap().as_bytes().unwrap()).unwrap(),body);
                let result:reqwest::Response=tauri::http::Response::builder().status(200).header("Content-Type","application/json").body(fixture["sent"].to_string()).unwrap().into();
                async{Ok(result)}
            })).unwrap();
            assert_eq!(count.get(),1);assert_eq!(result,fixture["sent"]);
        }
    }

    #[test]
    fn native_session_send_absent_readonly_and_expired_private_tokens_never_dispatch() {
        for fixture in native_session_send_fixtures() {
            for mode in ["absent","read","expired"] {
                let state=native_executive_state(if mode=="read"{"mastermind.executive.read"}else{EXECUTIVE_SCOPE});
                {let mut i=state.lock().unwrap();i.acquisition=None;i.content=None;
                    if mode=="absent"{i.executive=None;}
                    if mode=="expired"{i.executive.as_mut().unwrap().expires=Instant::now()-Duration::from_secs(1);}}
                let count=std::cell::Cell::new(0);
                let result=tauri::async_runtime::block_on(executive_post_with_dispatch(&state,crate::native_session_send::PATH,crate::native_session_send::body(fixture["arguments"].clone()).unwrap(),|_|{
                    count.set(count.get()+1);async{Ok(tauri::http::Response::builder().status(200).body("{}").unwrap().into())}
                }));
                assert_eq!(count.get(),0);assert_eq!(result.unwrap_err(),if mode=="read"{"EXECUTIVE_SEND_SCOPE_REQUIRED"}else{"EXECUTIVE_AUTH_REQUIRED"});
            }
        }
    }

    #[test]
    fn native_session_send_unknown_fields_or_foreign_route_never_dispatch() {
        for fixture in native_session_send_fixtures() {
            let state=native_executive_state(EXECUTIVE_SCOPE);
            for extra in ["principal_scope","url","work_ref","permission"] {
                let mut args=fixture["arguments"].clone();args[extra]="not an authority".into();let count=std::cell::Cell::new(0);
                let result=tauri::async_runtime::block_on(executive_post_with_dispatch(&state,crate::native_session_send::PATH,serde_json::json!({"arguments":args}),|_|{
                    count.set(count.get()+1);async{Ok(tauri::http::Response::builder().status(200).body("{}").unwrap().into())}
                }));assert_eq!(count.get(),0);assert_eq!(result.unwrap_err(),"REQUEST_INVALID");
            }
            let count=std::cell::Cell::new(0);
            let result=tauri::async_runtime::block_on(executive_post_with_dispatch(&state,"/os/executive/session/send/",serde_json::json!({"arguments":fixture["arguments"]}),|_|{
                count.set(count.get()+1);async{Ok(tauri::http::Response::builder().status(200).body("{}").unwrap().into())}
            }));assert_eq!(count.get(),0);assert_eq!(result.unwrap_err(),"REQUEST_INVALID");
        }
    }

    #[test]
    fn native_session_send_auth_change_after_one_dispatch_withholds_receipt_without_retry() {
        for fixture in native_session_send_fixtures() {
            let state=native_executive_state(EXECUTIVE_SCOPE);let count=std::cell::Cell::new(0);
            let result=tauri::async_runtime::block_on(executive_post_with_dispatch(&state,crate::native_session_send::PATH,crate::native_session_send::body(fixture["arguments"].clone()).unwrap(),|_|{
                count.set(count.get()+1);state.lock().unwrap().executive_generation+=1;
                let response:reqwest::Response=tauri::http::Response::builder().status(200).header("Content-Type","application/json").body(fixture["sent"].to_string()).unwrap().into();async{Ok(response)}
            }));assert_eq!(count.get(),1);assert_eq!(result.unwrap_err(),"EXECUTIVE_AUTH_CHANGED");
        }
    }

    #[test]
    fn native_e_only_fresh_recovery_keeps_workspace_effects_closed() {
        // Actual signed-source public replies, with only the private token
        // and HTTP dispatch replaced by the existing native test fixtures.
        let fixture: Value=serde_json::from_str(include_str!("../../src/auth-recovery/fixtures/native-executive-draft-owner.json")).unwrap();
        let state=native_executive_state(EXECUTIVE_SCOPE);
        {let mut inner=state.lock().unwrap();inner.acquisition=None;inner.content=None;}
        assert!(state.lock().unwrap().acquisition.is_none());
        let selected=serde_json::json!({"work_ref":fixture["request"]["work_ref"],"operation_key":fixture["request"]["operation_key"]});
        for (operation,arguments,reply) in [
            ("status",selected.clone(),fixture["status"].clone()),
            ("read",selected.clone(),fixture["read"].clone()),
            ("preview",fixture["request"].clone(),Value::Null),
            ("create",fixture["create_request"].clone(),Value::Null),
            ("consume",fixture["consume_request"].clone(),Value::Null),
        ] {
            let path=crate::fresh_conversation::path(operation).unwrap();
            let calls=std::cell::Cell::new(0);
            let result=tauri::async_runtime::block_on(executive_post_with_dispatch(&state,path,
                serde_json::json!({"arguments":arguments}),|builder|{
                    calls.set(calls.get()+1);let request=builder.build().unwrap();
                    assert_eq!(request.url().as_str(),format!("{ORIGIN}{path}"));
                    assert_eq!(request.headers()["authorization"],"Bearer fixture-native-executive");
                    assert!(!request.headers().contains_key("x-mastermind-workspace-authorization"));
                    let response:reqwest::Response=tauri::http::Response::builder().status(200)
                        .header("Content-Type","application/json").body(reply.to_string()).unwrap().into();
                    async {Ok(response)}
                }));
            if operation=="status" || operation=="read" {
                assert_eq!(calls.get(),1);assert!(result.is_ok());
            } else {
                assert_eq!(calls.get(),0);assert_eq!(result.unwrap_err(),"WORKSPACE_AUTH_REQUIRED");
            }
        }
    }

    #[test]
    fn project_planning_requires_both_private_resources_before_native_dispatch() {
        for workspace in [false,true] {
            let state=native_executive_state(EXECUTIVE_SCOPE);
            state.lock().unwrap().acquisition=if workspace {Some(token("fixture-workspace"))} else {None};
            let calls=std::cell::Cell::new(0);
            let result=tauri::async_runtime::block_on(executive_post_with_dispatch(&state,
                "/os/executive/project-planning/status",serde_json::json!({"arguments":{"operation_key":"original","work_ref":"WS:EXAMPLE"}}),|builder|{
                    calls.set(calls.get()+1);let request=builder.build().unwrap();
                    assert_eq!(request.url().as_str(),format!("{ORIGIN}/os/executive/project-planning/status"));
                    assert_eq!(request.headers()["x-mastermind-workspace-authorization"],"Bearer fixture-workspace");
                    assert_eq!(request.headers()["authorization"],"Bearer fixture-native-executive");
                    async {Ok(native_fixture_response())}
                }));
            assert_eq!(calls.get(),usize::from(workspace));assert_eq!(result.is_ok(),workspace);
        }
        let state=native_executive_state("mastermind.executive.read");
        state.lock().unwrap().acquisition=Some(token("fixture-workspace"));
        let calls=std::cell::Cell::new(0);
        let result=tauri::async_runtime::block_on(executive_post_with_dispatch(&state,
            "/os/executive/project-planning/status",serde_json::json!({"arguments":{"operation_key":"original","work_ref":"WS:EXAMPLE"}}),|_|{
                calls.set(calls.get()+1);async {Ok(native_fixture_response())}
            }));
        assert_eq!(calls.get(),0);assert!(result.is_err());
    }

    #[test]
    fn project_planning_secondary_resource_generation_and_expiry_fence_pending_native_response() {
        for change in ["generation","remove","expire"] {
            let state=native_executive_state(EXECUTIVE_SCOPE);
            state.lock().unwrap().acquisition=Some(token("fixture-workspace"));
            let result=tauri::async_runtime::block_on(executive_post_with_dispatch(&state,
                "/os/executive/project-planning/status",serde_json::json!({"arguments":{"operation_key":"original","work_ref":"WS:EXAMPLE"}}),|_|async{
                    {let mut inner=state.lock().unwrap();match change {
                        "generation"=>inner.generation+=1,"remove"=>inner.acquisition=None,
                        _=>inner.acquisition.as_mut().unwrap().wall_expires=SystemTime::UNIX_EPOCH,
                    }}
                    Ok(native_fixture_response())
                }));
            assert_eq!(result.unwrap_err(),"WORKSPACE_AUTH_CHANGED");
        }
    }

    #[test]
    fn native_direct_selection_is_closed_and_consumption_is_explicit() {
        let read = serde_json::json!({"work_ref":"WS:H2", "job_id":"JOB-1", "attempt_id":null});
        assert_eq!(direct_native_arguments(read.clone(), false).unwrap(), read);
        assert!(direct_native_arguments(read.clone(), true).is_err());
        let consume = serde_json::json!({"work_ref":"WS:H2", "job_id":"JOB-1", "attempt_id":"ATTEMPT-1",
            "result_digest":"a".repeat(64), "operation_key":"ack-original"});
        assert_eq!(direct_native_arguments(consume.clone(), true).unwrap(), consume);
        assert!(direct_native_arguments(consume.clone(), false).is_err());
        for (field, value) in [("job_id", serde_json::json!("../foreign")),
            ("work_ref", serde_json::json!("WS:H2\n")), ("attempt_id", Value::Null),
            ("result_digest", serde_json::json!("A".repeat(64))),
            ("operation_key", serde_json::json!("bad/key"))] {
            let mut changed = consume.clone(); changed[field] = value;
            assert!(direct_native_arguments(changed, true).is_err());
        }
        let mut injected = read; injected["operation"] = "consume".into();
        assert!(direct_native_arguments(injected, false).is_err());
    }

    #[test]
    fn native_direct_transport_preserves_flat_body_and_requires_send_for_consumption() {
        for (path, consume) in [("/os/executive/direct-native/result", false),
            ("/os/executive/direct-native/consume", true)] {
            for send in [false, true] {
                let state = native_executive_state(if send { EXECUTIVE_SCOPE } else { "mastermind.executive.read" });
                let mut body = serde_json::json!({"work_ref":"WS:H2", "job_id":"JOB-1", "attempt_id":"ATTEMPT-1"});
                if consume { body["result_digest"] = "a".repeat(64).into(); body["operation_key"] = "ack-original".into(); }
                let body = direct_native_arguments(body, consume).unwrap();
                let calls = std::cell::Cell::new(0);
                let result = tauri::async_runtime::block_on(executive_post_with_dispatch(&state, path,
                    body.clone(), |builder| {
                        calls.set(calls.get() + 1);
                        let request = builder.build().unwrap();
                        assert_eq!(request.url().as_str(), format!("{ORIGIN}{path}"));
                        assert_eq!(serde_json::from_slice::<Value>(request.body().unwrap().as_bytes().unwrap()).unwrap(), body);
                        assert_eq!(request.method(), reqwest::Method::POST);
                        async { Ok(native_fixture_response()) }
                    }));
                if consume && !send {
                    assert_eq!(calls.get(), 0);
                    assert_eq!(result.unwrap_err(), "EXECUTIVE_SEND_SCOPE_REQUIRED");
                } else { assert_eq!(calls.get(), 1); assert!(result.is_ok()); }
            }
        }
    }

    #[test]
    fn native_direct_typed_unavailable_is_bounded_and_schema_specific() {
        let state = native_executive_state("mastermind.executive.read");
        for (status, response, accepted) in [
            (503, serde_json::json!({"schema":"mastermind.direct_native_result_response.v1", "availability":"UNAVAILABLE"}), true),
            (503, serde_json::json!({"schema":"foreign", "availability":"UNAVAILABLE"}), false),
            (503, serde_json::json!({"schema":"mastermind.direct_native_result_response.v1", "availability":"AVAILABLE"}), false),
            (200, serde_json::json!({"oversized":"x".repeat(DIRECT_NATIVE_RESPONSE_CAP)}), false),
        ] {
            let result = tauri::async_runtime::block_on(executive_post_with_dispatch(&state,
                "/os/executive/direct-native/result", native_direct_request(false), |_| async {
                    Ok(tauri::http::Response::builder().status(status).header("Content-Type", "application/json")
                        .body(response.to_string()).unwrap().into())
                }));
            assert_eq!(result.is_ok(), accepted);
        }
    }

    #[test]
    fn native_direct_correction_inspect_cannot_smuggle_a_request() {
        let inspect = serde_json::json!({"operation":"inspect", "work_ref":"WS:H2",
            "job_id":"JOB-1", "attempt_id":null});
        assert!(direct_native_correction_arguments(inspect.clone()).is_ok());
        for (field, value) in [("fence_generation", serde_json::json!(1)),
            ("operation_key", serde_json::json!("cancel-original")), ("request", serde_json::json!(true))] {
            let mut changed = inspect.clone(); changed[field] = value;
            assert!(direct_native_correction_arguments(changed).is_err());
        }
        let request = serde_json::json!({"operation":"request", "work_ref":"WS:H2", "job_id":"JOB-1",
            "attempt_id":"ATTEMPT-1", "fence_generation":1, "operation_key":"cancel-original"});
        assert!(direct_native_correction_arguments(request.clone()).is_ok());
        for (field, value) in [("fence_generation", serde_json::json!(0)),
            ("fence_generation", serde_json::json!(1.5)), ("attempt_id", Value::Null),
            ("operation", serde_json::json!("consume")), ("operation_key", serde_json::json!("../foreign"))] {
            let mut changed = request.clone(); changed[field] = value;
            assert!(direct_native_correction_arguments(changed).is_err());
        }
    }

    #[test]
    fn native_direct_correction_actual_scope_gate_preserves_unknown_without_retry() {
        for operation in ["inspect", "request"] {
            for send in [false, true] {
                let state = native_executive_state(if send { EXECUTIVE_SCOPE } else { "mastermind.executive.read" });
                let mut body = serde_json::json!({"operation":operation,"work_ref":"WS:H2",
                    "job_id":"JOB-1","attempt_id":"ATTEMPT-1"});
                if operation == "request" { body["fence_generation"] = 1.into(); body["operation_key"] = "cancel-original".into(); }
                let calls = std::cell::Cell::new(0);
                let result = tauri::async_runtime::block_on(executive_post_with_dispatch(&state,
                    "/os/executive/direct-native/correction", body.clone(), |builder| {
                        calls.set(calls.get() + 1);
                        let request = builder.build().unwrap();
                        assert_eq!(serde_json::from_slice::<Value>(request.body().unwrap().as_bytes().unwrap()).unwrap(), body);
                        async { Ok(tauri::http::Response::builder().status(202).header("Content-Type", "application/json")
                            .body(r#"{"error":{"code":"effect_unknown"}}"#.to_owned()).unwrap().into()) }
                    }));
                if operation == "request" && !send {
                    assert_eq!(calls.get(), 0); assert_eq!(result.unwrap_err(), "EXECUTIVE_SEND_SCOPE_REQUIRED");
                } else {
                    assert_eq!(calls.get(), 1);
                    assert_eq!(result.unwrap(), serde_json::json!({"error":{"code":"effect_unknown"}}));
                }
            }
        }
    }

    fn native_direct_request(consume: bool) -> Value {
        let mut body = serde_json::json!({
            "work_ref": "WS:NATIVE-H2", "job_id": "JOB-original", "attempt_id": "ATT-original",
        });
        if consume {
            body["result_digest"] = Value::String("d".repeat(64));
            body["operation_key"] = Value::String("mmos-consume-original".into());
        }
        body
    }

    #[test]
    fn native_direct_result_closed_selectors_refuse_before_dispatch() {
        let state = native_executive_state(EXECUTIVE_SCOPE);
        for consume in [false, true] {
            let path = if consume { "/os/executive/direct-native/consume" } else { "/os/executive/direct-native/result" };
            let mut bad = vec![Value::Null, serde_json::json!({})];
            for (key, value) in [
                ("job_id", serde_json::json!("JOB-original/other")),
                ("attempt_id", serde_json::json!(42)),
                ("work_ref", serde_json::json!("WS:NATIVE-H2\n")),
                ("work_ref", serde_json::json!("x".repeat(513))),
                ("resource", serde_json::json!("https://caller.invalid")),
            ] {
                let mut body = native_direct_request(consume);
                body[key] = value;
                bad.push(body);
            }
            if consume {
                for (key, value) in [
                    ("attempt_id", Value::Null),
                    ("result_digest", Value::String("A".repeat(64))),
                    ("operation_key", Value::String("caller/path".into())),
                ] {
                    let mut body = native_direct_request(true);
                    body[key] = value;
                    bad.push(body);
                }
            }
            for body in bad {
                let calls = std::cell::Cell::new(0);
                let result = tauri::async_runtime::block_on(executive_post_with_dispatch(
                    &state, path, body, |_| {
                        calls.set(calls.get() + 1);
                        std::future::ready(Ok(native_fixture_response()))
                    }));
                assert_eq!(result.unwrap_err(), "DIRECT_SELECTION_INVALID");
                assert_eq!(calls.get(), 0);
            }
        }
    }

    #[test]
    fn native_direct_result_and_consume_keep_exact_grant_and_fixed_request() {
        for scope in ["mastermind.executive.read", EXECUTIVE_SCOPE] {
            for consume in [false, true] {
                let state = native_executive_state(scope);
                let path = if consume { "/os/executive/direct-native/consume" } else { "/os/executive/direct-native/result" };
                let mut body = native_direct_request(consume);
                if !consume { body["attempt_id"] = Value::Null; }
                let calls = std::cell::Cell::new(0);
                let expected = body.clone();
                let result = tauri::async_runtime::block_on(executive_post_with_dispatch(
                    &state, path, body, |builder| {
                        calls.set(calls.get() + 1);
                        let request = builder.build().unwrap();
                        assert_eq!(request.method(), reqwest::Method::POST);
                        assert_eq!(request.url().as_str(), format!("{ORIGIN}{path}"));
                        assert_eq!(request.headers()["authorization"], "Bearer fixture-native-executive");
                        assert_eq!(serde_json::from_slice::<Value>(request.body().unwrap().as_bytes().unwrap()).unwrap(), expected);
                        assert!(request.timeout().is_none(), "direct reads/consumes inherited the research foreground deadline");
                        std::future::ready(Ok(native_fixture_response()))
                    }));
                if consume && scope != EXECUTIVE_SCOPE {
                    assert_eq!(calls.get(), 0);
                    assert_eq!(result.unwrap_err(), "EXECUTIVE_SEND_SCOPE_REQUIRED");
                } else {
                    assert_eq!(calls.get(), 1);
                    assert!(result.is_ok());
                }
            }
        }
    }

    #[test]
    fn native_direct_result_and_consume_cancel_old_generation_without_replay() {
        use std::sync::{Arc, atomic::{AtomicBool, Ordering}};
        struct PendingDrop(Arc<AtomicBool>);
        impl Drop for PendingDrop {
            fn drop(&mut self) { self.0.store(true, Ordering::SeqCst); }
        }
        for consume in [false, true] {
            let state = native_executive_state(EXECUTIVE_SCOPE);
            let path = if consume { "/os/executive/direct-native/consume" } else { "/os/executive/direct-native/result" };
            let calls = std::cell::Cell::new(0);
            let dropped = Arc::new(AtomicBool::new(false));
            let sentinel = PendingDrop(dropped.clone());
            let result = tauri::async_runtime::block_on(executive_post_with_dispatch(
                &state, path, native_direct_request(consume), |_| async {
                    calls.set(calls.get() + 1);
                    let _pending = sentinel;
                    state.lock().unwrap().clear_executive();
                    std::future::pending::<std::result::Result<reqwest::Response, reqwest::Error>>().await
                }));
            assert_eq!(result.unwrap_err(), "EXECUTIVE_AUTH_CHANGED");
            assert_eq!(calls.get(), 1);
            assert!(dropped.load(Ordering::SeqCst));
        }
    }

    #[test]
    fn native_direct_correction_drops_pending_http_on_drift_or_expiry_without_replay() {
        use std::sync::{Arc, atomic::{AtomicBool, Ordering}};
        struct PendingDrop(Arc<AtomicBool>);
        impl Drop for PendingDrop {
            fn drop(&mut self) { self.0.store(true, Ordering::SeqCst); }
        }
        for operation in ["inspect", "request"] {
            for expiry in [false, true] {
                let state = native_executive_state(EXECUTIVE_SCOPE);
                let mut body = native_direct_request(false);
                body["operation"] = serde_json::json!(operation);
                if operation == "request" {
                    body["fence_generation"] = serde_json::json!(1);
                    body["operation_key"] = serde_json::json!("original-correction");
                }
                let calls = std::cell::Cell::new(0);
                let dropped = Arc::new(AtomicBool::new(false));
                let sentinel = PendingDrop(dropped.clone());
                let result = tauri::async_runtime::block_on(async {
                    if expiry {
                        state.lock().unwrap().executive.as_mut().unwrap().expires =
                            Instant::now() + Duration::from_millis(20);
                    }
                    executive_post_with_dispatch(&state, "/os/executive/direct-native/correction", body, |_| async {
                        calls.set(calls.get() + 1);
                        let _pending = sentinel;
                        if !expiry { state.lock().unwrap().clear_executive(); }
                        std::future::pending::<std::result::Result<reqwest::Response, reqwest::Error>>().await
                    }).await
                });
                assert_eq!(result.unwrap_err(), "EXECUTIVE_AUTH_CHANGED");
                assert_eq!(calls.get(), 1);
                assert!(dropped.load(Ordering::SeqCst), "pending correction HTTP survived auth boundary");
            }
        }
    }

    #[test]
    fn native_direct_result_and_consume_missing_or_expired_grant_never_dispatch() {
        for consume in [false, true] {
            for expired in [false, true] {
                let state = native_executive_state(EXECUTIVE_SCOPE);
                {
                    let mut inner = state.lock().unwrap();
                    if expired { inner.executive.as_mut().unwrap().expires = Instant::now() - Duration::from_secs(1); }
                    else { inner.executive = None; }
                }
                let path = if consume { "/os/executive/direct-native/consume" } else { "/os/executive/direct-native/result" };
                let calls = std::cell::Cell::new(0);
                let result = tauri::async_runtime::block_on(executive_post_with_dispatch(
                    &state, path, native_direct_request(consume), |_| {
                        calls.set(calls.get() + 1);
                        std::future::ready(Ok(native_fixture_response()))
                    }));
                assert_eq!(result.unwrap_err(), "EXECUTIVE_AUTH_REQUIRED");
                assert_eq!(calls.get(), 0);
            }
        }
    }

    #[test]
    fn native_direct_result_response_budget_is_bounded_before_webview_release() {
        for consume in [false, true] {
            let state = native_executive_state(EXECUTIVE_SCOPE);
            let path = if consume { "/os/executive/direct-native/consume" } else { "/os/executive/direct-native/result" };
            let result = tauri::async_runtime::block_on(executive_post_with_dispatch(
                &state, path, native_direct_request(consume), |_| {
                    let response = tauri::http::Response::builder().status(200)
                        .header("Content-Type", "application/json")
                        .body(serde_json::to_string(&serde_json::json!({"oversized": "x".repeat(DIRECT_NATIVE_RESPONSE_CAP)})).unwrap())
                        .unwrap().into();
                    std::future::ready(Ok(response))
                }));
            assert_eq!(result.unwrap_err(), "RESPONSE_BOUND");
        }
    }

    fn native_post_spy(state: &NativeAuth, path: &'static str) -> (Result<Value>, usize) {
        let calls = std::cell::Cell::new(0);
        let result = tauri::async_runtime::block_on(executive_post_with_dispatch(
            state, path, serde_json::json!({"arguments": {}}), |builder| {
                calls.set(calls.get() + 1);
                let request = builder.build().unwrap();
                assert_eq!(request.method(), reqwest::Method::POST);
                assert_eq!(request.url().as_str(), format!("{ORIGIN}{path}"));
                std::future::ready(Ok(native_fixture_response()))
            },
        ));
        (result, calls.get())
    }

    #[test]
    fn native_research_foreground_deadline_does_not_change_other_submits() {
        for profile in ["research_only", "native_research_only", "bounded_code_change"] {
            let state = native_executive_state(EXECUTIVE_SCOPE);
            let result = tauri::async_runtime::block_on(executive_post_with_dispatch(
                &state, "/os/executive/submit",
                serde_json::json!({"arguments":{"execution_profile":profile}}), |builder| {
                    let request = builder.build().unwrap();
                    assert_eq!(request.timeout().copied(),
                        if profile == "research_only" { Some(EXECUTIVE_FOREGROUND_TIMEOUT) } else { None });
                    std::future::ready(Ok(native_fixture_response()))
                }));
            assert!(result.is_ok());
        }
    }

    #[test]
    fn native_research_foreground_drops_pending_transport_on_auth_change() {
        use std::sync::{Arc, atomic::{AtomicBool, Ordering}};
        struct PendingDrop(Arc<AtomicBool>);
        impl Drop for PendingDrop {
            fn drop(&mut self) { self.0.store(true, Ordering::SeqCst); }
        }
        let state = native_executive_state(EXECUTIVE_SCOPE);
        let dropped = Arc::new(AtomicBool::new(false));
        let sentinel = PendingDrop(dropped.clone());
        let result = tauri::async_runtime::block_on(executive_post_with_dispatch(
            &state, "/os/executive/submit",
            serde_json::json!({"arguments":{"execution_profile":"research_only"}}), |_| async {
                let _pending = sentinel;
                state.lock().unwrap().clear_executive();
                std::future::pending::<std::result::Result<reqwest::Response, reqwest::Error>>().await
            }));
        assert_eq!(result.unwrap_err(), "EXECUTIVE_AUTH_CHANGED");
        assert!(dropped.load(Ordering::SeqCst), "pending HTTP owner survived auth invalidation");
    }

    #[test]
    fn native_research_foreground_ends_at_original_token_expiry() {
        let state = native_executive_state(EXECUTIVE_SCOPE);
        let dispatched = std::cell::Cell::new(false);
        let result = tauri::async_runtime::block_on(async {
            // Start the short-lived token inside the running owner, rather
            // than spending its lifetime initializing the async runtime.
            state.lock().unwrap().executive.as_mut().unwrap().expires =
                Instant::now() + Duration::from_millis(20);
            executive_post_with_dispatch(&state, "/os/executive/submit",
                serde_json::json!({"arguments":{"execution_profile":"research_only"}}), |_| {
                    dispatched.set(true);
                    std::future::pending::<std::result::Result<reqwest::Response, reqwest::Error>>()
                }).await
        });
        assert!(dispatched.get(), "token expired before the foreground dispatch began");
        assert_eq!(result.unwrap_err(), "EXECUTIVE_AUTH_CHANGED");
    }

    #[test]
    fn native_executive_read_only_submit_never_dispatches() {
        let state = native_executive_state("mastermind.executive.read");
        assert!(state.lock().unwrap().executive_status().available);
        let (result, calls) = native_post_spy(&state, "/os/executive/submit");
        assert_eq!(calls, 0, "READ-only token reached the transport dispatcher");
        assert_eq!(result.unwrap_err(), "EXECUTIVE_SEND_SCOPE_REQUIRED");
    }

    #[test]
    fn native_executive_read_only_observation_routes_dispatch() {
        for path in [
            "/os/executive/context",
            "/os/executive/status",
            "/os/executive/session/context",
            "/os/executive/session/reply",
            "/os/executive/session/references",
        ] {
            let state = native_executive_state("mastermind.executive.read");
            let (result, calls) = native_post_spy(&state, path);
            assert_eq!(calls, 1);
            assert_eq!(result.unwrap(), serde_json::json!({"fixture":"native-dispatch"}));
        }
    }

    #[test]
    fn native_executive_exact_combined_grants_dispatch_submit() {
        for scope in [EXECUTIVE_SCOPE, "mastermind.executive.intent.submit mastermind.executive.read"] {
            let state = native_executive_state(scope);
            let (result, calls) = native_post_spy(&state, "/os/executive/submit");
            assert_eq!(calls, 1);
            assert_eq!(result.unwrap(), serde_json::json!({"fixture":"native-dispatch"}));
        }
    }

    #[test]
    fn native_executive_downgrade_does_not_keep_send_permission() {
        let state = native_executive_state(EXECUTIVE_SCOPE);
        assert_eq!(native_post_spy(&state, "/os/executive/submit").1, 1);
        {
            let mut inner = state.lock().unwrap();
            inner.transaction(Resource::Executive).unwrap();
            install_native_executive_token(&mut inner, "mastermind.executive.read");
        }
        let (result, calls) = native_post_spy(&state, "/os/executive/submit");
        assert_eq!(calls, 0, "new READ-only token inherited old SEND permission");
        assert_eq!(result.unwrap_err(), "EXECUTIVE_SEND_SCOPE_REQUIRED");
        assert_eq!(native_post_spy(&state, "/os/executive/context").1, 1);
    }

    #[test]
    fn native_executive_missing_or_expired_token_never_dispatches() {
        for expired in [false, true] {
            let state = native_executive_state(EXECUTIVE_SCOPE);
            {
                let mut inner = state.lock().unwrap();
                if expired {
                    inner.executive.as_mut().unwrap().expires = Instant::now() - Duration::from_secs(1);
                } else {
                    inner.executive = None;
                }
            }
            let (result, calls) = native_post_spy(&state, "/os/executive/submit");
            assert_eq!(calls, 0);
            assert_eq!(result.unwrap_err(), "EXECUTIVE_AUTH_REQUIRED");
        }
    }

    #[test]
    fn native_executive_unknown_route_never_dispatches() {
        for scope in [EXECUTIVE_SCOPE, "mastermind.executive.read"] {
            for path in ["/os/executive/not-enrolled", "/os/executive/session/send"] {
                let state = native_executive_state(scope);
                let (result, calls) = native_post_spy(&state, path);
                assert_eq!(calls, 0);
                assert_eq!(result.unwrap_err(), "REQUEST_INVALID");
            }
        }
    }

    #[test]
    fn native_executive_signout_or_token_rotation_withholds_in_flight_reply() {
        for signout in [false, true] {
            let state = native_executive_state(EXECUTIVE_SCOPE);
            let calls = std::cell::Cell::new(0);
            let result = tauri::async_runtime::block_on(executive_post_with_dispatch(
                &state, "/os/executive/submit", serde_json::json!({"arguments":{}}), |_| {
                    calls.set(calls.get() + 1);
                    let mut inner = state.lock().unwrap();
                    if signout {
                        inner.invalidate();
                    } else {
                        inner.transaction(Resource::Executive).unwrap();
                        install_native_executive_token(&mut inner, "mastermind.executive.read");
                    }
                    std::future::ready(Ok(native_fixture_response()))
                },
            ));
            assert_eq!(calls.get(), 1);
            assert_eq!(result.unwrap_err(), "EXECUTIVE_AUTH_CHANGED");
        }
    }

}

#[cfg(test)]
mod fabric_read_selection_tests {
    use super::*;

    #[test]
    fn catalog_and_status_have_fixed_origin_routes_and_byte_limits() {
        let (catalog, schema, cap) = fabric_read_target(None).unwrap();
        assert_eq!(catalog.as_str(), "https://mcp.mastermind-x.com/workspace/fabric/catalog/current");
        assert_eq!(schema, "mastermind.attended_fabric_catalog.v1");
        assert_eq!(cap, 65_536);
        assert!(catalog.query().is_none());
        let selected = FabricStatusSelection { root_id: "JOB-42".into(),
            run_id: format!("ATT-{}", "a".repeat(32)) };
        let (status, schema, cap) = fabric_read_target(Some(&selected)).unwrap();
        assert_eq!(status.origin().ascii_serialization(), "https://mcp.mastermind-x.com");
        assert_eq!(status.path(), "/workspace/fabric/status/current");
        assert_eq!(schema, "mastermind.fabric_task_status.v1");
        assert_eq!(cap, 16_384);
        assert_eq!(status.query_pairs().into_owned().collect::<Vec<_>>(), vec![
            ("root_id".to_string(), selected.root_id), ("run_id".to_string(), selected.run_id),
        ]);
    }

    #[test]
    fn paid_selector_rejects_foreign_namespaces_paths_and_aliases() {
        for root in ["ROOT:manual", "../JOB-1", "JOB-", "JOB--1", "JOB-1234567890",
                     "https://example.invalid/root", "JOB-1&run_id=foreign"] {
            assert!(fabric_read_target(Some(&FabricStatusSelection { root_id: root.into(),
                run_id: format!("ATT-{}", "a".repeat(32)) })).is_err());
        }
        for run in ["ATT-1", "../foreign", "att-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                    "ATT-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA", "run&root_id=foreign"] {
            assert!(fabric_read_target(Some(&FabricStatusSelection { root_id: "JOB-1".into(),
                run_id: run.into() })).is_err());
        }
    }

    #[test]
    fn selector_accepts_only_the_two_typed_fields() {
        let valid = serde_json::json!({"root_id":"JOB-1", "run_id":format!("ATT-{}", "a".repeat(32))});
        assert!(serde_json::from_value::<FabricStatusSelection>(valid.clone()).unwrap().validate().is_ok());
        let mut extra = valid.clone();
        extra["owner_path"] = serde_json::json!("/private/foreign");
        assert!(serde_json::from_value::<FabricStatusSelection>(extra).is_err());
        let mut mistyped = valid;
        mistyped["run_id"] = serde_json::json!(3);
        assert!(serde_json::from_value::<FabricStatusSelection>(mistyped).is_err());
    }
}

#[cfg(test)]
mod retained_activity_selection_tests {
    use super::*;

    fn selection() -> RetainedActivitySelection {
        RetainedActivitySelection {
            work_ref: "WS:ORIGINAL".into(),
            root_job_id: "JOB-123".into(),
            job_id: "JOB-124".into(),
            attempt_id: format!("ATT-{}", "a".repeat(32)),
        }
    }

    #[test]
    fn accepts_only_exact_original_executor_selection() {
        assert!(selection().validate().is_ok());
        let mut invalid = selection();
        invalid.job_id = invalid.root_job_id.clone();
        assert!(invalid.validate().is_err());
        let mut invalid = selection();
        invalid.attempt_id = format!("ATT-{}", "A".repeat(32));
        assert!(invalid.validate().is_err());
        let mut invalid = selection();
        invalid.attempt_id = "ATT-123".into();
        assert!(invalid.validate().is_err());
        let mut invalid = selection();
        invalid.work_ref = "WS:foreign!".into();
        assert!(invalid.validate().is_err());
        let mut invalid = selection();
        invalid.job_id = "JOB-123/../private".into();
        assert!(invalid.validate().is_err());
    }
    #[test]
    fn retained_activity_never_reuses_executive_or_native_fabric_resource() {
        assert_eq!(Resource::Acquisition.audience(), "https://mcp.mastermind-x.com/workspace/read");
        assert_eq!(Resource::Acquisition.scope(), "mastermind.workspace.read");
        assert_eq!(RETAINED_ACTIVITY_PATH, "/workspace/operator/activity/current");
        assert_eq!(RETAINED_ACTIVITY_SCHEMA, "mastermind.workspace_retained_activity.v1");
        assert_eq!(RETAINED_ACTIVITY_CAP, PLAN_RESPONSE_CAP);
    }
    #[test]
    fn native_idle_refresh_timer_enters_renewal_window() {
        let now = Instant::now();
        let expires = now + Duration::from_secs(3600);
        let at = native_refresh_deadline(expires, now);
        assert_eq!(expires.duration_since(at), Duration::from_secs(35));
        assert!(expires.duration_since(at) < Duration::from_secs(45));
        assert_eq!(native_refresh_deadline(now + Duration::from_secs(3), now),
            now + Duration::from_secs(10));
    }

    #[test]
    fn auth0_revocation_terminal_status_is_exactly_scoped() {
        let invalid = serde_json::json!({"error": "invalid_grant"});
        for status in [400, 401, 403] {
            assert!(terminal_invalid_grant(status, &invalid));
        }
        for status in [200, 404, 408, 409, 429, 500, 502, 503] {
            assert!(!terminal_invalid_grant(status, &invalid));
        }
        for error in ["temporarily_unavailable", "invalid_client", "login_required"] {
            assert!(!terminal_invalid_grant(403, &serde_json::json!({"error": error})));
        }
        assert!(!terminal_invalid_grant(403, &serde_json::json!({})));
        assert!(!terminal_invalid_grant(403, &serde_json::json!({"error": null})));
        assert!(!terminal_invalid_grant(403, &serde_json::json!(["invalid_grant"])));
        // Malformed or ambiguous bodies on the statuses refresh_one actually
        // observes stay non-terminal: the grant and its marker remain held
        // for the ambiguous-replay fence instead of any cleanup path.
        for status in [400, 401] {
            assert!(!terminal_invalid_grant(status, &serde_json::json!({})));
            assert!(!terminal_invalid_grant(status, &serde_json::json!({"error": null})));
            assert!(!terminal_invalid_grant(status, &serde_json::json!(["invalid_grant"])));
            assert!(!terminal_invalid_grant(status,
                &serde_json::json!({"error": "temporarily_unavailable"})));
        }
    }

    #[test]
    fn native_offline_scope_is_workspace_only_and_build_gated() {
        let url = authorization_url("public-client", Resource::Acquisition, "state", "verifier");
        let parsed = Url::parse(&url).unwrap();
        let scope = parsed.query_pairs().find(|(key, _)| key == "scope").unwrap().1.to_string();
        assert_eq!(scope.contains("offline_access"), crate::native_refresh::enabled());
        let executive = authorization_url_for_audience(
            "public-client", Resource::Executive,
            "https://mcp.mastermind-x.com/os/executive", "state", "verifier",
        );
        let exec_scope = Url::parse(&executive).unwrap().query_pairs()
            .find(|(key, _)| key == "scope").unwrap().1.to_string();
        assert_eq!(exec_scope, EXECUTIVE_SCOPE);
        assert!(!exec_scope.contains("offline_access"));
    }

    #[test]
    fn restoring_is_cancelled_by_generation_changing_logout() {
        let mut inner = Inner::new(Some("native-client"));
        inner.restoring = true;
        assert_eq!(inner.status().status, "signing_in");
        inner.invalidate();
        assert!(!inner.restoring);
        assert_eq!(inner.status().status, "signed_out");
    }

    #[test]
    fn unapproved_offline_scope_never_becomes_an_api_permission() {
        let scopes = if crate::native_refresh::enabled() {
            "offline_access mastermind.workspace.read"
        } else { "mastermind.workspace.read" };
        assert!(parse_token(serde_json::json!({
            "access_token":"a-valid-synthetic-access-token","expires_in":3600,
            "token_type":"Bearer","scope":scopes
        }), Resource::Acquisition).is_ok());
        assert!(parse_token(serde_json::json!({
            "access_token":"a-valid-synthetic-access-token","expires_in":3600,
            "token_type":"Bearer","scope":"mastermind.workspace.read mastermind.executive.intent.submit"
        }), Resource::Acquisition).is_err());
        assert!(parse_token(serde_json::json!({
            "access_token":"a-valid-synthetic-access-token","expires_in":3600,
            "token_type":"Bearer","scope":"mastermind.executive.read offline_access"
        }), Resource::Executive).is_err());
    }
}

#[cfg(test)]
mod resource_capacity_read_tests {
    use super::*;
    fn selection() -> RetainedActivitySelection {
        RetainedActivitySelection { work_ref: "WS:ONE".into(), root_job_id: "JOB-1".into(), job_id: "JOB-2".into(), attempt_id: format!("ATT-{}", "a".repeat(32)) }
    }
    #[test]
    fn resource_capacity_read_is_only_fixed_historical_acquisition() {
        assert!(selection().validate().is_ok());
        assert_eq!(RESOURCE_CAPACITY_PATH, "/workspace/resources/capacity/current");
        assert_eq!(RESOURCE_CAPACITY_SCHEMA, "mastermind.workspace_resource_capacity_result.v1");
        assert_eq!(RESOURCE_CAPACITY_CAP, 16_384);
    }
    #[test]
    fn resource_capacity_read_rejects_unknown_host_clock_and_path_fields() {
        for key in ["host_ref", "clock", "path"] {
            let mut value = serde_json::json!({"work_ref":"WS:ONE","root_job_id":"JOB-1","job_id":"JOB-2","attempt_id":format!("ATT-{}","a".repeat(32))});
            value[key] = Value::String("supplied".into());
            assert!(serde_json::from_value::<RetainedActivitySelection>(value).is_err());
        }
    }
    #[test]
    fn resource_capacity_read_requires_a_distinct_job_and_exact_attempt() {
        let mut value=selection(); value.job_id=value.root_job_id.clone(); assert!(value.validate().is_err());
        let mut value=selection(); value.attempt_id="../private".into(); assert!(value.validate().is_err());
    }
}

#[cfg(test)]
mod project_session_read_tests {
    use super::*;
    #[test]
    fn project_session_read_uses_only_fixed_pair_and_acquisition_body() {
        let selection = MissionSelection { work_ref: "WS:TEST-PROJECT".into(), root_job_id: "JOB-123".into() };
        let url = project_session_target(&selection).unwrap();
        assert_eq!(url.path(), "/workspace/project-session/current");
        assert_eq!(url.query_pairs().map(|(key, value)| (key.into_owned(), value.into_owned())).collect::<Vec<_>>(), vec![("work_ref".to_string(), "WS:TEST-PROJECT".to_string()), ("root_job_id".to_string(), "JOB-123".to_string())]);
        assert_eq!(PROJECT_SESSION_SCHEMA, "mastermind.workspace_project_session_association.v1");
        assert_eq!(PROJECT_SESSION_RESPONSE_CAP, 16_384);
    }
    #[test]
    fn project_session_read_refuses_caller_session_or_noncanonical_root_selectors() {
        let extra = serde_json::json!({"work_ref":"WS:TEST","root_job_id":"JOB-1","provider_session_id":"client"});
        assert!(serde_json::from_value::<MissionSelection>(extra).is_err());
        for (work,root) in [("WS:lower", "JOB-1"), ("WS:--TEST", "JOB-1"), ("WS:TEST", "JOB-private"), ("WS:TEST", "JOB-1234567890")] {
            assert!(project_session_target(&MissionSelection { work_ref: work.into(), root_job_id: root.into() }).is_err());
        }
    }
}

#[cfg(test)]
mod project_direction_read_tests {
    use super::*;

    #[test]
    fn project_direction_is_one_fixed_rootless_read_target() {
        let selected = ProjectPlanSelection { work_ref: "WS:DIRECTION-TEST".into() };
        let url = project_direction_target(&selected).unwrap();
        assert_eq!(url.origin().ascii_serialization(), ORIGIN);
        assert_eq!(url.path(), "/workspace/project-direction/current");
        assert_eq!(url.query_pairs().map(|(k, v)| (k.into_owned(), v.into_owned())).collect::<Vec<_>>(),
            vec![("work_ref".to_owned(), "WS:DIRECTION-TEST".to_owned())]);
        assert_eq!(PROJECT_DIRECTION_RESPONSE_CAP, 65_536);
    }

    #[test]
    fn project_direction_refuses_paths_foreign_roots_and_extra_selectors() {
        for work in ["../private", "WS:lower", "WS:AA/BB", "JOB-1", "WS:A", "WS:AA--BB"] {
            assert!(project_direction_target(&ProjectPlanSelection { work_ref: work.into() }).is_err());
        }
        for extra in ["path", "root_job_id", "commit", "history_revision"] {
            let mut raw = serde_json::json!({"work_ref": "WS:DIRECTION-TEST"});
            raw[extra] = serde_json::json!("caller-selected");
            assert!(serde_json::from_value::<ProjectPlanSelection>(raw).is_err());
        }
    }

    #[test]
    fn project_direction_response_header_stays_bound_to_exact_scope_and_schema() {
        let selected = ProjectPlanSelection { work_ref: "WS:DIRECTION-TEST".into() };
        assert!(project_direction_header_matches(&serde_json::json!({"schema": PROJECT_DIRECTION_SCHEMA,
            "selection": {"work_ref": "WS:DIRECTION-TEST"}}), &selected));
        assert!(!project_direction_header_matches(&serde_json::json!({"schema": PROJECT_PLAN_SCHEMA,
            "selection": {"work_ref": "WS:DIRECTION-TEST"}}), &selected));
        assert!(!project_direction_header_matches(&serde_json::json!({"schema": PROJECT_DIRECTION_SCHEMA,
            "selection": {"work_ref": "WS:OTHER"}}), &selected));
    }
}

#[cfg(test)]
mod project_archive_read_tests {
    use super::*;
    #[test]
    fn project_archive_has_only_one_fixed_rootless_acquisition_target() {
        let target = project_archive_target().unwrap();
        assert_eq!(target.origin().ascii_serialization(), ORIGIN);
        assert_eq!(target.path(), "/workspace/projects/archive/current");
        assert!(target.query().is_none());
        assert_eq!(PROJECT_ARCHIVE_RESPONSE_CAP, 262_144);
        assert_eq!(PROJECT_ARCHIVE_SCHEMA, "mastermind.workspace_project_archive.v1");
    }
    #[test]
    fn project_archive_continuation_has_only_fixed_member_and_digest_selectors() {
        let cursor = ProjectArchiveCursor { after_work_ref: "WS:PAGE-127".into(), catalogue_digest: "a".repeat(64) };
        let target = project_archive_page_target(&cursor).unwrap();
        assert_eq!(target.origin().ascii_serialization(), ORIGIN);
        assert_eq!(target.path(), PROJECT_ARCHIVE_PATH);
        assert_eq!(target.query_pairs().map(|(k, v)| (k.into_owned(), v.into_owned())).collect::<Vec<_>>(),
            vec![("after_work_ref".to_owned(), "WS:PAGE-127".to_owned()), ("catalogue_digest".to_owned(), "a".repeat(64))]);
        let extra = serde_json::json!({"after_work_ref":"WS:PAGE-127","catalogue_digest":"a".repeat(64),"root_job_id":"JOB-1"});
        assert!(serde_json::from_value::<ProjectArchiveCursor>(extra).is_err());
        assert!(project_archive_page_target(&ProjectArchiveCursor { after_work_ref: "../private".into(), catalogue_digest: "a".repeat(64) }).is_err());
        assert!(project_archive_page_target(&ProjectArchiveCursor { after_work_ref: "WS:PAGE-127".into(), catalogue_digest: "A".repeat(64) }).is_err());
    }
}

#[cfg(test)]
mod source_operation_transport_tests {
    use super::*;
    fn correction_owner_fixture() -> Value {
        serde_json::from_str(include_str!("../../src/fixtures/discovery-correction-owner.json")).unwrap()
    }
    #[test]
    fn discovery_correction_keeps_eight_field_lookup_and_fixed_routes() {
        let fixture=correction_owner_fixture();let lookup=&fixture["lookup"];
        let url=source_operation_target("read",lookup).unwrap();
        assert_eq!(url.path(),"/workspace/source-operation/operation");
        let pairs:std::collections::HashMap<_,_>=url.query_pairs().into_owned().collect();
        assert_eq!(pairs.len(),8);assert!(!pairs.contains_key("expected_preference_revision"));
        assert_eq!(pairs["discovery_ref"],"DSC:ORIGINAL-FINDING");
        assert_eq!(pairs["expected_discovery_revision"],lookup["expected_discovery_revision"].as_str().unwrap());
        assert_eq!(source_operation_target("reconcile",lookup).unwrap().path(),"/workspace/source-operation/reconcile");
        assert!(source_operation_target("advance",lookup).is_err());
        let prepare=serde_json::json!({"action":"correct_project_discovery","request":fixture["request"]});
        assert!(source_operation_target("prepare",&prepare).is_ok());
        assert_eq!(source_operation_body(fixture["preview"].clone(),"prepare",&prepare).unwrap(),fixture["preview"]);
        assert_eq!(source_operation_body(fixture["source_status"].clone(),"read",lookup).unwrap(),fixture["source_status"]);
    }
    #[test]
    fn discovery_correction_refuses_authority_grafts_and_invalid_evidence() {
        let fixture=correction_owner_fixture();
        for (field,value) in [("expected_preference_revision",Value::Null),("principal_scope",serde_json::json!("f".repeat(64))),
            ("discovery_ref",serde_json::json!("DSC:ORIGINAL-FINDING\n")),
            ("request_id",serde_json::json!(format!("mmos-project-file-add-{}","a".repeat(40))))] {
            let mut lookup=fixture["lookup"].clone();lookup[field]=value;
            assert!(source_operation_target("read",&lookup).is_err(),"{field}");
            assert!(source_operation_target("reconcile",&lookup).is_err(),"{field}");
        }
        for (field,value) in [("verified_at",serde_json::json!("2026-02-29")),("expires",serde_json::json!("2026-11-04")),
            ("confidence",serde_json::json!("")),("claim",serde_json::json!("中".repeat(683))),
            ("evidence",serde_json::json!(["same","same"])),("auto_verify",serde_json::json!(true))] {
            let mut request=fixture["request"].clone();request["replacement"][field]=value;
            assert!(source_operation_target("prepare",&serde_json::json!({"action":"correct_project_discovery","request":request})).is_err(),"{field}");
        }
    }
    fn lookup() -> Value {
        serde_json::json!({"schema":"mastermind.workspace_source_operation_lookup.v1","action":"ADOPT_PLAN","request_id":format!("mmos-project-adopt-{}","a".repeat(40)),"work_ref":"WS:TEST"})
    }
    #[test]
    fn file_prepare_uses_actual_utf8_serializer_with_decoded_content_limit() {
        for unit in ["\"", "\\", "\r", "\n", "\t", "中文😀", "\"\\\r\n\t中文😀"] {
            let content = unit.repeat(32_768 / unit.len()) + &"x".repeat(32_768 % unit.len());
            let mut body = serde_json::json!({"action":"add_project_file","request":{
                "schema":"mastermind.project_file_add_request.v1","request_id":format!("mmos-project-file-add-{}","a".repeat(40)),
                "work_ref":format!("WS:{}","A".repeat(64)),"source_commit":"b".repeat(40),"base_revision":"c".repeat(64),
                "file":{"display_name":format!("{}.MD","\"".repeat(125)),"media_type":"text/markdown","content_utf8":content}}});
            let actual = serde_json::to_vec(&body).unwrap();
            assert!(actual.len() > SOURCE_OPERATION_CAP && actual.len() <= PROJECT_FILE_PREPARE_CAP);
            assert_eq!(serde_json::from_slice::<Value>(&actual).unwrap()["request"]["file"]["content_utf8"], content);
            assert!(source_operation_target("prepare", &body).is_ok());
            body["request"]["file"]["content_utf8"] = serde_json::json!(format!("{content}x"));
            assert!(source_operation_target("prepare", &body).is_err());
            let other = serde_json::json!({"action":"ADOPT_PLAN","request":{"request_id":format!("mmos-project-adopt-{}","a".repeat(40)),"work_ref":"WS:TEST","body":content}});
            assert!(source_operation_target("prepare", &other).is_err());
        }
    }
    fn knowledge_lookup(preference: bool) -> Value {
        serde_json::json!({"action": if preference {"set_project_communication_preference"} else {"add_project_file"},
            "request_id": format!("{}{}", if preference {"mmos-project-preference-set-"} else {"mmos-project-file-add-"}, "a".repeat(40)),
            "work_ref":"WS:TEST", "source_commit":"b".repeat(40), "base_revision":"c".repeat(64),
            "request_sha256":"d".repeat(64), "expected_preference_revision": if preference {Value::String("e".repeat(64))} else {Value::Null}})
    }
    #[test]
    fn knowledge_original_lookup_preserves_closed_seven_fields_and_null_encoding() {
        for preference in [false, true] {
            let body = knowledge_lookup(preference);
            let url = source_operation_target("read", &body).unwrap();
            let pairs: std::collections::HashMap<_,_> = url.query_pairs().into_owned().collect();
            assert_eq!(pairs.len(), 7);
            assert_eq!(pairs["expected_preference_revision"], if preference {"e".repeat(64)} else {"null".to_owned()});
            assert_eq!(pairs["request_sha256"], "d".repeat(64));
            assert_eq!(source_operation_target("reconcile", &body).unwrap().query(), None);
            assert_eq!(body["expected_preference_revision"].is_null(), !preference);
        }
    }
    #[test]
    fn knowledge_lookup_refuses_extra_authority_and_mismatched_original_fields() {
        for (field, value) in [("schema",serde_json::json!("mastermind.workspace_source_operation_lookup.v1")),
            ("source_commit",serde_json::json!("B".repeat(40))), ("base_revision",serde_json::json!("short")),
            ("request_sha256",serde_json::json!(format!("{}\n","d".repeat(64)))),
            ("expected_preference_revision",serde_json::json!("e".repeat(64))),
            ("principal_scope",serde_json::json!("f".repeat(64))), ("source_path",serde_json::json!("/private/file")),
            ("work_ref",serde_json::json!("WS:OTHER\n")),
            ("request_id",serde_json::json!(format!("mmos-project-preference-set-{}","a".repeat(40))))] {
            let mut body=knowledge_lookup(false); body[field]=value;
            assert!(source_operation_target("read",&body).is_err(),"{field}");
            assert!(source_operation_target("reconcile",&body).is_err(),"{field}");
        }
        let mut graft=knowledge_lookup(false);graft["action"]=serde_json::json!("ADOPT_PLAN");
        graft["request_id"]=serde_json::json!(format!("mmos-project-adopt-{}","a".repeat(40)));
        assert!(source_operation_target("read",&graft).is_err());
    }
    #[test]
    fn source_operation_transport_fixed_targets_preserve_original_identity() {
        let body = lookup();
        let url = source_operation_target("read", &body).unwrap();
        assert_eq!(url.path(), "/workspace/source-operation/operation");
        assert_eq!(
            url.query_pairs().collect::<Vec<_>>(),
            vec![
                ("action".into(), "ADOPT_PLAN".into()),
                (
                    "request_id".into(),
                    format!("mmos-project-adopt-{}", "a".repeat(40)).into()
                ),
                ("work_ref".into(), "WS:TEST".into())
            ]
        );
        let reconcile = source_operation_target("reconcile", &body).unwrap();
        assert_eq!(reconcile.path(), "/workspace/source-operation/reconcile");
        assert_eq!(reconcile.query(), None);
        let mut advance = body.clone();
        advance["schema"] = "mastermind.workspace_source_operation_advance.v1".into();
        advance["phase_receipt_digest"] = "f".repeat(64).into();
        assert_eq!(
            source_operation_target("advance", &advance).unwrap().path(),
            "/workspace/source-operation/advance"
        );
        let prepare = serde_json::json!({"action":"ADOPT_PLAN","request":{"request_id":body["request_id"],"work_ref":"WS:TEST"}});
        assert_eq!(
            source_operation_target("prepare", &prepare).unwrap().path(),
            "/workspace/source-operation/prepare"
        );
        assert_eq!(SOURCE_OPERATION_CAP, 32768);
    }
    #[test]
    fn source_operation_transport_rejects_forged_identity_extra_authority_and_payloads() {
        for (key, value) in [
            ("principal", serde_json::json!("caller")),
            ("work_ref", serde_json::json!("WS:TEST\n")),
            (
                "request_id",
                serde_json::json!(format!("mmos-project-create-{}", "a".repeat(40))),
            ),
        ] {
            let mut body = lookup();
            body[key] = value;
            assert!(source_operation_target("read", &body).is_err());
        }
        let mut file = lookup();
        file["action"] = "add_project_file".into();
        file["request_id"] = format!("mmos-project-file-add-{}", "a".repeat(40)).into();
        assert!(source_operation_target("read", &file).is_err());
        let oversized = serde_json::json!({"action":"ADOPT_PLAN","request":{"request_id":lookup()["request_id"],"work_ref":"WS:TEST","content":"x".repeat(32768)}});
        assert!(source_operation_target("prepare", &oversized).is_err());
        let mut advance = lookup();
        advance["schema"] = "mastermind.workspace_source_operation_advance.v1".into();
        advance["phase_receipt_digest"] = format!("{}\n", "f".repeat(64)).into();
        assert!(source_operation_target("advance", &advance).is_err());
        let submit = serde_json::json!({"action":"ADOPT_PLAN","request_id":lookup()["request_id"],"work_ref":"WS:TEST","preview_witness":{"principal":"caller"}});
        assert!(source_operation_target("submit", &submit).is_err());
        assert!(source_operation_target("caller/path", &lookup()).is_err());
    }
}

#[cfg(test)]
mod project_knowledge_read_tests {
    use super::*;
    #[test]
    fn three_reads_have_only_fixed_rootless_project_routes() {
        for (kind,path) in [(ProjectKnowledgeReadKind::Catalogue,"/workspace/project-knowledge/current"),
                (ProjectKnowledgeReadKind::Memory,"/workspace/project-memory/current")] {
            let url=project_knowledge_target(kind,"WS:ONE",None).unwrap();
            assert_eq!(url.path(),path);
            assert_eq!(url.query_pairs().map(|(k,v)|(k.into_owned(),v.into_owned())).collect::<Vec<_>>(),vec![("work_ref".to_string(),"WS:ONE".to_string())]);
        }
        let reference=format!("project-file.v1.{}","a".repeat(64)); let revision="b".repeat(40);
        let url=project_knowledge_target(ProjectKnowledgeReadKind::Source,"WS:ONE",Some((&reference,&revision))).unwrap();
        assert_eq!(url.path(),"/workspace/project-source/current");
        assert_eq!(url.query_pairs().map(|(k,v)|(k.into_owned(),v.into_owned())).collect::<Vec<_>>(),vec![("work_ref".to_string(),"WS:ONE".to_string()),("source_ref".to_string(),reference),("expected_revision".to_string(),revision)]);
    }
    #[test]
    fn source_selector_rejects_paths_and_foreign_principal_selectors() {
        let valid=serde_json::json!({"work_ref":"WS:ONE","source_ref":format!("project-record.v1.{}","a".repeat(64)),"expected_revision":"b".repeat(40)});
        let parsed:ProjectKnowledgeSourceSelection=serde_json::from_value(valid.clone()).unwrap();assert!(parsed.validate().is_ok());
        for key in ["path","root_job_id","principal_scope","provider_session_id"] {
            let mut value=valid.clone();value.as_object_mut().unwrap().insert(key.to_string(),serde_json::json!("caller"));
            assert!(serde_json::from_value::<ProjectKnowledgeSourceSelection>(value).is_err());
        }
        for reference in ["docs/private.md","https://example.com/file","project-file.v1.not-a-digest"] {
            assert!(project_knowledge_target(ProjectKnowledgeReadKind::Source,"WS:ONE",Some((reference,&"b".repeat(40)))).is_err());
        }
    }
    #[test]
    fn source_tuple_is_neither_optional_nor_transferable_to_another_read_kind() {
        assert!(project_knowledge_target(ProjectKnowledgeReadKind::Source,"WS:ONE",None).is_err());
        assert!(project_knowledge_target(ProjectKnowledgeReadKind::Memory,"WS:ONE",Some((&format!("project-file.v1.{}","a".repeat(64)),&"b".repeat(40)))).is_err());
        assert!(project_knowledge_target(ProjectKnowledgeReadKind::Catalogue,"WS:ONE\n",None).is_err());
        assert!(project_knowledge_target(ProjectKnowledgeReadKind::Source,"WS:ONE",Some((&format!("project-file.v1.{}\n","a".repeat(64)),&"b".repeat(40)))).is_err());
    }
}

#[cfg(test)]
mod source_operation_context_tests {
    use super::*;
    #[test]
    fn source_context_uses_only_fixed_action_and_optional_canonical_work() {
        let selection: SourceOperationContextSelection = serde_json::from_value(serde_json::json!({
            "action": "ADOPT_PLAN", "work_ref": "WS:PROJECT-TEST"
        })).unwrap();
        let url = source_operation_context_target(&selection).unwrap();
        assert_eq!(url.as_str(), "https://mcp.mastermind-x.com/workspace/source-operation/context?action=ADOPT_PLAN&work_ref=WS%3APROJECT-TEST");
        let creation: SourceOperationContextSelection = serde_json::from_value(serde_json::json!({
            "action": "publish_project_proposal", "work_ref": null
        })).unwrap();
        assert_eq!(source_operation_context_target(&creation).unwrap().query(), Some("action=publish_project_proposal"));
    }
    #[test]
    fn source_context_rejects_principal_grant_and_non_source_action_selectors() {
        assert!(serde_json::from_value::<SourceOperationContextSelection>(serde_json::json!({
            "action": "ADOPT_PLAN", "work_ref": "WS:TEST", "principal_scope": "a".repeat(64)
        })).is_err());
        for (action, work) in [("pause_workstream_admission", Some("WS:TEST")),
            ("ADOPT_PLAN\n", Some("WS:TEST")), ("ADOPT_PLAN", None),
            ("ADOPT_PLAN", Some("WS:TEST\n")), ("ADOPT_PLAN", Some("WS:lower"))] {
            assert!(source_operation_context_target(&SourceOperationContextSelection {
                action: action.into(), work_ref: work.map(str::to_string)
            }).is_err());
        }
    }

}


#[cfg(test)]
mod secretary_selection_contract_tests {
    use super::*;

    #[test]
    fn session_kind_omission_and_closed_strings_preserve_the_wire_shape() {
        let pair = serde_json::json!({"work_ref": "WS:ALPHA", "root_job_id": "JOB-1"});
        let legacy: SessionSelection = serde_json::from_value(pair.clone()).unwrap();
        legacy.validate().unwrap();
        assert_eq!(legacy.wire(), pair);
        for kind in ["fabric_attempt", "hermes_secretary", "hermes_meta"] {
            let value = serde_json::json!({
                "work_ref": "WS:ALPHA", "root_job_id": "JOB-1", "target_kind": kind
            });
            let selected: SessionSelection = serde_json::from_value(value.clone()).unwrap();
            selected.validate().unwrap();
            assert_eq!(selected.wire(), value);
        }
    }

    #[test]
    fn an_explicit_null_kind_is_never_legacy_fabric() {
        for kind in [Value::Null, serde_json::json!(true), serde_json::json!(7), serde_json::json!([])] {
            let value = serde_json::json!({
                "work_ref": "WS:ALPHA", "root_job_id": "JOB-1", "target_kind": kind
            });
            assert!(serde_json::from_value::<SessionSelection>(value).is_err());
        }
        let unsupported: SessionSelection = serde_json::from_value(serde_json::json!({
            "work_ref": "WS:ALPHA", "root_job_id": "JOB-1", "target_kind": "other"
        })).unwrap();
        assert!(unsupported.validate().is_err());
    }
}
