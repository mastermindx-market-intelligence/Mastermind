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
    println!("cargo:rerun-if-env-changed=MM_NATIVE_CLIENT_ID");
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
