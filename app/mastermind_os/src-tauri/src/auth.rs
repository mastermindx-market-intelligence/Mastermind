//! The native client owns OAuth transactions and bearer tokens. The webview
//! receives fixed read results and sanitized state, never credential material.
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
const DIRECT_NATIVE_REQUEST_CAP: usize = 4_096;
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
}
struct Inner {
    client_id: Option<String>,
    executive_resource: Option<String>,
    executive_generation: u64,
    executive_changed: tokio::sync::watch::Sender<()>,
    executive: Option<Token>,
    generation: u64,
    pending: Option<Pending>,
    exchanging: bool,
    acquisition: Option<Token>,
    content: Option<Token>,
    reason: Option<&'static str>,
    restoring: bool,
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
            executive_changed: tokio::sync::watch::channel(()).0,
            executive: None,
            generation: 0,
            pending: None,
            exchanging: false,
            acquisition: None,
            content: None,
            reason: None,
            restoring: false,
        }
    }
    fn token(&self, resource: Resource) -> Option<&Token> {
        match resource {
            Resource::Acquisition => self.acquisition.as_ref(),
            Resource::Content => self.content.as_ref(),
            Resource::Executive => self.executive.as_ref().filter(|_| self.executive_resource.is_some()),
        }
        .filter(|t| t.expires > Instant::now() && t.wall_expires > SystemTime::now())
    }
    fn status(&self) -> AuthStatus {
        let acquisition = self.token(Resource::Acquisition).is_some();
        let content = self.token(Resource::Content).is_some();
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
                self.reason
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
        self.restoring = false;
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
    let _keychain = state.keychain_lock.lock().map_err(|_| "KEYCHAIN_UNAVAILABLE")?;
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
    inner.invalidate();
    if crate::native_refresh::enabled() {
        let client = inner.client_id.as_deref().ok_or("NATIVE_CLIENT_ID_MISSING")?;
        for resource in [Resource::Acquisition, Resource::Content] {
            crate::native_refresh::delete(client, resource.audience())?;
        }
    }
    let url = inner.transaction(Resource::Acquisition)?;
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
            if pending.resource.persistent() {
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
            Resource::Acquisition => inner.acquisition = Some(access),
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
    let (token, generation) = ensure_native_token(&app, resource).await?;
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
// Mirror the existing closed direct-native wire contract. These selectors are
// data only; the server rejoins the original principal, Job and Attempt.
fn direct_native_body(body: &Value, consume: bool) -> Result<()> {
    let invalid = || "DIRECT_SELECTION_INVALID".to_owned();
    let object = body.as_object().ok_or_else(invalid)?;
    let keys: &[&str] = if consume {
        &["work_ref", "job_id", "attempt_id", "result_digest", "operation_key"]
    } else {
        &["work_ref", "job_id", "attempt_id"]
    };
    if object.len() != keys.len() || keys.iter().any(|key| !object.contains_key(*key)) {
        return Err(invalid());
    }
    let identifier = |value: &Value| value.as_str().is_some_and(|text| {
        !text.is_empty() && text.len() <= 128 && text.as_bytes()[0].is_ascii_alphanumeric()
            && text.bytes().all(|byte| byte.is_ascii_alphanumeric() || b"._:-".contains(&byte))
    });
    let work = body["work_ref"].as_str().ok_or_else(invalid)?;
    if work.is_empty() || work.trim() != work || work.chars().count() > 512
        || work.chars().any(|c| (c as u32) < 32 || c == '\u{7f}')
        || !identifier(&body["job_id"])
        || !(identifier(&body["attempt_id"]) || (!consume && body["attempt_id"].is_null()))
        || (consume && (!body["result_digest"].as_str().is_some_and(|v| lowercase_hex(v, 64))
            || !identifier(&body["operation_key"])))
        || serde_json::to_vec(body).map_err(|_| invalid())?.len() > DIRECT_NATIVE_REQUEST_CAP {
        return Err(invalid());
    }
    Ok(())
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
    let direct_native = match path {
        "/os/executive/direct-native/result" => Some(false),
        "/os/executive/direct-native/consume" => Some(true),
        _ => None,
    };
    if let Some(consume) = direct_native {
        direct_native_body(&body, consume)?;
    }
    let foreground_research = path == "/os/executive/submit"
        && body.get("arguments").and_then(|v| v.get("execution_profile"))
            .and_then(Value::as_str) == Some("research_only");
    let (token, token_expires, generation, changed) = {
        let inner = state.lock()?;
        let token = inner.token(Resource::Executive).ok_or("EXECUTIVE_AUTH_REQUIRED")?;
        match path {
            "/os/executive/context"
            | "/os/executive/status"
            | "/os/executive/session/context"
            | "/os/executive/session/reply"
            | "/os/executive/session/references"
            | "/os/executive/direct-native/result" => {}
            "/os/executive/submit" | "/os/executive/direct-native/consume" => {
                if !token.executive_send {
                    return Err("EXECUTIVE_SEND_SCOPE_REQUIRED".into());
                }
            }
            _ => return Err("REQUEST_INVALID".into()),
        }
        (
            token.value.clone(),
            token.expires,
            inner.executive_generation,
            inner.executive_changed.subscribe(),
        )
    };
    let serialized = executive_body(&body)?;
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
    if foreground_research {
        request = request.timeout(EXECUTIVE_FOREGROUND_TIMEOUT);
    }
    let exchange = async {
        let response = dispatch(request)
            .await
            .map_err(|_| "EXECUTIVE_TRANSPORT_UNAVAILABLE".to_owned())?;
        { executive_guard(&mut *state.lock()?, generation, token_expires)?; }
        let status = response.status();
        let result = if status.is_success() {
            read_json_body(response, if direct_native.is_some() {
                DIRECT_NATIVE_RESPONSE_CAP
            } else { EXECUTIVE_RESPONSE_CAP }).await
        } else {
            Err(match status.as_u16() {
                401 => "EXECUTIVE_AUTH_REQUIRED",
                403 => "EXECUTIVE_ACCESS_REFUSED",
                _ => "EXECUTIVE_TRANSPORT_UNAVAILABLE",
            }.into())
        };
        { executive_guard(&mut *state.lock()?, generation, token_expires)?; }
        result
    };
    if foreground_research || direct_native.is_some() {
        // Same current-token owner, with the ordinary 30s transport ceiling for
        // direct result/consume. Invalidation never replays a possible consume.
        executive_foreground_exchange(state, generation, token_expires, changed, exchange).await
    } else {
        exchange.await
    }
}

async fn executive_foreground_exchange<T, F>(
    state: &NativeAuth, generation: u64, expires: Instant,
    mut changed: tokio::sync::watch::Receiver<()>, exchange: F,
) -> Result<T>
where F: std::future::Future<Output = Result<T>> {
    use std::{future::Future, task::Poll};
    let mut exchange = std::pin::pin!(exchange);
    let mut expiry = std::pin::pin!(tokio::time::sleep_until(expires.into()));
    let mut notification = std::pin::pin!(changed.changed());
    std::future::poll_fn(|cx| {
        if notification.as_mut().poll(cx).is_ready() || expiry.as_mut().poll(cx).is_ready() {
            return Poll::Ready(Err("EXECUTIVE_AUTH_CHANGED".into()));
        }
        if let Err(error) = state.lock().and_then(|mut inner| executive_guard(&mut inner, generation, expires)) {
            return Poll::Ready(Err(error));
        }
        exchange.as_mut().poll(cx)
    }).await
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

#[tauri::command]
pub async fn executive_direct_native_result(app: AppHandle, arguments: Value) -> Result<Value> {
    let result = executive_post(app.clone(), "/os/executive/direct-native/result", arguments).await;
    if result.is_err() { emit(&app); }
    result
}
#[tauri::command]
pub async fn executive_direct_native_consume(app: AppHandle, arguments: Value) -> Result<Value> {
    let result = executive_post(app.clone(), "/os/executive/direct-native/consume", arguments).await;
    if result.is_err() { emit(&app); }
    result
}

// Read-only original-answer transport on the existing Executive token and
// generation. These commands do not originate or ACK a CONTINUE; in particular
// there is deliberately no executive_session_send native command. The separate
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
#[tauri::command]
pub async fn executive_session_context(app: AppHandle, selection: MissionSelection) -> Result<Value> {
    selection.validate()?;
    // The Session context endpoint requires the selected pair directly,
    // whereas replies/references use the existing arguments envelope.
    let result = executive_post(app.clone(), "/os/executive/session/context",
        serde_json::json!({ "selection": {
            "work_ref": selection.work_ref, "root_job_id": selection.root_job_id
        }})).await;
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
        {
            let mut inner = state.lock().unwrap();
            inner.executive.as_mut().unwrap().expires = Instant::now() + Duration::from_millis(20);
        }
        let result = tauri::async_runtime::block_on(executive_post_with_dispatch(
            &state, "/os/executive/submit",
            serde_json::json!({"arguments":{"execution_profile":"research_only"}}), |_| {
                std::future::pending::<std::result::Result<reqwest::Response, reqwest::Error>>()
            }));
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
