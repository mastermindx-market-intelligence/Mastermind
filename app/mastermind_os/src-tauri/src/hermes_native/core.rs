//! Dependency-free guards shared by the native host and standalone contract tests.
use std::path::{Path, PathBuf};

pub fn valid_fields(operation: &str, keys: &[&str]) -> bool {
    let expected: &[&str] = match operation {
        "status" | "list" => &["operation"],
        "create" => &["operation", "role", "requestId"],
        "read" => &["operation", "sessionId"],
        "send" => &["operation", "sessionId", "requestId", "text"],
        "receipt" => &["operation", "sessionId", "admissionId"],
        "recover_create" => &["operation", "requestId"],
        "recover_send" | "stop_send" => &["operation", "sessionId", "requestId"],
        _ => return false,
    };
    keys.len() == expected.len() && expected.iter().all(|key| keys.contains(key))
}
pub fn valid_id(value: &str) -> bool {
    (1..=160).contains(&value.len())
        && value.as_bytes()[0].is_ascii_alphanumeric()
        && value.bytes().all(|c| c.is_ascii_alphanumeric() || b"_.:-".contains(&c))
}
pub fn valid_request_id(value: &str) -> bool {
    value.len() == 32 && value.bytes().all(|c| c.is_ascii_digit() || (b'a'..=b'f').contains(&c))
}
pub fn valid_prompt(value: &str) -> bool {
    !value.trim().is_empty() && value.len() <= 32768
        && value.chars().all(|c| c != '\u{7f}' && (c >= ' ' || matches!(c, '\n' | '\r' | '\t')))
}
pub fn dispatch_generation_allowed(expected: Option<u64>, current: u64, mutating: bool) -> bool {
    expected.map_or(!mutating, |generation| generation == current)
}
pub fn release_allowed(original: u64, current: u64, valid_token: bool, signed_in: bool) -> bool {
    original == current && valid_token && signed_in
}
pub fn launcher_python(home: &Path, launcher: &str) -> Result<PathBuf, &'static str> {
    let line = launcher.lines().nth(1).ok_or("NATIVE_INSTALL_UNAVAILABLE")?;
    if launcher.lines().next() != Some("#!/bin/sh") {
        return Err("NATIVE_INSTALL_UNAVAILABLE");
    }
    let selected = line.strip_prefix("exec ").and_then(|line| line.split_once(" -I -c "))
        .map(|(path, _)| path).ok_or("NATIVE_INSTALL_UNAVAILABLE")?;
    let path = PathBuf::from(selected);
    let base = home.join(".hermes/tools");
    if !path.starts_with(&base) || path.file_name().and_then(|n| n.to_str()) != Some("python3")
        || !selected.bytes().all(|c| c.is_ascii_alphanumeric() || b"/_-.+".contains(&c))
        || path.components().any(|c| matches!(c, std::path::Component::ParentDir | std::path::Component::CurDir))
        || path.parent().and_then(|p| p.file_name()).and_then(|n| n.to_str()) != Some("bin") {
        return Err("NATIVE_INSTALL_UNAVAILABLE");
    }
    Ok(path)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn closed_operations() {
        assert!(valid_fields("status", &["operation"]));
        assert!(valid_fields("send", &["operation", "requestId", "sessionId", "text"]));
        assert!(!valid_fields("status", &["operation", "url"]));
        assert!(!valid_fields("send", &["operation", "text"]));
        assert!(!valid_fields("shell", &["operation"]));
        assert!(valid_fields("recover_create", &["operation", "requestId"]));
        assert!(valid_fields("recover_send", &["operation", "requestId", "sessionId"]));
        assert!(!valid_fields("recover_send", &["operation", "requestId", "sessionId", "text"]));
    }
    #[test]
    fn stop_uses_only_the_original_send_identity() {
        assert!(valid_fields("stop_send", &["operation", "sessionId", "requestId"]));
        assert!(!valid_fields("stop_send", &["operation", "sessionId", "requestId", "admissionId"]));
        assert!(!valid_fields("stop_send", &["operation", "sessionId"]));
        assert!(!dispatch_generation_allowed(None, 7, true));
        assert!(!dispatch_generation_allowed(Some(6), 7, true));
    }
    #[test]
    fn exact_identifiers_not_paths_or_authority() {
        assert!(valid_id("local-0123_abc"));
        for bad in ["", "../other", "/tmp/evil", "a\nb", "a b", "https://x", "💀"] {
            assert!(!valid_id(bad), "{bad}");
        }
        assert!(!valid_id(&"a".repeat(161)));
        assert!(valid_request_id(&"a".repeat(32)));
        assert!(!valid_request_id(&"A".repeat(32)));
        assert!(!valid_request_id(&"a".repeat(31)));
    }
    #[test]
    fn original_prompt_is_not_trimmed_or_normalized() {
        assert!(valid_prompt("  keep\n 中文\t\r"));
        assert!(valid_prompt(&"x".repeat(32768)));
        for bad in ["", "  \n", "x\0y", "x\x7fy"] { assert!(!valid_prompt(bad)); }
        assert!(!valid_prompt(&"x".repeat(32769)));
        assert!(!valid_prompt(&"🦀".repeat(8193)));
    }
    #[test]
    fn reservation_requires_current_generation_before_mutation() {
        assert!(dispatch_generation_allowed(Some(7), 7, true));
        assert!(!dispatch_generation_allowed(Some(6), 7, true));
        assert!(!dispatch_generation_allowed(None, 7, true));
        assert!(dispatch_generation_allowed(None, 7, false));
        assert!(!dispatch_generation_allowed(Some(6), 7, false));
    }
    #[test]
    fn result_requires_same_current_signed_in_generation() {
        assert!(release_allowed(4, 4, true, true));
        assert!(!release_allowed(4, 5, true, true));
        assert!(!release_allowed(4, 4, false, true));
        assert!(!release_allowed(4, 4, true, false));
    }
    #[test]
    fn interpreter_comes_only_from_fixed_installed_launcher_shape() {
        let home = Path::new("/Users/operator");
        let valid = "#!/bin/sh\nexec /Users/operator/.hermes/tools/python-3.14/bin/python3 -I -c 'fixed launcher'\n";
        assert_eq!(launcher_python(home, valid).unwrap(), PathBuf::from("/Users/operator/.hermes/tools/python-3.14/bin/python3"));
        for bad in ["#!/bin/sh\nexec /tmp/python3 -I -c 'x'", "#!/bin/sh\nexec /Users/operator/.hermes/tools/../evil/bin/python3 -I -c 'x'", "#!/bin/sh\nexec /Users/operator/.hermes/tools/a/bin/sh -I -c 'x'", "#!/bin/sh\nexec /Users/operator/.hermes/tools/a/bin/python3;echo bad -I -c 'x'"] {
            assert!(launcher_python(home, bad).is_err());
        }
    }
}
