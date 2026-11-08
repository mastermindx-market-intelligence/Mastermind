//! A presentation window over the incumbent complete DeepSeek application.
//! No provider client, message proxy, credential injection or company-parent
//! impersonation. Application IPC is denied to this remote webview by the ACL.
use super::{AppHandle, Manager, NativeAuth, Resource, Result};
use std::sync::Mutex;
use tauri::{WebviewUrl, WebviewWindow, WebviewWindowBuilder};
use url::Url;

const LABEL: &str = "deepseek-chat";
const ORIGIN: &str = "https://chat.mastermind-x.com/";
static VIEW_GENERATION: Mutex<Option<u64>> = Mutex::new(None);

// Hide immediately, then force retirement without a cancellable close-request
// event. Keep the original generation fence if native destruction is unconfirmed.
fn retire(attached: &mut Option<u64>, hide: impl FnOnce(), destroy: impl FnOnce() -> bool) -> bool {
    hide();
    if destroy() { *attached = None; true } else { false }
}

fn retire_window(app: &AppHandle, attached: &mut Option<u64>) -> bool {
    match app.get_webview_window(LABEL) {
        Some(window) => retire(attached, || { let _ = window.hide(); }, || window.destroy().is_ok()),
        None => { *attached = None; true }
    }
}

fn remote_navigation_allowed(url: &Url) -> bool {
    url.scheme() == "https" && url.host_str() == Some("chat.mastermind-x.com")
        && url.port().is_none()
        && url.username().is_empty() && url.password().is_none()
}

fn local_main(label: &str, url: &Url) -> bool {
    label == "main" && url.username().is_empty() && url.password().is_none() &&
        ((url.scheme() == "tauri" && url.host_str() == Some("localhost") && url.port().is_none()) ||
         (matches!(url.scheme(), "http" | "https") && url.host_str() == Some("tauri.localhost") && url.port().is_none()) ||
         (cfg!(debug_assertions) && url.scheme() == "http" && url.host_str() == Some("localhost") && url.port() == Some(5173)))
}

/// Called by the incumbent authentication owner, including passive status reads.
/// Closing a private view does not stop DeepSeek or modify its native credentials.
pub(super) fn auth_changed(app: &AppHandle, generation: u64, signed_in: bool) {
    let Ok(mut attached) = VIEW_GENERATION.lock() else { return; };
    if attached.is_some_and(|original| original != generation || !signed_in) {
        if !retire_window(app, &mut attached) { eprintln!("NATIVE_CHAT_RETIREMENT_UNCONFIRMED"); }
    }
}

#[derive(serde::Serialize)]
pub struct Opened { state: &'static str, window_label: &'static str }

#[tauri::command]
pub async fn open_deepseek_chat(app: AppHandle, webview: WebviewWindow) -> Result<Opened> {
    if !local_main(webview.label(), &webview.url().map_err(|_| "NATIVE_CHAT_CALLER_UNAVAILABLE")?) {
        return Err("NATIVE_CHAT_CALLER_REFUSED".into());
    }
    let state = app.state::<NativeAuth>();
    let inner = state.lock()?;
    if inner.status().status != "signed_in" || inner.token(Resource::Acquisition).is_none() {
        return Err("NATIVE_CHAT_SIGN_IN_REQUIRED".into());
    }
    let generation = inner.generation;
    let mut attached = VIEW_GENERATION.try_lock().map_err(|_| "NATIVE_CHAT_BUSY")?;
    if let Some(window) = app.get_webview_window(LABEL) {
        if *attached != Some(generation) {
            if !retire_window(&app, &mut attached) { return Err("NATIVE_CHAT_RETIREMENT_UNCONFIRMED".into()); }
            return Err("AUTHENTICATION_CHANGED".into());
        }
        window.show().map_err(|_| "NATIVE_CHAT_WINDOW_UNAVAILABLE")?;
        window.set_focus().map_err(|_| "NATIVE_CHAT_WINDOW_UNAVAILABLE")?;
    } else {
        let url = Url::parse(ORIGIN).map_err(|_| "NATIVE_CHAT_CONFIG_INVALID")?;
        WebviewWindowBuilder::new(&app, LABEL, WebviewUrl::External(url))
            .title("Mastermind OS · DeepSeek")
            .inner_size(1080.0, 780.0).min_inner_size(390.0, 600.0)
            .on_navigation(remote_navigation_allowed)
            .on_new_window(|_, _| tauri::webview::NewWindowResponse::Deny)
            .build().map_err(|_| "NATIVE_CHAT_WINDOW_UNAVAILABLE")?;
        *attached = Some(generation);
    }
    // Window creation is not native authentication, a streamed reply, or service
    // installation. The existing app's signed-cookie/provider owners remain owed.
    Ok(Opened { state: "OPENED", window_label: LABEL })
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn signout_hides_first_and_keeps_the_generation_fence_until_destroyed() {
        use std::cell::RefCell;
        let effects = RefCell::new(Vec::new());
        let mut attached = Some(7);
        assert!(!retire(&mut attached, || effects.borrow_mut().push("hide"), || { effects.borrow_mut().push("destroy failed"); false }));
        assert_eq!(attached, Some(7));
        assert_eq!(*effects.borrow(), vec!["hide", "destroy failed"]);
        assert!(retire(&mut attached, || effects.borrow_mut().push("hide"), || { effects.borrow_mut().push("destroyed"); true }));
        assert_eq!(attached, None);
        assert_eq!(*effects.borrow(), vec!["hide", "destroy failed", "hide", "destroyed"]);
    }
    #[test]
    fn remote_navigation_never_reaches_local_or_other_origins() {
        for value in [ORIGIN, "https://chat.mastermind-x.com/session/one", "https://chat.mastermind-x.com/?token=private-fixture"] {
            assert!(remote_navigation_allowed(&Url::parse(value).unwrap()));
        }
        for value in ["http://chat.mastermind-x.com/", "https://chat.mastermind-x.com.evil/", "https://chat.mastermind-x.com:444/",
            "https://user:secret@chat.mastermind-x.com/", "https://mcp.mastermind-x.com/", "http://127.0.0.1:4180/", "tauri://localhost", "file:///tmp/a"] {
            assert!(!remote_navigation_allowed(&Url::parse(value).unwrap()), "{value}");
        }
    }
    #[test]
    fn a_remote_or_secondary_view_cannot_open_privileged_windows() {
        assert!(local_main("main", &Url::parse("tauri://localhost/").unwrap()));
        for (label, url) in [(LABEL, ORIGIN), ("main", ORIGIN), (LABEL, "tauri://localhost/"), ("main", "file:///tmp/a")] {
            assert!(!local_main(label, &Url::parse(url).unwrap()));
        }
    }
}
