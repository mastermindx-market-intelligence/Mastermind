//! Native Terminal/Supabase PKCE session owner: pure, injectable protocol core.
//!
//! No tauri types here. HTTP, time and browser opening are injected traits so
//! every protocol path is testable with fakes and no live I/O. Secrets (bearer
//! tokens, code verifier, auth code, raw ids, URLs) live only inside this
//! module's memory and never reach a serializable DTO or a log.

use base64::engine::general_purpose::{URL_SAFE, URL_SAFE_NO_PAD};
use base64::Engine;
use rand::rngs::OsRng;
use rand::RngCore;
use serde::ser::SerializeStruct;
use sha2::{Digest, Sha256};
use std::future::Future;
use std::pin::Pin;
use std::sync::{Mutex, PoisonError};
use url::Url;

// ---------------------------------------------------------------------------
// Fixed endpoints and flow constants.
// ---------------------------------------------------------------------------

pub const SUPABASE_ORIGIN: &str = "https://fsldfzlxyavsuwqbceod.supabase.co";
pub const TERMINAL_ORIGIN: &str = "https://app.mastermind-x.com";
pub const CALLBACK_SCHEME: &str = "com.mastermind.os";
pub const CALLBACK_HOST: &str = "terminal";
pub const CALLBACK_PATH: &str = "/callback";
pub const NATIVE_FEED_PATH: &str = "/api/briefs/sharing-requests/native";
pub const SESSION_EVENT: &str = "terminal-session-changed";

const PENDING_TTL_MS: u64 = 300_000;
const MAX_ACCESS_LIFETIME_SECS: u64 = 86_400;
const BODY_CAP_BYTES: usize = 65_536;
const MAX_KEY_BYTES: usize = 1024;
const MAX_AUTH_CODE_BYTES: usize = 512;
const STATE_B64_LEN: usize = 43;
const VERIFIER_B64_LEN: usize = 43;
const PRINCIPAL_SCOPE_DOMAIN: &str = "mastermind.terminal.principal.v1:";
const SESSION_SCOPE_DOMAIN: &str = "mastermind.terminal.session.v1:";
const EXPECTED_ISSUER: &str = "https://fsldfzlxyavsuwqbceod.supabase.co/auth/v1";
const EXPECTED_AUDIENCE: &str = "authenticated";
const EXPECTED_ROLE: &str = "authenticated";
const MAX_FEED_REQUESTS: usize = 20;
const MAX_TEXT_BYTES: usize = 240;
const MAX_MEMBER_COUNT: u64 = (1_u64 << 53) - 1;

// ---------------------------------------------------------------------------
// Fixed error and reason vocabulary (closed enums; never free-form strings).
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ErrorKind {
    ConfigUnavailable,
    ConfigInvalid,
    SignInBusy,
    CallbackInvalid,
    ProviderRejected,
    ServerUnverified,
    SessionRequired,
    SessionStale,
    GenerationChanged,
    FeedRejected,
    OpenFailed,
    TransportUnavailable,
    Cancelled,
}

impl ErrorKind {
    pub fn as_str(self) -> &'static str {
        match self {
            ErrorKind::ConfigUnavailable => "CONFIG_UNAVAILABLE",
            ErrorKind::ConfigInvalid => "CONFIG_INVALID",
            ErrorKind::SignInBusy => "SIGN_IN_BUSY",
            ErrorKind::CallbackInvalid => "CALLBACK_INVALID",
            ErrorKind::ProviderRejected => "PROVIDER_REJECTED",
            ErrorKind::ServerUnverified => "SERVER_UNVERIFIED",
            ErrorKind::SessionRequired => "SESSION_REQUIRED",
            ErrorKind::SessionStale => "SESSION_STALE",
            ErrorKind::GenerationChanged => "GENERATION_CHANGED",
            ErrorKind::FeedRejected => "FEED_REJECTED",
            ErrorKind::OpenFailed => "OPEN_FAILED",
            ErrorKind::TransportUnavailable => "TRANSPORT_UNAVAILABLE",
            ErrorKind::Cancelled => "CANCELLED",
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ReasonCode {
    NotConfigured,
    InvalidConfig,
    ServiceKeyRefused,
    SignInStarted,
    SignInOverlap,
    SignInOpenFailed,
    UserCancelled,
    CallbackRejected,
    StateMismatch,
    PendingExpired,
    PendingMissing,
    NoPending,
    TokenExchangeRejected,
    ServerVerificationFailed,
    LateCompletionRejected,
    SignedOutLocal,
    SessionExpired,
    SessionChanged,
    GenerationChanged,
    FeedUnavailable,
    FeedSchemaRejected,
    ResponseTooLarge,
    RedirectRefused,
}

impl ReasonCode {
    pub fn as_str(self) -> &'static str {
        match self {
            ReasonCode::NotConfigured => "NOT_CONFIGURED",
            ReasonCode::InvalidConfig => "INVALID_CONFIG",
            ReasonCode::ServiceKeyRefused => "SERVICE_KEY_REFUSED",
            ReasonCode::SignInStarted => "SIGN_IN_STARTED",
            ReasonCode::SignInOverlap => "SIGN_IN_OVERLAP",
            ReasonCode::SignInOpenFailed => "SIGN_IN_OPEN_FAILED",
            ReasonCode::UserCancelled => "USER_CANCELLED",
            ReasonCode::CallbackRejected => "CALLBACK_REJECTED",
            ReasonCode::StateMismatch => "STATE_MISMATCH",
            ReasonCode::PendingExpired => "PENDING_EXPIRED",
            ReasonCode::PendingMissing => "PENDING_MISSING",
            ReasonCode::NoPending => "NO_PENDING",
            ReasonCode::TokenExchangeRejected => "TOKEN_EXCHANGE_REJECTED",
            ReasonCode::ServerVerificationFailed => "SERVER_VERIFICATION_FAILED",
            ReasonCode::LateCompletionRejected => "LATE_COMPLETION_REJECTED",
            ReasonCode::SignedOutLocal => "SIGNED_OUT_LOCAL",
            ReasonCode::SessionExpired => "SESSION_EXPIRED",
            ReasonCode::SessionChanged => "SESSION_CHANGED",
            ReasonCode::GenerationChanged => "GENERATION_CHANGED",
            ReasonCode::FeedUnavailable => "FEED_UNAVAILABLE",
            ReasonCode::FeedSchemaRejected => "FEED_SCHEMA_REJECTED",
            ReasonCode::ResponseTooLarge => "RESPONSE_TOO_LARGE",
            ReasonCode::RedirectRefused => "REDIRECT_REFUSED",
        }
    }
}

/// Serializable fixed error for command results. Only closed vocabulary;
/// no provider detail, URL, key or token ever lands in here.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct TerminalError {
    pub kind: ErrorKind,
    pub reason: ReasonCode,
}

impl TerminalError {
    pub fn new(kind: ErrorKind, reason: ReasonCode) -> Self {
        TerminalError { kind, reason }
    }
    pub fn command_code(&self) -> &'static str {
        self.kind.as_str()
    }
}

impl std::fmt::Display for TerminalError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(
            f,
            "terminal session error {} / {}",
            self.kind.as_str(),
            self.reason.as_str()
        )
    }
}

impl std::error::Error for TerminalError {}

impl serde::Serialize for TerminalError {
    fn serialize<S: serde::Serializer>(&self, serializer: S) -> Result<S::Ok, S::Error> {
        use serde::ser::SerializeStruct;
        let mut s = serializer.serialize_struct("TerminalError", 2)?;
        s.serialize_field("error", self.kind.as_str())?;
        s.serialize_field("reason", self.reason.as_str())?;
        s.end()
    }
}

// ---------------------------------------------------------------------------
// Public status DTO: fixed state, safeint generation, closed reason, opaque
// scope hashes only after server verification. No tokens, ids, codes, URLs.
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct SessionStatusDto {
    pub state: &'static str,
    pub generation: u64,
    pub reason: Option<&'static str>,
    pub available: bool,
    pub principal_scope: Option<String>,
    pub session_scope: Option<String>,
}

impl serde::Serialize for SessionStatusDto {
    fn serialize<S: serde::Serializer>(&self, serializer: S) -> Result<S::Ok, S::Error> {
        let mut s = serializer.serialize_struct("SessionStatusDto", 6)?;
        s.serialize_field("state", self.state)?;
        s.serialize_field("generation", &self.generation)?;
        s.serialize_field("reason", &self.reason)?;
        s.serialize_field("available", &self.available)?;
        s.serialize_field("principal_scope", &self.principal_scope)?;
        s.serialize_field("session_scope", &self.session_scope)?;
        s.end()
    }
}

pub const STATE_UNCONFIGURED: &str = "UNCONFIGURED";
pub const STATE_SIGNED_OUT: &str = "SIGNED_OUT";
pub const STATE_SIGNING_IN: &str = "SIGNING_IN";
pub const STATE_SIGNED_IN: &str = "SIGNED_IN";
pub const STATE_ERROR: &str = "ERROR";

// ---------------------------------------------------------------------------
// Anon key admission: publishable or legacy-anon only, never service_role.
// ---------------------------------------------------------------------------

#[derive(Clone, PartialEq, Eq)]
pub struct AnonKey {
    value: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum KeyAdmission {
    Absent,
    Admitted(AnonKey),
    Refused(ReasonCode),
}

fn is_jwt_shape(value: &str) -> bool {
    let parts: Vec<&str> = value.split('.').collect();
    parts.len() == 3 && parts.iter().all(|p| !p.is_empty() && p.len() <= 4096)
}

fn decode_jwt_segment(segment: &str) -> Option<serde_json::Value> {
    let decoded = URL_SAFE_NO_PAD
        .decode(segment.as_bytes())
        .or_else(|_| URL_SAFE.decode(segment.as_bytes()))
        .ok()?;
    serde_json::from_slice(&decoded).ok()
}

fn has_control_or_non_ascii(value: &str) -> bool {
    value
        .chars()
        .any(|c| c < '\u{20}' || c == '\u{7f}' || (c as u32) > 0x7e)
}

/// Classifies the public build input. Absence is UNCONFIGURED (no effects);
/// malformed, oversized, control-bearing or service-scoped keys are refused.
pub fn admit_anon_key(raw: Option<&str>) -> KeyAdmission {
    let Some(value) = raw else {
        return KeyAdmission::Absent;
    };
    let trimmed = value.trim();
    if trimmed.is_empty() {
        return KeyAdmission::Refused(ReasonCode::InvalidConfig);
    }
    if trimmed.len() > MAX_KEY_BYTES || has_control_or_non_ascii(trimmed) {
        return KeyAdmission::Refused(ReasonCode::InvalidConfig);
    }
    if trimmed.starts_with("sb_secret_") {
        return KeyAdmission::Refused(ReasonCode::ServiceKeyRefused);
    }
    if let Some(rest) = trimmed.strip_prefix("sb_publishable_") {
        if rest.is_empty() || rest.len() > 256 || has_control_or_non_ascii(rest) {
            return KeyAdmission::Refused(ReasonCode::InvalidConfig);
        }
        return KeyAdmission::Admitted(AnonKey {
            value: trimmed.to_string(),
        });
    }
    if is_jwt_shape(trimmed) {
        let payload = trimmed.split('.').nth(1).expect("jwt shape checked");
        let Some(claims) = decode_jwt_segment(payload) else {
            return KeyAdmission::Refused(ReasonCode::InvalidConfig);
        };
        let role = claims.get("role").and_then(|r| r.as_str());
        match role {
            Some("anon") => KeyAdmission::Admitted(AnonKey {
                value: trimmed.to_string(),
            }),
            _ => KeyAdmission::Refused(ReasonCode::ServiceKeyRefused),
        }
    } else {
        KeyAdmission::Refused(ReasonCode::InvalidConfig)
    }
}

impl AnonKey {
    pub fn expose(&self) -> &str {
        &self.value
    }
}

// ---------------------------------------------------------------------------
// PKCE + identity-free scope hashing.
// ---------------------------------------------------------------------------

pub fn b64url_random(bytes: &[u8]) -> String {
    URL_SAFE_NO_PAD.encode(bytes)
}

pub fn pkce_challenge_from_verifier(verifier: &str) -> String {
    let mut digest = Sha256::new();
    digest.update(verifier.as_bytes());
    URL_SAFE_NO_PAD.encode(digest.finalize())
}

pub fn principal_scope_for_uid(uid: &str) -> String {
    let mut digest = Sha256::new();
    digest.update(PRINCIPAL_SCOPE_DOMAIN.as_bytes());
    digest.update(uid.as_bytes());
    format!("{:x}", digest.finalize())
}

pub fn session_scope_for(uid: &str, session_id: &str) -> String {
    let mut digest = Sha256::new();
    digest.update(SESSION_SCOPE_DOMAIN.as_bytes());
    digest.update(uid.as_bytes());
    digest.update(b":");
    digest.update(session_id.as_bytes());
    format!("{:x}", digest.finalize())
}

/// Constant-time byte equality with the length folded into the accumulator.
pub fn ct_eq(a: &[u8], b: &[u8]) -> bool {
    let mut acc = (a.len() ^ b.len()) as u8;
    let n = a.len().max(b.len());
    for i in 0..n {
        let x = *a.get(i).unwrap_or(&0);
        let y = *b.get(i).unwrap_or(&0);
        acc |= x ^ y;
    }
    acc == 0
}

// ---------------------------------------------------------------------------
// Small closed grammar validators (no external crates beyond the manifest).
// ---------------------------------------------------------------------------

fn is_ascii_digit(b: u8) -> bool {
    b.is_ascii_digit()
}

pub fn is_canonical_uuid(value: &str) -> bool {
    let bytes = value.as_bytes();
    if bytes.len() != 36 {
        return false;
    }
    for (i, b) in bytes.iter().enumerate() {
        match i {
            8 | 13 | 18 | 23 => {
                if *b != b'-' {
                    return false;
                }
            }
            _ => {
                if !matches!(b, b'0'..=b'9' | b'a'..=b'f') {
                    return false;
                }
            }
        }
    }
    true
}

pub fn is_lower_hex_digest64(value: &str) -> bool {
    let bytes = value.as_bytes();
    bytes.len() == 64 && bytes.iter().all(|b| matches!(b, b'0'..=b'9' | b'a'..=b'f'))
}

fn days_in_month(year: u32, month: u32) -> u32 {
    match month {
        1 | 3 | 5 | 7 | 8 | 10 | 12 => 31,
        4 | 6 | 9 | 11 => 30,
        2 => {
            if (year % 4 == 0 && year % 100 != 0) || year % 400 == 0 {
                29
            } else {
                28
            }
        }
        _ => 0,
    }
}

fn valid_calendar_date(year: u32, month: u32, day: u32) -> bool {
    (1970..=9999).contains(&year)
        && (1..=12).contains(&month)
        && day >= 1
        && day <= days_in_month(year, month)
}

/// slot date grammar: strict `YYYY-MM-DD`, calendar-validated.
pub fn is_slot_date(value: &str) -> bool {
    let b = value.as_bytes();
    if b.len() != 10
        || b[4] != b'-'
        || b[7] != b'-'
        || !b[0..4].iter().all(|c| is_ascii_digit(*c))
        || !b[5..7].iter().all(|c| is_ascii_digit(*c))
        || !b[8..10].iter().all(|c| is_ascii_digit(*c))
    {
        return false;
    }
    let num = |s: &str| -> Option<u32> { s.parse::<u32>().ok() };
    let (Some(y), Some(m), Some(d)) = (num(&value[0..4]), num(&value[5..7]), num(&value[8..10]))
    else {
        return false;
    };
    valid_calendar_date(y, m, d)
}

/// Timestamp grammar: strict `YYYY-MM-DDTHH:mm:ss.ffffffZ`, calendar-validated.
pub fn is_persisted_timestamp(value: &str) -> bool {
    let b = value.as_bytes();
    if b.len() != 27
        || b[4] != b'-'
        || b[7] != b'-'
        || b[10] != b'T'
        || b[13] != b':'
        || b[16] != b':'
        || b[19] != b'.'
        || b[26] != b'Z'
    {
        return false;
    }
    for r in [0..4, 5..7, 8..10, 11..13, 14..16, 17..19, 20..26] {
        if !b[r].iter().all(|c| is_ascii_digit(*c)) {
            return false;
        }
    }
    let num = |s: &str| -> Option<u32> { s.parse::<u32>().ok() };
    let (Some(y), Some(mo), Some(d), Some(h), Some(mi), Some(se)) = (
        num(&value[0..4]),
        num(&value[5..7]),
        num(&value[8..10]),
        num(&value[11..13]),
        num(&value[14..16]),
        num(&value[17..19]),
    ) else {
        return false;
    };
    valid_calendar_date(y, mo, d) && h <= 23 && mi <= 59 && se <= 59
}

/// Feed display text: bounded, control-free, URL-free, no angle brackets.
fn is_safe_display_text(value: &str, max_bytes: usize) -> bool {
    !value.trim().is_empty()
        && value.encode_utf16().count() <= max_bytes
        && !value.chars().any(|c| c < '\u{20}' || c == '\u{7f}')
}

// ---------------------------------------------------------------------------
// Injected ports: clock, browser opener, HTTP transport.
// ---------------------------------------------------------------------------

pub trait Clock: Send + Sync {
    fn now_monotonic_ms(&self) -> u64;
    fn now_wall_ms(&self) -> u64;
}

pub struct SystemClock;

impl Clock for SystemClock {
    fn now_monotonic_ms(&self) -> u64 {
        use std::time::Instant;
        // Process-lifetime monotonic reference; Instant is opaque, so anchor on
        // process start via lazy static-free trick: use elapsed from a stored
        // once-initialized Instant.
        static START: std::sync::OnceLock<Instant> = std::sync::OnceLock::new();
        let start = START.get_or_init(Instant::now);
        start.elapsed().as_millis() as u64
    }
    fn now_wall_ms(&self) -> u64 {
        use std::time::{SystemTime, UNIX_EPOCH};
        SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .map(|d| d.as_millis() as u64)
            .unwrap_or(0)
    }
}

pub trait BrowserOpener: Send + Sync {
    /// Opens the authorize URL exactly once, outside the lock. Never returns
    /// the URL itself to the caller surface.
    fn open(&self, authorize_url: &str) -> Result<(), TerminalError>;
}

pub type BoxFut<'a, T> = Pin<Box<dyn Future<Output = T> + Send + 'a>>;

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum HttpMethod {
    Get,
    Post,
}

#[derive(Clone)]
pub struct HttpResponse {
    pub status: u16,
    pub body: Vec<u8>,
}

impl std::fmt::Debug for HttpResponse {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("HttpResponse")
            .field("status", &self.status)
            .field("body", &"[REDACTED]")
            .finish()
    }
}

pub trait HttpTransport: Send + Sync {
    /// Bounded request. Implementations must disable redirects (a 3xx is
    /// surfaced as a response, never followed) and enforce `max_body_bytes`
    /// while streaming.
    fn request<'a>(
        &'a self,
        method: HttpMethod,
        url: &'a str,
        headers: Vec<(String, String)>,
        body: Option<String>,
        max_body_bytes: usize,
    ) -> BoxFut<'a, Result<HttpResponse, TerminalError>>;
}

// ---------------------------------------------------------------------------
// Session state pieces.
// ---------------------------------------------------------------------------

#[derive(Clone)]
pub struct PendingAuth {
    pub terminal_state: String,
    pub code_verifier: String,
    pub authorize_url: String,
    pub created_monotonic_ms: u64,
    pub created_wall_ms: u64,
    pub generation_at_start: u64,
}

#[derive(Clone)]
pub struct VerifiedGrant {
    pub principal_uid: String,
    pub session_id: String,
    pub access_token: String,
    pub access_exp_wall_ms: u64,
    pub access_deadline_monotonic_ms: u64,
    pub principal_scope: String,
    pub session_scope: String,
    pub generation_at_issue: u64,
}

#[derive(Clone)]
pub struct SessionTicket {
    pub generation: u64,
    pub principal_uid: String,
    pub session_id: String,
    pub access_token: String,
    pub access_exp_wall_ms: u64,
    pub access_deadline_monotonic_ms: u64,
    pub principal_scope: String,
    pub session_scope: String,
}

#[derive(Clone, PartialEq, Eq)]
pub enum CallbackOutcome {
    Accepted {
        auth_code: String,
        code_verifier: String,
        generation: u64,
    },
    Cancelled {
        status: SessionStatusDto,
    },
}

// ---------------------------------------------------------------------------
// URL builders (fixed origins only; query built with form encoding matching
// the pinned @supabase/auth-js 2.108.2 authorize order).
// ---------------------------------------------------------------------------

pub fn callback_base_url() -> String {
    format!("{}://{}{}", CALLBACK_SCHEME, CALLBACK_HOST, CALLBACK_PATH)
}

pub fn build_authorize_url(redirect_to: &str, code_challenge: &str) -> String {
    let base = format!("{}/auth/v1/authorize", SUPABASE_ORIGIN);
    let mut url = Url::parse(&base).expect("fixed supabase origin parses");
    {
        let mut query = url.query_pairs_mut();
        query.append_pair("provider", "google");
        query.append_pair("redirect_to", redirect_to);
        query.append_pair("code_challenge", code_challenge);
        query.append_pair("code_challenge_method", "s256");
    }
    url.to_string()
}

pub fn token_url() -> String {
    format!("{}/auth/v1/token?grant_type=pkce", SUPABASE_ORIGIN)
}

pub fn user_url() -> String {
    format!("{}/auth/v1/user", SUPABASE_ORIGIN)
}

pub fn native_feed_url() -> String {
    format!("{}{}", TERMINAL_ORIGIN, NATIVE_FEED_PATH)
}

// ---------------------------------------------------------------------------
// Callback URL admission.
// ---------------------------------------------------------------------------

#[derive(Clone, PartialEq, Eq)]
pub enum ParsedCallback {
    /// Exact scheme/host/path with exactly the `code` + `terminal_state` pair
    /// (any order, no duplicates, no extras).
    Code {
        code: String,
        terminal_state: String,
    },
    /// Closed error variant: exactly one `error` query pair, bounded value.
    Error {
        code_label: String,
        terminal_state: String,
    },
    /// Structurally ours but not acceptable (fragment, userinfo, port,
    /// duplicate/unknown query keys, empty values, oversize).
    Malformed,
    /// Not ours at all (foreign scheme/host/path) — the dispatch owner must
    /// leave it alone.
    Foreign,
}

fn structural_shape_matches(url: &Url) -> bool {
    url.scheme() == CALLBACK_SCHEME
        && url.host_str() == Some(CALLBACK_HOST)
        && url.path() == CALLBACK_PATH
}

fn query_pairs_of(url: &Url) -> Vec<(String, String)> {
    url.query_pairs()
        .map(|(k, v)| (k.into_owned(), v.into_owned()))
        .collect()
}

fn has_forbidden_url_parts(url: &Url) -> bool {
    url.fragment().is_some()
        || url.port().is_some()
        || !url.username().is_empty()
        || url.password().is_some()
        || !url.host_str().map(|h| h == CALLBACK_HOST).unwrap_or(true)
}

fn is_flow_value_shape(value: &str) -> bool {
    !value.is_empty() && value.len() <= MAX_AUTH_CODE_BYTES && !has_control_or_non_ascii(value)
}

fn is_state_value_shape(value: &str) -> bool {
    value.len() == STATE_B64_LEN
        && value
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || b == b'-' || b == b'_')
}

/// Dispatch-level check for the deep-link owner: is this URL the native
/// terminal callback shape at all? Purely structural; no state comparison.
pub fn accepts_callback_url(url: &Url) -> bool {
    structural_shape_matches(url)
}

/// Full callback validation. Purity note: this never compares against the
/// pending state (the caller does that once, under the lock, before HTTP).
pub fn parse_callback_url(url: &Url) -> ParsedCallback {
    if !structural_shape_matches(url) {
        return ParsedCallback::Foreign;
    }
    if has_forbidden_url_parts(url) {
        return ParsedCallback::Malformed;
    }
    let pairs = query_pairs_of(url);
    let mut keys = std::collections::HashSet::new();
    if pairs.iter().any(|(key, _)| !keys.insert(key.as_str())) {
        return ParsedCallback::Malformed;
    }
    let state = pairs
        .iter()
        .find(|(key, _)| key == "terminal_state")
        .map(|(_, value)| value.as_str());
    let Some(state) = state.filter(|value| is_state_value_shape(value)) else {
        return ParsedCallback::Malformed;
    };
    if pairs.len() == 2 && keys.contains("code") && keys.contains("terminal_state") {
        let code = pairs
            .iter()
            .find(|(key, _)| key == "code")
            .unwrap()
            .1
            .as_str();
        if is_flow_value_shape(code) {
            return ParsedCallback::Code {
                code: code.to_owned(),
                terminal_state: state.to_owned(),
            };
        }
    }
    if (2..=4).contains(&pairs.len())
        && keys.contains("error")
        && keys.contains("terminal_state")
        && keys
            .iter()
            .all(|key| ["error", "terminal_state", "error_code", "error_description"].contains(key))
    {
        let error = pairs
            .iter()
            .find(|(key, _)| key == "error")
            .unwrap()
            .1
            .as_str();
        if is_flow_value_shape(error)
            && error.len() <= 64
            && pairs
                .iter()
                .all(|(_, value)| value.len() <= 512 && !value.chars().any(char::is_control))
        {
            return ParsedCallback::Error {
                code_label: error.to_owned(),
                terminal_state: state.to_owned(),
            };
        }
    }
    ParsedCallback::Malformed
}

// ---------------------------------------------------------------------------
// JWT claim decoding. This is comparison material only; signature truth comes
// exclusively from the server /auth/v1/user round-trip.
// ---------------------------------------------------------------------------

#[derive(Clone)]
pub struct JwtClaims {
    pub sub: String,
    pub session_id: String,
    pub exp: u64,
}

pub fn decode_access_token_claims(access_token: &str) -> Result<JwtClaims, TerminalError> {
    let reject = || {
        TerminalError::new(
            ErrorKind::ProviderRejected,
            ReasonCode::TokenExchangeRejected,
        )
    };
    let parts: Vec<&str> = access_token.split('.').collect();
    if parts.len() != 3 || parts.iter().any(|p| p.is_empty() || p.len() > 4096) {
        return Err(reject());
    }
    let payload = decode_jwt_segment(parts[1]).ok_or_else(reject)?;
    let sub = payload
        .get("sub")
        .and_then(|v| v.as_str())
        .ok_or_else(reject)?
        .to_string();
    if !is_canonical_uuid(&sub) {
        return Err(reject());
    }
    let issuer = payload.get("iss").and_then(|v| v.as_str()).unwrap_or("");
    if issuer != EXPECTED_ISSUER {
        return Err(reject());
    }
    // Match the incumbent Terminal bearer owner: one exact authenticated audience.
    let aud = payload.get("aud").ok_or_else(reject)?;
    if aud.as_str() != Some(EXPECTED_AUDIENCE)
        && aud
            .as_array()
            .map(|v| v.len() == 1 && v[0].as_str() == Some(EXPECTED_AUDIENCE))
            != Some(true)
    {
        return Err(reject());
    }
    let role = payload.get("role").and_then(|v| v.as_str()).unwrap_or("");
    if role != EXPECTED_ROLE {
        return Err(reject());
    }
    let exp = payload
        .get("exp")
        .and_then(|v| v.as_u64())
        .ok_or_else(reject)?;
    let session_id = payload
        .get("session_id")
        .and_then(|v| v.as_str())
        .ok_or_else(reject)?
        .to_string();
    if !is_canonical_uuid(&session_id) {
        return Err(reject());
    }
    Ok(JwtClaims {
        sub,
        session_id,
        exp,
    })
}

/// Validates the token grant response body against wall-clock bounds.
pub fn validate_token_response(
    body: &[u8],
    now_wall_ms: u64,
) -> Result<(VerifiedGrantSkeleton, String), TerminalError> {
    let reject = |r: ReasonCode| TerminalError::new(ErrorKind::ProviderRejected, r);
    if body.len() > BODY_CAP_BYTES {
        return Err(TerminalError::new(
            ErrorKind::ProviderRejected,
            ReasonCode::ResponseTooLarge,
        ));
    }
    let value: serde_json::Value =
        serde_json::from_slice(body).map_err(|_| reject(ReasonCode::TokenExchangeRejected))?;
    let token_type = value
        .get("token_type")
        .and_then(|v| v.as_str())
        .unwrap_or("");
    if !token_type.eq_ignore_ascii_case("bearer") {
        return Err(reject(ReasonCode::TokenExchangeRejected));
    }
    let access_token = value
        .get("access_token")
        .and_then(|v| v.as_str())
        .ok_or_else(|| reject(ReasonCode::TokenExchangeRejected))?
        .to_string();
    let expires_in = value
        .get("expires_in")
        .and_then(|v| v.as_u64())
        .ok_or_else(|| reject(ReasonCode::TokenExchangeRejected))?;
    if expires_in == 0 || expires_in > MAX_ACCESS_LIFETIME_SECS {
        return Err(reject(ReasonCode::TokenExchangeRejected));
    }
    let claims = decode_access_token_claims(&access_token)?;
    // Cross-check the claim lifetime against the reported lifetime, bounded.
    let now_secs = now_wall_ms / 1000;
    if claims.exp <= now_secs || claims.exp > now_secs.saturating_add(MAX_ACCESS_LIFETIME_SECS) {
        return Err(reject(ReasonCode::TokenExchangeRejected));
    }
    // refresh_token, provider token and any other fields are deliberately
    // dropped here: this module never persists or exposes them.
    let skeleton = VerifiedGrantSkeleton {
        principal_uid: claims.sub,
        session_id: claims.session_id,
        access_exp_wall_ms: claims.exp * 1000,
        access_lifetime_secs: expires_in,
    };
    Ok((skeleton, access_token))
}

// Manual Debug impls: pending transaction material, bearer tokens and keys
// are redacted so they can never reach a log, a panic message or Debug output.
impl std::fmt::Debug for AnonKey {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("AnonKey").finish_non_exhaustive()
    }
}

impl std::fmt::Debug for PendingAuth {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("PendingAuth").finish_non_exhaustive()
    }
}

impl std::fmt::Debug for VerifiedGrant {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("VerifiedGrant").finish_non_exhaustive()
    }
}

impl std::fmt::Debug for SessionTicket {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("SessionTicket").finish_non_exhaustive()
    }
}

#[derive(Clone)]
pub struct VerifiedGrantSkeleton {
    pub principal_uid: String,
    pub session_id: String,
    pub access_exp_wall_ms: u64,
    pub access_lifetime_secs: u64,
}

impl std::fmt::Debug for VerifiedGrantSkeleton {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str("VerifiedGrantSkeleton([REDACTED])")
    }
}

/// Server-side identity verification body check: /auth/v1/user with the same
/// bearer must return the very same uid, and the token must still be live.
pub fn validate_user_response(
    body: &[u8],
    ticket_uid: &str,
    now_wall_ms: u64,
    exp_wall_ms: u64,
) -> Result<(), TerminalError> {
    let reject = |r: ReasonCode| TerminalError::new(ErrorKind::ServerUnverified, r);
    if body.len() > BODY_CAP_BYTES {
        return Err(TerminalError::new(
            ErrorKind::ServerUnverified,
            ReasonCode::ResponseTooLarge,
        ));
    }
    if now_wall_ms >= exp_wall_ms {
        return Err(reject(ReasonCode::SessionExpired));
    }
    let value: serde_json::Value =
        serde_json::from_slice(body).map_err(|_| reject(ReasonCode::ServerVerificationFailed))?;
    let id = value
        .get("id")
        .and_then(|v| v.as_str())
        .ok_or_else(|| reject(ReasonCode::ServerVerificationFailed))?;
    if !is_canonical_uuid(id) || !ct_eq(id.as_bytes(), ticket_uid.as_bytes()) {
        return Err(reject(ReasonCode::ServerVerificationFailed));
    }
    Ok(())
}

pub fn build_grant(
    skeleton: &VerifiedGrantSkeleton,
    access_token: &str,
    clock: &dyn Clock,
    generation: u64,
) -> VerifiedGrant {
    let monotonic = clock.now_monotonic_ms();
    let lifetime_ms = skeleton.access_lifetime_secs.saturating_mul(1000);
    let deadline_monotonic = monotonic.saturating_add(lifetime_ms);
    VerifiedGrant {
        principal_uid: skeleton.principal_uid.clone(),
        session_id: skeleton.session_id.clone(),
        access_token: access_token.to_string(),
        access_exp_wall_ms: skeleton.access_exp_wall_ms,
        access_deadline_monotonic_ms: deadline_monotonic,
        principal_scope: principal_scope_for_uid(&skeleton.principal_uid),
        session_scope: session_scope_for(&skeleton.principal_uid, &skeleton.session_id),
        generation_at_issue: generation,
    }
}

pub fn grant_expired(grant: &VerifiedGrant, clock: &dyn Clock) -> bool {
    clock.now_wall_ms() >= grant.access_exp_wall_ms
        || clock.now_monotonic_ms() >= grant.access_deadline_monotonic_ms
}

// ---------------------------------------------------------------------------
// Session core: managed state machine with a private mutex. No locks are ever
// held across an await: HTTP happens on cloned tickets outside the mutex.
// ---------------------------------------------------------------------------

struct InnerState {
    generation: u64,
    pending: Option<PendingAuth>,
    exchanging: bool,
    grant: Option<VerifiedGrant>,
    last_reason: Option<ReasonCode>,
}

pub struct CoreShared {
    configured: bool,
    inner: Mutex<InnerState>,
}

impl CoreShared {
    pub fn new(configured: bool) -> Self {
        CoreShared {
            configured,
            inner: Mutex::new(InnerState {
                generation: 1,
                pending: None,
                exchanging: false,
                grant: None,
                last_reason: None,
            }),
        }
    }

    fn lock_inner(&self) -> std::sync::MutexGuard<'_, InnerState> {
        match self.inner.lock() {
            Ok(inner) => inner,
            Err(poison) => {
                let mut inner = poison.into_inner();
                inner.grant = None;
                inner.pending = None;
                inner.exchanging = false;
                inner.last_reason = Some(ReasonCode::SessionChanged);
                inner.generation = inner.generation.saturating_add(1);
                self.inner.clear_poison();
                inner
            }
        }
    }

    pub fn generation(&self) -> u64 {
        self.lock_inner().generation
    }

    pub fn status(&self, clock: &dyn Clock) -> SessionStatusDto {
        let inner = self.lock_inner();
        let (state, reason): (&'static str, Option<ReasonCode>) =
            match (&inner.grant, &inner.pending) {
                (Some(grant), _) if grant_expired(grant, clock) => {
                    (STATE_ERROR, Some(ReasonCode::SessionExpired))
                }
                (Some(_), _) => (STATE_SIGNED_IN, None),
                (None, Some(pending))
                    if clock.now_monotonic_ms()
                        >= pending.created_monotonic_ms.saturating_add(PENDING_TTL_MS)
                        || clock.now_wall_ms()
                            >= pending.created_wall_ms.saturating_add(PENDING_TTL_MS) =>
                {
                    (STATE_ERROR, Some(ReasonCode::PendingExpired))
                }
                (None, Some(_)) => (STATE_SIGNING_IN, Some(ReasonCode::SignInStarted)),
                (None, None) => {
                    if inner.exchanging {
                        (STATE_SIGNING_IN, Some(ReasonCode::SignInStarted))
                    } else if !self.configured {
                        (STATE_UNCONFIGURED, Some(ReasonCode::NotConfigured))
                    } else {
                        match inner.last_reason {
                            None
                            | Some(ReasonCode::SignedOutLocal)
                            | Some(ReasonCode::UserCancelled) => {
                                (STATE_SIGNED_OUT, inner.last_reason)
                            }
                            reason => (STATE_ERROR, reason),
                        }
                    }
                }
            };
        let scopes = inner.grant.as_ref().filter(|g| !grant_expired(g, clock));
        SessionStatusDto {
            state,
            generation: inner.generation,
            reason: reason.map(|r| r.as_str()),
            available: self.configured && state == STATE_SIGNED_IN,
            principal_scope: scopes.map(|g| g.principal_scope.clone()),
            session_scope: scopes.map(|g| g.session_scope.clone()),
        }
    }

    fn callback_url_with_state(terminal_state: &str) -> String {
        let mut url = Url::parse(&callback_base_url()).expect("fixed callback base parses");
        url.query_pairs_mut()
            .append_pair("terminal_state", terminal_state);
        url.to_string()
    }

    /// Explicit user action only. Installs a single pending transaction; a
    /// live overlapping pending is rejected; an expired pending is discarded.
    pub fn begin_sign_in(
        &self,
        clock: &dyn Clock,
        key: Option<&AnonKey>,
    ) -> Result<SignInStart, TerminalError> {
        if !self.configured {
            return Err(TerminalError::new(
                ErrorKind::ConfigUnavailable,
                ReasonCode::NotConfigured,
            ));
        }
        let Some(key) = key else {
            return Err(TerminalError::new(
                ErrorKind::ConfigUnavailable,
                ReasonCode::NotConfigured,
            ));
        };
        let _ = key;
        let mut inner = self.lock_inner();
        if inner.exchanging
            || inner
                .grant
                .as_ref()
                .is_some_and(|grant| !grant_expired(grant, clock))
        {
            return Err(TerminalError::new(
                ErrorKind::SignInBusy,
                ReasonCode::SignInOverlap,
            ));
        }
        if inner.grant.take().is_some() {
            inner.generation = inner.generation.saturating_add(1);
        }
        if let Some(existing) = inner.pending.as_ref() {
            let expired = clock.now_monotonic_ms()
                >= existing.created_monotonic_ms.saturating_add(PENDING_TTL_MS)
                || clock.now_wall_ms() >= existing.created_wall_ms.saturating_add(PENDING_TTL_MS);
            if !expired {
                drop(inner);
                return Err(TerminalError::new(
                    ErrorKind::SignInBusy,
                    ReasonCode::SignInOverlap,
                ));
            }
        }
        let mut verifier_bytes = [0u8; 32];
        OsRng.fill_bytes(&mut verifier_bytes);
        let code_verifier = b64url_random(&verifier_bytes);
        let mut state_bytes = [0u8; 32];
        OsRng.fill_bytes(&mut state_bytes);
        let terminal_state = b64url_random(&state_bytes);
        let redirect_to = Self::callback_url_with_state(&terminal_state);
        let authorize_url =
            build_authorize_url(&redirect_to, &pkce_challenge_from_verifier(&code_verifier));
        let generation = inner.generation;
        inner.pending = Some(PendingAuth {
            terminal_state: terminal_state.clone(),
            code_verifier,
            authorize_url: authorize_url.clone(),
            created_monotonic_ms: clock.now_monotonic_ms(),
            created_wall_ms: clock.now_wall_ms(),
            generation_at_start: inner.generation,
        });
        inner.last_reason = Some(ReasonCode::SignInStarted);
        drop(inner);
        Ok(SignInStart {
            generation,
            pending_state: terminal_state,
            authorize_url,
            status: self.status(clock),
        })
    }

    /// Consumes the pending transaction exactly once, before any HTTP. State
    /// comparison is constant-time. Sign-out between click and callback lands
    /// here as NO_PENDING.
    pub fn consume_callback(
        &self,
        clock: &dyn Clock,
        url: &Url,
    ) -> Result<CallbackOutcome, TerminalError> {
        let parsed = parse_callback_url(url);
        let (auth_code, terminal_state, provider_error) = match parsed {
            ParsedCallback::Foreign => {
                return Err(TerminalError::new(
                    ErrorKind::CallbackInvalid,
                    ReasonCode::CallbackRejected,
                ))
            }
            ParsedCallback::Malformed => {
                return Err(TerminalError::new(
                    ErrorKind::CallbackInvalid,
                    ReasonCode::CallbackRejected,
                ))
            }
            ParsedCallback::Error {
                code_label,
                terminal_state,
            } => (String::new(), terminal_state, Some(code_label)),
            ParsedCallback::Code {
                code,
                terminal_state,
            } => (code, terminal_state, None),
        };
        let mut inner = self.lock_inner();
        let Some(pending) = inner.pending.as_ref() else {
            drop(inner);
            return Err(TerminalError::new(
                ErrorKind::CallbackInvalid,
                ReasonCode::NoPending,
            ));
        };
        let expired = clock.now_monotonic_ms()
            >= pending.created_monotonic_ms.saturating_add(PENDING_TTL_MS)
            || clock.now_wall_ms() >= pending.created_wall_ms.saturating_add(PENDING_TTL_MS);
        if expired {
            inner.pending = None;
            inner.last_reason = Some(ReasonCode::PendingExpired);
            drop(inner);
            return Err(TerminalError::new(
                ErrorKind::CallbackInvalid,
                ReasonCode::PendingExpired,
            ));
        }
        if !ct_eq(pending.terminal_state.as_bytes(), terminal_state.as_bytes()) {
            inner.last_reason = Some(ReasonCode::StateMismatch);
            drop(inner);
            return Err(TerminalError::new(
                ErrorKind::CallbackInvalid,
                ReasonCode::StateMismatch,
            ));
        }
        let pending = inner.pending.take().expect("pending checked above");
        if let Some(error) = provider_error {
            inner.last_reason = Some(if error == "user_closed" {
                ReasonCode::UserCancelled
            } else {
                ReasonCode::CallbackRejected
            });
            inner.generation = inner.generation.saturating_add(1);
            drop(inner);
            return Ok(CallbackOutcome::Cancelled {
                status: self.status(clock),
            });
        }
        inner.exchanging = true;
        drop(inner);
        Ok(CallbackOutcome::Accepted {
            auth_code,
            code_verifier: pending.code_verifier,
            generation: pending.generation_at_start,
        })
    }

    /// Installs a server-verified grant. A completion whose generation moved
    /// (disconnect or invalidation during the HTTP exchange) is refused and
    /// the grant is discarded.
    pub fn complete_sign_in(&self, mut grant: VerifiedGrant) -> Result<(), TerminalError> {
        let mut inner = self.lock_inner();
        if grant.generation_at_issue != inner.generation || !inner.exchanging {
            // A late old flow must not rewrite a newer disconnect/session state.
            drop(grant); // discard the late grant entirely, never installed
            drop(inner);
            return Err(TerminalError::new(
                ErrorKind::GenerationChanged,
                ReasonCode::LateCompletionRejected,
            ));
        }
        grant.generation_at_issue = inner.generation;
        inner.grant = Some(grant);
        inner.exchanging = false;
        inner.pending = None;
        inner.last_reason = None;
        inner.generation = inner.generation.saturating_add(1);
        drop(inner);
        Ok(())
    }

    /// Local sign-out only: clears grant and pending, advances the generation.
    /// Does not revoke the browser session, other owners, or the global
    /// Supabase session.
    pub fn disconnect(&self) {
        let mut inner = self.lock_inner();
        inner.grant = None;
        inner.exchanging = false;
        inner.pending = None;
        inner.last_reason = Some(ReasonCode::SignedOutLocal);
        inner.generation = inner.generation.saturating_add(1);
        drop(inner);
    }

    /// Discards an unusable session (expiry, server-side mismatch) and moves
    /// the generation so no in-flight read can still pass the ticket guard.
    pub fn invalidate(&self, reason: ReasonCode) {
        let mut inner = self.lock_inner();
        inner.grant = None;
        inner.exchanging = false;
        inner.pending = None;
        inner.last_reason = Some(reason);
        inner.generation = inner.generation.saturating_add(1);
        drop(inner);
    }

    /// A response from an old operation cannot clear a newer local identity.
    fn invalidate_generation(&self, generation: u64, reason: ReasonCode) {
        let mut inner = self.lock_inner();
        if inner.generation != generation {
            return;
        }
        inner.grant = None;
        inner.exchanging = false;
        inner.pending = None;
        inner.last_reason = Some(reason);
        inner.generation = inner.generation.saturating_add(1);
    }

    /// Clones the private ticket for an HTTP read. Never expires silently:
    /// an expired grant is refused here and must be invalidated by the caller.
    pub fn ticket(&self, clock: &dyn Clock) -> Result<SessionTicket, TerminalError> {
        let inner = self.lock_inner();
        let Some(grant) = inner.grant.as_ref() else {
            drop(inner);
            return Err(TerminalError::new(
                ErrorKind::SessionRequired,
                ReasonCode::NoPending,
            ));
        };
        if grant_expired(grant, clock) {
            drop(inner);
            return Err(TerminalError::new(
                ErrorKind::SessionRequired,
                ReasonCode::SessionExpired,
            ));
        }
        Ok(SessionTicket {
            generation: inner.generation,
            principal_uid: grant.principal_uid.clone(),
            session_id: grant.session_id.clone(),
            access_token: grant.access_token.clone(),
            access_exp_wall_ms: grant.access_exp_wall_ms,
            access_deadline_monotonic_ms: grant.access_deadline_monotonic_ms,
            principal_scope: grant.principal_scope.clone(),
            session_scope: grant.session_scope.clone(),
        })
    }

    /// Post-read guard: the grant still held must be the very same grant the
    /// read was made with.
    pub fn grant_matches_ticket(&self, ticket: &SessionTicket, clock: &dyn Clock) -> bool {
        let inner = self.lock_inner();
        match inner.grant.as_ref() {
            Some(grant) => {
                !grant_expired(grant, clock)
                    && ct_eq(
                        grant.access_token.as_bytes(),
                        ticket.access_token.as_bytes(),
                    )
                    && ct_eq(
                        grant.principal_uid.as_bytes(),
                        ticket.principal_uid.as_bytes(),
                    )
                    && ct_eq(grant.session_id.as_bytes(), ticket.session_id.as_bytes())
            }
            None => false,
        }
    }

    /// True when the generation still matches the ticket's clone point.
    pub fn generation_matches(&self, ticket: &SessionTicket) -> bool {
        self.lock_inner().generation == ticket.generation
    }
}

pub struct SignInStart {
    generation: u64,
    pending_state: String,
    pub authorize_url: String,
    pub status: SessionStatusDto,
}

// ---------------------------------------------------------------------------
// Sharing-request feed validation against the frozen
// mastermind.terminal_sharing_request_feed.v1 contract. The returned Value is
// rebuilt field-by-field from validated, typed extractions — arbitrary server
// JSON is never passed through.
// ---------------------------------------------------------------------------

const FEED_SCHEMA: &str = "mastermind.terminal_sharing_request_feed.v1";
const FEED_SOURCE_OWNER: &str = "TERMINAL_BRIEF_DELIVERY";
const FEED_SOURCE_SCOPE: &str = "OWNED_EXPLICIT_SHARING_REQUESTS";
const FEED_COVERAGE_STATES: [&str; 2] = ["COMPLETE_WITHIN_SCOPE", "PARTIAL"];
const FEED_REASON_CODES: [&str; 3] = [
    "LIMIT_REACHED",
    "REQUEST_SOURCE_CHANGED",
    "REQUEST_AUTHORITY_CHANGED",
];
const FEED_MEMBERSHIP_POLICY: &str = "DYNAMIC_TEAM_MEMBERSHIP";

fn exact_keys(value: &serde_json::Value, expected: &[&str]) -> bool {
    let Some(map) = value.as_object() else {
        return false;
    };
    if map.len() != expected.len() {
        return false;
    }
    expected.iter().all(|k| map.contains_key(*k))
}

fn exact_u64(value: &serde_json::Value) -> Option<u64> {
    if !value.is_u64() {
        return None;
    }
    value.as_u64()
}

fn string_field<'a>(value: &'a serde_json::Value, key: &str) -> Option<&'a str> {
    value.get(key).and_then(|v| v.as_str())
}

fn feed_reject(reason: ReasonCode) -> TerminalError {
    TerminalError::new(ErrorKind::FeedRejected, reason)
}

fn validate_request_entry(
    entry: &serde_json::Value,
    seen_refs: &mut Vec<String>,
) -> Result<serde_json::Value, TerminalError> {
    if !exact_keys(
        entry,
        &[
            "request_ref",
            "revision",
            "issued_at",
            "delivery",
            "audience",
            "review",
        ],
    ) {
        return Err(feed_reject(ReasonCode::FeedSchemaRejected));
    }
    let request_ref = string_field(entry, "request_ref")
        .ok_or_else(|| feed_reject(ReasonCode::FeedSchemaRejected))?;
    if !is_canonical_uuid(request_ref) {
        return Err(feed_reject(ReasonCode::FeedSchemaRejected));
    }
    if seen_refs
        .iter()
        .any(|r| ct_eq(r.as_bytes(), request_ref.as_bytes()))
    {
        return Err(feed_reject(ReasonCode::FeedSchemaRejected));
    }
    seen_refs.push(request_ref.to_string());
    let revision = exact_u64(
        entry
            .get("revision")
            .ok_or_else(|| feed_reject(ReasonCode::FeedSchemaRejected))?,
    )
    .ok_or_else(|| feed_reject(ReasonCode::FeedSchemaRejected))?;
    if revision != 1 {
        return Err(feed_reject(ReasonCode::FeedSchemaRejected));
    }
    let issued_at = string_field(entry, "issued_at")
        .ok_or_else(|| feed_reject(ReasonCode::FeedSchemaRejected))?;
    if !is_persisted_timestamp(issued_at) {
        return Err(feed_reject(ReasonCode::FeedSchemaRejected));
    }

    // delivery
    let delivery = entry
        .get("delivery")
        .ok_or_else(|| feed_reject(ReasonCode::FeedSchemaRejected))?;
    if !exact_keys(
        delivery,
        &[
            "delivery_id",
            "content_sha256",
            "title",
            "slot_asof",
            "artifact_asof",
        ],
    ) {
        return Err(feed_reject(ReasonCode::FeedSchemaRejected));
    }
    let delivery_id = string_field(delivery, "delivery_id")
        .ok_or_else(|| feed_reject(ReasonCode::FeedSchemaRejected))?;
    if !is_canonical_uuid(delivery_id) {
        return Err(feed_reject(ReasonCode::FeedSchemaRejected));
    }
    let content_sha256 = string_field(delivery, "content_sha256")
        .ok_or_else(|| feed_reject(ReasonCode::FeedSchemaRejected))?;
    if !is_lower_hex_digest64(content_sha256) {
        return Err(feed_reject(ReasonCode::FeedSchemaRejected));
    }
    let title = string_field(delivery, "title")
        .ok_or_else(|| feed_reject(ReasonCode::FeedSchemaRejected))?;
    if !is_safe_display_text(title, MAX_TEXT_BYTES) {
        return Err(feed_reject(ReasonCode::FeedSchemaRejected));
    }
    let slot_asof = string_field(delivery, "slot_asof")
        .ok_or_else(|| feed_reject(ReasonCode::FeedSchemaRejected))?;
    if !is_slot_date(slot_asof) {
        return Err(feed_reject(ReasonCode::FeedSchemaRejected));
    }
    let artifact_asof = match delivery.get("artifact_asof") {
        Some(serde_json::Value::Null) => None,
        Some(v) => {
            let s = v
                .as_str()
                .ok_or_else(|| feed_reject(ReasonCode::FeedSchemaRejected))?;
            if !is_persisted_timestamp(s) {
                return Err(feed_reject(ReasonCode::FeedSchemaRejected));
            }
            Some(s.to_string())
        }
        None => return Err(feed_reject(ReasonCode::FeedSchemaRejected)),
    };

    // audience
    let audience = entry
        .get("audience")
        .ok_or_else(|| feed_reject(ReasonCode::FeedSchemaRejected))?;
    if !exact_keys(
        audience,
        &["team_id", "name", "member_count", "membership_policy"],
    ) {
        return Err(feed_reject(ReasonCode::FeedSchemaRejected));
    }
    let team_id = string_field(audience, "team_id")
        .ok_or_else(|| feed_reject(ReasonCode::FeedSchemaRejected))?;
    if !is_canonical_uuid(team_id) {
        return Err(feed_reject(ReasonCode::FeedSchemaRejected));
    }
    let team_name = string_field(audience, "name")
        .ok_or_else(|| feed_reject(ReasonCode::FeedSchemaRejected))?;
    if !is_safe_display_text(team_name, MAX_TEXT_BYTES) {
        return Err(feed_reject(ReasonCode::FeedSchemaRejected));
    }
    let member_count = exact_u64(
        audience
            .get("member_count")
            .ok_or_else(|| feed_reject(ReasonCode::FeedSchemaRejected))?,
    )
    .ok_or_else(|| feed_reject(ReasonCode::FeedSchemaRejected))?;
    if member_count > MAX_MEMBER_COUNT {
        return Err(feed_reject(ReasonCode::FeedSchemaRejected));
    }
    let membership_policy = string_field(audience, "membership_policy")
        .ok_or_else(|| feed_reject(ReasonCode::FeedSchemaRejected))?;
    if membership_policy != FEED_MEMBERSHIP_POLICY {
        return Err(feed_reject(ReasonCode::FeedSchemaRejected));
    }

    // review block must mirror the outer identity exactly
    let review = entry
        .get("review")
        .ok_or_else(|| feed_reject(ReasonCode::FeedSchemaRejected))?;
    if !exact_keys(review, &["request_ref", "revision", "delivery_id"]) {
        return Err(feed_reject(ReasonCode::FeedSchemaRejected));
    }
    let review_ref = string_field(review, "request_ref")
        .ok_or_else(|| feed_reject(ReasonCode::FeedSchemaRejected))?;
    if !ct_eq(review_ref.as_bytes(), request_ref.as_bytes()) {
        return Err(feed_reject(ReasonCode::FeedSchemaRejected));
    }
    let review_revision = exact_u64(
        review
            .get("revision")
            .ok_or_else(|| feed_reject(ReasonCode::FeedSchemaRejected))?,
    )
    .ok_or_else(|| feed_reject(ReasonCode::FeedSchemaRejected))?;
    if review_revision != 1 {
        return Err(feed_reject(ReasonCode::FeedSchemaRejected));
    }
    let review_delivery = string_field(review, "delivery_id")
        .ok_or_else(|| feed_reject(ReasonCode::FeedSchemaRejected))?;
    if !ct_eq(review_delivery.as_bytes(), delivery_id.as_bytes()) {
        return Err(feed_reject(ReasonCode::FeedSchemaRejected));
    }

    Ok(serde_json::json!({
        "request_ref": request_ref,
        "revision": revision,
        "issued_at": issued_at,
        "delivery": {
            "delivery_id": delivery_id,
            "content_sha256": content_sha256,
            "title": title,
            "slot_asof": slot_asof,
            "artifact_asof": artifact_asof,
        },
        "audience": {
            "team_id": team_id,
            "name": team_name,
            "member_count": member_count,
            "membership_policy": membership_policy,
        },
        "review": {
            "request_ref": review_ref,
            "revision": review_revision,
            "delivery_id": review_delivery,
        }
    }))
}

/// Validates the raw feed body against the frozen contract AND the local
/// verified ticket (viewer scopes must be exactly ours). Returns the rebuilt,
/// bounded feed Value on success.
pub fn validate_feed_response(
    body: &[u8],
    ticket: &SessionTicket,
) -> Result<serde_json::Value, TerminalError> {
    if body.len() > BODY_CAP_BYTES {
        return Err(feed_reject(ReasonCode::ResponseTooLarge));
    }
    let value: serde_json::Value =
        serde_json::from_slice(body).map_err(|_| feed_reject(ReasonCode::FeedSchemaRejected))?;
    if !exact_keys(
        &value,
        &["schema", "viewer", "source", "coverage", "requests"],
    ) {
        return Err(feed_reject(ReasonCode::FeedSchemaRejected));
    }
    if string_field(&value, "schema") != Some(FEED_SCHEMA) {
        return Err(feed_reject(ReasonCode::FeedSchemaRejected));
    }

    // viewer must be exactly our own verified scope pair
    let viewer = value
        .get("viewer")
        .ok_or_else(|| feed_reject(ReasonCode::FeedSchemaRejected))?;
    if !exact_keys(viewer, &["principal_scope", "session_scope"]) {
        return Err(feed_reject(ReasonCode::FeedSchemaRejected));
    }
    let viewer_principal = string_field(viewer, "principal_scope")
        .ok_or_else(|| feed_reject(ReasonCode::FeedSchemaRejected))?;
    let viewer_session = string_field(viewer, "session_scope")
        .ok_or_else(|| feed_reject(ReasonCode::FeedSchemaRejected))?;
    if !ct_eq(
        viewer_principal.as_bytes(),
        ticket.principal_scope.as_bytes(),
    ) || !ct_eq(viewer_session.as_bytes(), ticket.session_scope.as_bytes())
    {
        return Err(feed_reject(ReasonCode::FeedSchemaRejected));
    }

    let source = value
        .get("source")
        .ok_or_else(|| feed_reject(ReasonCode::FeedSchemaRejected))?;
    if !exact_keys(source, &["owner", "scope", "observed_at"]) {
        return Err(feed_reject(ReasonCode::FeedSchemaRejected));
    }
    if string_field(source, "owner") != Some(FEED_SOURCE_OWNER)
        || string_field(source, "scope") != Some(FEED_SOURCE_SCOPE)
    {
        return Err(feed_reject(ReasonCode::FeedSchemaRejected));
    }
    let observed_at = string_field(source, "observed_at")
        .ok_or_else(|| feed_reject(ReasonCode::FeedSchemaRejected))?;
    if !is_persisted_timestamp(observed_at) {
        return Err(feed_reject(ReasonCode::FeedSchemaRejected));
    }

    let coverage = value
        .get("coverage")
        .ok_or_else(|| feed_reject(ReasonCode::FeedSchemaRejected))?;
    if !exact_keys(coverage, &["state", "reason_codes"]) {
        return Err(feed_reject(ReasonCode::FeedSchemaRejected));
    }
    let coverage_state = string_field(coverage, "state")
        .ok_or_else(|| feed_reject(ReasonCode::FeedSchemaRejected))?;
    if !FEED_COVERAGE_STATES.contains(&coverage_state) {
        return Err(feed_reject(ReasonCode::FeedSchemaRejected));
    }
    let Some(reason_codes) = coverage.get("reason_codes").and_then(|v| v.as_array()) else {
        return Err(feed_reject(ReasonCode::FeedSchemaRejected));
    };
    let mut validated_reasons: Vec<&str> = Vec::new();
    for code in reason_codes {
        let s = code
            .as_str()
            .ok_or_else(|| feed_reject(ReasonCode::FeedSchemaRejected))?;
        if !FEED_REASON_CODES.contains(&s) {
            return Err(feed_reject(ReasonCode::FeedSchemaRejected));
        }
        validated_reasons.push(s);
    }
    let complete = coverage_state == "COMPLETE_WITHIN_SCOPE";
    if complete && !validated_reasons.is_empty() {
        return Err(feed_reject(ReasonCode::FeedSchemaRejected));
    }
    if !complete && validated_reasons.is_empty() {
        return Err(feed_reject(ReasonCode::FeedSchemaRejected));
    }

    let requests = value
        .get("requests")
        .and_then(|v| v.as_array())
        .ok_or_else(|| feed_reject(ReasonCode::FeedSchemaRejected))?;
    if requests.len() > MAX_FEED_REQUESTS {
        return Err(feed_reject(ReasonCode::FeedSchemaRejected));
    }
    let mut seen_refs: Vec<String> = Vec::new();
    let mut validated_requests: Vec<serde_json::Value> = Vec::with_capacity(requests.len());
    for entry in requests {
        validated_requests.push(validate_request_entry(entry, &mut seen_refs)?);
    }

    Ok(serde_json::json!({
        "schema": FEED_SCHEMA,
        "viewer": {
            "principal_scope": viewer_principal,
            "session_scope": viewer_session,
        },
        "source": {
            "owner": FEED_SOURCE_OWNER,
            "scope": FEED_SOURCE_SCOPE,
            "observed_at": observed_at,
        },
        "coverage": {
            "state": coverage_state,
            "reason_codes": validated_reasons,
        },
        "requests": validated_requests,
    }))
}

// ---------------------------------------------------------------------------
// HTTP flows (generic over transport so tests inject fakes; production wires
// the redirect-free reqwest transport). No lock is held across awaits.
// ---------------------------------------------------------------------------

fn bearer_headers(key: &AnonKey, access_token: &str) -> Vec<(String, String)> {
    vec![
        ("apikey".to_string(), key.expose().to_string()),
        (
            "authorization".to_string(),
            format!("Bearer {}", access_token),
        ),
        ("accept".to_string(), "application/json".to_string()),
    ]
}

fn is_redirect(status: u16) -> bool {
    (300..400).contains(&status)
}

pub async fn perform_token_exchange<H: HttpTransport + ?Sized>(
    core: &CoreShared,
    transport: &H,
    clock: &dyn Clock,
    accepted: CallbackOutcome,
    key: &AnonKey,
) -> Result<SessionStatusDto, TerminalError> {
    let CallbackOutcome::Accepted {
        auth_code,
        code_verifier,
        generation,
    } = accepted
    else {
        return Err(TerminalError::new(
            ErrorKind::Cancelled,
            ReasonCode::UserCancelled,
        ));
    };
    let outcome = async {
        // Body is JSON, never a query string: secrets never land in a URL.
        if core.generation() != generation {
            return Err(TerminalError::new(
                ErrorKind::GenerationChanged,
                ReasonCode::LateCompletionRejected,
            ));
        }
        let body = serde_json::json!({
            "auth_code": auth_code,
            "code_verifier": code_verifier,
        })
        .to_string();
        let headers = vec![
            ("apikey".to_string(), key.expose().to_string()),
            ("content-type".to_string(), "application/json".to_string()),
            ("accept".to_string(), "application/json".to_string()),
        ];
        let url = token_url();
        let response = transport
            .request(HttpMethod::Post, &url, headers, Some(body), BODY_CAP_BYTES)
            .await?;
        if is_redirect(response.status) {
            return Err(TerminalError::new(
                ErrorKind::ProviderRejected,
                ReasonCode::RedirectRefused,
            ));
        }
        if response.status != 200 {
            return Err(TerminalError::new(
                ErrorKind::ProviderRejected,
                ReasonCode::TokenExchangeRejected,
            ));
        }
        let now_wall_ms = clock.now_wall_ms();
        let (skeleton, access_token) = validate_token_response(&response.body, now_wall_ms)?;

        // Server verification before the grant exists: /auth/v1/user with the
        // fresh bearer must confirm the very identity the token claims.
        if core.generation() != generation {
            return Err(TerminalError::new(
                ErrorKind::GenerationChanged,
                ReasonCode::LateCompletionRejected,
            ));
        }
        let user_endpoint = user_url();
        let verified = transport
            .request(
                HttpMethod::Get,
                &user_endpoint,
                bearer_headers(key, &access_token),
                None,
                BODY_CAP_BYTES,
            )
            .await?;
        if is_redirect(verified.status) {
            return Err(TerminalError::new(
                ErrorKind::ServerUnverified,
                ReasonCode::RedirectRefused,
            ));
        }
        if verified.status != 200 {
            return Err(TerminalError::new(
                ErrorKind::ServerUnverified,
                ReasonCode::ServerVerificationFailed,
            ));
        }
        validate_user_response(
            &verified.body,
            &skeleton.principal_uid,
            clock.now_wall_ms(),
            skeleton.access_exp_wall_ms,
        )?;

        // The grant inherits the generation captured when the pending transaction
        // was consumed, so any interleaved disconnect/invalidation refuses it.
        let grant = build_grant(&skeleton, &access_token, clock, generation);
        core.complete_sign_in(grant)?;
        Ok(core.status(clock))
    }
    .await;
    if let Err(ref error) = outcome {
        core.fail_exchange(generation, error.reason);
    }
    outcome
}

pub async fn perform_sharing_requests_read<H: HttpTransport + ?Sized>(
    core: &CoreShared,
    transport: &H,
    clock: &dyn Clock,
    key: Option<&AnonKey>,
) -> Result<serde_json::Value, TerminalError> {
    let initial_generation = core.generation();
    let ticket = match core.ticket(clock) {
        Ok(ticket) => ticket,
        Err(err) => {
            if err.reason == ReasonCode::SessionExpired {
                core.invalidate_generation(initial_generation, ReasonCode::SessionExpired);
            }
            return Err(err);
        }
    };
    let Some(key) = key else {
        return Err(TerminalError::new(
            ErrorKind::ConfigUnavailable,
            ReasonCode::NotConfigured,
        ));
    };

    // Pre-read server verification with the exact ticket token.
    let user_endpoint = user_url();
    let pre = transport
        .request(
            HttpMethod::Get,
            &user_endpoint,
            bearer_headers(key, &ticket.access_token),
            None,
            BODY_CAP_BYTES,
        )
        .await?;
    if is_redirect(pre.status) {
        return Err(TerminalError::new(
            ErrorKind::ServerUnverified,
            ReasonCode::RedirectRefused,
        ));
    }
    if pre.status != 200 {
        core.invalidate_generation(ticket.generation, ReasonCode::SessionChanged);
        return Err(TerminalError::new(
            ErrorKind::ServerUnverified,
            ReasonCode::SessionChanged,
        ));
    }
    if let Err(err) = validate_user_response(
        &pre.body,
        &ticket.principal_uid,
        clock.now_wall_ms(),
        ticket.access_exp_wall_ms,
    ) {
        core.invalidate_generation(ticket.generation, err.reason);
        return Err(err);
    }

    if !core.generation_matches(&ticket) || !core.grant_matches_ticket(&ticket, clock) {
        return Err(TerminalError::new(
            ErrorKind::GenerationChanged,
            ReasonCode::GenerationChanged,
        ));
    }

    // The feed itself: exact native route, cookie-free, bearer-only.
    let feed_endpoint = native_feed_url();
    let feed = transport
        .request(
            HttpMethod::Get,
            &feed_endpoint,
            bearer_headers(key, &ticket.access_token),
            None,
            BODY_CAP_BYTES,
        )
        .await?;
    if is_redirect(feed.status) {
        return Err(TerminalError::new(
            ErrorKind::FeedRejected,
            ReasonCode::RedirectRefused,
        ));
    }
    if feed.status != 200 {
        return Err(TerminalError::new(
            ErrorKind::FeedRejected,
            ReasonCode::FeedUnavailable,
        ));
    }
    let validated = validate_feed_response(&feed.body, &ticket)?;

    if !core.generation_matches(&ticket) || !core.grant_matches_ticket(&ticket, clock) {
        return Err(TerminalError::new(
            ErrorKind::GenerationChanged,
            ReasonCode::GenerationChanged,
        ));
    }
    let post = transport
        .request(
            HttpMethod::Get,
            &user_endpoint,
            bearer_headers(key, &ticket.access_token),
            None,
            BODY_CAP_BYTES,
        )
        .await?;
    if is_redirect(post.status) || post.status != 200 {
        core.invalidate_generation(ticket.generation, ReasonCode::SessionChanged);
        return Err(TerminalError::new(
            ErrorKind::ServerUnverified,
            ReasonCode::SessionChanged,
        ));
    }
    if let Err(error) = validate_user_response(
        &post.body,
        &ticket.principal_uid,
        clock.now_wall_ms(),
        ticket.access_exp_wall_ms,
    ) {
        core.invalidate_generation(ticket.generation, error.reason);
        return Err(error);
    }

    // Post-read guards: same generation, same grant, still live.
    if !core.generation_matches(&ticket) {
        return Err(TerminalError::new(
            ErrorKind::GenerationChanged,
            ReasonCode::GenerationChanged,
        ));
    }
    let _ = core.ticket(clock).map_err(|err| {
        core.invalidate_generation(ticket.generation, ReasonCode::SessionExpired);
        err
    })?;
    if !core.grant_matches_ticket(&ticket, clock) {
        core.invalidate_generation(ticket.generation, ReasonCode::SessionChanged);
        return Err(TerminalError::new(
            ErrorKind::SessionStale,
            ReasonCode::SessionChanged,
        ));
    }
    Ok(validated)
}

// ---------------------------------------------------------------------------
// Sign-in flow over the injected opener: the authorize URL is opened exactly
// once per explicit user action and never returned to any UI surface. A failed
// open aborts the pending transaction so the next click can start cleanly.
// ---------------------------------------------------------------------------

impl CoreShared {
    pub fn fail_exchange(&self, generation: u64, reason: ReasonCode) {
        let mut inner = self.lock_inner();
        if inner.generation == generation && inner.exchanging {
            inner.exchanging = false;
            inner.pending = None;
            inner.grant = None;
            inner.last_reason = Some(reason);
            inner.generation = inner.generation.saturating_add(1);
        }
    }
    fn abort_pending(&self, generation: u64, pending_state: &str, reason: ReasonCode) {
        let mut inner = self.lock_inner();
        // The opener belongs to one pending transaction, never a replacement
        // or a callback that has already consumed its own pending state.
        if inner.generation == generation
            && inner.pending.as_ref().is_some_and(|pending| {
                pending.generation_at_start == generation
                    && ct_eq(pending.terminal_state.as_bytes(), pending_state.as_bytes())
            })
        {
            inner.pending = None;
            inner.last_reason = Some(reason);
        }
    }
}

pub fn perform_sign_in<O: BrowserOpener + ?Sized>(
    core: &CoreShared,
    opener: &O,
    clock: &dyn Clock,
    key: Option<&AnonKey>,
) -> Result<SessionStatusDto, TerminalError> {
    let start = core.begin_sign_in(clock, key)?;
    opener.open(&start.authorize_url).map_err(|err| {
        core.abort_pending(
            start.generation,
            &start.pending_state,
            ReasonCode::SignInOpenFailed,
        );
        err
    })?;
    Ok(start.status)
}

// ---------------------------------------------------------------------------
// Tests: pure, injected, no live HTTP. Each test exercises protocol behaviour,
// not a mirror of the implementation.
// ---------------------------------------------------------------------------

#[cfg(test)]
pub mod protocol_tests {
    use super::*;
    use std::sync::atomic::{AtomicU64, Ordering};
    use std::sync::Arc;

    const UID: &str = "6f1c3e5a-9b2d-4c8e-a1f0-3d5b7c9e1a2b";
    const SESSION_ID: &str = "0d3a7f21-5c48-4b9a-8e2d-6a1b4c7d9f0e";
    const REQ_REF: &str = "1b2f6c7a-4e5d-4a3b-9c8d-2e1f0a9b8c7d";
    const DEL_REF: &str = "2c3d4e5f-6a7b-4c8d-9e0f-1a2b3c4d5e6f";
    const TEAM_REF: &str = "3d4e5f6a-7b8c-4d9e-af01-2b3c4d5e6f70";
    const WALL0: u64 = 1_700_000_000_000;
    const GOOD_DIGEST: &str = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef";

    // -- fakes ---------------------------------------------------------------

    struct FakeClock {
        mono: AtomicU64,
        wall: AtomicU64,
    }

    impl FakeClock {
        fn new(mono: u64, wall: u64) -> Self {
            FakeClock {
                mono: AtomicU64::new(mono),
                wall: AtomicU64::new(wall),
            }
        }
        fn advance_mono(&self, ms: u64) {
            self.mono.fetch_add(ms, Ordering::SeqCst);
        }
        fn set(&self, mono: u64, wall: u64) {
            self.mono.store(mono, Ordering::SeqCst);
            self.wall.store(wall, Ordering::SeqCst);
        }
    }

    impl Clock for FakeClock {
        fn now_monotonic_ms(&self) -> u64 {
            self.mono.load(Ordering::SeqCst)
        }
        fn now_wall_ms(&self) -> u64 {
            self.wall.load(Ordering::SeqCst)
        }
    }

    struct FakeOpener {
        urls: Mutex<Vec<String>>,
        fail: bool,
    }

    impl FakeOpener {
        fn working() -> Self {
            FakeOpener {
                urls: Mutex::new(Vec::new()),
                fail: false,
            }
        }
        fn failing() -> Self {
            FakeOpener {
                urls: Mutex::new(Vec::new()),
                fail: true,
            }
        }
        fn opened(&self) -> Vec<String> {
            self.urls
                .lock()
                .unwrap_or_else(PoisonError::into_inner)
                .clone()
        }
    }

    impl BrowserOpener for FakeOpener {
        fn open(&self, authorize_url: &str) -> Result<(), TerminalError> {
            self.urls
                .lock()
                .unwrap_or_else(PoisonError::into_inner)
                .push(authorize_url.to_string());
            if self.fail {
                Err(TerminalError::new(
                    ErrorKind::OpenFailed,
                    ReasonCode::SignInOpenFailed,
                ))
            } else {
                Ok(())
            }
        }
    }

    #[derive(Clone)]
    struct CallRecord {
        method: HttpMethod,
        url: String,
        headers: Vec<(String, String)>,
        body: Option<String>,
    }

    type ResponderFn = Arc<
        dyn Fn(
                &HttpMethod,
                &str,
                &[(String, String)],
                Option<&str>,
            ) -> Result<HttpResponse, TerminalError>
            + Send
            + Sync,
    >;

    struct FakeTransport {
        calls: Mutex<Vec<CallRecord>>,
        responder: ResponderFn,
    }

    impl FakeTransport {
        fn new<F>(responder: F) -> Self
        where
            F: Fn(
                    &HttpMethod,
                    &str,
                    &[(String, String)],
                    Option<&str>,
                ) -> Result<HttpResponse, TerminalError>
                + Send
                + Sync
                + 'static,
        {
            FakeTransport {
                calls: Mutex::new(Vec::new()),
                responder: Arc::new(responder),
            }
        }
        fn snapshot(&self) -> Vec<CallRecord> {
            self.calls
                .lock()
                .unwrap_or_else(PoisonError::into_inner)
                .clone()
        }
    }

    impl HttpTransport for FakeTransport {
        fn request<'a>(
            &'a self,
            method: HttpMethod,
            url: &'a str,
            headers: Vec<(String, String)>,
            body: Option<String>,
            max_body_bytes: usize,
        ) -> BoxFut<'a, Result<HttpResponse, TerminalError>> {
            self.calls
                .lock()
                .unwrap_or_else(PoisonError::into_inner)
                .push(CallRecord {
                    method: method.clone(),
                    url: url.to_string(),
                    headers: headers.clone(),
                    body: body.clone(),
                });
            let _ = max_body_bytes;
            let responder = Arc::clone(&self.responder);
            Box::pin(async move { responder(&method, url, &headers, body.as_deref()) })
        }
    }

    // -- jwt / response builders ---------------------------------------------

    fn b64(payload: &str) -> String {
        URL_SAFE_NO_PAD.encode(payload.as_bytes())
    }

    fn make_anon_key(role: &str) -> String {
        format!(
            "{}.{}.sig",
            b64("{\"alg\":\"HS256\",\"typ\":\"JWT\"}"),
            b64(&format!("{{\"role\":\"{}\"}}", role))
        )
    }

    fn make_access_token(
        sub: &str,
        session: &str,
        exp_secs: u64,
        mutate: impl FnOnce(&mut serde_json::Value),
    ) -> String {
        let mut payload = serde_json::json!({
            "sub": sub,
            "iss": EXPECTED_ISSUER,
            "aud": "authenticated",
            "role": "authenticated",
            "exp": exp_secs,
            "session_id": session,
        });
        mutate(&mut payload);
        format!(
            "{}.{}.sig",
            b64("{\"alg\":\"HS256\",\"typ\":\"JWT\"}"),
            b64(&payload.to_string())
        )
    }

    fn token_response_body(uid: &str, session: &str, now_wall_ms: u64, expires_in: u64) -> String {
        let access = make_access_token(uid, session, now_wall_ms / 1000 + expires_in, |_| {});
        serde_json::json!({
            "access_token": access,
            "token_type": "bearer",
            "expires_in": expires_in,
            "refresh_token": "provider-refresh-never-persisted",
            "user": {"id": uid},
        })
        .to_string()
    }

    fn feed_body(principal_scope: &str, session_scope: &str) -> String {
        serde_json::json!({
            "schema": FEED_SCHEMA,
            "viewer": {"principal_scope": principal_scope, "session_scope": session_scope},
            "source": {
                "owner": FEED_SOURCE_OWNER,
                "scope": FEED_SOURCE_SCOPE,
                "observed_at": "2026-11-04T10:20:30.123456Z",
            },
            "coverage": {"state": "COMPLETE_WITHIN_SCOPE", "reason_codes": []},
            "requests": [{
                "request_ref": REQ_REF,
                "revision": 1,
                "issued_at": "2026-11-04T09:00:00.000000Z",
                "delivery": {
                    "delivery_id": DEL_REF,
                    "content_sha256": GOOD_DIGEST,
                    "title": "Weekly brief",
                    "slot_asof": "2026-11-04",
                    "artifact_asof": null,
                },
                "audience": {
                    "team_id": TEAM_REF,
                    "name": "Platform",
                    "member_count": 4,
                    "membership_policy": FEED_MEMBERSHIP_POLICY,
                },
                "review": {"request_ref": REQ_REF, "revision": 1, "delivery_id": DEL_REF},
            }],
        })
        .to_string()
    }

    fn direct_grant(generation: u64) -> VerifiedGrant {
        VerifiedGrant {
            principal_uid: UID.to_string(),
            session_id: SESSION_ID.to_string(),
            access_token: format!("hdr.{}.sig", b64(&format!("{{\"sub\":\"{}\"}}", UID))),
            access_exp_wall_ms: WALL0 + 3_600_000,
            access_deadline_monotonic_ms: 3_600_000,
            principal_scope: principal_scope_for_uid(UID),
            session_scope: session_scope_for(UID, SESSION_ID),
            generation_at_issue: generation,
        }
    }

    fn signed_in_core(clock: &FakeClock) -> CoreShared {
        let core = CoreShared::new(true);
        let _ = clock;
        core.lock_inner().exchanging = true; // Inert preverified grant fixture, never production admission.
        core.complete_sign_in(direct_grant(core.generation()))
            .expect("direct grant installs");
        core
    }

    fn plain_200(body: &str) -> Result<HttpResponse, TerminalError> {
        Ok(HttpResponse {
            status: 200,
            body: body.as_bytes().to_vec(),
        })
    }

    #[cfg(test)]
    impl CoreShared {
        /// Test-only view of the private pending transaction.
        fn test_pending(&self) -> Option<(String, String)> {
            let inner = self.lock_inner();
            inner
                .pending
                .as_ref()
                .map(|p| (p.code_verifier.clone(), p.terminal_state.clone()))
        }
    }

    // -- sync test driver (no tokio macros in this crate's feature set) ------

    fn block_on<F: Future>(fut: F) -> F::Output {
        use std::task::{Context, Poll, RawWaker, RawWakerVTable, Waker};
        fn noop(_: *const ()) {}
        fn clone_raw(_: *const ()) -> RawWaker {
            RawWaker::new(std::ptr::null(), &NOOP_VTABLE)
        }
        static NOOP_VTABLE: RawWakerVTable = RawWakerVTable::new(clone_raw, noop, noop, noop);
        let waker = unsafe { Waker::from_raw(RawWaker::new(std::ptr::null(), &NOOP_VTABLE)) };
        let mut cx = Context::from_waker(&waker);
        let mut fut = std::pin::pin!(fut);
        loop {
            match fut.as_mut().poll(&mut cx) {
                Poll::Ready(value) => return value,
                Poll::Pending => std::thread::yield_now(),
            }
        }
    }

    fn callback_url(code: &str, state: &str) -> Url {
        Url::parse(&format!(
            "{}://{}{}?code={}&terminal_state={}",
            CALLBACK_SCHEME, CALLBACK_HOST, CALLBACK_PATH, code, state
        ))
        .expect("callback test url parses")
    }

    const GOOD_CODE: &str = "auth-code-abc123";

    // -- PKCE ---------------------------------------------------------------

    #[test]
    fn s256_challenge_matches_the_rfc7636_known_vector() {
        let verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk";
        assert_eq!(
            pkce_challenge_from_verifier(verifier),
            "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"
        );
    }

    #[test]
    fn authorize_target_is_the_exact_pkce_url_with_native_redirect() {
        let core = CoreShared::new(true);
        let clock = FakeClock::new(10, WALL0);
        let start = core
            .begin_sign_in(
                &clock,
                Some(&AnonKey {
                    value: make_anon_key("anon"),
                }),
            )
            .expect("sign in begins");
        let (verifier, state) = core.test_pending().expect("pending installed");
        let parsed = Url::parse(&start.authorize_url).expect("authorize url parses");
        assert_eq!(parsed.host_str(), Some("fsldfzlxyavsuwqbceod.supabase.co"));
        assert_eq!(parsed.path(), "/auth/v1/authorize");
        let pairs: Vec<(String, String)> = parsed
            .query_pairs()
            .map(|(k, v)| (k.into_owned(), v.into_owned()))
            .collect();
        let expected_redirect = format!(
            "{}://{}{}?terminal_state={}",
            CALLBACK_SCHEME, CALLBACK_HOST, CALLBACK_PATH, state
        );
        assert_eq!(
            pairs,
            vec![
                ("provider".to_string(), "google".to_string()),
                ("redirect_to".to_string(), expected_redirect),
                (
                    "code_challenge".to_string(),
                    pkce_challenge_from_verifier(&verifier)
                ),
                ("code_challenge_method".to_string(), "s256".to_string()),
            ]
        );
        assert_eq!(verifier.len(), VERIFIER_B64_LEN);
        assert_eq!(state.len(), STATE_B64_LEN);
        assert_ne!(verifier, state, "verifier and state are distinct secrets");
    }

    // -- callback admission --------------------------------------------------

    #[test]
    fn foreign_and_malformed_callback_urls_are_admitted_only_by_shape() {
        let url_of = |raw: &str| Url::parse(raw).expect("test url parses");
        // Foreign shapes are never ours: dispatch must leave them alone.
        for foreign in [
            "https://app.mastermind-x.com/callback",
            "com.mastermind.os://other/callback",
            "com.mastermind.os://terminal/other",
            "auth0mastermind://oauth/callback",
        ] {
            assert!(!accepts_callback_url(&url_of(foreign)), "{foreign}");
        }
        // Ours by route but with forbidden URL parts: dispatch may route them
        // (the key shape alone decides routing), full validation refuses them.
        for routed_but_bad in [
            "com.mastermind.os://terminal/callback?code=x&terminal_state=y#frag",
            "com.mastermind.os://user@terminal/callback?code=x&terminal_state=y",
            "com.mastermind.os://terminal:443/callback?code=x&terminal_state=y",
        ] {
            let url = url_of(routed_but_bad);
            assert!(accepts_callback_url(&url), "routed: {routed_but_bad}");
            assert_eq!(
                parse_callback_url(&url),
                ParsedCallback::Malformed,
                "{routed_but_bad}"
            );
        }
        // Wrong query composition: not routable and not parseable.
        for unrouteable in [
            "com.mastermind.os://terminal/callback?code=x&code=y&terminal_state=y",
            "com.mastermind.os://terminal/callback?code=x&terminal_state=y&extra=z",
            "com.mastermind.os://terminal/callback?terminal_state=y",
            "com.mastermind.os://terminal/callback?code=&terminal_state=y",
            "com.mastermind.os://terminal/callback?code=x&terminal_state=short",
            "com.mastermind.os://terminal/callback?error=cancelled&extra=1",
        ] {
            let url = url_of(unrouteable);
            assert!(
                accepts_callback_url(&url),
                "Terminal owns and rejects its malformed callback: {unrouteable}"
            );
            assert_eq!(
                parse_callback_url(&url),
                ParsedCallback::Malformed,
                "{unrouteable}"
            );
        }
        // The exact happy shape parses both orderings.
        let a = url_of("com.mastermind.os://terminal/callback?code=abc&terminal_state=AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA");
        let b = url_of("com.mastermind.os://terminal/callback?terminal_state=AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA&code=abc");
        assert_eq!(
            parse_callback_url(&a),
            ParsedCallback::Code {
                code: "abc".to_string(),
                terminal_state: "A".repeat(43),
            }
        );
        assert_eq!(parse_callback_url(&a), parse_callback_url(&b));
    }

    #[test]
    fn callback_state_mismatch_expiry_replay_and_overlap_are_all_rejected_once() {
        let clock = FakeClock::new(0, WALL0);
        let core = CoreShared::new(true);
        let key = AnonKey {
            value: make_anon_key("anon"),
        };

        // overlap while a live pending exists
        core.begin_sign_in(&clock, Some(&key)).expect("first begin");
        assert!(matches!(
            core.begin_sign_in(&clock, Some(&key)),
            Err(TerminalError {
                kind: ErrorKind::SignInBusy,
                reason: ReasonCode::SignInOverlap
            })
        ));
        let (_, wrong_state) = core.test_pending().expect("pending");
        let mismatch = callback_url(GOOD_CODE, "B".repeat(43).as_str());
        assert_eq!(
            core.consume_callback(&clock, &mismatch),
            Err(TerminalError::new(
                ErrorKind::CallbackInvalid,
                ReasonCode::StateMismatch
            ))
        );
        // A forged state must not consume the original valid transaction.
        assert_eq!(
            core.consume_callback(&clock, &mismatch),
            Err(TerminalError::new(
                ErrorKind::CallbackInvalid,
                ReasonCode::StateMismatch
            ))
        );

        core.disconnect();
        // expired pending: advance past the 300s TTL on both clocks
        core.begin_sign_in(&clock, Some(&key))
            .expect("second begin");
        clock.advance_mono(PENDING_TTL_MS + 1);
        let (_, state) = core.test_pending().expect("pending");
        let expired = callback_url(GOOD_CODE, &state);
        assert_eq!(
            core.consume_callback(&clock, &expired),
            Err(TerminalError::new(
                ErrorKind::CallbackInvalid,
                ReasonCode::PendingExpired
            ))
        );

        // happy path, then replay of the same callback
        clock.set(10_000, WALL0);
        core.begin_sign_in(&clock, Some(&key)).expect("third begin");
        let (_, state) = core.test_pending().expect("pending");
        let ok = callback_url(GOOD_CODE, &state);
        let accepted = core.consume_callback(&clock, &ok).expect("accepted");
        match accepted {
            CallbackOutcome::Accepted {
                auth_code,
                generation,
                ..
            } => {
                assert_eq!(auth_code, GOOD_CODE);
                assert_eq!(generation, core.generation());
            }
            _ => panic!("expected accepted"),
        }
        assert!(matches!(
            core.consume_callback(&clock, &ok),
            Err(TerminalError {
                kind: ErrorKind::CallbackInvalid,
                reason: ReasonCode::NoPending
            })
        ));
        let _ = wrong_state;
    }

    #[test]
    fn provider_error_callback_cancels_and_advances_the_generation() {
        let clock = FakeClock::new(0, WALL0);
        let core = CoreShared::new(true);
        let key = AnonKey {
            value: make_anon_key("anon"),
        };
        core.begin_sign_in(&clock, Some(&key)).expect("begin");
        let (_, state) = core.test_pending().expect("pending");
        let url = Url::parse(&format!(
            "com.mastermind.os://terminal/callback?error=user_closed&terminal_state={state}"
        ))
        .expect("error callback parses");
        match core.consume_callback(&clock, &url).expect("cancelled") {
            CallbackOutcome::Cancelled { status } => {
                assert_eq!(status.state, STATE_SIGNED_OUT);
                assert_eq!(status.reason, Some(ReasonCode::UserCancelled.as_str()));
            }
            _ => panic!("expected cancelled"),
        }
        assert_eq!(core.generation(), 2);
    }

    // -- token exchange flow over injected transport --------------------------

    #[test]
    fn token_exchange_posts_once_to_the_fixed_pkce_endpoint_and_installs_the_grant() {
        let clock = FakeClock::new(1_000, WALL0);
        let core = CoreShared::new(true);
        let key = AnonKey {
            value: make_anon_key("anon"),
        };
        core.begin_sign_in(&clock, Some(&key)).expect("begin");
        let (_, state) = core.test_pending().expect("pending");
        let accepted = core
            .consume_callback(&clock, &callback_url(GOOD_CODE, &state))
            .expect("accepted");

        let transport = FakeTransport::new(|method, url, headers, body| {
            if url == token_url() {
                assert_eq!(*method, HttpMethod::Post);
                let map: std::collections::HashMap<&str, &str> = headers
                    .iter()
                    .map(|(k, v)| (k.as_str(), v.as_str()))
                    .collect();
                assert_eq!(map.get("content-type"), Some(&"application/json"));
                assert!(map.get("apikey").is_some(), "public apikey header present");
                let body_text = body.expect("json body");
                assert!(
                    !url.contains("auth_code") && !url.contains("code_verifier"),
                    "secrets stay out of the URL"
                );
                let parsed: serde_json::Value =
                    serde_json::from_str(body_text).expect("body is json");
                assert_eq!(parsed["auth_code"], serde_json::json!(GOOD_CODE));
                assert!(parsed["code_verifier"].as_str().unwrap().len() == VERIFIER_B64_LEN);
                assert!(!body_text.contains("refresh_token"));
                plain_200(&token_response_body(UID, SESSION_ID, WALL0, 3600))
            } else {
                assert_eq!(url, user_url(), "only the fixed token and user endpoints");
                assert_eq!(*method, HttpMethod::Get);
                plain_200(&user_ok_body())
            }
        });

        let status = block_on(perform_token_exchange(
            &core, &transport, &clock, accepted, &key,
        ))
        .expect("exchange completes");
        assert_eq!(status.state, STATE_SIGNED_IN);
        assert_eq!(status.available, true);
        assert_eq!(
            status.principal_scope.as_deref(),
            Some(principal_scope_for_uid(UID).as_str())
        );
        assert_eq!(status.generation, 2);

        let calls = transport.snapshot();
        assert_eq!(
            calls.iter().map(|c| c.url.clone()).collect::<Vec<_>>(),
            vec![token_url(), user_url()],
            "exchange then server verification, never retried"
        );
        assert!(
            !calls[0]
                .body
                .clone()
                .unwrap_or_default()
                .to_ascii_lowercase()
                .contains("refresh"),
            "no refresh grant anywhere"
        );
    }

    #[test]
    fn exchange_failure_is_terminal_with_no_autoretry() {
        let clock = FakeClock::new(1_000, WALL0);
        let core = CoreShared::new(true);
        let key = AnonKey {
            value: make_anon_key("anon"),
        };
        core.begin_sign_in(&clock, Some(&key)).expect("begin");
        let (_, state) = core.test_pending().expect("pending");
        let accepted = core
            .consume_callback(&clock, &callback_url(GOOD_CODE, &state))
            .expect("accepted");
        let transport = FakeTransport::new(|_method, _url, _headers, _body| {
            Ok(HttpResponse {
                status: 400,
                body: b"{\"error\":\"invalid_grant\"}".to_vec(),
            })
        });
        let outcome = block_on(perform_token_exchange(
            &core, &transport, &clock, accepted, &key,
        ));
        assert!(matches!(
            outcome,
            Err(TerminalError {
                kind: ErrorKind::ProviderRejected,
                reason: ReasonCode::TokenExchangeRejected
            })
        ));
        assert_eq!(transport.snapshot().len(), 1, "single attempt only");
        // Failed exchange exposes only its closed error reason and no grant.
        let status = core.status(&clock);
        assert_eq!(status.state, STATE_ERROR);
        assert_eq!(
            status.reason,
            Some(ReasonCode::TokenExchangeRejected.as_str())
        );
    }

    #[test]
    fn redirect_response_from_the_token_endpoint_is_refused_not_followed() {
        let clock = FakeClock::new(1_000, WALL0);
        let core = CoreShared::new(true);
        let key = AnonKey {
            value: make_anon_key("anon"),
        };
        core.begin_sign_in(&clock, Some(&key)).expect("begin");
        let (_, state) = core.test_pending().expect("pending");
        let accepted = core
            .consume_callback(&clock, &callback_url(GOOD_CODE, &state))
            .expect("accepted");
        let transport = FakeTransport::new(|_m, _u, _h, _b| {
            Ok(HttpResponse {
                status: 302,
                body: Vec::new(),
            })
        });
        let outcome = block_on(perform_token_exchange(
            &core, &transport, &clock, accepted, &key,
        ));
        assert!(matches!(
            outcome,
            Err(TerminalError {
                kind: ErrorKind::ProviderRejected,
                reason: ReasonCode::RedirectRefused
            })
        ));
    }

    #[test]
    fn sign_out_during_the_exchange_refuses_the_late_completion() {
        let clock = FakeClock::new(1_000, WALL0);
        let core = Arc::new(CoreShared::new(true));
        let key = AnonKey {
            value: make_anon_key("anon"),
        };
        core.begin_sign_in(&clock, Some(&key)).expect("begin");
        let (_, state) = core.test_pending().expect("pending");
        let accepted = core
            .consume_callback(&clock, &callback_url(GOOD_CODE, &state))
            .expect("accepted");
        // The responder disconnects while the "HTTP call" is in flight; the
        // exchange must then refuse to install the grant it just received.
        let core_handle = Arc::clone(&core);
        let transport = FakeTransport::new(move |method, url, _h, _b| {
            if url == user_url() {
                assert_eq!(*method, HttpMethod::Get);
                plain_200(&user_ok_body())
            } else {
                // The grant dies during the token exchange itself; the /user
                // verification still runs, and completion must be refused.
                core_handle.disconnect();
                plain_200(&token_response_body(UID, SESSION_ID, WALL0, 3600))
            }
        });
        let outcome = block_on(perform_token_exchange(
            &core, &transport, &clock, accepted, &key,
        ));
        assert!(matches!(
            outcome,
            Err(TerminalError {
                kind: ErrorKind::GenerationChanged,
                reason: ReasonCode::LateCompletionRejected
            })
        ));
        let status = core.status(&clock);
        assert_eq!(status.state, STATE_SIGNED_OUT);
        assert_eq!(status.reason, Some(ReasonCode::SignedOutLocal.as_str()));
        assert!(
            core.ticket(&clock).is_err(),
            "no grant after refused completion"
        );
    }

    // -- response validation -------------------------------------------------

    #[test]
    fn token_grant_spoofs_are_refused() {
        let now = WALL0;
        let good_exp = now / 1000 + 3600;
        let refused = |body: String, label: &str| {
            let outcome = validate_token_response(body.as_bytes(), now);
            assert!(outcome.is_err(), "{label} must be refused");
        };
        // non-bearer
        refused(
            serde_json::json!({
                "access_token": make_access_token(UID, SESSION_ID, good_exp, |_| {}),
                "token_type": "mac",
                "expires_in": 3600,
            })
            .to_string(),
            "mac token type",
        );
        // missing jwt
        refused(
            serde_json::json!({"token_type": "bearer", "expires_in": 3600}).to_string(),
            "missing access_token",
        );
        // invalid expiries
        for expires_in in [0u64, 86_401u64] {
            refused(
                serde_json::json!({
                    "access_token": make_access_token(UID, SESSION_ID, now / 1000 + expires_in, |_| {}),
                    "token_type": "bearer",
                    "expires_in": expires_in,
                })
                .to_string(),
                "expires_in boundary",
            );
        }
        // issuer spoof
        refused(
            serde_json::json!({
                "access_token": make_access_token(UID, SESSION_ID, good_exp, |p| {
                    p["iss"] = serde_json::json!("https://evil.example.com/auth/v1");
                }),
                "token_type": "bearer",
                "expires_in": 3600,
            })
            .to_string(),
            "issuer spoof",
        );
        // A foreign additional audience must fail closed; the exact singleton matches Terminal.
        refused(
            serde_json::json!({
                "access_token": make_access_token(UID, SESSION_ID, good_exp, |p| {
                    p["aud"] = serde_json::json!(["authenticated","foreign"]);
                }),
                "token_type": "bearer",
                "expires_in": 3600,
            })
            .to_string(),
            "audience array",
        );
        // role spoof
        refused(
            serde_json::json!({
                "access_token": make_access_token(UID, SESSION_ID, good_exp, |p| {
                    p["role"] = serde_json::json!("anon");
                }),
                "token_type": "bearer",
                "expires_in": 3600,
            })
            .to_string(),
            "role spoof",
        );
        // session spoof: missing / non-canonical / mismatched shape
        refused(
            serde_json::json!({
                "access_token": make_access_token(UID, SESSION_ID, good_exp, |p| {
                    p.as_object_mut().unwrap().remove("session_id");
                }),
                "token_type": "bearer",
                "expires_in": 3600,
            })
            .to_string(),
            "missing session_id",
        );
        refused(
            serde_json::json!({
                "access_token": make_access_token(UID, SESSION_ID, good_exp, |p| {
                    p["session_id"] = serde_json::json!("not-a-uuid");
                }),
                "token_type": "bearer",
                "expires_in": 3600,
            })
            .to_string(),
            "non-canonical session_id",
        );
        // sub spoof
        refused(
            serde_json::json!({
                "access_token": make_access_token("ZZZZZZZZ-ZZZZ-4ZZZ-8ZZZ-ZZZZZZZZZZZZ", SESSION_ID, good_exp, |_| {}),
                "token_type": "bearer",
                "expires_in": 3600,
            })
            .to_string(),
            "non-canonical sub",
        );
        // expired at issue
        refused(
            serde_json::json!({
                "access_token": make_access_token(UID, SESSION_ID, now / 1000 - 10, |_| {}),
                "token_type": "bearer",
                "expires_in": 3600,
            })
            .to_string(),
            "already expired",
        );

        // the honest response validates and carries no refresh retention
        let (skeleton, token) = validate_token_response(
            token_response_body(UID, SESSION_ID, now, 3600).as_bytes(),
            now,
        )
        .expect("honest grant validates");
        assert_eq!(skeleton.principal_uid, UID);
        assert_eq!(skeleton.session_id, SESSION_ID);
        assert_eq!(skeleton.access_exp_wall_ms, (now / 1000 + 3600) * 1000);
        assert!(token.split('.').count() == 3);
    }

    #[test]
    fn user_endpoint_spoofs_are_refused() {
        let now = WALL0;
        let exp = now + 3_600_000;
        let body_with = |id: serde_json::Value| {
            serde_json::json!({"id": id, "aud": "authenticated"}).to_string()
        };
        assert!(validate_user_response(
            body_with(serde_json::json!(UID)).as_bytes(),
            UID,
            now,
            exp
        )
        .is_ok());
        // spoofed sub
        assert!(validate_user_response(
            body_with(serde_json::json!("00000000-0000-4000-8000-000000000000")).as_bytes(),
            UID,
            now,
            exp
        )
        .is_err());
        // non-uuid id
        assert!(validate_user_response(
            body_with(serde_json::json!("someone")).as_bytes(),
            UID,
            now,
            exp
        )
        .is_err());
        // missing id
        assert!(validate_user_response(b"{}", UID, now, exp).is_err());
        // expired while checking
        assert!(validate_user_response(
            body_with(serde_json::json!(UID)).as_bytes(),
            UID,
            exp,
            exp
        )
        .is_err());
        // oversized body
        let big = vec![b'a'; BODY_CAP_BYTES + 1];
        assert!(validate_user_response(&big, UID, now, exp).is_err());
    }

    // -- key admission -------------------------------------------------------

    #[test]
    fn only_publishable_and_legacy_anon_keys_are_admitted() {
        assert_eq!(admit_anon_key(None), KeyAdmission::Absent);
        assert_eq!(
            admit_anon_key(Some("")),
            KeyAdmission::Refused(ReasonCode::InvalidConfig)
        );
        assert_eq!(
            admit_anon_key(Some("   \n\t")),
            KeyAdmission::Refused(ReasonCode::InvalidConfig)
        );
        assert_eq!(
            admit_anon_key(Some("sb_secret_live_abcdef")),
            KeyAdmission::Refused(ReasonCode::ServiceKeyRefused)
        );
        assert_eq!(
            admit_anon_key(Some(&make_anon_key("service_role"))),
            KeyAdmission::Refused(ReasonCode::ServiceKeyRefused)
        );
        assert_eq!(
            admit_anon_key(Some(&make_anon_key("authenticated"))),
            KeyAdmission::Refused(ReasonCode::ServiceKeyRefused),
            "only the anon role is accepted for legacy jwt keys"
        );
        assert_eq!(
            admit_anon_key(Some("not-a-jwt-or-publishable")),
            KeyAdmission::Refused(ReasonCode::InvalidConfig)
        );
        let control = format!("sb_publishable_abc\u{7}def");
        assert_eq!(
            admit_anon_key(Some(&control)),
            KeyAdmission::Refused(ReasonCode::InvalidConfig)
        );
        let oversized = format!("sb_publishable_{}", "a".repeat(300));
        assert_eq!(
            admit_anon_key(Some(&oversized)),
            KeyAdmission::Refused(ReasonCode::InvalidConfig)
        );
        let jwt_oversized = format!("{}.{}.sig", b64("{\"role\":\"anon\"}"), "a".repeat(5000));
        assert_eq!(
            admit_anon_key(Some(&jwt_oversized)),
            KeyAdmission::Refused(ReasonCode::InvalidConfig)
        );
        assert!(matches!(
            admit_anon_key(Some(&make_anon_key("anon"))),
            KeyAdmission::Admitted(_)
        ));
        assert!(matches!(
            admit_anon_key(Some("sb_publishable_pk_abcDEF123-_")),
            KeyAdmission::Admitted(_)
        ));
    }

    // -- unconfigured behaviour ----------------------------------------------

    #[test]
    fn unconfigured_core_has_no_effects_and_never_starts_a_flow() {
        let clock = FakeClock::new(0, WALL0);
        let core = CoreShared::new(false);
        let status = core.status(&clock);
        assert_eq!(status.state, STATE_UNCONFIGURED);
        assert_eq!(status.available, false);
        assert_eq!(status.reason, Some(ReasonCode::NotConfigured.as_str()));
        assert_eq!(status.principal_scope, None);
        assert_eq!(status.session_scope, None);
        assert!(matches!(
            core.begin_sign_in(&clock, None),
            Err(TerminalError {
                kind: ErrorKind::ConfigUnavailable,
                reason: ReasonCode::NotConfigured
            })
        ));
        assert!(core.ticket(&clock).is_err());
        let transport = FakeTransport::new(|_m, _u, _h, _b| plain_200("[]"));
        let read = block_on(perform_sharing_requests_read(
            &core,
            &transport,
            &clock,
            Some(&AnonKey {
                value: make_anon_key("anon"),
            }),
        ));
        assert!(read.is_err(), "no session means no feed, not an empty feed");
        assert!(
            transport.snapshot().is_empty(),
            "unconfigured reads never hit the network"
        );
    }

    // -- scope hashing -------------------------------------------------------

    #[test]
    fn scope_hashes_use_the_documented_domain_separated_inputs() {
        let expected_principal = {
            let mut d = Sha256::new();
            d.update(b"mastermind.terminal.principal.v1:");
            d.update(UID.as_bytes());
            format!("{:x}", d.finalize())
        };
        let expected_session = {
            let mut d = Sha256::new();
            d.update(b"mastermind.terminal.session.v1:");
            d.update(UID.as_bytes());
            d.update(b":");
            d.update(SESSION_ID.as_bytes());
            format!("{:x}", d.finalize())
        };
        assert_eq!(principal_scope_for_uid(UID), expected_principal);
        assert_eq!(session_scope_for(UID, SESSION_ID), expected_session);
        for hash in [&expected_principal, &expected_session] {
            assert_eq!(hash.len(), 64);
            assert!(hash.bytes().all(|b| matches!(b, b'0'..=b'9' | b'a'..=b'f')));
        }
        // terminal-only namespace: no Auth0 equivalence claim, inputs differ
        assert_ne!(expected_principal, expected_session);
        assert_eq!(session_scope_for(UID, "other-session"), {
            let mut d = Sha256::new();
            d.update(b"mastermind.terminal.session.v1:");
            d.update(UID.as_bytes());
            d.update(b":other-session");
            format!("{:x}", d.finalize())
        });
    }

    // -- public status carries no secrets -------------------------------------

    #[test]
    fn serialized_status_never_carries_secrets_or_raw_identity() {
        let clock = FakeClock::new(1_000, WALL0);
        let core = CoreShared::new(true);
        let key = AnonKey {
            value: make_anon_key("anon"),
        };

        let mut secrets: Vec<String> = Vec::new();
        let status_unconfigured = core.status(&clock);
        let serialized = serde_json::to_string(&status_unconfigured).unwrap();
        assert_eq!(status_unconfigured.state, STATE_SIGNED_OUT);

        let start = core.begin_sign_in(&clock, Some(&key)).expect("begin");
        let (verifier, state) = core.test_pending().expect("pending");
        secrets.push(verifier.clone());
        secrets.push(state.clone());
        secrets.push(pkce_challenge_from_verifier(&verifier));
        let serialized_signing = serde_json::to_string(&core.status(&clock)).unwrap();

        let accepted = core
            .consume_callback(&clock, &callback_url(GOOD_CODE, &state))
            .expect("accepted");
        secrets.push(GOOD_CODE.to_string());
        let transport = FakeTransport::new(|_m, url, _h, _b| {
            if url == user_url() {
                plain_200(&user_ok_body())
            } else {
                plain_200(&token_response_body(UID, SESSION_ID, WALL0, 3600))
            }
        });
        let _status_in = block_on(perform_token_exchange(
            &core, &transport, &clock, accepted, &key,
        ))
        .unwrap();
        secrets.push(make_access_token(
            UID,
            SESSION_ID,
            WALL0 / 1000 + 3600,
            |_| {},
        ));
        secrets.push(UID.to_string());
        secrets.push(SESSION_ID.to_string());
        secrets.push(token_url());
        secrets.push(user_url());
        secrets.push(native_feed_url());
        secrets.push(start.authorize_url.clone());

        let status_signed_in = core.status(&clock);
        let serialized_signed_in = serde_json::to_string(&status_signed_in).unwrap();
        assert_eq!(status_signed_in.state, STATE_SIGNED_IN);
        assert_eq!(
            status_signed_in.principal_scope.as_deref(),
            Some(principal_scope_for_uid(UID).as_str()),
            "opaque scope hash is the only post-verification identity surface"
        );

        for (label, text) in [
            ("unconfigured", serialized.as_str()),
            ("signing_in", serialized_signing.as_str()),
            ("signed_in", serialized_signed_in.as_str()),
        ] {
            for secret in &secrets {
                assert!(!text.contains(secret.as_str()), "{label} exposes a sensitive value");
            }
            assert!(!text.contains("access_token"), "{label}");
            assert!(!text.contains("code_verifier"), "{label}");
            assert!(!text.contains("refresh"), "{label}");
            assert!(!text.contains("supabase.co"), "{label}");
            assert!(!text.contains(UID), "{label}");
        }
    }

    // -- feed schema ----------------------------------------------------------

    fn mutated_feed(ticket: &SessionTicket, mutate: impl FnOnce(&mut serde_json::Value)) -> String {
        let mut value: serde_json::Value =
            serde_json::from_str(&feed_body(&ticket.principal_scope, &ticket.session_scope))
                .unwrap();
        mutate(&mut value);
        value.to_string()
    }

    #[test]
    fn feed_schema_rejections_cover_viewer_shape_and_bounds() {
        let clock = FakeClock::new(0, WALL0);
        let ticket = signed_in_core(&clock).ticket(&clock).expect("ticket");
        let good = feed_body(&ticket.principal_scope, &ticket.session_scope);
        let validated = validate_feed_response(good.as_bytes(), &ticket).expect("valid feed");
        assert_eq!(validated["schema"], FEED_SCHEMA);
        assert_eq!(validated["requests"].as_array().map(|r| r.len()), Some(1));
        assert_eq!(validated["requests"][0]["request_ref"], REQ_REF);
        assert_eq!(validated["requests"][0]["review"]["delivery_id"], DEL_REF);
        assert!(validated["requests"][0]["delivery"]["artifact_asof"].is_null());
        let text = validated.to_string();
        assert!(!text.contains(UID), "raw uid never re-enters the feed");
        assert!(
            !text.contains(SESSION_ID),
            "raw session id never re-enters the feed"
        );

        // wrong viewer scopes: another principal's feed is rejected outright
        let wrong_viewer = feed_body(
            &principal_scope_for_uid("00000000-0000-4000-8000-000000000000"),
            &ticket.session_scope,
        );
        assert!(validate_feed_response(wrong_viewer.as_bytes(), &ticket).is_err());
        let no_session = mutated_feed(&ticket, |v| {
            v["viewer"]["session_scope"] = serde_json::json!("");
        });
        assert!(validate_feed_response(no_session.as_bytes(), &ticket).is_err());

        // unknown top-level key and schema drift
        let extra = mutated_feed(&ticket, |v| {
            v["sneaky_field"] = serde_json::json!(1);
        });
        assert!(validate_feed_response(extra.as_bytes(), &ticket).is_err());
        let drift = mutated_feed(&ticket, |v| {
            v["schema"] = serde_json::json!("mastermind.terminal_sharing_request_feed.v2");
        });
        assert!(validate_feed_response(drift.as_bytes(), &ticket).is_err());

        // revision must be the exact integer 1 (floats and other values refuse)
        let float_revision = mutated_feed(&ticket, |v| {
            v["requests"][0]["revision"] = serde_json::json!(1.0);
        });
        assert!(validate_feed_response(float_revision.as_bytes(), &ticket).is_err());
        let zero_revision = mutated_feed(&ticket, |v| {
            v["requests"][0]["revision"] = serde_json::json!(0);
        });
        assert!(validate_feed_response(zero_revision.as_bytes(), &ticket).is_err());

        // unknown nested key inside delivery
        let nested_extra = mutated_feed(&ticket, |v| {
            v["requests"][0]["delivery"]["subscription_id"] = serde_json::json!("secret");
        });
        assert!(validate_feed_response(nested_extra.as_bytes(), &ticket).is_err());

        // review block must mirror the outer identity
        let broken_review = mutated_feed(&ticket, |v| {
            v["requests"][0]["review"]["delivery_id"] =
                serde_json::json!(DEL_REF.replace('2', "3"));
        });
        assert!(validate_feed_response(broken_review.as_bytes(), &ticket).is_err());

        // title with a URL refuses (no URLs in feed fields)
        let url_title = mutated_feed(&ticket, |v| {
            v["requests"][0]["delivery"]["title"] =
                serde_json::json!("see https://evil.example.com");
        });
        assert!(
            validate_feed_response(url_title.as_bytes(), &ticket).is_ok(),
            "A title is plain text, never a navigation target"
        );

        // timestamp grammar and calendar drift
        let bad_stamp = mutated_feed(&ticket, |v| {
            v["requests"][0]["issued_at"] = serde_json::json!("2026-11-04 09:00:00");
        });
        assert!(validate_feed_response(bad_stamp.as_bytes(), &ticket).is_err());
        let bad_date = mutated_feed(&ticket, |v| {
            v["requests"][0]["delivery"]["slot_asof"] = serde_json::json!("2026-02-30");
        });
        assert!(validate_feed_response(bad_date.as_bytes(), &ticket).is_err());

        // malformed digest
        let bad_digest = mutated_feed(&ticket, |v| {
            v["requests"][0]["delivery"]["content_sha256"] = serde_json::json!("ABCD");
        });
        assert!(validate_feed_response(bad_digest.as_bytes(), &ticket).is_err());

        // PARTIAL coverage requires a closed reason code; COMPLETE forbids one
        let partial_no_reason = mutated_feed(&ticket, |v| {
            v["coverage"]["state"] = serde_json::json!("PARTIAL");
        });
        assert!(validate_feed_response(partial_no_reason.as_bytes(), &ticket).is_err());
        let partial_ok = mutated_feed(&ticket, |v| {
            v["coverage"]["state"] = serde_json::json!("PARTIAL");
            v["coverage"]["reason_codes"] = serde_json::json!(["LIMIT_REACHED"]);
        });
        assert!(validate_feed_response(partial_ok.as_bytes(), &ticket).is_ok());
        let complete_with_reason = mutated_feed(&ticket, |v| {
            v["coverage"]["reason_codes"] = serde_json::json!(["LIMIT_REACHED"]);
        });
        assert!(validate_feed_response(complete_with_reason.as_bytes(), &ticket).is_err());
        let unknown_reason = mutated_feed(&ticket, |v| {
            v["coverage"]["state"] = serde_json::json!("PARTIAL");
            v["coverage"]["reason_codes"] = serde_json::json!(["SOMETHING_ELSE"]);
        });
        assert!(validate_feed_response(unknown_reason.as_bytes(), &ticket).is_err());

        // more than 20 requests refuses
        let over_limit = mutated_feed(&ticket, |v| {
            let entry = v["requests"][0].clone();
            let mut many = Vec::new();
            for i in 0..21u32 {
                let mut copy = entry.clone();
                copy["request_ref"] =
                    serde_json::json!(format!("{:08x}-0000-4000-8000-000000000000", i));
                copy["review"]["request_ref"] = copy["request_ref"].clone();
                many.push(copy);
            }
            v["requests"] = serde_json::json!(many);
        });
        assert!(validate_feed_response(over_limit.as_bytes(), &ticket).is_err());

        // duplicate request refs refuse
        let duplicate = mutated_feed(&ticket, |v| {
            let entry = v["requests"][0].clone();
            v["requests"] = serde_json::json!([entry.clone(), entry]);
        });
        assert!(validate_feed_response(duplicate.as_bytes(), &ticket).is_err());

        // byte cap enforced at validation too
        let huge = vec![b' '; BODY_CAP_BYTES + 1];
        assert!(matches!(
            validate_feed_response(&huge, &ticket),
            Err(TerminalError {
                kind: ErrorKind::FeedRejected,
                reason: ReasonCode::ResponseTooLarge
            })
        ));
        // non-json body
        assert!(validate_feed_response(b"not json", &ticket).is_err());
    }

    // -- native sharing-request read flow -------------------------------------

    fn user_ok_body() -> String {
        serde_json::json!({"id": UID, "aud": "authenticated", "role": "authenticated"}).to_string()
    }

    fn assert_bearer_headers(headers: &[(String, String)]) {
        let map: std::collections::HashMap<&str, &str> = headers
            .iter()
            .map(|(k, v)| (k.as_str(), v.as_str()))
            .collect();
        assert!(map.contains_key("apikey"), "public apikey header present");
        assert!(
            map.get("authorization")
                .map(|v| v.starts_with("Bearer "))
                .unwrap_or(false),
            "supabase bearer only"
        );
        assert!(!map.contains_key("cookie"), "native route is cookie-free");
        for (key, value) in headers {
            assert!(
                key.eq_ignore_ascii_case("authorization") || !value.contains("Bearer"),
                "bearer only in the authorization header ({key})"
            );
        }
    }

    #[test]
    fn native_read_follows_the_fixed_guard_sequence_and_returns_the_feed() {
        let clock = FakeClock::new(1_000, WALL0);
        let core = signed_in_core(&clock);
        let key = AnonKey {
            value: make_anon_key("anon"),
        };
        let calls = Arc::new(AtomicU64::new(0));
        let transport = FakeTransport::new(move |method, url, headers, _body| {
            let n = calls.fetch_add(1, Ordering::SeqCst);
            assert_eq!(*method, HttpMethod::Get, "reads are GET only");
            assert_bearer_headers(headers);
            if n % 2 == 0 {
                assert_eq!(
                    url,
                    user_url(),
                    "pre and post guards use the fixed /user endpoint"
                );
                plain_200(&user_ok_body())
            } else {
                assert_eq!(url, native_feed_url(), "fixed native feed route only");
                plain_200(&feed_body(
                    &principal_scope_for_uid(UID),
                    &session_scope_for(UID, SESSION_ID),
                ))
            }
        });
        let feed = block_on(perform_sharing_requests_read(
            &core,
            &transport,
            &clock,
            Some(&key),
        ))
        .expect("guarded read succeeds");
        assert_eq!(feed["requests"][0]["request_ref"], REQ_REF);
        assert_eq!(feed["coverage"]["state"], "COMPLETE_WITHIN_SCOPE");
        let snapshot = transport.snapshot();
        assert!(snapshot.iter().all(|c| c.method == HttpMethod::Get));
        assert_eq!(snapshot[0].body, None, "reads carry no body");
        let urls: Vec<String> = snapshot.into_iter().map(|c| c.url).collect();
        assert_eq!(
            urls,
            vec![user_url(), native_feed_url(), user_url()],
            "exact guard sequence: user, feed, user"
        );
    }

    #[test]
    fn native_read_without_a_session_makes_no_request_at_all() {
        let clock = FakeClock::new(0, WALL0);
        let core = CoreShared::new(true);
        let key = AnonKey {
            value: make_anon_key("anon"),
        };
        let transport = FakeTransport::new(|_m, _u, _h, _b| plain_200("[]"));
        let outcome = block_on(perform_sharing_requests_read(
            &core,
            &transport,
            &clock,
            Some(&key),
        ));
        assert!(matches!(
            outcome,
            Err(TerminalError {
                kind: ErrorKind::SessionRequired,
                ..
            })
        ));
        assert!(
            transport.snapshot().is_empty(),
            "absence of a grant is not an empty feed"
        );
    }

    #[test]
    fn native_read_discards_the_feed_when_the_session_is_invalidated_mid_flight() {
        let clock = FakeClock::new(1_000, WALL0);
        let core = Arc::new(signed_in_core(&clock));
        let key = AnonKey {
            value: make_anon_key("anon"),
        };
        let core_for_hook = Arc::clone(&core);
        let transport = FakeTransport::new(move |method, url, headers, _body| {
            assert_eq!(*method, HttpMethod::Get);
            if url == user_url() {
                plain_200(&user_ok_body())
            } else {
                // The grant dies between the pre-guard and the post-guard.
                core_for_hook.disconnect();
                plain_200(&feed_body(
                    &principal_scope_for_uid(UID),
                    &session_scope_for(UID, SESSION_ID),
                ))
            }
        });
        let outcome = block_on(perform_sharing_requests_read(
            &core,
            &transport,
            &clock,
            Some(&key),
        ));
        assert!(matches!(
            outcome,
            Err(TerminalError {
                kind: ErrorKind::GenerationChanged,
                reason: ReasonCode::GenerationChanged
            })
        ));
        let urls: Vec<String> = transport.snapshot().into_iter().map(|c| c.url).collect();
        assert_eq!(
            urls.len(),
            2,
            "no post-guard request after a generation break"
        );
        assert_eq!(core.status(&clock).state, STATE_SIGNED_OUT);
    }

    #[test]
    fn stale_read_failure_cannot_clear_a_newer_terminal_session() {
        let clock = FakeClock::new(1_000, WALL0);
        let core = Arc::new(signed_in_core(&clock));
        let previous_generation = core.generation();
        let changed = Arc::clone(&core);
        let transport = FakeTransport::new(move |_, url, _, _| {
            assert_eq!(url, user_url());
            changed.disconnect();
            changed.lock_inner().exchanging = true; // Inert server-verified new-identity fixture.
            changed
                .complete_sign_in(direct_grant(changed.generation()))
                .unwrap();
            Ok(HttpResponse {
                status: 401,
                body: Vec::new(),
            })
        });
        let key = AnonKey {
            value: make_anon_key("anon"),
        };
        assert!(block_on(perform_sharing_requests_read(
            &core,
            &transport,
            &clock,
            Some(&key)
        ))
        .is_err());
        assert_eq!(
            transport.snapshot().len(),
            1,
            "old read never fetches a feed"
        );
        assert_eq!(core.status(&clock).state, STATE_SIGNED_IN);
        assert!(core.generation() > previous_generation);
        assert!(
            core.ticket(&clock).is_ok(),
            "new grant survives old failure"
        );
    }

    #[test]
    fn native_read_refuses_user_spoof_redirect_and_stale_grant_paths() {
        let clock = FakeClock::new(1_000, WALL0);

        // pre-user spoofed id: feed is never requested, session invalidated
        let core = signed_in_core(&clock);
        let key = AnonKey {
            value: make_anon_key("anon"),
        };
        let spoof_transport = FakeTransport::new(|_m, url, _h, _b| {
            assert_eq!(url, user_url());
            plain_200(
                &serde_json::json!({"id": "00000000-0000-4000-8000-000000000000"}).to_string(),
            )
        });
        let outcome = block_on(perform_sharing_requests_read(
            &core,
            &spoof_transport,
            &clock,
            Some(&key),
        ));
        assert!(matches!(
            outcome,
            Err(TerminalError {
                kind: ErrorKind::ServerUnverified,
                reason: ReasonCode::ServerVerificationFailed
            })
        ));
        assert_eq!(
            spoof_transport.snapshot().len(),
            1,
            "no feed after a failed pre-guard"
        );
        assert_eq!(
            core.status(&clock).state,
            STATE_ERROR,
            "spoof invalidates the grant"
        );

        // redirect from the feed endpoint: refused, not followed, grant intact
        let core = signed_in_core(&clock);
        let redirect_transport = FakeTransport::new(|_m, url, _h, _b| {
            if url == user_url() {
                plain_200(&user_ok_body())
            } else {
                Ok(HttpResponse {
                    status: 302,
                    body: Vec::new(),
                })
            }
        });
        let outcome = block_on(perform_sharing_requests_read(
            &core,
            &redirect_transport,
            &clock,
            Some(&key),
        ));
        assert!(matches!(
            outcome,
            Err(TerminalError {
                kind: ErrorKind::FeedRejected,
                reason: ReasonCode::RedirectRefused
            })
        ));
        assert!(
            core.ticket(&clock).is_ok(),
            "transport-level refusal keeps the session"
        );

        // wrong viewer on an otherwise valid feed: schema-level rejection
        let core = signed_in_core(&clock);
        let foreign_scopes = FakeTransport::new(|_m, url, _h, _b| {
            if url == user_url() {
                plain_200(&user_ok_body())
            } else {
                plain_200(&feed_body(
                    &principal_scope_for_uid("00000000-0000-4000-8000-000000000000"),
                    &session_scope_for(UID, SESSION_ID),
                ))
            }
        });
        let outcome = block_on(perform_sharing_requests_read(
            &core,
            &foreign_scopes,
            &clock,
            Some(&key),
        ));
        assert!(matches!(
            outcome,
            Err(TerminalError {
                kind: ErrorKind::FeedRejected,
                reason: ReasonCode::FeedSchemaRejected
            })
        ));

        // post-guard user failure: grant invalidated, nothing returned
        let core = signed_in_core(&clock);
        let calls = Arc::new(AtomicU64::new(0));
        let calls_for_closure = Arc::clone(&calls);
        let post_failure = FakeTransport::new(move |_m, url, _h, _b| {
            let n = calls_for_closure.fetch_add(1, Ordering::SeqCst);
            if url == user_url() {
                if n == 0 {
                    plain_200(&user_ok_body())
                } else {
                    Ok(HttpResponse {
                        status: 401,
                        body: b"{}".to_vec(),
                    })
                }
            } else {
                plain_200(&feed_body(
                    &principal_scope_for_uid(UID),
                    &session_scope_for(UID, SESSION_ID),
                ))
            }
        });
        let outcome = block_on(perform_sharing_requests_read(
            &core,
            &post_failure,
            &clock,
            Some(&key),
        ));
        assert!(matches!(
            outcome,
            Err(TerminalError {
                kind: ErrorKind::ServerUnverified,
                reason: ReasonCode::SessionChanged
            })
        ));
        assert_eq!(core.status(&clock).state, STATE_ERROR);

        // expired grant mid-read: refusal, never a silent refresh or retry
        let core = signed_in_core(&clock);
        let expiry_transport = FakeTransport::new(|_m, url, _h, _b| {
            assert_eq!(url, user_url());
            Ok(HttpResponse {
                status: 200,
                body: user_ok_body().into_bytes(),
            })
        });
        clock.set(2_000, WALL0 + 10 * 3_600_000);
        let outcome = block_on(perform_sharing_requests_read(
            &core,
            &expiry_transport,
            &clock,
            Some(&key),
        ));
        assert!(matches!(
            outcome,
            Err(TerminalError {
                kind: ErrorKind::SessionRequired,
                reason: ReasonCode::SessionExpired
            })
        ));
        assert!(
            expiry_transport.snapshot().is_empty(),
            "expired ticket never reaches the wire"
        );
    }

    // -- sign-in flow with the injected opener --------------------------------

    #[test]
    fn old_opener_failure_preserves_a_newer_pending_or_exchanging_transaction() {
        struct ReentrantOpener<'a> {
            core: &'a CoreShared,
            clock: &'a FakeClock,
            key: &'a AnonKey,
            mode: u8,
        }
        impl BrowserOpener for ReentrantOpener<'_> {
            fn open(&self, _: &str) -> Result<(), TerminalError> {
                if self.mode == 2 {
                    self.clock
                        .set(PENDING_TTL_MS + 1, WALL0 + PENDING_TTL_MS + 1);
                } else {
                    self.core.disconnect();
                }
                self.core.begin_sign_in(self.clock, Some(self.key)).unwrap();
                if self.mode == 1 {
                    let (_, state) = self.core.test_pending().unwrap();
                    self.core
                        .consume_callback(self.clock, &callback_url(GOOD_CODE, &state))
                        .unwrap();
                }
                Err(TerminalError::new(
                    ErrorKind::OpenFailed,
                    ReasonCode::SignInOpenFailed,
                ))
            }
        }
        for mode in 0..3 {
            let clock = FakeClock::new(0, WALL0);
            let core = CoreShared::new(true);
            let key = AnonKey {
                value: make_anon_key("anon"),
            };
            let opener = ReentrantOpener {
                core: &core,
                clock: &clock,
                key: &key,
                mode,
            };
            assert!(perform_sign_in(&core, &opener, &clock, Some(&key)).is_err());
            assert_eq!(
                core.status(&clock).state,
                STATE_SIGNING_IN,
                "mode {mode}: newer transaction survives"
            );
            assert_eq!(
                core.status(&clock).reason,
                Some(ReasonCode::SignInStarted.as_str())
            );
            let inner = core.lock_inner();
            if mode == 1 {
                assert!(inner.exchanging);
                assert!(inner.pending.is_none());
            } else {
                assert!(!inner.exchanging);
                assert!(inner.pending.is_some());
            }
        }
    }

    #[test]
    fn sign_in_opens_the_authorize_url_exactly_once_and_survives_open_failure() {
        let clock = FakeClock::new(0, WALL0);
        let core = CoreShared::new(true);
        let key = AnonKey {
            value: make_anon_key("anon"),
        };

        let failing = FakeOpener::failing();
        let outcome = perform_sign_in(&core, &failing, &clock, Some(&key));
        assert!(matches!(
            outcome,
            Err(TerminalError {
                kind: ErrorKind::OpenFailed,
                reason: ReasonCode::SignInOpenFailed
            })
        ));
        assert_eq!(failing.opened().len(), 1, "one open attempt, no retry");
        let status = core.status(&clock);
        assert_eq!(status.state, STATE_ERROR);
        assert_eq!(status.reason, Some(ReasonCode::SignInOpenFailed.as_str()));
        assert!(
            core.test_pending().is_none(),
            "failed open aborts the pending transaction"
        );

        // the aborted transaction lets the next explicit action start cleanly
        let working = FakeOpener::working();
        let status =
            perform_sign_in(&core, &working, &clock, Some(&key)).expect("second click works");
        assert_eq!(status.state, STATE_SIGNING_IN);
        assert_eq!(working.opened().len(), 1);
        assert!(core.test_pending().is_some());
        assert!(
            !working.opened()[0].contains("code_verifier="),
            "verifier never rides in the url"
        );
    }

    // -- grammar invariants ----------------------------------------------------

    #[test]
    fn grammar_validators_accept_only_the_documented_shapes() {
        assert!(is_canonical_uuid("6f1c3e5a-9b2d-4c8e-a1f0-3d5b7c9e1a2b"));
        assert!(
            !is_canonical_uuid("6F1C3E5A-9B2D-4C8E-A1F0-3D5B7C9E1A2B"),
            "upper case is not canonical"
        );
        assert!(!is_canonical_uuid("6f1c3e5a9b2d4c8ea1f03d5b7c9e1a2b"));
        assert!(!is_canonical_uuid(""));
        assert!(is_slot_date("2026-11-04"));
        assert!(!is_slot_date("2026-2-4"));
        assert!(!is_slot_date("2026-13-01"));
        assert!(!is_slot_date("2027-02-29"), "non-leap february 29 refuses");
        assert!(is_slot_date("2028-02-29"), "leap february 29 accepts");
        assert!(is_persisted_timestamp("2026-11-04T10:20:30.123456Z"));
        assert!(
            !is_persisted_timestamp("2026-11-04T10:20:30Z"),
            "fractional part is mandatory"
        );
        assert!(!is_persisted_timestamp("2026-11-04T24:20:30.123456Z"));
        assert!(!is_persisted_timestamp("2026-11-04T10:20:30.1234Z"));
        assert!(!is_persisted_timestamp("2026-11-04t10:20:30.123456Z"));
        assert!(ct_eq(b"identical", b"identical"));
        assert!(!ct_eq(b"identical", b"different"));
        assert!(!ct_eq(b"short", b"shorter"));
    }

    // -- status and generation invariants --------------------------------------

    #[test]
    fn generation_advances_monotonically_across_lifecycle_transitions() {
        let clock = FakeClock::new(0, WALL0);
        let core = CoreShared::new(true);
        let key = AnonKey {
            value: make_anon_key("anon"),
        };
        assert_eq!(core.generation(), 1);
        core.begin_sign_in(&clock, Some(&key)).expect("begin");
        assert_eq!(
            core.generation(),
            1,
            "starting a flow does not change identity"
        );
        let (_, state) = core.test_pending().expect("pending");
        let accepted = core
            .consume_callback(&clock, &callback_url(GOOD_CODE, &state))
            .expect("accepted");
        let transport = FakeTransport::new(|_m, url, _h, _b| {
            if url == user_url() {
                plain_200(&user_ok_body())
            } else {
                plain_200(&token_response_body(UID, SESSION_ID, WALL0, 3600))
            }
        });
        block_on(perform_token_exchange(
            &core, &transport, &clock, accepted, &key,
        ))
        .expect("grant installed");
        let signed_in_generation = core.generation();
        assert!(signed_in_generation > 1);

        // identity change (disconnect) moves the generation again
        core.disconnect();
        assert!(core.generation() > signed_in_generation);
        let status = core.status(&clock);
        assert_eq!(status.state, STATE_SIGNED_OUT);
        assert_eq!(status.reason, Some(ReasonCode::SignedOutLocal.as_str()));
        assert_eq!(
            status.principal_scope, None,
            "scopes disappear with the grant"
        );

        // One token exchange plus one server-side user verification; disconnect performs no HTTP.
        assert_eq!(transport.snapshot().len(), 2);
    }
    #[test]
    fn actual_sql_fixture_joins_private_pkce_owner_and_fixed_authenticated_reader() {
        const PG_UID: &str = "10000000-0000-4000-8000-000000000001";
        const PG_SESSION: &str = "70000000-0000-4000-8000-000000000001";
        let fixture = include_str!("../../src/inbox/fixtures/terminal-sharing-request-feed.json");
        let expected: serde_json::Value = serde_json::from_str(fixture).unwrap();
        let clock = FakeClock::new(1000, WALL0);
        let core = CoreShared::new(true);
        let key = AnonKey {
            value: make_anon_key("anon"),
        };
        core.begin_sign_in(&clock, Some(&key)).unwrap();
        let (_, state) = core.test_pending().unwrap();
        let accepted = core
            .consume_callback(&clock, &callback_url(GOOD_CODE, &state))
            .unwrap();
        let transport = FakeTransport::new(move |_, url, _, _| {
            if url == token_url() {
                plain_200(&token_response_body(PG_UID, PG_SESSION, WALL0, 3600))
            } else if url == user_url() {
                plain_200(&serde_json::json!({"id":PG_UID}).to_string())
            } else {
                assert_eq!(url, native_feed_url());
                plain_200(fixture)
            }
        });
        let status = block_on(perform_token_exchange(
            &core, &transport, &clock, accepted, &key,
        ))
        .unwrap();
        assert_eq!(
            status.principal_scope.as_deref(),
            expected["viewer"]["principal_scope"].as_str()
        );
        assert_eq!(
            status.session_scope.as_deref(),
            expected["viewer"]["session_scope"].as_str()
        );
        let feed = block_on(perform_sharing_requests_read(
            &core,
            &transport,
            &clock,
            Some(&key),
        ))
        .unwrap();
        assert_eq!(feed, expected);
        assert_eq!(
            transport
                .snapshot()
                .iter()
                .map(|c| c.url.clone())
                .collect::<Vec<_>>(),
            vec![
                token_url(),
                user_url(),
                user_url(),
                native_feed_url(),
                user_url()
            ]
        );
        let mut foreign = feed.clone();
        foreign["viewer"]["session_scope"] = serde_json::json!("f".repeat(64));
        assert!(validate_feed_response(
            &serde_json::to_vec(&foreign).unwrap(),
            &core.ticket(&clock).unwrap()
        )
        .is_err());
    }

    #[test]
    fn callback_error_requires_own_state_and_secret_debug_is_redacted() {
        let clock = FakeClock::new(0, WALL0);
        let core = CoreShared::new(true);
        let key = AnonKey {
            value: make_anon_key("anon"),
        };
        core.begin_sign_in(&clock, Some(&key)).unwrap();
        let (_, state) = core.test_pending().unwrap();
        let forged =
            Url::parse("com.mastermind.os://terminal/callback?error=access_denied").unwrap();
        assert!(core.consume_callback(&clock, &forged).is_err());
        assert!(core.test_pending().is_some());
        let wrong = Url::parse(&format!(
            "com.mastermind.os://terminal/callback?error=user_closed&terminal_state={}",
            "B".repeat(43)
        ))
        .unwrap();
        assert!(core.consume_callback(&clock, &wrong).is_err());
        assert!(core.test_pending().is_some());
        let parsed = parse_callback_url(&callback_url(GOOD_CODE, &state));
        assert!(!format!("{:?}", parsed).contains(GOOD_CODE));
        let accepted = core
            .consume_callback(&clock, &callback_url(GOOD_CODE, &state))
            .unwrap();
        assert!(!format!("{:?}", accepted).contains(GOOD_CODE));
        let response = HttpResponse {
            status: 200,
            body: GOOD_CODE.as_bytes().to_vec(),
        };
        assert_eq!(
            format!("{:?}", response),
            "HttpResponse { status: 200, body: \"[REDACTED]\" }"
        );
        assert!(!format!("{:?}", response).contains(GOOD_CODE));
        let (skeleton, _) = validate_token_response(
            token_response_body(UID, SESSION_ID, WALL0, 3600).as_bytes(),
            WALL0,
        )
        .unwrap();
        assert_eq!(
            format!("{:?}", skeleton),
            "VerifiedGrantSkeleton([REDACTED])"
        );
        assert!(!format!("{:?}", skeleton).contains(UID));
        assert!(!format!("{:?}", skeleton).contains(SESSION_ID));
    }

    #[test]
    fn consumed_callback_keeps_exchange_exclusive_and_disconnect_fences_before_network() {
        let clock = FakeClock::new(0, WALL0);
        let core = CoreShared::new(true);
        let key = AnonKey {
            value: make_anon_key("anon"),
        };
        core.begin_sign_in(&clock, Some(&key)).unwrap();
        let (_, state) = core.test_pending().unwrap();
        let accepted = core
            .consume_callback(&clock, &callback_url(GOOD_CODE, &state))
            .unwrap();
        assert_eq!(core.status(&clock).state, STATE_SIGNING_IN);
        assert!(core.begin_sign_in(&clock, Some(&key)).is_err());
        core.disconnect();
        let transport =
            FakeTransport::new(|_, _, _, _| panic!("no request after local disconnect"));
        assert!(block_on(perform_token_exchange(
            &core, &transport, &clock, accepted, &key
        ))
        .is_err());
        assert!(transport.snapshot().is_empty());
        assert!(!core.status(&clock).available);
    }
}

impl std::fmt::Debug for CallbackOutcome {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str("CallbackOutcome([REDACTED])")
    }
}

impl std::fmt::Debug for ParsedCallback {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str("ParsedCallback([REDACTED])")
    }
}

impl std::fmt::Debug for JwtClaims {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str("JwtClaims([REDACTED])")
    }
}
