mod auth;
use tauri_plugin_deep_link::DeepLinkExt;

#[derive(serde::Serialize)]
struct Readiness {
    version: &'static str,
    source_revision: &'static str,
    build_identity: &'static str,
    transport: &'static str,
    state: &'static str,
}

#[tauri::command]
fn readiness() -> Readiness {
    Readiness {
        version: env!("CARGO_PKG_VERSION"),
        source_revision: env!("MM_SOURCE_REVISION"),
        build_identity: env!("MM_BUILD_IDENTITY"),
        transport: "UNCONFIGURED",
        state: "BUILT_NOT_PROVEN",
    }
}

fn main() {
    tauri::Builder::default()
        .manage(auth::NativeAuth::new().expect("native transport configuration"))
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_deep_link::init())
        .setup(|app| {
            let handle = app.handle().clone();
            app.deep_link().on_open_url(move |event| {
                // Callback values stay in Rust and are never logged.
                for url in event.urls() {
                    let app = handle.clone();
                    tauri::async_runtime::spawn(auth::callback(app, url.to_string()));
                }
            });
            if let Some(urls) = app.deep_link().get_current()? {
                for url in urls {
                    tauri::async_runtime::spawn(auth::callback(
                        app.handle().clone(),
                        url.to_string(),
                    ));
                }
            }
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            readiness,
            auth::auth_status,
            auth::sign_in,
            auth::sign_out,
            auth::read_programs,
            auth::read_mission,
            auth::read_current_window
        ])
        .run(tauri::generate_context!())
        .expect("tauri runtime error");
}
