//! The app's native menu bar.
//!
//! Tauri's default menu already carries the standard Edit items (Undo, Cut,
//! Copy, Paste, Select All) and File > Close Window, and WKWebView honors
//! them in the focused field. What it lacks is everything a person expects
//! under View for a window that is a web page: Reload, text Zoom In / Out /
//! Actual Size, and Back (lane T8's keyboard table found the gap). This
//! module installs the default-equivalent menu plus those items, wired to
//! the main window's webview; nothing here grants a page any native command
//! — the handlers act only on menu events the person (or the menu's own
//! shortcuts, which are app-level, not page-level) triggers.

use tauri::menu::{Menu, MenuItem, PredefinedMenuItem, Submenu};
use tauri::Manager;

use crate::MAIN_WINDOW_LABEL;

/// Zoom bounds: WKWebView magnification is comfortable well inside this
/// range, and clamping stops a held shortcut from walking off to unreadable.
pub const ZOOM_MIN: f64 = 0.5;
pub const ZOOM_MAX: f64 = 2.0;
pub const ZOOM_STEP: f64 = 0.1;

/// One zoom step for the menu handlers. Pure so the clamp is testable.
#[derive(Debug, Clone, Copy, PartialEq)]
pub enum ZoomStep {
    In,
    Out,
    Reset,
}

pub fn next_zoom(current: f64, step: ZoomStep) -> f64 {
    let target = match step {
        ZoomStep::In => current + ZOOM_STEP,
        ZoomStep::Out => current - ZOOM_STEP,
        ZoomStep::Reset => 1.0,
    };
    target.clamp(ZOOM_MIN, ZOOM_MAX)
}

/// Shared so In/Out compose across menu events; a reload keeps the current
/// magnification, and this is also the single place it is reset from.
pub struct ZoomState(pub std::sync::Mutex<f64>);

impl Default for ZoomState {
    fn default() -> Self {
        // The webview starts unzoomed; a Mutex<f64> would default to 0.0.
        ZoomState(std::sync::Mutex::new(1.0))
    }
}

/// Install the menu bar. Replaces Tauri's default with an equivalent plus
/// the View additions; called once from `setup`.
pub fn install(app: &tauri::AppHandle) -> tauri::Result<()> {
    let about = PredefinedMenuItem::about(app, None, None)?;
    let services = PredefinedMenuItem::services(app, None)?;
    let hide = PredefinedMenuItem::hide(app, None)?;
    let hide_others = PredefinedMenuItem::hide_others(app, None)?;
    let quit = PredefinedMenuItem::quit(app, None)?;
    let sep_app_1 = PredefinedMenuItem::separator(app)?;
    let sep_app_2 = PredefinedMenuItem::separator(app)?;
    let sep_app_3 = PredefinedMenuItem::separator(app)?;
    let app_menu = Submenu::with_items(
        app,
        "Mastermind OS",
        true,
        &[
            &about,
            &sep_app_1,
            &services,
            &sep_app_2,
            &hide,
            &hide_others,
            &sep_app_3,
            &quit,
        ],
    )?;

    let close = PredefinedMenuItem::close_window(app, None)?;
    let file_menu = Submenu::with_items(app, "File", true, &[&close])?;

    let undo = PredefinedMenuItem::undo(app, None)?;
    let redo = PredefinedMenuItem::redo(app, None)?;
    let cut = PredefinedMenuItem::cut(app, None)?;
    let copy = PredefinedMenuItem::copy(app, None)?;
    let paste = PredefinedMenuItem::paste(app, None)?;
    let select_all = PredefinedMenuItem::select_all(app, None)?;
    let sep_edit = PredefinedMenuItem::separator(app)?;
    let edit_menu = Submenu::with_items(
        app,
        "Edit",
        true,
        &[&undo, &redo, &sep_edit, &cut, &copy, &paste, &select_all],
    )?;

    let reload = MenuItem::with_id(app, "shell-reload", "Reload", true, Some("CmdOrCtrl+R"))?;
    let zoom_in = MenuItem::with_id(app, "shell-zoom-in", "Zoom In", true, Some("CmdOrCtrl+="))?;
    let zoom_out = MenuItem::with_id(app, "shell-zoom-out", "Zoom Out", true, Some("CmdOrCtrl+-"))?;
    let zoom_actual =
        MenuItem::with_id(app, "shell-zoom-actual", "Actual Size", true, Some("CmdOrCtrl+0"))?;
    let back = MenuItem::with_id(app, "shell-back", "Back", true, Some("CmdOrCtrl+["))?;
    let fullscreen = PredefinedMenuItem::fullscreen(app, None)?;
    let sep_view_1 = PredefinedMenuItem::separator(app)?;
    let sep_view_2 = PredefinedMenuItem::separator(app)?;
    let sep_view_3 = PredefinedMenuItem::separator(app)?;
    let view_menu = Submenu::with_items(
        app,
        "View",
        true,
        &[
            &reload,
            &sep_view_1,
            &zoom_in,
            &zoom_out,
            &zoom_actual,
            &sep_view_2,
            &back,
            &sep_view_3,
            &fullscreen,
        ],
    )?;

    let minimize = PredefinedMenuItem::minimize(app, None)?;
    let maximize = PredefinedMenuItem::maximize(app, None)?;
    let close_dup = PredefinedMenuItem::close_window(app, None)?;
    let sep_window = PredefinedMenuItem::separator(app)?;
    let window_menu = Submenu::with_items(
        app,
        "Window",
        true,
        &[&minimize, &maximize, &sep_window, &close_dup],
    )?;

    let menu = Menu::with_items(
        app,
        &[&app_menu, &file_menu, &edit_menu, &view_menu, &window_menu],
    )?;
    app.set_menu(menu)?;
    Ok(())
}

/// Handle one menu event. Unknown ids (none exist today) are ignored.
pub fn handle_event(app: &tauri::AppHandle, id: &str) {
    let Some(window) = app.get_webview_window(MAIN_WINDOW_LABEL) else {
        return;
    };
    let zoom = app
        .try_state::<ZoomState>()
        .map(|state| state.0.lock().expect("zoom state lock").to_owned());
    match id {
        "shell-reload" => {
            let _ = window.eval("location.reload()");
        }
        "shell-back" => {
            let _ = window.eval("history.back()");
        }
        "shell-zoom-in" | "shell-zoom-out" | "shell-zoom-actual" => {
            let step = match id {
                "shell-zoom-in" => ZoomStep::In,
                "shell-zoom-out" => ZoomStep::Out,
                _ => ZoomStep::Reset,
            };
            let current = zoom.unwrap_or(1.0);
            let target = next_zoom(current, step);
            if window.set_zoom(target).is_ok() {
                if let Some(state) = app.try_state::<ZoomState>() {
                    *state.0.lock().expect("zoom state lock") = target;
                }
            }
        }
        _ => {}
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn zoom_steps_clamp_at_the_bounds_and_reset() {
        let mut z = 1.0;
        for _ in 0..50 {
            z = next_zoom(z, ZoomStep::In);
        }
        assert_eq!(z, ZOOM_MAX);
        for _ in 0..50 {
            z = next_zoom(z, ZoomStep::Out);
        }
        assert_eq!(z, ZOOM_MIN);
        assert_eq!(next_zoom(z, ZoomStep::Reset), 1.0);
        let close = |a: f64, b: f64| (a - b).abs() < 1e-9;
        assert!(close(next_zoom(1.0, ZoomStep::In), 1.1));
        assert!(close(next_zoom(1.05, ZoomStep::Out), 0.95));
    }
}
