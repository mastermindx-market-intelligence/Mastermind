//! Navigation stays separate from Terminal request issuance and sharing effects.
use crate::terminal_request_handoff::{RequestHandoffReceipt, RequestSelection};
use crate::terminal_session::TerminalSession;
use tauri::{AppHandle, State};
use tauri_plugin_opener::OpenerExt;
const ERROR: &str = "TERMINAL_SHARING_HANDOFF_UNAVAILABLE";

#[tauri::command]
pub async fn open_terminal_sharing_request(
    app: AppHandle,
    state: State<'_, TerminalSession>,
    selection: RequestSelection,
) -> Result<RequestHandoffReceipt, &'static str> {
    // This is a fresh read through the distinct private Terminal bearer owner.
    // A frontend UUID or old response alone can never qualify the handoff.
    let before = serde_json::to_value(crate::terminal_session::terminal_session_status(
        state.clone(),
    ))
    .map_err(|_| ERROR)?;
    if before.get("available").and_then(serde_json::Value::as_bool) != Some(true) {
        return Err(ERROR);
    }
    let feed = crate::terminal_session::read_terminal_sharing_requests(app.clone(), state.clone())
        .await
        .map_err(|_| ERROR)?;
    let after = serde_json::to_value(crate::terminal_session::terminal_session_status(state))
        .map_err(|_| ERROR)?;
    if before != after
        || feed.pointer("/viewer/principal_scope") != before.get("principal_scope")
        || feed.pointer("/viewer/session_scope") != before.get("session_scope")
    {
        return Err(ERROR);
    }
    crate::terminal_request_handoff::request_review(&selection, &feed, |url| {
        app.opener().open_url(url, None::<&str>).map_err(|_| ())
    })
}
