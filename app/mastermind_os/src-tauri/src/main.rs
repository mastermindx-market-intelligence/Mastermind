#[derive(serde::Serialize)]
struct Readiness { build_identity: &'static str, transport: &'static str, state: &'static str }
#[tauri::command]
fn readiness() -> Readiness { Readiness { build_identity: env!("CARGO_PKG_VERSION"), transport: "UNCONFIGURED", state: "BUILT_NOT_PROVEN" } }
fn main() { tauri::Builder::default().invoke_handler(tauri::generate_handler![readiness]).run(tauri::generate_context!()).expect("tauri runtime error"); }
