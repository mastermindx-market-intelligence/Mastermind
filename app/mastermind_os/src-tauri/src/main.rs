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

/// Serializes tests that temporarily swap process-wide environment variables
/// (`HOME`, `MMOS_DEV_ROOT`): several of them exist across modules and would
/// otherwise race each other's save/restore windows.
#[cfg(test)]
pub static ENV_SWAP_LOCK: std::sync::Mutex<()> = std::sync::Mutex::new(());

/// Reads the shell URL exactly once, preferring `MM_SHELL_URL_FILE` over the
/// legacy `MM_SHELL_URL`, both over the fixed per-user config file (lane T8:
/// a Finder/Dock launch has no environment). The file keeps a one-time
/// pairing fragment out of argv and the process environment. Unset settings
/// and a missing config file change nothing; refused settings are logged
/// without their input and are treated exactly like unset.
fn shell_url_from_env(identifier: &str) -> (Option<url::Url>, shell_mode::ShellConfig) {
    shell_mode::resolve_shell_settings(identifier)
}

/// Build (or rebuild) the one configured main window. This is the *one*
/// shared window-building function: the first shell-mode build in `setup` and
/// the Dock-reopen rebuild both go through it, so the two paths cannot drift
/// (panel repair A).
///
/// The configuration window is normally created by Tauri before `setup` runs, which
/// leaves no way to add an initialization script. In shell mode the config entry is
/// marked `create: false`, so this builder is the only creator and can inject the
/// page bootstrap before any page script runs. `.navigate` then points the webview
/// at the local shell server; `setup` runs before the event loop, so the app
/// frontend never gets a chance to paint (no sign-in gate flash).
///
/// Panel repair B: every shell window this builds carries the navigation
/// allowlist — the configured origin (scheme, host and port exact), the inert
/// blank page and the pairing failure page; every other http or https
/// address is refused in the window and opened in the person's default
/// browser through the opener plugin, and everything else is refused and
/// logged. Each successful build bumps the window generation so the
/// process-wide pairing watchdog can tell window instances apart. The
/// watchdog itself is started exactly once, in `setup`, when a helper is
/// configured — never here.
fn create_main_window(
    app: &tauri::AppHandle,
    shell: Option<&url::Url>,
    board: Option<&url::Url>,
) -> Result<tauri::WebviewWindow, &'static str> {
    let config = app
        .config()
        .app
        .windows
        .iter()
        .find(|config| config.label == MAIN_WINDOW_LABEL)
        .ok_or("MAIN_WINDOW_CONFIG_UNAVAILABLE")?;
    let mut builder = tauri::WebviewWindowBuilder::from_config(app, config)
        .map_err(|_| "MAIN_WINDOW_REOPEN_UNAVAILABLE")?;
    // Only shell mode builds its window with the page bootstrap and the
    // navigation allowlist.
    if let Some(url) = shell {
        let origin = url.clone();
        let board_origin = board.cloned();
        let failure_page = shell_pairing::failure_page_url().to_string();
        let handle = app.clone();
        builder = builder.on_navigation(move |url| {
            match shell_pairing::navigation_allowed(url, &origin, &failure_page, board_origin.as_ref()) {
                shell_pairing::NavDecision::Allow => true,
                shell_pairing::NavDecision::External => {
                    // The maintained way to hand an outside address to the
                    // person's default browser is the opener plugin, behind
                    // one throttle (panel round 2): the WebKit new-window
                    // path funnels into this same arm, so one throttle
                    // bounds both open paths, and a dropped open is logged
                    // there, never queued.
                    if shell_pairing::allow_external_open() {
                        let target = url.to_string();
                        let handle = handle.clone();
                        std::thread::spawn(move || {
                            use tauri_plugin_opener::OpenerExt;
                            let _ = handle.opener().open_url(target, None::<&str>);
                        });
                    }
                    shell_pairing::log_navigation_refused();
                    false
                }
                shell_pairing::NavDecision::Refuse => {
                    shell_pairing::log_navigation_refused();
                    false
                }
            }
        });
        // The generation this build will register: `create_main_window` is
        // the only build path and it runs on the event loop, so the bump
        // after a successful build returns exactly this value. When this
        // webview finishes its first load the gate opens — only then may
        // the watchdog poll the webview URL (wry 0.55.1 unwraps a nil URL
        // before any commit and would take the app down).
        let committed_generation = shell_pairing::window_generation() + 1;
        builder = builder.on_page_load(move |_, payload| {
            if matches!(payload.event(), tauri::webview::PageLoadEvent::Finished) {
                shell_pairing::mark_window_committed(committed_generation);
            }
        });
        builder = builder.initialization_script(shell_mode::SHELL_PAGE_BOOTSTRAP);
    }
    let window = builder
        .build()
        .map_err(|_| "MAIN_WINDOW_REOPEN_UNAVAILABLE")?;
    shell_pairing::bump_window_generation();
    if let Some(url) = shell {
        window
            .navigate(url.clone())
            .map_err(|_| "MAIN_WINDOW_REOPEN_UNAVAILABLE")?;
    }
    Ok(window)
}

fn terminal_callback_owner(url: &url::Url) -> bool {
    url.scheme() == "com.mastermind.os" && url.host_str() == Some("terminal")
}

/// Panel repair M: `--check-window-config`. One judge: this mode runs the
/// same loader functions a real launch runs (`fixed_config_dir`, the
/// repair-N folder check, the 0600/no-symlink file readers, the URL and
/// helper-line parsers, the helper trust walk) and prints one line per
/// item — `shell-url: ok` or `shell-url: refused <code>`, same for
/// `pair-helper` and `config-dir`. Lane PF adds `board-url: ok|absent|refused
/// <code>`: the board origin is optional, so `absent` is normal and does not
/// fail the check. No window is built, no helper or watchdog is started, and
/// no address or file contents are printed. Exit 0 only when every required
/// item passes.
fn run_window_config_check(identifier: &str) -> i32 {
    use std::io::Write as _;
    let (code, lines) = window_config_check_report(identifier);
    for line in &lines {
        println!("{line}");
    }
    let _ = std::io::stdout().flush();
    code
}

/// The judge's exact line list and exit code, separated from printing so a
/// test can assert the reported lines. Same loader a real launch uses.
fn window_config_check_report(identifier: &str) -> (i32, Vec<String>) {
    let mut lines: Vec<String> = Vec::new();
    let mut all_ok = true;
    fn line(
        lines: &mut Vec<String>,
        all_ok: &mut bool,
        item: &str,
        outcome: Result<(), String>,
    ) {
        match outcome {
            Ok(()) => lines.push(format!("{item}: ok")),
            Err(code) => {
                *all_ok = false;
                lines.push(format!("{item}: refused {code}"));
            }
        }
    }
    let home = std::env::var_os("HOME")
        .filter(|home| !home.is_empty())
        .map(std::path::PathBuf::from);
    let Some(dir) = home.as_deref().and_then(|home| {
        shell_mode::fixed_config_dir(identifier, home)
    }) else {
        for item in ["config-dir", "shell-url", "pair-helper"] {
            line(&mut lines, &mut all_ok, item, Err("no_dir_for_identifier".into()));
        }
        lines.push("board-url: absent".into());
        return (1, lines);
    };
    line(
        &mut lines,
        &mut all_ok,
        "config-dir",
        shell_mode::config_dir_refusal(&dir).map_or(Ok(()), |r| Err(r.subcode())),
    );
    let address = shell_mode::read_config_line(&dir, shell_mode::SHELL_URL_CONFIG_NAME)
        .and_then(|value| {
            shell_mode::parse_shell_url(&value).map_err(shell_mode::ShellUrlFileRefusal::Url)
        });
    match address {
        Ok(_) => line(&mut lines, &mut all_ok, "shell-url", Ok(())),
        Err(refusal) => line(&mut lines, &mut all_ok, "shell-url", Err(refusal.subcode())),
    }
    let helper = shell_mode::read_config_line(&dir, shell_mode::PAIR_HELPER_CONFIG_NAME)
        .and_then(|value| shell_mode::parse_pair_helper_line(&value));
    match helper {
        Ok(path) => {
            if shell_pairing::helper_is_trusted(&path) {
                line(&mut lines, &mut all_ok, "pair-helper", Ok(()));
            } else {
                line(&mut lines, &mut all_ok, "pair-helper", Err("helper_untrusted".into()));
            }
        }
        Err(refusal) => line(&mut lines, &mut all_ok, "pair-helper", Err(refusal.subcode())),
    }
    // Lane PF: the board origin is optional — a missing file or folder is the
    // normal unconfigured case (`absent`, exit stays 0); a clean origin is
    // `ok`; any other refusal fails the check with the board's own code.
    let board = shell_mode::read_config_line(&dir, shell_mode::BOARD_URL_CONFIG_NAME)
        .and_then(|value| {
            shell_mode::parse_board_url(&value).map_err(shell_mode::ShellUrlFileRefusal::BoardUrl)
        });
    match board {
        Ok(_) => line(&mut lines, &mut all_ok, "board-url", Ok(())),
        Err(shell_mode::ShellUrlFileRefusal::Missing) => lines.push("board-url: absent".into()),
        Err(refusal) => line(&mut lines, &mut all_ok, "board-url", Err(refusal.subcode())),
    }
    (if all_ok { 0 } else { 1 }, lines)
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
fn reopen_main_window(
    app: &tauri::AppHandle,
    shell: Option<&url::Url>,
    board: Option<&url::Url>,
) -> Result<(), &'static str> {
    use tauri::Manager;

    // Closing the macOS window can leave the existing application alive. Reopen
    // its one configured window through the shared builder (repair A) without
    // rebuilding app state or restarting auth. The rebuild bumps the window
    // generation, so the process-wide pairing watchdog drops any address it
    // minted for the previous instance and re-arms.
    let window = match app.get_webview_window(MAIN_WINDOW_LABEL) {
        Some(window) => window,
        None => create_main_window(app, shell, board)?,
    };
    window.show().map_err(|_| "MAIN_WINDOW_REOPEN_UNAVAILABLE")?;
    window.unminimize().map_err(|_| "MAIN_WINDOW_REOPEN_UNAVAILABLE")?;
    window.set_focus().map_err(|_| "MAIN_WINDOW_REOPEN_UNAVAILABLE")?;
    Ok(())
}

fn main() {
    use tauri::Manager;

    let mut context = tauri::generate_context!();
    // Panel repair M: `--check-window-config` builds no window, starts no
    // helper and no watchdog; it judges the fixed config with the same
    // loader a real launch uses and exits before any Tauri runtime exists.
    if std::env::args().nth(1).as_deref() == Some("--check-window-config") {
        std::process::exit(run_window_config_check(&context.config().identifier));
    }
    let (shell_url, shell_config) = shell_url_from_env(&context.config().identifier);
    // Lane PF: the optional board origin comes from the same fixed config
    // folder as the address, independent of the address source. Resolve it
    // before `shell_config` moves into the setup closure.
    let board_url = shell_mode::resolve_board_origin(&shell_config);
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
    let setup_board_url = board_url.clone();
    // Captured for the single-instance callback below (repair G).
    let single_instance_shell_url = shell_url.clone();
    let single_instance_board_url = board_url.clone();
    let app = tauri::Builder::default()
        .manage(auth::NativeAuth::new().expect("native transport configuration"))
        .manage(terminal_session::TerminalSession::new().expect("Terminal transport configuration"))
        .manage(shell_menu::ZoomState::default())
        // Registered first so it wins before any other plugin observes the
        // second launch. A second launch must never start a second session,
        // watchdog or auth restore: it only brings the existing window
        // forward, rebuilding it through the shared builder exactly like a
        // Dock reopen if the person had closed it.
        .plugin(tauri_plugin_single_instance::init(
            move |app, _argv, _cwd| {
                #[cfg(target_os = "macos")]
                if let Err(code) =
                    reopen_main_window(app, single_instance_shell_url.as_ref(), single_instance_board_url.as_ref())
                {
                    // Only a fixed local window error is logged, never callback data.
                    eprintln!("Mastermind OS: {code}");
                }
                #[cfg(not(target_os = "macos"))]
                {
                    use tauri::Manager;
                    if let Some(window) = app.get_webview_window(MAIN_WINDOW_LABEL) {
                        let _ = window.show();
                        let _ = window.set_focus();
                    }
                }
            },
        ))
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
            if let Some(url) = setup_shell_url.as_ref() {
                // The configured origin, for the View > Go to Server item.
                // Managed before the menu installs so the item can be enabled.
                app.manage(shell_menu::ShellAddress(url.clone()));
            }
            shell_menu::install(app.handle())?;
            if let Some(urls) = app.deep_link().get_current()? {
                for url in urls {
                    dispatch_auth_callback(app.handle().clone(), url);
                }
            }
            if let Some(url) = setup_shell_url.as_ref() {
                create_main_window(app.handle(), Some(url), setup_board_url.as_ref())?;
                // One watchdog per app process (repair A): started here, once,
                // only when a pair helper is configured. It follows the window
                // by generation, not label, and outlives every window build.
                if let Some(helper) = setup_shell_config.pair_helper.as_deref() {
                    shell_pairing::spawn_watchdog(
                        app.handle().clone(),
                        MAIN_WINDOW_LABEL,
                        url.clone(),
                        helper.to_path_buf(),
                    );
                }
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
            if let Err(code) = reopen_main_window(_app, shell_url.as_ref(), board_url.as_ref()) {
                // Only a fixed local window error is logged, never callback data.
                eprintln!("Mastermind OS: {code}");
            }
        }
    });
}

#[cfg(test)]
mod readiness_tests {
    use super::*;

    /// Panel repair M: the `--check-window-config` judge runs the real
    /// loader — a well-formed config passes all three items, and a symlinked
    /// config folder refuses every item with the folder's own code (N).
    /// Output is stdout-only codes; this test asserts the exit semantics.
    #[test]
    fn window_config_check_judges_the_real_loader_outcomes() {
        use std::fs;
        use std::os::unix::fs::PermissionsExt;

        let _guard = crate::ENV_SWAP_LOCK.lock().unwrap_or_else(|poisoned| poisoned.into_inner());

        let nanos = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let home = std::env::temp_dir().join(format!(
            "mmos-config-check-{}-{}",
            std::process::id(),
            nanos
        ));
        let config = home
            .join(".mastermind")
            .join("mmos_dev")
            .join("window-dev-t8");
        let bin = home.join("bin");
        fs::create_dir_all(&config).unwrap();
        fs::create_dir_all(&bin).unwrap();
        fs::set_permissions(&config, fs::Permissions::from_mode(0o700)).unwrap();
        fs::set_permissions(&bin, fs::Permissions::from_mode(0o700)).unwrap();
        let helper = bin.join("helper.sh");
        fs::write(&helper, "#!/bin/sh\ntrue\n").unwrap();
        fs::set_permissions(&helper, fs::Permissions::from_mode(0o755)).unwrap();
        for (name, contents) in [
            ("shell-url", "http://127.0.0.1:3780/env-1/thread-1"),
            ("pair-helper", helper.to_str().unwrap()),
        ] {
            fs::write(config.join(name), format!("{contents}\n")).unwrap();
            fs::set_permissions(config.join(name), fs::Permissions::from_mode(0o600)).unwrap();
        }

        let previous = std::env::var_os("HOME");
        std::env::set_var("HOME", &home);
        let good = run_window_config_check("com.mastermind.os.dev.t8");
        // A symlinked config folder (to an identical, valid folder) refuses
        // every item (repair N): replace the directory with a link to a copy.
        let real = home.join("config-real");
        fs::rename(&config, &real).unwrap();
        std::os::unix::fs::symlink(&real, &config).unwrap();
        let broken = run_window_config_check("com.mastermind.os.dev.t8");
        match previous {
            Some(value) => std::env::set_var("HOME", value),
            None => std::env::remove_var("HOME"),
        }

        assert_eq!(good, 0, "a well-formed config passes all items");
        assert_eq!(broken, 1, "a symlinked config folder fails the check");

        let _ = fs::remove_file(&config);
        fs::remove_dir_all(&home).ok();
    }

    /// Lane PF: the judge reports the optional board origin — `ok` when the
    /// file is a clean origin, `absent` when unconfigured (still exit 0), and
    /// `refused <code>` with the board's own code otherwise (exit 1). The
    /// report is the exact line list the printer emits.
    #[test]
    fn window_config_check_reports_board_url_ok_absent_and_refused() {
        use std::fs;
        use std::os::unix::fs::PermissionsExt;

        let _guard = crate::ENV_SWAP_LOCK.lock().unwrap_or_else(|poisoned| poisoned.into_inner());

        let nanos = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let home = std::env::temp_dir().join(format!(
            "mmos-board-check-{}-{}",
            std::process::id(),
            nanos
        ));
        let config = home
            .join(".mastermind")
            .join("mmos_dev")
            .join("window-next");
        let bin = home.join("bin");
        fs::create_dir_all(&config).unwrap();
        fs::create_dir_all(&bin).unwrap();
        fs::set_permissions(&config, fs::Permissions::from_mode(0o700)).unwrap();
        fs::set_permissions(&bin, fs::Permissions::from_mode(0o700)).unwrap();
        let helper = bin.join("helper.sh");
        fs::write(&helper, "#!/bin/sh\ntrue\n").unwrap();
        fs::set_permissions(&helper, fs::Permissions::from_mode(0o755)).unwrap();
        for (name, contents) in [
            ("shell-url", "http://127.0.0.1:3780/env-1/thread-1"),
            ("pair-helper", helper.to_str().unwrap()),
        ] {
            fs::write(config.join(name), format!("{contents}\n")).unwrap();
            fs::set_permissions(config.join(name), fs::Permissions::from_mode(0o600)).unwrap();
        }

        let previous = std::env::var_os("HOME");
        std::env::set_var("HOME", &home);

        // Absent board file: normal, exit 0, one absent line.
        let (code, lines) = window_config_check_report("com.mastermind.os.next");
        assert_eq!(code, 0, "{lines:?}");
        assert!(lines.contains(&"board-url: absent".to_string()), "{lines:?}");

        // Clean origin: ok.
        fs::write(config.join("board-url"), "http://127.0.0.1:3196\n").unwrap();
        fs::set_permissions(config.join("board-url"), fs::Permissions::from_mode(0o600)).unwrap();
        let (code, lines) = window_config_check_report("com.mastermind.os.next");
        assert_eq!(code, 0, "{lines:?}");
        assert!(lines.contains(&"board-url: ok".to_string()), "{lines:?}");

        // A path is not an origin: refused with the board's own code.
        fs::write(config.join("board-url"), "http://127.0.0.1:3196/board\n").unwrap();
        let (code, lines) = window_config_check_report("com.mastermind.os.next");
        assert_eq!(code, 1, "{lines:?}");
        assert!(
            lines.contains(&"board-url: refused board_url.path_not_allowed".to_string()),
            "{lines:?}"
        );

        // A loosened file is refused like the address file.
        fs::write(config.join("board-url"), "http://127.0.0.1:3196\n").unwrap();
        fs::set_permissions(config.join("board-url"), fs::Permissions::from_mode(0o644)).unwrap();
        let (code, lines) = window_config_check_report("com.mastermind.os.next");
        assert_eq!(code, 1, "{lines:?}");
        assert!(
            lines.contains(&"board-url: refused wrong_permissions".to_string()),
            "{lines:?}"
        );

        match previous {
            Some(value) => std::env::set_var("HOME", value),
            None => std::env::remove_var("HOME"),
        }
        fs::remove_dir_all(&home).ok();
    }

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
