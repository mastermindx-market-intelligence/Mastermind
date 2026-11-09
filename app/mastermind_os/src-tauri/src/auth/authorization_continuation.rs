//! Explicit one-shot Content continuation after a pre-exchange Pending timeout.
//! No credential persistence, Executive chaining, caller selector or token getter.
use super::*;

const SCHEMA: &str = "mastermind.native_authorization_continuation.v1";
const IDENTITY_SCHEMA: &str = "mastermind.native_authorization_identity.v1";
const IDENTITY_CAP: usize = 1024;
const ACQUISITION_IDENTITY: &str = "/workspace/native-authorization-identity/acquisition/current";
const CONTENT_IDENTITY: &str = "/workspace/native-authorization-identity/content/current";
const INELIGIBLE: &str = "AUTH_CONTINUATION_INELIGIBLE";
const IDENTITY_UNAVAILABLE: &str = "AUTHORIZATION_IDENTITY_UNAVAILABLE";
const IDENTITY_CHANGED: &str = "AUTHORIZATION_IDENTITY_CHANGED";
const EXCHANGE_UNCONFIRMED: &str = "AUTH_CONTINUATION_EXCHANGE_UNCONFIRMED";

#[derive(Serialize)]
pub struct ContinuationStatus {
    schema: &'static str,
    state: &'static str,
    resource: Option<&'static str>,
    reason: &'static str,
}

// Private anchors contain bearer material and are deliberately not Debug or
// Serialize. The expired state is hashed ONLY to recognize a late refusal;
// neither old state, code nor verifier can be reused for a new transaction.
#[derive(Clone)]
pub(super) struct ContentTimeout {
    generation: u64,
    intent: SignInIntent,
    original_state_digest: [u8; 32],
    acquisition: String,
    client: String,
    acquisition_expires: Instant,
    acquisition_wall: SystemTime,
    used: bool,
    refused: bool,
}
#[derive(Clone)]
struct AccountIdentity {
    digest: String,
    expires_at_ms: u64,
}
#[derive(Clone)]
pub(super) struct ContentContinuation {
    anchor: ContentTimeout,
    account: AccountIdentity,
}

fn millis(time: SystemTime) -> Option<u64> {
    u64::try_from(
        time.duration_since(SystemTime::UNIX_EPOCH)
            .ok()?
            .as_millis(),
    )
    .ok()
}
fn identity(
    value: Value,
    resource: Resource,
    token_wall: SystemTime,
    now: SystemTime,
) -> Result<AccountIdentity> {
    let kind = match resource {
        Resource::Acquisition => "ACQUISITION",
        Resource::Content => "CONTENT",
        _ => return Err(INELIGIBLE.into()),
    };
    let object = value.as_object().ok_or(IDENTITY_UNAVAILABLE)?;
    if object.len() != 4
        || !["schema", "resource", "account_digest", "expires_at_ms"]
            .iter()
            .all(|key| object.contains_key(*key))
        || object.get("schema").and_then(Value::as_str) != Some(IDENTITY_SCHEMA)
        || object.get("resource").and_then(Value::as_str) != Some(kind)
    {
        return Err(IDENTITY_UNAVAILABLE.into());
    }
    let digest = object
        .get("account_digest")
        .and_then(Value::as_str)
        .ok_or(IDENTITY_UNAVAILABLE)?;
    if digest.len() != 64
        || !digest
            .bytes()
            .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
    {
        return Err(IDENTITY_UNAVAILABLE.into());
    }
    let expiry = object
        .get("expires_at_ms")
        .and_then(Value::as_u64)
        .filter(|n| *n <= 8_640_000_000_000_000)
        .ok_or(IDENTITY_UNAVAILABLE)?;
    let expires_at_ms = expiry.min(millis(token_wall).ok_or(IDENTITY_UNAVAILABLE)?);
    if expires_at_ms <= millis(now).ok_or(IDENTITY_UNAVAILABLE)? {
        return Err(IDENTITY_UNAVAILABLE.into());
    }
    Ok(AccountIdentity {
        digest: digest.to_owned(),
        expires_at_ms,
    })
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct IdentityWire {
    schema: String,
    resource: String,
    account_digest: String,
    expires_at_ms: u64,
}
fn identity_bytes(
    bytes: &[u8],
    resource: Resource,
    token_wall: SystemTime,
    now: SystemTime,
) -> Result<AccountIdentity> {
    if bytes.len() > IDENTITY_CAP {
        return Err(IDENTITY_UNAVAILABLE.into());
    }
    // Struct decoding rejects duplicate as well as unknown fields, non-UTF8,
    // nonintegral expiry and trailing input before the value-level checks.
    let wire: IdentityWire = serde_json::from_slice(bytes).map_err(|_| IDENTITY_UNAVAILABLE)?;
    identity(
        serde_json::json!({"schema":wire.schema,"resource":wire.resource,
        "account_digest":wire.account_digest,"expires_at_ms":wire.expires_at_ms}),
        resource,
        token_wall,
        now,
    )
}

impl Inner {
    fn continuation_anchor_current(&self, anchor: &ContentTimeout) -> bool {
        !crate::native_refresh::enabled()
            && self.generation == anchor.generation
            && !anchor.refused
            && self.client_id.as_ref() == Some(&anchor.client)
            && !self.restoring
            && self.token(Resource::Content).is_none()
            && self.content.is_none()
            && self.executive.is_none()
            && matches!(self.executive_reason, ExecutiveReason::NotEstablished)
            && self.token(Resource::Acquisition).is_some_and(|token| {
                token.value == anchor.acquisition
                    && token.expires == anchor.acquisition_expires
                    && token.wall_expires == anchor.acquisition_wall
            })
    }
    pub(super) fn remember_content_timeout(&mut self, pending: &Pending) {
        if pending.resource != Resource::Content
            || pending.continuation.is_some()
            || pending.generation != self.generation
            || self.pending.is_some()
            || self.exchanging
            || self.restoring
        {
            return;
        }
        if let Some(token) = self.token(Resource::Acquisition) {
            let anchor = ContentTimeout {
                intent: pending.intent,
                generation: self.generation,
                original_state_digest: Sha256::digest(pending.state.as_bytes()).into(),
                acquisition: token.value.clone(),
                client: self.client_id.clone().unwrap_or_default(),
                acquisition_expires: token.expires,
                acquisition_wall: token.wall_expires,
                used: false,
                refused: false,
            };
            if self.continuation_anchor_current(&anchor) {
                self.content_timeout = Some(anchor);
            }
        }
    }
    pub(super) fn observe_timed_out_refusal(&mut self, state: &str) -> bool {
        let state_digest: [u8; 32] = Sha256::digest(state.as_bytes()).into();
        if !self.content_timeout.as_ref().is_some_and(|anchor| {
            anchor.generation == self.generation && anchor.original_state_digest == state_digest
        }) {
            return false;
        }
        if let Some(anchor) = self.content_timeout.as_mut() {
            anchor.refused = true;
        }
        // A known refusal before candidate publication retires only this
        // continuation. It never clears Acquisition or a later normal login.
        if self
            .pending
            .as_ref()
            .is_some_and(|pending| pending.continuation.is_some())
        {
            self.pending = None;
        }
        self.exchanging = false;
        self.reason = Some("AUTHORIZATION_REFUSED");
        true
    }
    fn continuation_status(&self) -> ContinuationStatus {
        let eligible = self.pending.is_none()
            && !self.exchanging
            && !self.restoring
            && self.reason == Some("AUTH_TRANSACTION_EXPIRED")
            && self
                .content_timeout
                .as_ref()
                .is_some_and(|anchor| !anchor.used && self.continuation_anchor_current(anchor));
        ContinuationStatus {
            schema: SCHEMA,
            state: if eligible { "ELIGIBLE" } else { "INELIGIBLE" },
            resource: if eligible { Some("CONTENT") } else { None },
            reason: if eligible {
                "CONTENT_PENDING_TIMEOUT"
            } else {
                "NOT_ELIGIBLE"
            },
        }
    }
    pub(super) fn continuation_handoff_current(&self) -> bool {
        let Some(pending) = self.pending.as_ref() else {
            return false;
        };
        let Some(witness) = pending.continuation.as_ref() else {
            return true;
        };
        !self.exchanging
            && pending.expires > Instant::now()
            && self.continuation_anchor_current(&witness.anchor)
            && millis(SystemTime::now()).is_some_and(|now| now < witness.account.expires_at_ms)
            && self.content_timeout.as_ref().is_some_and(|current| {
                current.used
                    && !current.refused
                    && current.generation == self.generation
                    && current.original_state_digest == witness.anchor.original_state_digest
            })
    }
    fn begin_continuation_check(&mut self) -> Result<ContentTimeout> {
        if self.continuation_status().state != "ELIGIBLE" {
            return Err(INELIGIBLE.into());
        }
        let anchor = self.content_timeout.as_mut().ok_or(INELIGIBLE)?;
        anchor.used = true;
        let captured = anchor.clone();
        self.exchanging = true;
        self.reason = None;
        Ok(captured)
    }
    fn probe_current(&self, anchor: &ContentTimeout) -> bool {
        self.exchanging
            && self.pending.is_none()
            && self.continuation_anchor_current(anchor)
            && self.content_timeout.as_ref().is_some_and(|current| {
                current.used
                    && !current.refused
                    && current.original_state_digest == anchor.original_state_digest
                    && current.generation == anchor.generation
            })
    }
    pub(super) fn continuation_exchange_guard(&mut self, pending: &Pending) -> Result<()> {
        let Some(witness) = pending.continuation.as_ref() else {
            return Ok(());
        };
        if pending.resource != Resource::Content
            || pending.intent != witness.anchor.intent
            || pending.generation != self.generation
            || pending.expires <= Instant::now()
            || !self.probe_current(&witness.anchor)
            || millis(SystemTime::now()).is_none_or(|now| now >= witness.account.expires_at_ms)
        {
            self.fail_continuation(pending.generation, "AUTHENTICATION_CHANGED");
            return Err("AUTHENTICATION_CHANGED".into());
        }
        Ok(())
    }
    fn fail_continuation(&mut self, generation: u64, reason: &'static str) {
        if self.generation == generation
            && self
                .content_timeout
                .as_ref()
                .is_some_and(|anchor| anchor.used)
        {
            self.exchanging = false;
            if self.reason != Some("AUTHORIZATION_REFUSED")
                && !self
                    .content_timeout
                    .as_ref()
                    .is_some_and(|anchor| anchor.refused)
            {
                self.reason = Some(reason);
            }
        }
    }
    fn open_content_continuation(
        &mut self,
        anchor: &ContentTimeout,
        account: AccountIdentity,
    ) -> Result<(String, u64)> {
        if !self.probe_current(anchor)
            || millis(SystemTime::now()).is_none_or(|now| now >= account.expires_at_ms)
        {
            return Err("AUTHENTICATION_CHANGED".into());
        }
        let generation = self
            .generation
            .checked_add(1)
            .ok_or("AUTHENTICATION_CHANGED")?;
        self.generation = generation;
        self.exchanging = false;
        self.programs_sequence = 0;
        self.programs_read = ProgramsRead::default();
        self.draft_continuity.begin_reauthentication();
        let mut active = anchor.clone();
        active.generation = generation;
        self.content_timeout = Some(active.clone());
        let url = self.transaction_for(Resource::Content, anchor.intent)?;
        self.pending.as_mut().ok_or(INELIGIBLE)?.continuation = Some(ContentContinuation {
            anchor: active,
            account,
        });
        Ok((url, generation))
    }
    fn finish_content_continuation(
        &mut self,
        generation: u64,
        witness: &ContentContinuation,
        candidate: Result<(Token, AccountIdentity, AccountIdentity)>,
    ) -> Result<()> {
        if !self.probe_current(&witness.anchor) || generation != self.generation {
            self.fail_continuation(generation, "AUTHENTICATION_CHANGED");
            return Err("AUTHENTICATION_CHANGED".into());
        }
        match candidate {
            Ok((token, acquisition, content)) => {
                let now = millis(SystemTime::now()).ok_or(IDENTITY_CHANGED)?;
                if token.expires <= Instant::now()
                    || token.wall_expires <= SystemTime::now()
                    || now >= witness.account.expires_at_ms
                    || now >= acquisition.expires_at_ms
                    || now >= content.expires_at_ms
                    || acquisition.digest != witness.account.digest
                    || content.digest != witness.account.digest
                {
                    self.fail_continuation(generation, IDENTITY_CHANGED);
                    return Err(IDENTITY_CHANGED.into());
                }
                self.content = Some(token);
                self.exchanging = false;
                self.reason = None;
                self.content_timeout = None;
                // Deliberately no finish_exchange/Executive transaction.
                Ok(())
            }
            Err(reason) => {
                let closed = if reason == IDENTITY_CHANGED {
                    IDENTITY_CHANGED
                } else if reason == EXCHANGE_UNCONFIRMED {
                    EXCHANGE_UNCONFIRMED
                } else {
                    IDENTITY_UNAVAILABLE
                };
                self.fail_continuation(generation, closed);
                Err(closed.into())
            }
        }
    }
}

async fn read_identity(
    app: &AppHandle,
    resource: Resource,
    access: &str,
    token_wall: SystemTime,
) -> Result<AccountIdentity> {
    let path = match resource {
        Resource::Acquisition => ACQUISITION_IDENTITY,
        Resource::Content => CONTENT_IDENTITY,
        _ => return Err(INELIGIBLE.into()),
    };
    let url = Url::parse(&format!("{ORIGIN}{path}")).map_err(|_| IDENTITY_UNAVAILABLE)?;
    let state = app.state::<NativeAuth>();
    let response = state
        .http
        .get(url)
        .bearer_auth(access)
        .header("Accept", "application/json")
        .header("Cache-Control", "no-store")
        .timeout(HTTP_TIMEOUT)
        .send()
        .await
        .map_err(|_| IDENTITY_UNAVAILABLE)?;
    if !response.status().is_success()
        || response
            .content_length()
            .is_some_and(|n| n > IDENTITY_CAP as u64)
        || !response
            .headers()
            .get(reqwest::header::CONTENT_TYPE)
            .and_then(|v| v.to_str().ok())
            .is_some_and(|v| {
                v.split(';')
                    .next()
                    .is_some_and(|v| v.trim() == "application/json")
            })
    {
        return Err(IDENTITY_UNAVAILABLE.into());
    }
    let mut response = response;
    let mut bytes = Vec::new();
    while let Some(chunk) = response.chunk().await.map_err(|_| IDENTITY_UNAVAILABLE)? {
        if bytes.len().saturating_add(chunk.len()) > IDENTITY_CAP {
            return Err(IDENTITY_UNAVAILABLE.into());
        }
        bytes.extend_from_slice(&chunk);
    }
    identity_bytes(&bytes, resource, token_wall, SystemTime::now())
}

#[tauri::command]
pub fn read_authorization_continuation(
    state: tauri::State<'_, NativeAuth>,
) -> Result<ContinuationStatus> {
    Ok(state.lock()?.continuation_status())
}

#[tauri::command]
pub async fn continue_authorization(app: AppHandle) -> Result<AuthStatus> {
    let state = app.state::<NativeAuth>();
    let anchor = state.lock()?.begin_continuation_check()?;
    emit(&app);
    let account = read_identity(
        &app,
        Resource::Acquisition,
        &anchor.acquisition,
        anchor.acquisition_wall,
    )
    .await;
    let (url, generation) = {
        let mut inner = state.lock()?;
        match account {
            Ok(account) => match inner.open_content_continuation(&anchor, account) {
                Ok(next) => next,
                Err(error) => {
                    inner.fail_continuation(anchor.generation, IDENTITY_CHANGED);
                    drop(inner);
                    emit(&app);
                    return Err(error);
                }
            },
            Err(_) => {
                inner.fail_continuation(anchor.generation, IDENTITY_UNAVAILABLE);
                drop(inner);
                emit(&app);
                return Err(IDENTITY_UNAVAILABLE.into());
            }
        }
    };
    emit(&app);
    // The original Acquisition timer belongs to the old generation. Retain
    // the SAME expiry, without renewal, even if Content later fails/times out.
    schedule_expiration(
        app.clone(),
        Resource::Acquisition,
        anchor.acquisition_expires,
        anchor.acquisition_wall,
        generation,
    );
    open_transaction(&app, url, generation)?;
    let status = state.lock()?.status();
    Ok(status)
}

pub(super) async fn finish_callback(
    app: &AppHandle,
    pending: &Pending,
    witness: &ContentContinuation,
    token: Result<Token>,
) {
    let candidate = match token {
        Ok(token) => {
            let still_current = app
                .state::<NativeAuth>()
                .lock()
                .is_ok_and(|inner| inner.probe_current(&witness.anchor));
            if !still_current {
                if let Ok(mut inner) = app.state::<NativeAuth>().lock() {
                    inner.fail_continuation(pending.generation, "AUTHENTICATION_CHANGED");
                }
                emit(app);
                return;
            }
            let acquisition = read_identity(
                app,
                Resource::Acquisition,
                &witness.anchor.acquisition,
                witness.anchor.acquisition_wall,
            )
            .await;
            let content = if acquisition.is_ok() {
                read_identity(app, Resource::Content, &token.value, token.wall_expires).await
            } else {
                Err(IDENTITY_UNAVAILABLE.into())
            };
            match (acquisition, content) {
                (Ok(a), Ok(c)) => Ok((token, a, c)),
                _ => Err(IDENTITY_UNAVAILABLE.into()),
            }
        }
        Err(_) => Err(EXCHANGE_UNCONFIRMED.into()),
    };
    let expiry = candidate
        .as_ref()
        .ok()
        .map(|(token, _, _)| (token.expires, token.wall_expires));
    let published = app.state::<NativeAuth>().lock().is_ok_and(|mut inner| {
        inner
            .finish_content_continuation(pending.generation, witness, candidate)
            .is_ok()
    });
    emit(app);
    if published {
        if let Some((expires, wall)) = expiry {
            schedule_expiration(
                app.clone(),
                Resource::Content,
                expires,
                wall,
                pending.generation,
            );
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn token(value: &str) -> Token {
        Token {
            value: value.into(),
            expires: Instant::now() + Duration::from_secs(600),
            wall_expires: SystemTime::now() + Duration::from_secs(600),
            executive_send: false,
        }
    }
    fn timeout() -> (Inner, String) {
        let mut inner = Inner::with_executive_resource(
            Some("public-client"),
            Some("https://mcp.mastermind-x.com/os/executive"),
        );
        inner.acquisition = Some(token("synthetic-acquisition"));
        inner.transaction(Resource::Content).unwrap();
        let state = inner.pending.as_ref().unwrap().state.clone();
        let expired = Instant::now() - Duration::from_secs(1);
        inner.pending.as_mut().unwrap().expires = expired;
        assert!(inner.expire_transaction(inner.generation, expired, Instant::now()));
        (inner, state)
    }
    #[test]
    fn primary_purpose_survives_timeout_witness_and_explicit_content_continuation() {
        let mut inner = Inner::with_executive_resource(Some("public-client"),
            Some("https://mcp.mastermind-x.com/os/executive"));
        inner.acquisition = Some(token("synthetic-acquisition"));
        inner.transaction_for(Resource::Content, SignInIntent::PrimaryAccount).unwrap();
        let expired = Instant::now() - Duration::from_secs(1);
        inner.pending.as_mut().unwrap().expires = expired;
        assert!(inner.expire_transaction(inner.generation, expired, Instant::now()));
        let anchor = inner.begin_continuation_check().unwrap();
        assert!(anchor.intent == SignInIntent::PrimaryAccount);
        let proof = account(Resource::Acquisition, anchor.acquisition_wall, &"a".repeat(64));
        inner.open_content_continuation(&anchor, proof).unwrap();
        assert!(inner.pending.as_ref().unwrap().intent == SignInIntent::PrimaryAccount);
        let state = inner.pending.as_ref().unwrap().state.clone();
        let (pending, _, _) = inner.consume(&format!("{CALLBACK}?state={state}&code=inert-new-code")).unwrap();
        assert!(pending.intent == SignInIntent::PrimaryAccount);
        assert!(inner.continuation_exchange_guard(&pending).is_ok());
        assert!(inner.executive.is_none());
    }
    fn account(resource: Resource, wall: SystemTime, digest: &str) -> AccountIdentity {
        let kind = if resource == Resource::Acquisition {
            "ACQUISITION"
        } else {
            "CONTENT"
        };
        let body = serde_json::to_vec(
            &serde_json::json!({"schema":IDENTITY_SCHEMA,"resource":kind,
            "account_digest":digest,"expires_at_ms":millis(wall).unwrap()}),
        )
        .unwrap();
        identity_bytes(&body, resource, wall, SystemTime::now()).unwrap()
    }
    fn pending() -> (Inner, Pending, ContentContinuation, String) {
        let (mut inner, old) = timeout();
        let anchor = inner.begin_continuation_check().unwrap();
        let proof = account(
            Resource::Acquisition,
            anchor.acquisition_wall,
            &"a".repeat(64),
        );
        let (url, generation) = inner.open_content_continuation(&anchor, proof).unwrap();
        assert!(!url.contains("prompt=") && !url.contains("login_hint="));
        let parsed = Url::parse(&url).unwrap();
        let pairs: std::collections::BTreeMap<_, _> = parsed.query_pairs().collect();
        assert_eq!(pairs["audience"], Resource::Content.audience());
        assert_eq!(pairs["scope"], Resource::Content.scope());
        assert_eq!(pairs["redirect_uri"], CALLBACK);
        assert_eq!(pairs["code_challenge_method"], "S256");
        let state = inner.pending.as_ref().unwrap().state.clone();
        assert_ne!(state, old);
        let callback = format!("{CALLBACK}?state={state}&code=synthetic-new-code");
        let (pending, _, _) = inner.consume(&callback).unwrap();
        assert_eq!(pending.generation, generation);
        let witness = pending.continuation.as_ref().unwrap().clone();
        (inner, pending, witness, old)
    }
    fn callback_before_exchange_fixture() -> (Inner, String, String) {
        let (mut inner, old) = timeout();
        let anchor = inner.begin_continuation_check().unwrap();
        let proof = account(
            Resource::Acquisition,
            anchor.acquisition_wall,
            &"a".repeat(64),
        );
        inner.open_content_continuation(&anchor, proof).unwrap();
        let state = inner.pending.as_ref().unwrap().state.clone();
        (
            inner,
            format!("{CALLBACK}?state={state}&code=synthetic-new-code"),
            old,
        )
    }
    fn callback_before_exchange_refuses(change: &str) {
        if crate::native_refresh::enabled() {
            let (inner, _) = timeout();
            assert_eq!(inner.continuation_status().state, "INELIGIBLE");
            return;
        }
        let (mut inner, callback, _) = callback_before_exchange_fixture();
        match change {
            "expiry" => inner.acquisition.as_mut().unwrap().expires = Instant::now(),
            "token" => inner.acquisition = Some(token("replacement-acquisition")),
            "proof" => {
                inner
                    .pending
                    .as_mut()
                    .unwrap()
                    .continuation
                    .as_mut()
                    .unwrap()
                    .account
                    .expires_at_ms = 1
            }
            _ => unreachable!(),
        }
        let retained = inner.acquisition.as_ref().unwrap().value.clone();
        // This is the actual callback's gate: only consume's success permits
        // construction of the oauth/token request. No HTTP/provider is invoked.
        let mut exchange_progressions = 0;
        let result = inner.consume(&callback).map(|_| exchange_progressions += 1);
        assert!(result.is_err(), "{change} reached exchange progression");
        assert_eq!(exchange_progressions, 0);
        assert!(!inner.exchanging && inner.pending.is_none() && inner.content.is_none());
        assert_eq!(inner.acquisition.as_ref().unwrap().value, retained);
        assert_eq!(inner.continuation_status().state, "INELIGIBLE");
    }
    #[test]
    fn callback_before_exchange_refuses_expired_acquisition() {
        callback_before_exchange_refuses("expiry");
    }
    #[test]
    fn callback_before_exchange_refuses_replaced_acquisition_without_generation_change() {
        callback_before_exchange_refuses("token");
    }
    #[test]
    fn callback_before_exchange_refuses_expired_account_proof() {
        callback_before_exchange_refuses("proof");
    }
    #[test]
    fn callback_before_exchange_retains_valid_callback_and_known_denial() {
        if crate::native_refresh::enabled() {
            let (inner, _) = timeout();
            assert_eq!(inner.continuation_status().state, "INELIGIBLE");
            return;
        }
        let (mut inner, callback, _) = callback_before_exchange_fixture();
        assert!(inner.consume(&callback).is_ok());
        assert!(inner.exchanging && inner.status().acquisition);
        for late_original in [false, true] {
            let (mut inner, callback, old) = callback_before_exchange_fixture();
            inner.acquisition.as_mut().unwrap().expires = Instant::now();
            let denial = if late_original {
                format!("{CALLBACK}?state={old}&error=access_denied")
            } else {
                callback.replace("code=synthetic-new-code", "error=access_denied")
            };
            assert_eq!(
                inner.consume(&denial).err().as_deref(),
                Some("AUTHORIZATION_REFUSED")
            );
            assert!(!inner.exchanging && inner.pending.is_none() && inner.content.is_none());
            assert!(inner.acquisition.is_some());
            assert_eq!(inner.reason, Some("AUTHORIZATION_REFUSED"));
        }
    }
    #[test]
    fn prepost_recheck_refuses_expiry_replacement_proof_and_late_denial_after_consume() {
        if crate::native_refresh::enabled() {
            let (inner, _) = timeout();
            assert_eq!(inner.continuation_status().state, "INELIGIBLE");
            return;
        }
        for change in [
            "monotonic_expiry",
            "wall_expiry",
            "token",
            "client",
            "proof",
            "denial",
            "logout",
        ] {
            let (mut inner, pending, mut witness, old) = pending();
            match change {
                "monotonic_expiry" => inner.acquisition.as_mut().unwrap().expires = Instant::now(),
                "wall_expiry" => {
                    inner.acquisition.as_mut().unwrap().wall_expires = SystemTime::now()
                }
                "token" => inner.acquisition = Some(token("replacement-acquisition")),
                "client" => inner.client_id = Some("replacement-client".into()),
                "proof" => witness.account.expires_at_ms = 1,
                "denial" => {
                    assert!(inner.observe_timed_out_refusal(&old));
                }
                _ => inner.invalidate(),
            }
            let mut original = pending;
            original.continuation = Some(witness);
            let mut exchange_progressions = 0;
            let result = inner
                .continuation_exchange_guard(&original)
                .map(|_| exchange_progressions += 1);
            assert!(result.is_err(), "{change} reached exchange progression");
            assert_eq!(exchange_progressions, 0);
            assert!(!inner.exchanging && inner.content.is_none());
            if change == "denial" {
                assert_eq!(inner.reason, Some("AUTHORIZATION_REFUSED"));
            }
        }
    }
    #[test]
    fn actual_pending_timeout_is_required_and_projection_is_closed() {
        if crate::native_refresh::enabled() {
            let (inner, _) = timeout();
            assert_eq!(inner.continuation_status().state, "INELIGIBLE");
            return;
        }
        let (mut inner, _) = timeout();
        let status = serde_json::to_value(inner.continuation_status()).unwrap();
        assert_eq!(
            status,
            serde_json::json!({"schema":SCHEMA,"state":"ELIGIBLE","resource":"CONTENT","reason":"CONTENT_PENDING_TIMEOUT"})
        );
        println!("CONTINUATION_ELIGIBLE_FIXTURE={status}");
        inner.content_timeout = None;
        inner.reason = Some("AUTH_TRANSACTION_EXPIRED");
        assert_eq!(inner.continuation_status().state, "INELIGIBLE");
        assert!(inner.begin_continuation_check().is_err());
    }
    #[test]
    fn explicit_check_is_one_shot_and_never_reuses_old_callback() {
        if crate::native_refresh::enabled() {
            let (inner, _) = timeout();
            assert_eq!(inner.continuation_status().state, "INELIGIBLE");
            return;
        }
        let (mut inner, old) = timeout();
        let anchor = inner.begin_continuation_check().unwrap();
        assert!(inner.begin_continuation_check().is_err());
        assert!(inner
            .consume(&format!("{CALLBACK}?state={old}&code=expired-code"))
            .is_err());
        assert!(inner.probe_current(&anchor));
        inner.fail_continuation(anchor.generation, IDENTITY_UNAVAILABLE);
        assert_eq!(
            inner.token(Resource::Acquisition).unwrap().value,
            "synthetic-acquisition"
        );
        assert_eq!(inner.continuation_status().state, "INELIGIBLE");
    }
    #[test]
    fn current_same_account_content_publishes_without_executive_chaining() {
        if crate::native_refresh::enabled() {
            let (inner, _) = timeout();
            assert_eq!(inner.continuation_status().state, "INELIGIBLE");
            return;
        }
        let (mut inner, pending, witness, _) = pending();
        let candidate = token("synthetic-content");
        let a = account(
            Resource::Acquisition,
            witness.anchor.acquisition_wall,
            &"a".repeat(64),
        );
        let c = account(Resource::Content, candidate.wall_expires, &"a".repeat(64));
        assert!(inner
            .finish_content_continuation(pending.generation, &witness, Ok((candidate, a, c)))
            .is_ok());
        assert!(inner.status().acquisition && inner.status().content);
        assert!(inner.pending.is_none() && inner.executive.is_none());
        assert_eq!(inner.executive_reason, ExecutiveReason::NotEstablished);
        assert!(inner.content_timeout.is_none());
        println!(
            "CONTINUATION_SUCCESS_FIXTURE={}",
            serde_json::to_value(inner.status()).unwrap()
        );
    }
    #[test]
    fn foreign_or_changed_account_never_publishes_content_or_clears_acquisition() {
        if crate::native_refresh::enabled() {
            let (inner, _) = timeout();
            assert_eq!(inner.continuation_status().state, "INELIGIBLE");
            return;
        }
        for resource in [Resource::Acquisition, Resource::Content] {
            let (mut inner, pending, witness, _) = pending();
            let candidate = token("candidate");
            let a_digest = if resource == Resource::Acquisition {
                "b".repeat(64)
            } else {
                "a".repeat(64)
            };
            let a = account(
                Resource::Acquisition,
                witness.anchor.acquisition_wall,
                &a_digest,
            );
            let c_digest = if resource == Resource::Content {
                "b".repeat(64)
            } else {
                "a".repeat(64)
            };
            let c = account(Resource::Content, candidate.wall_expires, &c_digest);
            assert!(inner
                .finish_content_continuation(pending.generation, &witness, Ok((candidate, a, c)))
                .is_err());
            assert_eq!(
                inner.token(Resource::Acquisition).unwrap().value,
                "synthetic-acquisition"
            );
            assert!(inner.content.is_none() && inner.pending.is_none());
            assert_eq!(inner.continuation_status().state, "INELIGIBLE");
        }
    }
    #[test]
    fn currentness_expiry_logout_client_and_replaced_token_refuse_candidate() {
        if crate::native_refresh::enabled() {
            let (inner, _) = timeout();
            assert_eq!(inner.continuation_status().state, "INELIGIBLE");
            return;
        }
        for change in ["expiry", "logout", "client", "token", "proof"] {
            let (mut inner, pending, mut witness, _) = pending();
            let candidate = token("candidate");
            let a = account(
                Resource::Acquisition,
                witness.anchor.acquisition_wall,
                &"a".repeat(64),
            );
            let c = account(Resource::Content, candidate.wall_expires, &"a".repeat(64));
            match change {
                "expiry" => {
                    inner.acquisition.as_mut().unwrap().wall_expires =
                        SystemTime::now() - Duration::from_secs(1)
                }
                "logout" => inner.invalidate(),
                "client" => inner.client_id = Some("other-client".into()),
                "token" => inner.acquisition = Some(token("replacement")),
                _ => witness.account.expires_at_ms = 1,
            }
            assert!(inner
                .finish_content_continuation(pending.generation, &witness, Ok((candidate, a, c)))
                .is_err());
            assert!(inner.content.is_none());
            assert_eq!(inner.continuation_status().state, "INELIGIBLE");
        }
    }
    #[test]
    fn active_exchange_unknown_refusal_restore_and_noncontent_timeout_are_ineligible() {
        if crate::native_refresh::enabled() {
            let (inner, _) = timeout();
            assert_eq!(inner.continuation_status().state, "INELIGIBLE");
            return;
        }
        for reason in [
            "TOKEN_EXCHANGE_FAILED",
            "AUTHORIZATION_REFUSED",
            "REFRESH_OUTCOME_UNCONFIRMED",
        ] {
            let (mut inner, _) = timeout();
            inner.reason = Some(reason);
            assert!(inner.begin_continuation_check().is_err());
        }
        for busy in ["pending", "exchange", "restore", "executive"] {
            let (mut inner, _) = timeout();
            match busy {
                "pending" => {
                    inner.transaction(Resource::Content).unwrap();
                }
                "exchange" => inner.exchanging = true,
                "restore" => inner.restoring = true,
                _ => inner.executive_reason = ExecutiveReason::AuthorizationRefused,
            }
            assert!(inner.begin_continuation_check().is_err());
        }
        for resource in [Resource::Acquisition, Resource::Executive] {
            let mut inner = Inner::with_executive_resource(
                Some("public-client"),
                Some("https://mcp.mastermind-x.com/os/executive"),
            );
            inner.acquisition = Some(token("acquisition"));
            inner.transaction(resource).unwrap();
            let expired = Instant::now() - Duration::from_secs(1);
            inner.pending.as_mut().unwrap().expires = expired;
            assert!(inner.expire_transaction(inner.generation, expired, Instant::now()));
            assert!(inner.begin_continuation_check().is_err());
        }
    }
    #[test]
    fn consumed_content_exchange_cannot_become_an_eligible_timeout() {
        let mut inner = Inner::new(Some("public-client"));
        inner.acquisition = Some(token("acquisition"));
        inner.transaction(Resource::Content).unwrap();
        let state = inner.pending.as_ref().unwrap().state.clone();
        let deadline = inner.pending.as_ref().unwrap().expires;
        inner
            .consume(&format!("{CALLBACK}?state={state}&code=code"))
            .unwrap();
        assert!(!inner.expire_transaction(inner.generation, deadline, deadline));
        assert!(inner.content_timeout.is_none());
        assert!(inner.begin_continuation_check().is_err());
    }
    #[test]
    fn pre_browser_handoff_rejoins_actual_a_expiry_and_identity() {
        if crate::native_refresh::enabled() {
            let (inner, _) = timeout();
            assert_eq!(inner.continuation_status().state, "INELIGIBLE");
            return;
        }
        for change in ["expiry", "proof", "token", "logout", "none"] {
            let (mut inner, _) = timeout();
            let anchor = inner.begin_continuation_check().unwrap();
            let proof = account(
                Resource::Acquisition,
                anchor.acquisition_wall,
                &"a".repeat(64),
            );
            inner.open_content_continuation(&anchor, proof).unwrap();
            assert!(inner.continuation_handoff_current());
            match change {
                "expiry" => inner.acquisition.as_mut().unwrap().expires = Instant::now(),
                "proof" => {
                    inner
                        .pending
                        .as_mut()
                        .unwrap()
                        .continuation
                        .as_mut()
                        .unwrap()
                        .account
                        .expires_at_ms = 1
                }
                "token" => inner.acquisition = Some(token("replacement")),
                "logout" => inner.invalidate(),
                _ => inner.pending = None,
            }
            assert!(!inner.continuation_handoff_current());
        }
    }
    #[test]
    fn late_exact_refusal_retires_timeout_and_inflight_candidate_without_other_state_replay() {
        if crate::native_refresh::enabled() {
            let (inner, _) = timeout();
            assert_eq!(inner.continuation_status().state, "INELIGIBLE");
            return;
        }
        let (mut inner, old) = timeout();
        assert!(inner
            .consume(&format!("{CALLBACK}?state={old}&error=access_denied"))
            .is_err());
        assert_eq!(inner.reason, Some("AUTHORIZATION_REFUSED"));
        assert!(inner.begin_continuation_check().is_err());
        let (mut inner, pending, witness, old) = pending();
        assert!(inner
            .consume(&format!("{CALLBACK}?state={old}&error=access_denied"))
            .is_err());
        let candidate = token("candidate");
        let a = account(
            Resource::Acquisition,
            witness.anchor.acquisition_wall,
            &"a".repeat(64),
        );
        let c = account(Resource::Content, candidate.wall_expires, &"a".repeat(64));
        assert!(inner
            .finish_content_continuation(pending.generation, &witness, Ok((candidate, a, c)))
            .is_err());
        assert_eq!(inner.reason, Some("AUTHORIZATION_REFUSED"));
        assert!(inner.content.is_none());
        assert!(inner.status().acquisition);
    }
    #[test]
    fn all_candidate_failures_preserve_a_and_never_offer_a_second_continuation() {
        if crate::native_refresh::enabled() {
            let (inner, _) = timeout();
            assert_eq!(inner.continuation_status().state, "INELIGIBLE");
            return;
        }
        for failure in [IDENTITY_UNAVAILABLE, IDENTITY_CHANGED, EXCHANGE_UNCONFIRMED] {
            let (mut inner, pending, witness, _) = pending();
            assert!(inner
                .finish_content_continuation(pending.generation, &witness, Err(failure.into()))
                .is_err());
            assert!(inner.status().acquisition && !inner.status().content);
            assert_eq!(inner.reason, Some(failure));
            assert!(inner.begin_continuation_check().is_err());
        }
    }
    #[test]
    fn metadata_bytes_reject_duplicates_unknown_resource_nonutf8_expiry_and_oversize() {
        let now = SystemTime::UNIX_EPOCH + Duration::from_secs(1);
        let wall = now + Duration::from_secs(10);
        let raw = format!(
            r#"{{"schema":"{IDENTITY_SCHEMA}","resource":"CONTENT","account_digest":"{}","expires_at_ms":5000}}"#,
            "a".repeat(64)
        );
        assert!(identity_bytes(raw.as_bytes(), Resource::Content, wall, now).is_ok());
        for bad in [
            raw.replace("5000", "true"),
            raw.replace("5000", "1.5"),
            raw.replace("5000", "1000"),
            raw.replace("CONTENT", "EXECUTIVE"),
            raw.replace("CONTENT", "ACQUISITION"),
            raw.replace("5000}", "5000,\"extra\":true}"),
            raw.replace("5000}", "5000,\"resource\":\"CONTENT\"}"),
        ] {
            assert!(identity_bytes(bad.as_bytes(), Resource::Content, wall, now).is_err());
        }
        assert!(identity_bytes(&[0xff], Resource::Content, wall, now).is_err());
        assert!(
            identity_bytes(&vec![b' '; IDENTITY_CAP + 1], Resource::Content, wall, now).is_err()
        );
    }
    #[test]
    fn activation_is_never_derived_from_build_or_s35_identity_and_endpoints_are_fixed() {
        let inner = Inner::new(Some("public-client"));
        assert_eq!(inner.continuation_status().state, "INELIGIBLE");
        assert_eq!(
            ACQUISITION_IDENTITY,
            "/workspace/native-authorization-identity/acquisition/current"
        );
        assert_eq!(
            CONTENT_IDENTITY,
            "/workspace/native-authorization-identity/content/current"
        );
        for path in [ACQUISITION_IDENTITY, CONTENT_IDENTITY] {
            let url = Url::parse(&format!("{ORIGIN}{path}")).unwrap();
            assert_eq!(url.origin().ascii_serialization(), ORIGIN);
            assert!(url.query().is_none() && url.fragment().is_none());
        }
    }
}
