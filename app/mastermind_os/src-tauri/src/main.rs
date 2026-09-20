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
        .invoke_handler(tauri::generate_handler![readiness])
        .run(tauri::generate_context!())
        .expect("tauri runtime error");
}
