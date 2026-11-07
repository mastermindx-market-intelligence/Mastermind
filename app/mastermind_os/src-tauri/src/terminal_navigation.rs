//! Dedicated fixed public-site navigation; no caller-supplied URL or identity.
//! Terminal authenticates and authorizes its own user after navigation.

use tauri::AppHandle;
use tauri_plugin_opener::OpenerExt;

#[derive(serde::Serialize)]
pub struct BriefsLandingReceipt {
    schema: &'static str,
    destination: &'static str,
    outcome: &'static str,
}

/// The main crate registers this closed, zero-input command. The opener is
/// invoked once; neither a returned receipt nor an error permits an automatic
/// retry or proves browser load, sign-in, content, access, or a sharing effect.
#[tauri::command]
pub fn open_terminal_briefs(app: AppHandle) -> Result<BriefsLandingReceipt, &'static str> {
    let receipt = crate::terminal_handoff::request_briefs_landing(|url| {
        app.opener().open_url(url, None::<&str>).map_err(|_| ())
    })
    .map_err(|error| error.code())?;
    Ok(BriefsLandingReceipt {
        schema: receipt.schema,
        destination: receipt.destination,
        outcome: receipt.outcome,
    })
}
