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
#[cfg(any(target_os = "macos", test))]
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
    use security_framework::os::macos::keychain::SecKeychain;
    if !valid_refresh(value) { return Err("REFRESH_TOKEN_INVALID"); }
    let keychain = SecKeychain::default().map_err(|_| "KEYCHAIN_UNAVAILABLE")?;
    // Explicit sign-in clears its old grant before beginning OAuth. An item
    // appearing during that transaction belongs to another publication.
    // Never change a captured item reference into a reference to a new grant.
    keychain.add_generic_password(
        SERVICE, &account(client_id, audience), value.as_bytes(),
    ).map(|_| ()).map_err(|error| {
        if error.code() == -25299 { "REFRESH_TOKEN_CHANGED" }
        else { "KEYCHAIN_WRITE_FAILED" }
    })
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
/// Outcome of terminal cleanup bound to the exact old grant and its exclusive
/// pending marker. Missing or changed ownership never authorizes deletion.
#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub(crate) enum StaleGrantCleanup {
    RemovedStaleGrant,
    Superseded,
    AlreadyAbsent,
}
#[cfg(any(target_os = "macos", test))]
pub(crate) fn stale_cleanup_decision(
    stored_is_old: Option<bool>,
    marker_is_old: Option<bool>,
) -> StaleGrantCleanup {
    match (stored_is_old, marker_is_old) {
        (None, _) => StaleGrantCleanup::AlreadyAbsent,
        (Some(true), Some(true)) => StaleGrantCleanup::RemovedStaleGrant,
        // The marker must still exclude a second admitted rotation.
        _ => StaleGrantCleanup::Superseded,
    }
}

#[cfg(target_os = "macos")]
fn delete_keychain_item(
    item: security_framework::os::macos::keychain_item::SecKeychainItem,
) -> security_framework::base::Result<()> {
    use core_foundation::base::TCFType;
    use security_framework::base::Error;
    use security_framework_sys::keychain_item::SecKeychainItemDelete;
    // SAFETY: item owns a retained, typed reference and remains alive for this
    // synchronous call. This deletes that exact item, without an account lookup.
    // The high-level 3.7.0 delete() discards OSStatus; retain it here.
    let status = unsafe { SecKeychainItemDelete(item.as_concrete_TypeRef()) };
    if status == 0 { Ok(()) } else { Err(Error::from_code(status)) }
}

/// Clean a definitive invalid_grant only while its original marker still owns
/// exclusion. Login publication is add-only; successful rotation is the sole
/// in-place credential writer and requires that marker. Keep the marker until
/// the credential is gone. A crash retains an ambiguous marker and requires
/// explicit sign-in; it must not enable a second refresh of the dead grant.
#[cfg(target_os = "macos")]
pub(crate) fn delete_stale(
    client_id: &str,
    audience: &str,
    old: &str,
) -> Result<StaleGrantCleanup, &'static str> {
    delete_stale_after_lookup(client_id, audience, old, || {})
}

#[cfg(target_os = "macos")]
fn delete_stale_after_lookup<F: FnOnce()>(
    client_id: &str,
    audience: &str,
    old: &str,
    after_lookup: F,
) -> Result<StaleGrantCleanup, &'static str> {
    use security_framework::os::macos::keychain::SecKeychain;
    let keychain = SecKeychain::default().map_err(|_| "KEYCHAIN_UNAVAILABLE")?;
    let name = account(client_id, audience);
    let credential = match keychain.find_generic_password(SERVICE, &name) {
        Ok(value) => Some(value),
        Err(err) if err.code() == NOT_FOUND => None,
        Err(_) => return Err("KEYCHAIN_UNAVAILABLE"),
    };
    let pending = match keychain.find_generic_password(SERVICE, &format!("{name}:pending")) {
        Ok(value) => Some(value),
        Err(err) if err.code() == NOT_FOUND => None,
        Err(_) => return Err("KEYCHAIN_UNAVAILABLE"),
    };
    let decision = stale_cleanup_decision(
        credential.as_ref().map(|(stored, _)| stored.as_ref() == old.as_bytes()),
        pending.as_ref().map(|(marker, _)| marker.as_ref() == rotation_marker(old).as_bytes()),
    );
    if decision != StaleGrantCleanup::RemovedStaleGrant {
        return Ok(decision);
    }
    let (stored, credential_item) = credential.ok_or("REFRESH_OUTCOME_UNCONFIRMED")?;
    let (marker, marker_item) = pending.ok_or("REFRESH_OUTCOME_UNCONFIRMED")?;
    after_lookup();
    drop(stored);
    drop(marker);
    // Retain exclusion until the old credential is gone. Never compensate for
    // a refused exact-item delete with an account-level deletion.
    delete_keychain_item(credential_item).map_err(|_| "KEYCHAIN_DELETE_FAILED")?;
    delete_keychain_item(marker_item).map_err(|_| "KEYCHAIN_DELETE_FAILED")?;
    Ok(StaleGrantCleanup::RemovedStaleGrant)
}
#[cfg(not(target_os = "macos"))]
pub(crate) fn delete_stale(
    _: &str,
    _: &str,
    _: &str,
) -> Result<StaleGrantCleanup, &'static str> {
    Err("KEYCHAIN_UNSUPPORTED")
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

    #[cfg(target_os = "macos")]
    #[test]
    #[ignore = "explicit synthetic stale Keychain item vs sign-out canary on unlocked macOS"]
    fn deleted_keychain_item_reference_cannot_resurrect_signed_out_grant() {
        use security_framework::os::macos::keychain::SecKeychain;
        let client = format!("mmos-synthetic-signout-race-{}", std::process::id());
        let audience = format!("https://fixture.invalid/signout-race/{}", std::process::id());
        let old = "synthetic-original-grant-not-a-real-credential";
        let new_login = "synthetic-after-explicit-login-new-grant";
        let stale_rotation = "synthetic-stale-rotation-must-not-overwrite";
        struct Cleanup(String, String);
        impl Drop for Cleanup { fn drop(&mut self) { let _ = super::delete(&self.0, &self.1); } }
        let _cleanup = Cleanup(client.clone(), audience.clone());
        save(&client, &audience, old).expect("synthetic seed");
        let kc = SecKeychain::default().expect("default test Keychain");
        let (observed, mut stale_item) = kc.find_generic_password(
            SERVICE, &account(&client, &audience)).expect("fixture item");
        assert_eq!(observed.as_ref(), old.as_bytes());
        drop(observed);
        delete(&client, &audience).expect("explicit sign-out");
        assert!(stale_item.set_password(stale_rotation.as_bytes()).is_err());
        assert_eq!(load(&client, &audience).expect("logout read"), None);
        save(&client, &audience, new_login).expect("fresh explicit user login");
        assert!(stale_item.set_password(stale_rotation.as_bytes()).is_err());
        assert_eq!(load(&client, &audience).expect("new login read"), Some(new_login.to_owned()));
    }

    #[test]
    fn rotation_successor_must_be_new_and_opaque() {
        let first = "a".repeat(64);
        assert!(valid_successor(&first, &"b".repeat(64)));
        assert!(!valid_successor(&first, &first));
        assert!(!valid_successor(&first, "bad token with whitespace"));
        assert!(!valid_successor(&first, "short"));
    }
    #[test]
    fn stale_invalid_grant_cleanup_is_qualified_on_exact_old_ownership() {
        // The response is authoritative only about items it can still prove
        // hold the grant this process sent.
        // A newer credential occupies the account: a stale response
        // (changed/missing ownership) mutates nothing.
        assert_eq!(stale_cleanup_decision(Some(false), None),
            StaleGrantCleanup::Superseded);
        assert_eq!(stale_cleanup_decision(Some(false), Some(true)),
            StaleGrantCleanup::Superseded);
        assert_eq!(stale_cleanup_decision(Some(false), Some(false)),
            StaleGrantCleanup::Superseded);
        // No credential item: an explicit sign-out already removed the grant
        // (missing); nothing is deleted and no marker is freed either.
        assert_eq!(stale_cleanup_decision(None, None),
            StaleGrantCleanup::AlreadyAbsent);
        assert_eq!(stale_cleanup_decision(None, Some(true)),
            StaleGrantCleanup::AlreadyAbsent);
        // The stored grant is removed only with its own matching marker.
        // Missing exclusion must preserve the credential.
        assert_eq!(stale_cleanup_decision(Some(true), Some(true)),
            StaleGrantCleanup::RemovedStaleGrant);
        assert_eq!(stale_cleanup_decision(Some(true), None),
            StaleGrantCleanup::Superseded);
        // A pending item whose content belongs to a different rotation is
        // another process's current marker: never freed.
        assert_eq!(stale_cleanup_decision(Some(true), Some(false)),
            StaleGrantCleanup::Superseded);
    }
    #[test]
    fn stale_marker_qualification_is_derivable_by_every_process() {
        // Marker content derives only from the old grant itself, so any
        // instance processing a stale response qualifies the same pending
        // item without shared process state.
        let old = "synthetic-cross-process-qualification-grant";
        assert_eq!(rotation_marker(old), rotation_marker(old));
        assert_ne!(rotation_marker(old),
            rotation_marker("synthetic-different-grant-same-account"));
        let old = "a".repeat(64);
        assert_ne!(rotation_marker(&old), rotation_marker(&format!("{old}b")));
    }

    #[cfg(target_os = "macos")]
    #[test]
    #[ignore = "explicit synthetic stale invalid_grant Keychain canary on unlocked macOS only"]
    fn stale_invalid_grant_cleanup_spares_newer_grant_and_rotation_marker_canary() {
        // Instance A sent `old` and still holds its pending marker; instance
        // B explicitly signed out and a fresh sign-in persisted a newer grant
        // that B then began rotating. A's stale invalid_grant response must
        // not delete B's newer credential or free B's current marker.
        let client = format!("mmos-synthetic-stale-grant-canary-{}", std::process::id());
        let audience = format!("https://fixture.invalid/stale-grant/{}", std::process::id());
        let old = "synthetic-old-rotating-grant-dead-at-the-provider";
        let new_login = "synthetic-newer-login-grant-after-explicit-sign-in";
        let successor = "synthetic-newer-login-successor-after-its-rotation";
        struct Cleanup(String, String);
        impl Drop for Cleanup { fn drop(&mut self) { let _ = super::delete(&self.0, &self.1); } }
        // (1) Demonstrate the pre-repair defect on its own fixture account:
        // the unconditional account-level delete that terminal invalid_grant
        // handling used before this repair destroys the newer grant and its
        // marker. This documents why the caller had to change.
        let defect_client = format!("{client}-defect");
        let defect_audience = format!("{audience}-defect");
        let _defect_cleanup = Cleanup(defect_client.clone(), defect_audience.clone());
        save(&defect_client, &defect_audience, old).expect("defect seed");
        begin_rotation(&defect_client, &defect_audience, old).expect("defect claim");
        super::delete(&defect_client, &defect_audience).expect("instance B explicit sign-out");
        save(&defect_client, &defect_audience, new_login).expect("fresh explicit sign-in");
        begin_rotation(&defect_client, &defect_audience, new_login).expect("newer rotation claim");
        super::delete(&defect_client, &defect_audience).expect("stale account-level delete");
        assert!(finish_rotation(&defect_client, &defect_audience, new_login, successor).is_err(),
            "defect demonstrated: the newer grant and its marker were destroyed");
        // (2) The qualified terminal cleanup provably spares the newer items.
        let _cleanup = Cleanup(client.clone(), audience.clone());
        save(&client, &audience, old).expect("seed");
        begin_rotation(&client, &audience, old).expect("instance A claim");
        super::delete(&client, &audience).expect("instance B explicit sign-out");
        save(&client, &audience, new_login).expect("fresh explicit sign-in");
        begin_rotation(&client, &audience, new_login).expect("newer rotation claim");
        assert_eq!(
            delete_stale(&client, &audience, old).expect("qualified stale cleanup"),
            StaleGrantCleanup::Superseded);
        // The newer rotation still completes: both its credential and its
        // pending marker survived the stale response.
        finish_rotation(&client, &audience, new_login, successor).expect("newer rotation");
        assert_eq!(load(&client, &audience).expect("surviving newer grant"),
            Some(successor.to_owned()));
        super::delete(&client, &audience).expect("synthetic successor cleanup");
        assert_eq!(load(&client, &audience).expect("synthetic successor absence"), None);
        super::delete(&defect_client, &defect_audience).expect("synthetic defect cleanup");
        assert_eq!(load(&defect_client, &defect_audience).expect("synthetic defect absence"), None);
    }

    #[cfg(target_os = "macos")]
    #[test]
    #[ignore = "synthetic after-lookup stale cleanup canary on unlocked macOS only"]
    fn stale_invalid_grant_cleanup_after_lookup_preserves_new_login_canary() {
        use security_framework::os::macos::keychain::SecKeychain;
        use std::cell::Cell;
        let client = format!("mmos-synthetic-stale-after-lookup-{}", std::process::id());
        let audience = format!("https://fixture.invalid/stale-after-lookup/{}", std::process::id());
        let old = "synthetic-old-grant-for-after-lookup-cleanup";
        let new_login = "synthetic-new-login-after-stale-lookup";
        let successor = "synthetic-new-login-rotation-successor";
        struct Cleanup(String, String);
        impl Drop for Cleanup {
            fn drop(&mut self) { let _ = super::delete(&self.0, &self.1); }
        }
        let _cleanup = Cleanup(client.clone(), audience.clone());
        assert_eq!(load(&client, &audience).expect("initial absence"), None);
        save(&client, &audience, old).expect("synthetic seed");
        begin_rotation(&client, &audience, old).expect("old claim");
        let reached_after_lookup = Cell::new(false);
        let cleanup_result = delete_stale_after_lookup(&client, &audience, old, || {
            reached_after_lookup.set(true);
            // The delayed callback cannot overwrite the captured old item.
            assert_eq!(save(&client, &audience, new_login), Err("REFRESH_TOKEN_CHANGED"));
            let keychain = SecKeychain::default().expect("default test Keychain");
            let (stored, _) = keychain.find_generic_password(
                SERVICE, &account(&client, &audience),
            ).expect("old item remains");
            assert_eq!(stored.as_ref(), old.as_bytes());
            drop(stored);
            // Real signout/login replaces both items after cleanup's lookup.
            super::delete(&client, &audience).expect("other instance explicit signout");
            save(&client, &audience, new_login).expect("fresh login creates new item");
            begin_rotation(&client, &audience, new_login).expect("new login marker");
        });
        assert!(reached_after_lookup.get());
        assert!(cleanup_result.is_ok() || cleanup_result == Err("KEYCHAIN_DELETE_FAILED"),
            "{cleanup_result:?}");
        finish_rotation(&client, &audience, new_login, successor)
            .expect("newer rotation survives stale cleanup");
        assert_eq!(load(&client, &audience).expect("surviving successor"),
            Some(successor.to_owned()));
        super::delete(&client, &audience).expect("synthetic teardown");
        assert_eq!(load(&client, &audience).expect("final credential and marker absence"), None);
    }

    #[cfg(target_os = "macos")]
    #[test]
    #[ignore = "explicit synthetic stale cleanup removal canary on unlocked macOS only"]
    fn stale_invalid_grant_cleanup_removes_unchanged_old_grant_canary() {
        let client = format!("mmos-synthetic-stale-removal-{}", std::process::id());
        let audience = format!("https://fixture.invalid/stale-removal/{}", std::process::id());
        let old = "synthetic-unchanged-dead-grant-still-stored";
        struct Cleanup(String, String);
        impl Drop for Cleanup { fn drop(&mut self) { let _ = super::delete(&self.0, &self.1); } }
        let _cleanup = Cleanup(client.clone(), audience.clone());
        // The unchanged old grant is removed together with its own stale
        // marker; the account reads back empty.
        save(&client, &audience, old).expect("seed");
        begin_rotation(&client, &audience, old).expect("claim");
        assert_eq!(
            delete_stale(&client, &audience, old).expect("qualified cleanup"),
            StaleGrantCleanup::RemovedStaleGrant);
        assert_eq!(load(&client, &audience).expect("removal read"), None);
        // Without the old marker there is no exclusive cleanup authority.
        save(&client, &audience, old).expect("reseed");
        assert_eq!(
            delete_stale(&client, &audience, old).expect("cleanup without marker"),
            StaleGrantCleanup::Superseded);
        assert_eq!(load(&client, &audience).expect("unowned grant preserved"),
            Some(old.to_owned()));
        super::delete(&client, &audience).expect("synthetic unowned grant teardown");
        assert_eq!(load(&client, &audience).expect("absence"), None);
        // Cleaning an already-absent account is a typed missing outcome.
        assert_eq!(
            delete_stale(&client, &audience, old).expect("absent cleanup"),
            StaleGrantCleanup::AlreadyAbsent);
    }
}
