//! Auth0 native refresh-token custody. This module owns only Keychain
//! credential bytes; resource authorization stays in auth.rs.
use sha2::{Digest, Sha256};
const SERVICE: &str = "com.mastermind.os.auth0.refresh.v1";
const ISSUER: &str = "https://dev-eo0jf8us5mup7wd5.us.auth0.com/";
const NOT_FOUND: i32 = -25300;

pub(crate) fn enabled() -> bool {
    option_env!("MM_NATIVE_REFRESH_ENABLED") == Some("1")
}

pub(crate) fn account(client_id: &str, audience: &str) -> String {
    let mut hasher = Sha256::new();
    hasher.update(b"mastermind.os.native.refresh.account.v1\0");
    hasher.update(ISSUER.as_bytes());
    hasher.update(b"\0");
    hasher.update(client_id.as_bytes());
    hasher.update(b"\0");
    hasher.update(audience.as_bytes());
    format!("{:x}", hasher.finalize())
}
pub(crate) fn valid_refresh(value: &str) -> bool {
    (16..=4096).contains(&value.len()) && value.bytes().all(|b| b.is_ascii_graphic())
}
#[cfg(target_os = "macos")]
pub(crate) fn load(client_id: &str, audience: &str) -> Result<Option<String>, &'static str> {
    use security_framework::passwords::get_generic_password;
    // A pending refresh may have reached Auth0 before a crash or network loss.
    // Never replay a rotating token whose prior exchange is unconfirmed.
    if pending_exists(client_id, audience)? { return Err("REFRESH_OUTCOME_UNCONFIRMED"); }
    match get_generic_password(SERVICE, &account(client_id, audience)) {
        Ok(bytes) => {
            let value = String::from_utf8(bytes).map_err(|_| "KEYCHAIN_INVALID")?;
            if !valid_refresh(&value) { return Err("KEYCHAIN_INVALID"); }
            Ok(Some(value))
        }
        Err(err) if err.code() == NOT_FOUND => Ok(None),
        Err(_) => Err("KEYCHAIN_UNAVAILABLE"),
    }
}
#[cfg(target_os = "macos")]
fn pending_exists(client_id: &str, audience: &str) -> Result<bool, &'static str> {
    use security_framework::passwords::get_generic_password;
    let pending = format!("{}:pending", account(client_id, audience));
    match get_generic_password(SERVICE, &pending) {
        Ok(_) => Ok(true),
        Err(err) if err.code() == NOT_FOUND => Ok(false),
        Err(_) => Err("KEYCHAIN_UNAVAILABLE"),
    }
}
#[cfg(target_os = "macos")]
pub(crate) fn begin_rotation(client_id: &str, audience: &str, old: &str) -> Result<(), &'static str> {
    use security_framework::passwords::set_generic_password;
    if pending_exists(client_id, audience)? { return Err("REFRESH_OUTCOME_UNCONFIRMED"); }
    let original = load(client_id, audience)?.ok_or("AUTHENTICATION_REQUIRED")?;
    if original != old { return Err("REFRESH_TOKEN_CHANGED"); }
    let mut h = Sha256::new();
    h.update(b"mastermind.os.rotation.v1\0");
    h.update(old.as_bytes());
    let marker = format!("{:x}", h.finalize());
    set_generic_password(SERVICE, &format!("{}:pending", account(client_id, audience)), marker.as_bytes())
        .map_err(|_| "KEYCHAIN_WRITE_FAILED")
}
#[cfg(target_os = "macos")]
pub(crate) fn finish_rotation(client_id: &str, audience: &str, next: &str) -> Result<(), &'static str> {
    if !pending_exists(client_id, audience)? { return Err("REFRESH_OUTCOME_UNCONFIRMED"); }
    save(client_id, audience, next)?;
    use security_framework::passwords::delete_generic_password;
    delete_generic_password(SERVICE, &format!("{}:pending", account(client_id, audience)))
        .map_err(|_| "KEYCHAIN_DELETE_FAILED")
}
#[cfg(not(target_os = "macos"))]
pub(crate) fn begin_rotation(_: &str, _: &str, _: &str) -> Result<(), &'static str> {
    Err("KEYCHAIN_UNSUPPORTED")
}
#[cfg(not(target_os = "macos"))]
pub(crate) fn finish_rotation(_: &str, _: &str, _: &str) -> Result<(), &'static str> {
    Err("KEYCHAIN_UNSUPPORTED")
}
#[cfg(target_os = "macos")]
pub(crate) fn save(client_id: &str, audience: &str, value: &str) -> Result<(), &'static str> {
    use security_framework::passwords::set_generic_password;
    if !valid_refresh(value) { return Err("REFRESH_TOKEN_INVALID"); }
    set_generic_password(SERVICE, &account(client_id, audience), value.as_bytes())
        .map_err(|_| "KEYCHAIN_WRITE_FAILED")
}
#[cfg(target_os = "macos")]
pub(crate) fn delete(client_id: &str, audience: &str) -> Result<(), &'static str> {
    use security_framework::passwords::delete_generic_password;
    // Delete both the credential and its ambiguous-exchange marker.
    // Do not accept partial deletion as logout success.
    for key in [
        account(client_id, audience),
        format!("{}:pending", account(client_id, audience)),
    ] {
        match delete_generic_password(SERVICE, &key) {
            Ok(()) => (),
            Err(err) if err.code() == NOT_FOUND => (),
            Err(_) => return Err("KEYCHAIN_DELETE_FAILED"),
        }
    }
    Ok(())
}
#[cfg(not(target_os = "macos"))]
pub(crate) fn load(_: &str, _: &str) -> Result<Option<String>, &'static str> {
    Err("KEYCHAIN_UNSUPPORTED")
}
#[cfg(not(target_os = "macos"))]
pub(crate) fn save(_: &str, _: &str, _: &str) -> Result<(), &'static str> {
    Err("KEYCHAIN_UNSUPPORTED")
}
#[cfg(not(target_os = "macos"))]
pub(crate) fn delete(_: &str, _: &str) -> Result<(), &'static str> {
    Err("KEYCHAIN_UNSUPPORTED")
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn keychain_account_is_domain_separated_and_not_a_user_identifier() {
        let a = account("native-client-A", "https://mcp.mastermind-x.com/workspace/read");
        assert_eq!(a.len(), 64);
        assert!(a.bytes().all(|b| b.is_ascii_hexdigit()));
        assert!(!a.contains("native-client"));
        assert_ne!(a, account("native-client-B", "https://mcp.mastermind-x.com/workspace/read"));
        assert_ne!(a, account("native-client-A", "https://mcp.mastermind-x.com/workspace/window/current"));
    }
    #[test]
    fn malformed_refresh_tokens_cannot_enter_keychain() {
        for token in ["", "short", "has space in token", "bad\ncontrol", "\t", "A\0B"] {
            assert!(!valid_refresh(token), "{token:?}");
        }
        assert!(valid_refresh(&"x".repeat(16)));
        assert!(valid_refresh(&"x".repeat(4096)));
        assert!(!valid_refresh(&"x".repeat(4097)));
    }
}
