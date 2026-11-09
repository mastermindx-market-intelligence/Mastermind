//! Actual native Inner/Token/expiry-owner tests; no shim, host or OAuth call.
use super::*;

fn token_at(expires: Instant, wall: SystemTime) -> Token {
    Token { value: "synthetic-never-sent".into(), expires, wall_expires: wall, executive_send: false }
}

#[test]
fn genuine_native_expiry_and_logout_have_different_owner_causes() {
    let mut inner = Inner::new(Some("native-test-client"));
    let now = Instant::now(); let wall = SystemTime::now();
    inner.acquisition = Some(token_at(now - Duration::from_secs(1), wall - Duration::from_secs(1)));
    assert!(!inner.status().acquisition);
    assert_eq!(inner.status().reason, Some("NATIVE_TOKEN_EXPIRED"));
    inner.invalidate();
    assert!(inner.acquisition.is_none());
    assert_eq!(inner.status().reason, Some("USER_SIGNED_OUT"));
    assert!(matches!(inner.draft_continuity.snapshot(None).phase, draft_continuity::Phase::Withdrawn));
}

#[test]
fn early_refresh_failure_remains_with_original_owner_until_actual_expiry_only() {
    let mut inner = Inner::new(Some("native-test-client"));
    let started = Instant::now(); let wall = SystemTime::now();
    let expires = started + Duration::from_secs(60); let wall_expires = wall + Duration::from_secs(60);
    inner.acquisition = Some(token_at(expires, wall_expires));
    let generation = inner.generation;
    // Failed refresh leaves exactly the original token, with no extension.
    assert!(!original_expiry_due(&inner, Resource::Acquisition, expires, wall_expires, generation,
        started + Duration::from_secs(25), wall + Duration::from_secs(25)));
    assert!(original_expiry_due(&inner, Resource::Acquisition, expires, wall_expires, generation, expires, wall_expires));
    // Sleep/wall expiry is independently sufficient; no monotonic assumption.
    assert!(original_expiry_due(&inner, Resource::Acquisition, expires, wall_expires, generation, started, wall_expires));
    assert_eq!(inner.acquisition.as_ref().unwrap().expires, expires);
}

#[test]
fn refreshed_token_or_logout_retires_old_expiry_without_replay_or_state_change() {
    let mut inner = Inner::new(Some("native-test-client"));
    let started = Instant::now(); let wall = SystemTime::now();
    let expires = started + Duration::from_secs(60); let wall_expires = wall + Duration::from_secs(60);
    inner.acquisition = Some(token_at(expires, wall_expires)); let generation = inner.generation;
    inner.acquisition = Some(token_at(expires + Duration::from_secs(60), wall_expires + Duration::from_secs(60)));
    assert!(!original_expiry_due(&inner, Resource::Acquisition, expires, wall_expires, generation, expires, wall_expires));
    inner.invalidate();
    assert!(!original_expiry_due(&inner, Resource::Acquisition, expires, wall_expires, generation, expires, wall_expires));
    assert!(inner.acquisition.is_none()); assert_eq!(inner.status().status, "signed_out");
}

#[test]
fn reauthentication_quarantines_candidate_and_same_principal_can_requalify_without_tokens() {
    let mut inner = Inner::new(Some("native-test-client"));
    assert!(inner.draft_continuity.confirm(&"a".repeat(64)));
    let origin = inner.draft_continuity.snapshot(Some(5000));
    inner.begin_reauthentication();
    let hidden = inner.draft_continuity.snapshot(None);
    assert!(hidden.principal_scope.is_none());
    assert!(matches!(hidden.phase, draft_continuity::Phase::Reauthenticating));
    assert!(inner.draft_continuity.confirm(&"a".repeat(64)));
    assert_eq!(inner.draft_continuity.snapshot(Some(5000)).privacy_epoch, origin.privacy_epoch);
    inner.invalidate();
    assert!(inner.draft_continuity.confirm(&"a".repeat(64)));
    assert_ne!(inner.draft_continuity.snapshot(Some(5000)).privacy_epoch, origin.privacy_epoch);
    assert!(inner.acquisition.is_none()); assert!(inner.content.is_none());
}

#[test]
fn real_native_owner_sequence_for_host_consumer_fixture() {
    let identities: serde_json::Value = serde_json::from_str(include_str!("../../../src/auth-recovery/fixtures/native-draft-identity-owner.json")).unwrap();
    let wall = SystemTime::now(); let now = wall.duration_since(SystemTime::UNIX_EPOCH).unwrap().as_millis() as u64;
    let token_expiry = now + 60_000;
    let (first, deadline) = native_draft_identity::identity(&identities["first"], now, token_expiry).unwrap();
    let (other, _) = native_draft_identity::identity(&identities["different"], now, token_expiry).unwrap();
    assert_ne!(first, other);
    let mut inner = Inner::new(Some("native-test-client"));
    inner.acquisition = Some(token_at(Instant::now() + Duration::from_secs(60), wall + Duration::from_secs(60)));
    assert!(inner.draft_continuity.confirm(&first));
    let qualified = serde_json::to_value(inner.draft_continuity.snapshot(Some(deadline))).unwrap();
    inner.acquisition = Some(token_at(Instant::now() - Duration::from_secs(1), wall - Duration::from_secs(1)));
    let expired_auth = serde_json::to_value(inner.status()).unwrap();
    inner.draft_continuity.expire();
    let expired = serde_json::to_value(inner.draft_continuity.snapshot(None)).unwrap();
    inner.begin_reauthentication();
    let reauthenticating = serde_json::to_value(inner.draft_continuity.snapshot(None)).unwrap();
    assert!(inner.draft_continuity.confirm(&first));
    let same = serde_json::to_value(inner.draft_continuity.snapshot(Some(deadline))).unwrap();
    assert_eq!(same["privacy_epoch"], qualified["privacy_epoch"]);
    assert!(inner.draft_continuity.confirm(&other));
    let different = serde_json::to_value(inner.draft_continuity.snapshot(Some(deadline))).unwrap();
    assert_ne!(different["privacy_epoch"], qualified["privacy_epoch"]);
    inner.invalidate();
    let logout_auth = serde_json::to_value(inner.status()).unwrap();
    let logout = serde_json::to_value(inner.draft_continuity.snapshot(None)).unwrap();
    println!("S35_NATIVE_DRAFT_SEQUENCE={}", serde_json::json!({"now_ms":now,"qualified":qualified,
        "expired":expired,"expired_auth":expired_auth,"reauthenticating":reauthenticating,
        "same":same,"different":different,"logout":logout,"logout_auth":logout_auth}));
}
