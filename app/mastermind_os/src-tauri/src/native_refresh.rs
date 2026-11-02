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
/// A rotating grant must never return the same token as its predecessor.
pub(crate) fn valid_successor(previous: &str, next: &str) -> bool {
    valid_refresh(next) && next != previous
}
#[cfg(target_os = "macos")]
fn rotation_marker(previous: &str) -> String {
    let mut hasher = Sha256::new();
    hasher.update(b"mastermind.os.rotation.v1\0");
    hasher.update(previous.as_bytes());
    format!("{:x}", hasher.finalize())
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
    use security_framework::os::macos::keychain::SecKeychain;
    // The old get-then-set marker was only serialized within one process.
    // Across two app processes it could overwrite an existing marker and allow
    // both instances to send the same rotating token. Use Keychain's atomic
    // add-only operation: a duplicate is an existing owner, not a retry grant.
    let original = load(client_id, audience)?.ok_or("AUTHENTICATION_REQUIRED")?;
    if original != old { return Err("REFRESH_TOKEN_CHANGED"); }
    let marker = rotation_marker(old);
    let keychain = SecKeychain::default().map_err(|_| "KEYCHAIN_UNAVAILABLE")?;
    keychain.add_generic_password(
        SERVICE,
        &format!("{}:pending", account(client_id, audience)),
        marker.as_bytes(),
    ).map_err(|error| {
        if error.code() == -25299 { "REFRESH_OUTCOME_UNCONFIRMED" }
        else { "KEYCHAIN_WRITE_FAILED" }
    })?;
    // A successful create must also be visible through the read path used by
    // subsequent launches; no network effect is attempted if it is not.
    if !pending_exists(client_id, audience)? {
        return Err("KEYCHAIN_WRITE_FAILED");
    }
    Ok(())
}
/// Only a definitively pre-transmission connect error may release the marker.
/// A timeout or a lost response may already have rotated the token at Auth0.
#[cfg(target_os = "macos")]
pub(crate) fn rollback_untransmitted(client_id: &str, audience: &str, old: &str) -> Result<(), &'static str> {
    use security_framework::os::macos::keychain::SecKeychain;
    use security_framework::passwords::get_generic_password;
    let keychain = SecKeychain::default().map_err(|_| "KEYCHAIN_UNAVAILABLE")?;
    let (marker, item) = keychain.find_generic_password(
        SERVICE, &format!("{}:pending", account(client_id, audience)),
    ).map_err(|_| "REFRESH_OUTCOME_UNCONFIRMED")?;
    if marker.as_ref() != rotation_marker(old).as_bytes() {
        return Err("REFRESH_OUTCOME_UNCONFIRMED");
    }
    let current = get_generic_password(SERVICE, &account(client_id, audience))
        .map_err(|_| "REFRESH_OUTCOME_UNCONFIRMED")?;
    if current.as_slice() != old.as_bytes() {
        return Err("REFRESH_TOKEN_CHANGED");
    }
    drop(marker);
    // This item reference binds deletion to the original Keychain item, not
    // a new pending item that another process could add after a sign-out.
    item.delete();
    if pending_exists(client_id, audience)? { return Err("KEYCHAIN_DELETE_FAILED"); }
    Ok(())
}
#[cfg(not(target_os = "macos"))]
pub(crate) fn rollback_untransmitted(_: &str, _: &str, _: &str) -> Result<(), &'static str> {
    Err("KEYCHAIN_UNSUPPORTED")
}

#[cfg(target_os = "macos")]
pub(crate) fn finish_rotation(client_id: &str, audience: &str, previous: &str, next: &str) -> Result<(), &'static str> {
    use security_framework::os::macos::keychain::SecKeychain;
    if !valid_successor(previous, next) { return Err("REFRESH_TOKEN_NOT_ROTATED"); }
    let keychain = SecKeychain::default().map_err(|_| "KEYCHAIN_UNAVAILABLE")?;
    let (marker, pending_item) = keychain.find_generic_password(
        SERVICE, &format!("{}:pending", account(client_id, audience)),
    ).map_err(|_| "REFRESH_OUTCOME_UNCONFIRMED")?;
    if marker.as_ref() != rotation_marker(previous).as_bytes() {
        return Err("REFRESH_OUTCOME_UNCONFIRMED");
    }
    // Never re-create an item removed by a concurrent sign-out or replace a
    // newly signed-in user's credential. Unlike set_generic_password(), this
    // mutates ONLY the exact Keychain item found before the update.
    let (old_value, mut credential_item) = keychain.find_generic_password(
        SERVICE, &account(client_id, audience),
    ).map_err(|_| "REFRESH_TOKEN_CHANGED")?;
    if old_value.as_ref() != previous.as_bytes() { return Err("REFRESH_TOKEN_CHANGED"); }
    drop(old_value);
    credential_item.set_password(next.as_bytes()).map_err(|_| "KEYCHAIN_WRITE_FAILED")?;
    drop(marker);
    pending_item.delete();
    // A failed or concurrent replacement of the pending item remains blocked.
    if pending_exists(client_id, audience)? { return Err("KEYCHAIN_DELETE_FAILED"); }
    Ok(())
}
#[cfg(not(target_os = "macos"))]
pub(crate) fn begin_rotation(_: &str, _: &str, _: &str) -> Result<(), &'static str> {
    Err("KEYCHAIN_UNSUPPORTED")
}
#[cfg(not(target_os = "macos"))]
pub(crate) fn finish_rotation(_: &str, _: &str, _: &str, _: &str) -> Result<(), &'static str> {
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
    #[cfg(target_os = "macos")]
    #[test]
    #[ignore = "explicit synthetic Keychain canary on authorized unlocked macOS host only"]
    fn native_keychain_synthetic_roundtrip_canary() {
        // Never touch a registered client, user account, or real refresh token.
        let client = format!("mmos-synthetic-keychain-canary-{}", std::process::id());
        let audience = format!("https://fixture.invalid/keychain-canary/{}", std::process::id());
        let synthetic = "synthetic-keychain-roundtrip-token-only-no-credential";
        assert_eq!(load(&client, &audience).expect("Keychain read"), None);
        struct Cleanup(String, String);
        impl Drop for Cleanup {
            fn drop(&mut self) { let _ = super::delete(&self.0, &self.1); }
        }
        save(&client, &audience, synthetic).expect("Keychain write");
        let _cleanup = Cleanup(client.clone(), audience.clone());
        assert_eq!(load(&client, &audience).expect("Keychain readback"),
            Some(synthetic.to_owned()));
        delete(&client, &audience).expect("Keychain delete");
        assert_eq!(load(&client, &audience).expect("Keychain absence"), None);
    }

    #[cfg(target_os = "macos")]
    #[test]
    #[ignore = "explicit synthetic cross-instance Keychain rotation test on unlocked macOS only"]
    fn atomic_keychain_rotation_marker_rejects_competing_writers() {
        let client = format!("mmos-atomic-keychain-canary-{}", std::process::id());
        let audience = format!("https://fixture.invalid/keychain-lock/{}", std::process::id());
        let original = "synthetic-rotating-access-probe-credential-0001";
        let successor = "synthetic-rotating-access-probe-credential-0002";
        // Test teardown is independent of the explicit body assertions.
        struct Cleanup(String, String);
        impl Drop for Cleanup {
            fn drop(&mut self) { let _ = super::delete(&self.0, &self.1); }
        }
        let _cleanup = Cleanup(client.clone(), audience.clone());
        assert_eq!(load(&client, &audience).expect("initial read"), None);
        save(&client, &audience, original).expect("synthetic seed");
        // Two separately constructed callers race on the same *Keychain item*,
        // not on the app's process-local mutex.
        let gate = std::sync::Arc::new(std::sync::Barrier::new(3));
        let mut tasks = Vec::new();
        for _ in 0..2 {
            let gate = gate.clone();
            let (c, a, o) = (client.clone(), audience.clone(), original.to_owned());
            tasks.push(std::thread::spawn(move || {
                gate.wait();
                begin_rotation(&c, &a, &o)
            }));
        }
        gate.wait();
        let results: Vec<_> = tasks.into_iter().map(|t| t.join().expect("thread")).collect();
        assert_eq!(results.iter().filter(|result| result.is_ok()).count(), 1, "{results:?}");
        assert!(results.iter().any(|result| result.as_ref().err()
            == Some(&"REFRESH_OUTCOME_UNCONFIRMED")));
        assert_eq!(load(&client, &audience).unwrap_err(), "REFRESH_OUTCOME_UNCONFIRMED");
        finish_rotation(&client, &audience, original, successor).expect("rotation");
        assert_eq!(load(&client, &audience).expect("rotated read"), Some(successor.to_owned()));
        delete(&client, &audience).expect("teardown");
        assert_eq!(load(&client, &audience).expect("absence"), None);
    }

    #[cfg(target_os = "macos")]
    #[test]
    #[ignore = "synthetic macOS Keychain preconnect rollback only on an unlocked test host"]
    fn native_keychain_definite_preconnect_failure_preserves_grant_canary() {
        let client = format!("mmos-synthetic-offline-reopen-{}", std::process::id());
        let audience = format!("https://fixture.invalid/preconnect/{}", std::process::id());
        let old = "synthetic-preconnect-retry-grant-not-a-credential";
        let successor = "synthetic-preconnect-successor-not-a-credential";
        struct Cleanup(String, String);
        impl Drop for Cleanup { fn drop(&mut self) { let _ = super::delete(&self.0, &self.1); } }
        let _cleanup = Cleanup(client.clone(), audience.clone());
        save(&client, &audience, old).expect("seed");
        begin_rotation(&client, &audience, old).expect("first claim");
        assert_eq!(load(&client, &audience).unwrap_err(), "REFRESH_OUTCOME_UNCONFIRMED");
        rollback_untransmitted(&client, &audience, old).expect("proven preconnect rollback");
        assert_eq!(load(&client, &audience).expect("restored"), Some(old.to_owned()));
        begin_rotation(&client, &audience, old).expect("online restart claim");
        finish_rotation(&client, &audience, old, successor).expect("rotate on recovered network");
        assert_eq!(load(&client, &audience).expect("successor"), Some(successor.to_owned()));
    }

    #[test]
    fn rotation_successor_must_be_new_and_opaque() {
        let first = "a".repeat(64);
        assert!(valid_successor(&first, &"b".repeat(64)));
        assert!(!valid_successor(&first, &first));
        assert!(!valid_successor(&first, "bad token with whitespace"));
        assert!(!valid_successor(&first, "short"));
    }
}
