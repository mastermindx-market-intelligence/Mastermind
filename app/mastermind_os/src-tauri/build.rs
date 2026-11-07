#[path = "src/native_client.rs"]
mod native_client;
#[path = "src/terminal_public_config.rs"]
mod terminal_public_config;

fn required(name: &str) -> String {
    let value = std::env::var(name).unwrap_or_else(|_| panic!("{name} must be set at build time"));
    assert!(
        !value.is_empty() && value.len() <= 160,
        "{name} has an invalid length"
    );
    assert!(
        value.bytes().all(|byte| {
            byte.is_ascii_alphanumeric() || matches!(byte, b'.' | b'_' | b'-' | b':')
        }),
        "{name} contains an invalid character"
    );
    value
}

fn main() {
    println!("cargo:rerun-if-env-changed=MM_TERMINAL_SUPABASE_ANON_KEY");
    println!("cargo:rerun-if-changed=src/terminal_public_config.rs");
    match std::env::var("MM_TERMINAL_SUPABASE_ANON_KEY") {
        Ok(value) => terminal_public_config::validate_public_key(&value)
            .expect("MM_TERMINAL_SUPABASE_ANON_KEY must be a public Terminal project key"),
        Err(std::env::VarError::NotPresent) => {},
        Err(_) => panic!("MM_TERMINAL_SUPABASE_ANON_KEY contains invalid characters"),
    }
    println!("cargo:rerun-if-env-changed=MM_EXECUTIVE_RESOURCE");
    println!("cargo:rerun-if-env-changed=MM_NATIVE_CLIENT_ID");
    println!("cargo:rerun-if-env-changed=MM_NATIVE_REFRESH_ENABLED");
    match std::env::var("MM_NATIVE_REFRESH_ENABLED") {
        Ok(value) if value == "1" => (),
        Err(std::env::VarError::NotPresent) => (),
        _ => panic!("MM_NATIVE_REFRESH_ENABLED must be absent or exactly 1"),
    }
    match std::env::var("MM_NATIVE_CLIENT_ID") {
        Ok(value) => native_client::validate_native_client_id(&value)
            .unwrap_or_else(|message| panic!("MM_NATIVE_CLIENT_ID {message}")),
        Err(std::env::VarError::NotPresent) => {}
        Err(std::env::VarError::NotUnicode(_)) => {
            panic!("MM_NATIVE_CLIENT_ID contains an invalid character")
        }
    }
    println!("cargo:rerun-if-env-changed=MM_SOURCE_REVISION");
    println!("cargo:rerun-if-env-changed=MM_BUILD_IDENTITY");
    let revision = required("MM_SOURCE_REVISION");
    assert!(
        revision.len() == 40 && revision.bytes().all(|byte| byte.is_ascii_hexdigit()),
        "MM_SOURCE_REVISION must be a full Git object id"
    );
    println!("cargo:rustc-env=MM_SOURCE_REVISION={revision}");
    println!(
        "cargo:rustc-env=MM_BUILD_IDENTITY={}",
        required("MM_BUILD_IDENTITY")
    );
    tauri_build::build()
}
