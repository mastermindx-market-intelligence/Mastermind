//! Tauri command surface for the DISTINCT native Terminal/Supabase PKCE
//! session owner. This module never touches the Auth0 owner (`auth.rs`), never
//! logs or serializes secrets, and never accepts callback URLs, keys or tokens
//! from the webview. All protocol logic lives in the injected, testable core.

#[path = "terminal_session_core.rs"]
pub mod terminal_session_core;

use tauri::{AppHandle, Emitter, Manager};
use terminal_session_core::{
    admit_anon_key, perform_sharing_requests_read, perform_sign_in, perform_token_exchange,
    AnonKey, CallbackOutcome, CoreShared, ErrorKind, HttpMethod, HttpResponse, ReasonCode,
    SessionStatusDto, SystemClock, TerminalError, SESSION_EVENT, STATE_ERROR,
};
use url::Url;

// ---------------------------------------------------------------------------
// Production ports.
// ---------------------------------------------------------------------------

/// Redirect-free, time-bounded reqwest transport. Transport failures are
/// surfaced as status 0 responses so every caller maps them to its own fixed
/// error route; bodies are capped while streaming (`chunk`), never trusted to
/// a content-length header.
pub struct ReqwestTransport {
    client: reqwest::Client,
}

impl terminal_session_core::HttpTransport for ReqwestTransport {
    fn request<'a>(
        &'a self,
        method: HttpMethod,
        url: &'a str,
        headers: Vec<(String, String)>,
        body: Option<String>,
        max_body_bytes: usize,
    ) -> terminal_session_core::BoxFut<'a, Result<HttpResponse, TerminalError>> {
        Box::pin(async move {
            let mut request = match method {
                HttpMethod::Get => self.client.get(url),
                HttpMethod::Post => self.client.post(url),
            };
            for (name, value) in &headers {
                let mut header = reqwest::header::HeaderValue::from_str(value).map_err(|_| {
                    TerminalError::new(ErrorKind::TransportUnavailable, ReasonCode::FeedUnavailable)
                })?;
                if name.eq_ignore_ascii_case("authorization") || name.eq_ignore_ascii_case("apikey")
                {
                    header.set_sensitive(true);
                }
                request = request.header(name.as_str(), header);
            }
            if let Some(payload) = body {
                request = request
                    .header(reqwest::header::CONTENT_TYPE, "application/json")
                    .body(payload);
            }
            let mut response = match request.send().await {
                Ok(response) => response,
                Err(_) => {
                    return Ok(HttpResponse {
                        status: 0,
                        body: Vec::new(),
                    })
                }
            };
            let mut body_bytes: Vec<u8> = Vec::new();
            loop {
                let chunk = match response.chunk().await {
                    Ok(Some(chunk)) => chunk,
                    Ok(None) => break,
                    Err(_) => {
                        return Ok(HttpResponse {
                            status: 0,
                            body: Vec::new(),
                        })
                    }
                };
                if body_bytes.len().saturating_add(chunk.len()) > max_body_bytes {
                    return Ok(HttpResponse {
                        status: 0,
                        body: Vec::new(),
                    });
                }
                body_bytes.extend_from_slice(&chunk);
            }
            Ok(HttpResponse {
                status: response.status().as_u16(),
                body: body_bytes,
            })
        })
    }
}

/// Opens the authorize URL exactly once through the existing opener plugin.
/// The URL never crosses back into the webview.
fn open_authorize_url(app: &AppHandle, authorize_url: &str) -> Result<(), TerminalError> {
    use tauri_plugin_opener::OpenerExt;
    app.opener()
        .open_url(authorize_url.to_string(), None::<&str>)
        .map_err(|_| TerminalError::new(ErrorKind::OpenFailed, ReasonCode::SignInOpenFailed))
}

struct CallbackOpener<F>
where
    F: Fn(&str) -> Result<(), TerminalError> + Send + Sync,
{
    open: F,
}

impl<F> terminal_session_core::BrowserOpener for CallbackOpener<F>
where
    F: Fn(&str) -> Result<(), TerminalError> + Send + Sync,
{
    fn open(&self, authorize_url: &str) -> Result<(), TerminalError> {
        (self.open)(authorize_url)
    }
}

// ---------------------------------------------------------------------------
// Managed state.
// ---------------------------------------------------------------------------

pub struct TerminalSession {
    core: CoreShared,
    key: Option<AnonKey>,
    config_problem: Option<ReasonCode>,
    transport: std::sync::Arc<ReqwestTransport>,
    clock: std::sync::Arc<dyn terminal_session_core::Clock>,
}

impl TerminalSession {
    /// Admission of the public build input happens once, at construction.
    /// Absence is UNCONFIGURED with no effects; an invalid, oversized,
    /// control-bearing or service-scoped key is a visible ERROR and no
    /// effects. No credentials, Keychain entries or env reads happen at
    /// runtime; no Supabase call is made here.
    pub fn new() -> Result<TerminalSession, TerminalError> {
        let admitted = admit_anon_key(option_env!("MM_TERMINAL_SUPABASE_ANON_KEY"));
        let (key, config_problem, configured) = match admitted {
            terminal_session_core::KeyAdmission::Absent => (None, None, false),
            terminal_session_core::KeyAdmission::Admitted(key) => (Some(key), None, true),
            terminal_session_core::KeyAdmission::Refused(reason) => (None, Some(reason), false),
        };
        let client = reqwest::Client::builder()
            .redirect(reqwest::redirect::Policy::none())
            .timeout(std::time::Duration::from_secs(30))
            .build()
            .map_err(|_| {
                TerminalError::new(ErrorKind::TransportUnavailable, ReasonCode::FeedUnavailable)
            })?;
        Ok(TerminalSession {
            core: CoreShared::new(configured),
            key,
            config_problem,
            transport: std::sync::Arc::new(ReqwestTransport { client }),
            clock: std::sync::Arc::new(SystemClock),
        })
    }

    /// Public status: fixed states, safeint generation, closed reason, opaque
    /// scope hashes only after server verification.
    fn status_dto(&self) -> SessionStatusDto {
        if let Some(reason) = self.config_problem {
            return SessionStatusDto {
                state: STATE_ERROR,
                generation: self.core.generation(),
                reason: Some(reason.as_str()),
                available: false,
                principal_scope: None,
                session_scope: None,
            };
        }
        self.core.status(&*self.clock)
    }
}

// ---------------------------------------------------------------------------
// Commands (return serializable fixed-safe DTOs only).
// ---------------------------------------------------------------------------

#[tauri::command]
pub fn terminal_session_status(state: tauri::State<'_, TerminalSession>) -> SessionStatusDto {
    state.status_dto()
}

/// Explicit user action only: installs the pending transaction, opens the
/// authorize URL once (never returned to the UI), emits the public status.
#[tauri::command]
pub async fn terminal_sign_in(
    app: AppHandle,
    state: tauri::State<'_, TerminalSession>,
) -> Result<SessionStatusDto, TerminalError> {
    let app_for_open = app.clone();
    let opener = CallbackOpener {
        open: move |url| open_authorize_url(&app_for_open, url),
    };
    let status = perform_sign_in(&state.core, &opener, &*state.clock, state.key.as_ref())?;
    let _ = app.emit(SESSION_EVENT, &status);
    Ok(status)
}

/// Local disconnect: clears the grant and any pending transaction and advances
/// the generation. It does not revoke the browser session, other owners, or
/// the global Supabase session.
#[tauri::command]
pub fn terminal_disconnect(
    app: AppHandle,
    state: tauri::State<'_, TerminalSession>,
) -> SessionStatusDto {
    state.core.disconnect();
    let status = state.status_dto();
    let _ = app.emit(SESSION_EVENT, &status);
    status
}

/// Sharing-request feed read: bearer-only native route, full pre/post guards,
/// capped streaming, schema-validated rebuild. Returns only the validated
/// feed; every failure is a fixed error.
#[tauri::command]
pub async fn read_terminal_sharing_requests(
    app: AppHandle,
    state: tauri::State<'_, TerminalSession>,
) -> Result<serde_json::Value, TerminalError> {
    let result = perform_sharing_requests_read(
        &state.core,
        &*state.transport,
        &*state.clock,
        state.key.as_ref(),
    )
    .await;
    let _ = app.emit(SESSION_EVENT, &state.status_dto());
    result
}

// ---------------------------------------------------------------------------
// Deep-link callback dispatch.
// ---------------------------------------------------------------------------

/// Dispatch guard for the shared deep-link owner (main.rs keeps ownership of
/// `on_open_url`): only the exact `com.mastermind.os://terminal/callback`
/// shape is claimed. Everything else stays with the Auth0 owner.
pub fn accepts_callback_url(url: &Url) -> bool {
    terminal_session_core::accepts_callback_url(url)
}

/// Convenience for string-carrying dispatchers: parse-false, then shape check.
pub fn accepts_raw_callback(raw_url: &str) -> bool {
    Url::parse(raw_url)
        .map(|url| accepts_callback_url(&url))
        .unwrap_or(false)
}

/// Private-path callback: consumes the pending transaction once (before any
/// HTTP), performs the bounded PKCE exchange with server verification, and
/// emits the public status. Errors collapse to fixed reasons; the raw URL,
/// code, verifier and tokens never reach the event payload or any log.
pub async fn callback(app: AppHandle, raw_url: String) {
    let session = app.state::<TerminalSession>();
    let outcome = match Url::parse(&raw_url) {
        Ok(url) if accepts_callback_url(&url) => {
            match session.core.consume_callback(&*session.clock, &url) {
                Ok(CallbackOutcome::Cancelled { status }) => Ok(status),
                Ok(accepted) => match session.key.as_ref() {
                    Some(key) => {
                        perform_token_exchange(
                            &session.core,
                            &*session.transport,
                            &*session.clock,
                            accepted,
                            key,
                        )
                        .await
                    }
                    None => Err(TerminalError::new(
                        ErrorKind::ConfigUnavailable,
                        ReasonCode::NotConfigured,
                    )),
                },
                Err(err) => Err(err),
            }
        }
        _ => Err(TerminalError::new(
            ErrorKind::CallbackInvalid,
            ReasonCode::CallbackRejected,
        )),
    };
    let _ = outcome; // Private protocol owner has already recorded any actual exchange failure.
    let status = session.status_dto();
    let _ = app.emit(SESSION_EVENT, &status);
}
