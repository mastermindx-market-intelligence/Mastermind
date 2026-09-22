mod auth;
mod native_client;
use sha2::{Digest, Sha256};
use tauri_plugin_deep_link::DeepLinkExt;

#[derive(serde::Serialize)]
struct Readiness {
    version: &'static str,
    source_revision: &'static str,
    build_identity: &'static str,
    transport: &'static str,
    state: &'static str,
    native_client_ref: Option<String>,
}

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
            auth::read_mission_v3,
            auth::read_result,
            auth::read_current_window
        ])
        .run(tauri::generate_context!())
        .expect("tauri runtime error");
}

#[cfg(test)]
mod readiness_tests {
    use super::*;

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
    fn configured_identity_validation_is_closed_and_bounded() {
        for invalid in ["", "invalid client", "client/slash", "client\nnewline"] {
            assert!(
                readiness_from_client_id(Some(invalid)).is_err(),
                "{invalid:?}"
            );
        }
        let oversized = "a".repeat(161);
        assert!(readiness_from_client_id(Some(&oversized)).is_err());

        let boundary = "a".repeat(160);
        assert!(readiness_from_client_id(Some(&boundary)).is_ok());
        assert!(readiness_from_client_id(Some("tpc_A1._-:valid")).is_ok());
    }
}
