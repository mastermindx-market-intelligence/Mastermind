//! Private native binding to the existing authenticated Workspace READ owner.
//! No refresh/sign-in is attempted here. No bearer or draft reaches webview.
use super::{AppHandle, Manager, Resource, NativeAuth, Result, Url, Value, Duration,
    ORIGIN, bounded_json};
use super::draft_continuity::Phase;
use super::Inner;
use std::time::{SystemTime, UNIX_EPOCH};

const PATH: &str = "/workspace/native-draft-identity/current";
const SCHEMA: &str = "mastermind.native_draft_identity.v1";
fn millis(time: SystemTime) -> Option<u64> {
    u64::try_from(time.duration_since(UNIX_EPOCH).ok()?.as_millis()).ok()
}
pub(super) fn identity(body: &Value, now: u64, token_expires: u64) -> Option<(String, u64)> {
    let object = body.as_object()?;
    if object.len() != 3 || !["schema", "principal_scope", "expires_at_ms"].iter().all(|key| object.contains_key(*key))
        || object.get("schema")?.as_str()? != SCHEMA { return None; }
    let scope = object.get("principal_scope")?.as_str()?;
    if scope.len() != 64 || !scope.bytes().all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b)) { return None; }
    let expires = object.get("expires_at_ms")?.as_u64()?;
    let deadline = expires.min(token_expires);
    if expires > 8_640_000_000_000_000 || deadline <= now { return None; }
    Some((scope.to_owned(), deadline))
}

fn view(inner: &Inner, deadline: Option<u64>) -> Result<Value> {
    serde_json::to_value(inner.draft_continuity.snapshot(deadline)).map_err(|_| "IDENTITY_UNAVAILABLE".into())
}
#[tauri::command]
pub async fn read_native_draft_continuity(app: AppHandle) -> Result<Value> {
    let state = app.state::<NativeAuth>();
    let (generation, value, token_wall) = {
        let mut inner = state.lock()?;
        // Explicit logout is destructive even if Keychain deletion failed.
        if matches!(inner.draft_continuity.snapshot(None).phase, Phase::Withdrawn) {
            return view(&inner, None);
        }
        if inner.pending.is_some() || inner.exchanging || inner.restoring {
            inner.draft_continuity.begin_reauthentication();
            return view(&inner, None);
        }
        match inner.token(Resource::Acquisition) {
            Some(token) => (inner.generation, token.value.clone(), token.wall_expires),
            None => {
                if inner.acquisition.is_some() || inner.content.is_some() {
                    inner.draft_continuity.expire();
                } else { inner.draft_continuity.unqualified(); }
                return view(&inner, None);
            }
        }
    };
    let url = Url::parse(&format!("{ORIGIN}{PATH}")).map_err(|_| "REQUEST_INVALID")?;
    let response = state.http.get(url).bearer_auth(&value).header("Accept", "application/json")
        .header("Cache-Control", "no-store").timeout(Duration::from_secs(30)).send().await;
    let body = match response { Ok(response) => bounded_json(response, 1024).await.ok(), Err(_) => None };
    let mut inner = state.lock()?;
    if inner.generation != generation || !inner.token(Resource::Acquisition).is_some_and(|token| token.value == value) {
        // Never change a newer owner's private candidate with a stale read.
        return Err("AUTHENTICATION_CHANGED".into());
    }
    let qualified = body.as_ref().and_then(|body| identity(body, millis(SystemTime::now())?, millis(token_wall)?));
    if let Some((scope, expires)) = qualified {
        if inner.draft_continuity.confirm(&scope) {
            // A Content expiry still withholds that resource's private body.
            // The fresh identity is observation only; no lost grant is restored.
            if inner.content.as_ref().is_some_and(|_| inner.token(Resource::Content).is_none()) {
                inner.draft_continuity.expire();
                return view(&inner, None);
            }
            return view(&inner, Some(expires));
        }
    }
    inner.draft_continuity.unqualified();
    view(&inner, None)
}

#[cfg(test)]
mod native_draft_identity_tests {
    use super::*;
    #[test]
    fn fixed_current_identity_is_not_an_event_or_caller_scope() {
        let body = serde_json::json!({"schema":SCHEMA,"principal_scope":"a".repeat(64),"expires_at_ms":5000});
        assert_eq!(identity(&body, 1000, 4000), Some(("a".repeat(64),4000)));
        for now in [4000,5000] { assert!(identity(&body,now,4000).is_none()); }
        let mut foreign=body.clone();foreign["token"]=Value::String("not-public".into());assert!(identity(&foreign,1000,4000).is_none());
        foreign=body.clone();foreign["principal_scope"]=Value::String("a".repeat(64)+"\n");assert!(identity(&foreign,1000,4000).is_none());
        foreign=body;foreign["schema"]=Value::String("public-event".into());assert!(identity(&foreign,1000,4000).is_none());
        let url=Url::parse(&format!("{ORIGIN}{PATH}")).unwrap();assert_eq!(url.origin().ascii_serialization(),ORIGIN);
        assert_eq!(url.path(),PATH);assert!(url.query().is_none());
    }
}
