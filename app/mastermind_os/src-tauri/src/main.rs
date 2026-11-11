mod auth;
mod dev_log;
mod shell_menu;
mod shell_mode;
mod shell_pairing;
mod native_session_send;
mod project_planning;
mod project_execution;
mod fresh_conversation;
mod project_conversations_read;
mod native_client;
mod native_refresh;
mod terminal_handoff;
mod terminal_navigation;
mod terminal_public_config;
mod terminal_request_handoff;
mod terminal_session;
mod terminal_sharing_navigation;
use sha2::{Digest, Sha256};
use tauri_plugin_deep_link::DeepLinkExt;

#[derive(serde::Serialize)]
struct Readiness {
    version: &'static str,
    source_revision: &'static str,
    build_identity: &'static str,
    install_marker: &'static str,
    transport: &'static str,
    state: &'static str,
    native_client_ref: Option<String>,
}

/// One greppable line embedded in the executable so installed-bundle receipts
/// (scripts/mmos_installed_receipt.py) can extract the build identity with
/// provenance `embedded_marker` instead of a heuristic rodata scan. Referenced
/// by `Readiness` so the linker always keeps the bytes in the binary; the
/// build.rs charset assertion keeps the embedded JSON well-formed.
const MM_RECEIPT_MARKER: &str = concat!(
    "MM_RECEIPT:{\"source_revision\":\"",
    env!("MM_SOURCE_REVISION"),
    "\",\"build_identity\":\"",
    env!("MM_BUILD_IDENTITY"),
    "\"}"
);

fn readiness_from_client_id(client_id: Option<&str>) -> Result<Readiness, &'static str> {
    let native_client_ref = match client_id {
        None => None,
        Some(value) => {
            native_client::validate_native_client_id(value)?;
            let mut digest = Sha256::new();
            digest.update(b"mastermind.native_client_ref.v1\0");
            digest.update(value.as_bytes());
            Some(format!("native-client:v1:{:x}", digest.finalize()))
        }
    };
    Ok(Readiness {
        version: env!("CARGO_PKG_VERSION"),
        source_revision: env!("MM_SOURCE_REVISION"),
        build_identity: env!("MM_BUILD_IDENTITY"),
        install_marker: MM_RECEIPT_MARKER,
        transport: if native_client_ref.is_some() {
            "CONFIGURED"
        } else {
            "UNCONFIGURED"
        },
        state: "BUILT_NOT_PROVEN",
        native_client_ref,
    })
}

#[tauri::command]
fn readiness() -> Readiness {
    readiness_from_client_id(option_env!("MM_NATIVE_CLIENT_ID"))
        .expect("MM_NATIVE_CLIENT_ID was validated at build time")
}

const MAIN_WINDOW_LABEL: &str = "main";

/// Reads the shell URL exactly once, preferring `MM_SHELL_URL_FILE` over the
/// legacy `MM_SHELL_URL`, both over the fixed per-user config file (lane T8:
/// a Finder/Dock launch has no environment). The file keeps a one-time
/// pairing fragment out of argv and the process environment. Unset settings
/// and a missing config file change nothing; refused settings are logged
/// without their input and are treated exactly like unset.
fn shell_url_from_env(identifier: &str) -> (Option<url::Url>, shell_mode::ShellConfig) {
    shell_mode::resolve_shell_settings(identifier)
}

/// Build the shell-mode main window.
///
/// The configuration window is normally created by Tauri before `setup` runs, which
/// leaves no way to add an initialization script. In shell mode the config entry is
/// marked `create: false`, so this builder is the only creator and can inject the
/// page bootstrap before any page script runs. `.navigate` then points the webview
/// at the local shell server; `setup` runs before the event loop, so the app
/// frontend never gets a chance to paint (no sign-in gate flash).
fn build_shell_window(
    app: &tauri::AppHandle,
    url: &url::Url,
    pair_helper: Option<&std::path::Path>,
) -> Result<(), Box<dyn std::error::Error>> {
    let config = app
        .config()
        .app
        .windows
        .iter()
        .find(|config| config.label == MAIN_WINDOW_LABEL)
        .ok_or("MAIN_WINDOW_CONFIG_UNAVAILABLE")?;
    let window = tauri::WebviewWindowBuilder::from_config(app, config)?
        .initialization_script(shell_mode::SHELL_PAGE_BOOTSTRAP)
        .build()?;
    window.navigate(url.clone())?;
    if let Some(helper) = pair_helper {
        // Unattended re-pairing (lane T8): runs the fixed helper only when the
        // loaded page turns out to be this server's pairing page, once per
        // launch. See shell_pairing.rs for the authority and secret rules.
        shell_pairing::spawn_watchdog(app.clone(), MAIN_WINDOW_LABEL, url.clone(), helper.to_path_buf());
    }
    Ok(())
}

fn terminal_callback_owner(url: &url::Url) -> bool {
    url.scheme() == "com.mastermind.os" && url.host_str() == Some("terminal")
}

fn dispatch_auth_callback(app: tauri::AppHandle, url: url::Url) {
    // The Terminal callback has a distinct owner. Malformed Terminal callbacks
    // are refused there and never fall through to the Auth0 callback owner.
    if terminal_callback_owner(&url) {
        tauri::async_runtime::spawn(terminal_session::callback(app, url.to_string()));
    } else {
        tauri::async_runtime::spawn(auth::callback(app, url.to_string()));
    }
}

#[cfg(target_os = "macos")]
fn reopen_main_window(app: &tauri::AppHandle, shell: Option<&url::Url>) -> Result<(), &'static str> {
    use tauri::Manager;

    // Closing the macOS window can leave the existing application alive. Reopen
    // its one configured window without rebuilding app state or restarting auth.
    let window = match app.get_webview_window(MAIN_WINDOW_LABEL) {
        Some(window) => window,
        None => {
            let config = app.config().app.windows.iter()
                .find(|config| config.label == MAIN_WINDOW_LABEL)
                .ok_or("MAIN_WINDOW_CONFIG_UNAVAILABLE")?;
            let mut builder = tauri::WebviewWindowBuilder::from_config(app, config)
                .map_err(|_| "MAIN_WINDOW_REOPEN_UNAVAILABLE")?;
            // Only shell mode reopens its window with the page bootstrap.
            if shell.is_some() {
                builder = builder.initialization_script(shell_mode::SHELL_PAGE_BOOTSTRAP);
            }
            let window = builder
                .build()
                .map_err(|_| "MAIN_WINDOW_REOPEN_UNAVAILABLE")?;
            if let Some(url) = shell {
                window
                    .navigate(url.clone())
                    .map_err(|_| "MAIN_WINDOW_REOPEN_UNAVAILABLE")?;
            }
            window
        }
    };
    window.show().map_err(|_| "MAIN_WINDOW_REOPEN_UNAVAILABLE")?;
    window.unminimize().map_err(|_| "MAIN_WINDOW_REOPEN_UNAVAILABLE")?;
    window.set_focus().map_err(|_| "MAIN_WINDOW_REOPEN_UNAVAILABLE")?;
    Ok(())
}

fn main() {
    let mut context = tauri::generate_context!();
    let (shell_url, shell_config) = shell_url_from_env(&context.config().identifier);
    if shell_url.is_some() {
        // Shell mode builds the main window in `setup` so it can carry the page
        // bootstrap; stop Tauri from creating an unstamped one first.
        for window in context.config_mut().app.windows.iter_mut() {
            if window.label == MAIN_WINDOW_LABEL {
                window.create = false;
            }
        }
    }
    let setup_shell_url = shell_url.clone();
    let setup_shell_config = shell_config;
    let app = tauri::Builder::default()
        .manage(auth::NativeAuth::new().expect("native transport configuration"))
        .manage(terminal_session::TerminalSession::new().expect("Terminal transport configuration"))
        .manage(shell_menu::ZoomState::default())
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_deep_link::init())
        .on_menu_event(|app, event| shell_menu::handle_event(app, event.id().as_ref()))
        .setup(move |app| {
            let handle = app.handle().clone();
            app.deep_link().on_open_url(move |event| {
                // Callback values stay in Rust and are never logged.
                for url in event.urls() {
                    let app = handle.clone();
                    dispatch_auth_callback(app, url.clone());
                }
            });
            auth::start_restore(app.handle().clone());
            shell_menu::install(app.handle())?;
            if let Some(urls) = app.deep_link().get_current()? {
                for url in urls {
                    dispatch_auth_callback(app.handle().clone(), url);
                }
            }
            if let Some(url) = setup_shell_url.as_ref() {
                build_shell_window(
                    app.handle(),
                    url,
                    setup_shell_config.pair_helper.as_deref(),
                )?;
            }
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            readiness,
            terminal_navigation::open_terminal_briefs,
            terminal_session::terminal_session_status,
            terminal_session::terminal_sign_in,
            terminal_session::terminal_disconnect,
            terminal_session::read_terminal_sharing_requests,
            terminal_sharing_navigation::open_terminal_sharing_request,
            auth::auth_status,
            auth::hermes_native::hermes_native,
            auth::native_draft_identity::read_native_draft_continuity,
            auth::sign_in,
            auth::primary_account::sign_in_primary,
            auth::work_authorization::read_work_authorization,
            auth::work_authorization::sign_in_for_work,
            auth::authorization_continuation::read_authorization_continuation,
            auth::authorization_continuation::continue_authorization,
            auth::sign_out,
            auth::read_programs,
            auth::read_byok_roles,
            auth::control_room_read::read_control_room_state,
            auth::company_priorities::read_company_priorities,
            auth::read_work,
            auth::read_mission,
            auth::read_mission_v3,
            auth::read_project_plan,
            auth::read_project_journal,
            auth::read_project_knowledge_catalogue,
            auth::read_project_knowledge_memory,
            auth::read_project_knowledge_source,
            auth::read_project_session,
            auth::read_project_direction,
            auth::read_project_admission_control,
            auth::pause_project_admission,
            auth::resume_project_admission,
            auth::read_project_admission_operation,
            auth::read_project_archive,
            auth::read_project_archive_page,
            auth::read_source_operation_context,
            auth::source_operation_options,
            auth::source_operation_prepare,
            auth::source_operation_read,
            auth::source_operation_submit,
            auth::source_operation_reconcile,
            auth::source_operation_advance,
            auth::project_access::read_project_access,
            auth::instruction_admission::read_project_instructions,
            auth::instruction_admission::read_instruction_admission_control,
            auth::instruction_admission::pause_instruction_admission,
            auth::instruction_admission::read_instruction_admission_operation,
            auth::read_autonomy_policy,
            auth::read_admitted_plan,
            auth::read_retained_activity,
            auth::read_resource_capacity,
            auth::read_model_configuration,
            auth::read_capacity_fabric,
            auth::host_observation::read_host_observation,
            auth::read_fabric_catalog,
            auth::read_fabric_status,
            auth::read_t3_attempt_fleet,
            auth::read_result,
            auth::read_mission_result,
            auth::read_result_references,
            auth::read_current_window,
            auth::executive_auth_status,
            auth::executive_context,
            auth::executive_submit,
            auth::executive_status,
            auth::executive_direct_native_result,
            auth::executive_direct_native_consume,
            auth::executive_direct_correction,
            auth::executive_project_planning,
            auth::executive_project_execution,
            auth::executive_fresh_conversation,
            auth::executive_session_context,
            auth::executive_session_send,
            auth::executive_project_history_context,
            auth::executive_project_conversations_read,
            auth::executive_session_reply,
            auth::executive_session_references,
            auth::executive_project_session_references
        ])
        .build(context)
        .expect("tauri runtime error");
    app.run(move |_app, _event| {
        #[cfg(target_os = "macos")]
        if let tauri::RunEvent::Reopen { has_visible_windows: false, .. } = _event {
            if let Err(code) = reopen_main_window(_app, shell_url.as_ref()) {
                // Only a fixed local window error is logged, never callback data.
                eprintln!("Mastermind OS: {code}");
            }
        }
    });
}

#[cfg(test)]
mod readiness_tests {
    use super::*;

    #[test]
    fn terminal_callback_dispatch_keeps_existing_auth0_owner_separate() {
        for value in ["com.mastermind.os://terminal/callback?code=synthetic", "com.mastermind.os://terminal/wrong-path#rejected"] {
            assert!(terminal_callback_owner(&url::Url::parse(value).unwrap()));
        }
        for value in ["com.mastermind.os://oauth/callback?code=synthetic", "https://terminal/callback", "com.mastermind.os://terminal.evil/callback"] {
            assert!(!terminal_callback_owner(&url::Url::parse(value).unwrap()));
        }
    }

    #[test]
    fn unconfigured_readiness_has_no_native_client_reference() {
        let value = readiness_from_client_id(None).expect("unconfigured readiness");
        assert_eq!(value.transport, "UNCONFIGURED");
        assert_eq!(value.state, "BUILT_NOT_PROVEN");
        assert_eq!(value.native_client_ref, None);
        assert_eq!(
            serde_json::to_value(value).unwrap()["native_client_ref"],
            serde_json::Value::Null
        );
    }

    #[test]
    fn configured_readiness_exposes_only_the_domain_separated_reference() {
        let raw = "tpc_native-client-01";
        let value = readiness_from_client_id(Some(raw)).expect("configured readiness");
        assert_eq!(value.transport, "CONFIGURED");
        assert_eq!(value.state, "BUILT_NOT_PROVEN");
        assert_eq!(
            value.native_client_ref.as_deref(),
            Some(
                "native-client:v1:ed9e6a2e3cf7a24fcaf319eba68d91745e23cabcc14e1dfcacfb15b50191fb04"
            )
        );
        let serialized = serde_json::to_string(&value).unwrap();
        assert!(!serialized.contains(raw));
        assert!(!serialized.contains("tpc_"));
    }

    #[test]
    fn configured_identity_validation_matches_the_native_auth_owner() {
        for invalid in [
            "",
            "invalid client",
            "client/slash",
            "client.dot",
            "client:colon",
            "client\nnewline",
        ] {
            assert!(
                readiness_from_client_id(Some(invalid)).is_err(),
                "{invalid:?}"
            );
        }
        let oversized = "a".repeat(129);
        assert!(readiness_from_client_id(Some(&oversized)).is_err());

        let boundary = "a".repeat(128);
        assert!(readiness_from_client_id(Some(&boundary)).is_ok());
        assert!(readiness_from_client_id(Some("tpc_A1_-valid")).is_ok());
    }
}
