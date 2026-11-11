//! In-memory draft privacy-continuity state for the native workspace owner.
//!
//! Pure state machine: `std` + `serde::Serialize` only. No clock, host,
//! network, filesystem, credential, token, draft-text or persistence effects.
//! A hex string here is syntax, never identity or grant authentication, and a
//! `bool` return is syntax only: the parent (`auth.rs`) owns authoritative
//! HTTP identity and calls [`DraftContinuity::confirm`] only AFTER it has
//! independently qualified the fixed authenticated Workspace READ owner and
//! the current native generation. `confirm` never grants permission. The
//! parent supplies every fresh bounded server/token expiry itself; this
//! module never inspects a system clock.

use serde::Serialize;

/// Exact wire schema of [`Snapshot`].
const SCHEMA: &str = "mastermind.native_draft_continuity.v1";

/// Largest integer that survives a JSON/JS `Number` round-trip (2^53 - 1).
///
/// `privacy_epoch` is published verbatim, so it must stay JSON-safe. An
/// increment that would reach `MAX_SAFE_U53` permanently withdraws the
/// continuity instead (fail closed); no wrap, no reuse.
const MAX_SAFE_U53: u64 = 9_007_199_254_740_991;

/// Validity of a hex identifier used as pure syntax: exactly `len` lowercase
/// ASCII hex characters. Rejects uppercase, wrong lengths, non-hex bytes and
/// any multi-byte UTF-8 (continuation bytes are >= 0x80).
fn is_lower_hex(s: &str, len: usize) -> bool {
    s.len() == len
        && s.bytes()
            .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
}

/// Continuity lifecycle phase. Serialized SCREAMING_SNAKE_CASE.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize)]
#[serde(rename_all = "SCREAMING_SNAKE_CASE")]
pub(super) enum Phase {
    Unqualified,
    Qualified,
    Expired,
    Reauthenticating,
    Withdrawn,
}

/// Reason for the current [`Phase`]. Serialized SCREAMING_SNAKE_CASE.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize)]
#[serde(rename_all = "SCREAMING_SNAKE_CASE")]
pub(super) enum Cause {
    OwnerUnqualified,
    OwnerQualified,
    TokenExpired,
    Reauthentication,
    ExplicitLogout,
    PrincipalChanged,
    EpochExhausted,
}

/// Draft privacy-continuity state. The private `candidate_scope` and
/// `current_scope` bytes are never serialized, cloned or debug-printed; only
/// [`Snapshot`] carries state out, and only its gated fields do.
pub(super) struct DraftContinuity {
    owner_instance: String,
    privacy_epoch: u64,
    phase: Phase,
    cause: Cause,
    candidate_scope: Option<String>,
    current_scope: Option<String>,
    exhausted: bool,
}

impl DraftContinuity {
    /// Builds state for `instance` (exactly 32 lowercase hex characters,
    /// syntax only). A malformed instance is a permanent fail-closed
    /// withdrawal: no confirmation, no epoch, no restoration.
    pub(super) fn new(instance: String) -> Self {
        if is_lower_hex(&instance, 32) {
            DraftContinuity {
                owner_instance: instance,
                privacy_epoch: 0,
                phase: Phase::Unqualified,
                cause: Cause::OwnerUnqualified,
                candidate_scope: None,
                current_scope: None,
                exhausted: false,
            }
        } else {
            // Malformed instance syntax: permanently withdrawn. EPOCH_EXHAUSTED
            // is the only permanent, unrestorable cause in the vocabulary;
            // epoch 0 marks that no epoch was ever minted.
            DraftContinuity {
                owner_instance: instance,
                privacy_epoch: 0,
                phase: Phase::Withdrawn,
                cause: Cause::EpochExhausted,
                candidate_scope: None,
                current_scope: None,
                exhausted: true,
            }
        }
    }

    /// Confirms `principal_scope` (exactly 64 lowercase hex, syntax only) as
    /// the candidate principal. Returns whether qualification stands after
    /// the call. This is bookkeeping only: the parent must already have
    /// authenticated the owner independently; `true` grants nothing.
    pub(super) fn confirm(&mut self, principal_scope: &str) -> bool {
        // Malformed syntax: false, and no qualified current may survive. The
        // private candidate stays quarantined (retained for comparison,
        // never exposed, never overwritten by the malformed input).
        if !is_lower_hex(principal_scope, 64) {
            if self.phase == Phase::Qualified && self.current_scope.is_some() {
                self.current_scope = None;
                self.phase = Phase::Unqualified;
                self.cause = Cause::OwnerUnqualified;
            }
            return false;
        }
        // Permanently withdrawn (epoch exhausted or malformed instance):
        // fail closed forever.
        if self.exhausted || self.privacy_epoch >= MAX_SAFE_U53 {
            self.withdraw_epoch_exhausted();
            return false;
        }
        let same_candidate =
            matches!(&self.candidate_scope, Some(prev) if prev == principal_scope);
        let no_candidate = self.candidate_scope.is_none();
        if no_candidate {
            // Fresh instance mints epoch 1. After an explicit logout the
            // candidate was cleared, so a later confirmation re-establishes
            // on the post-logout epoch minted at logout time; the pre-logout
            // draft (its epoch and candidate) cannot resurrect.
            if self.privacy_epoch == 0 {
                self.privacy_epoch = 1;
            }
            self.cause = Cause::OwnerQualified;
        } else if same_candidate {
            // Natural expiry / reauthentication path: same candidate keeps
            // epoch and principal. Cause is rewritten only on the transition
            // into qualification; re-confirming a live qualification keeps
            // its provenance (e.g. PrincipalChanged).
            if self.current_scope.is_none() {
                self.cause = Cause::OwnerQualified;
            }
        } else {
            // Proven different candidate: new epoch, PrincipalChanged.
            if !self.bump_epoch() {
                return false; // bump withdrew permanently on overflow
            }
            self.cause = Cause::PrincipalChanged;
        }
        self.candidate_scope = Some(principal_scope.to_string());
        self.current_scope = Some(principal_scope.to_string());
        self.phase = Phase::Qualified;
        true
    }

    /// Natural expiry: clears the qualified current, keeps the private
    /// candidate and epoch. Same candidate re-confirms without a new epoch.
    pub(super) fn expire(&mut self) {
        self.demote(Phase::Expired, Cause::TokenExpired);
    }

    /// Reauthentication started: clears the qualified current, keeps the
    /// private candidate and epoch.
    pub(super) fn begin_reauthentication(&mut self) {
        // A genuine explicit sign-in may leave logout's withdrawn phase.
        // Its candidate was already erased and epoch advanced, so no old
        // draft can return. Exhaustion remains permanently withdrawn.
        if !self.exhausted && self.phase == Phase::Withdrawn && self.cause == Cause::ExplicitLogout {
            self.phase = Phase::Reauthenticating;
            self.cause = Cause::Reauthentication;
        } else {
            self.demote(Phase::Reauthenticating, Cause::Reauthentication);
        }
    }

    /// Owner no longer qualified: clears the qualified current, keeps the
    /// private candidate and epoch.
    pub(super) fn unqualified(&mut self) {
        self.demote(Phase::Unqualified, Cause::OwnerUnqualified);
    }

    fn demote(&mut self, phase: Phase, cause: Cause) {
        if self.exhausted || self.phase == Phase::Withdrawn {
            return; // Withdrawn is terminal; expiry/reauth cannot relabel it
        }
        self.current_scope = None;
        self.phase = phase;
        self.cause = cause;
    }

    /// Explicit logout: mints a new epoch and clears candidate AND current,
    /// so the same principal later re-establishes on the fresh epoch and can
    /// never resurrect the pre-logout draft. Permanently exhausted state
    /// stays exhausted; nothing restores it.
    pub(super) fn logout(&mut self) {
        if self.exhausted || self.phase == Phase::Withdrawn {
            return; // exhaustion is absolute; logout is idempotent
        }
        if !self.bump_epoch() {
            return; // bump already withdrew permanently
        }
        self.candidate_scope = None;
        self.current_scope = None;
        self.phase = Phase::Withdrawn;
        self.cause = Cause::ExplicitLogout;
    }

    /// Builds the emitted view. Scope and expiry are exposed only while the
    /// phase is Qualified AND `valid_until_ms` is a positive JSON-safe
    /// integer (1 ..= 2^53-1). Any other phase emits NULL scope/expiry and
    /// never the private candidate. Qualified-but-invalid expiry degrades
    /// the emitted view to Unqualified/OwnerUnqualified with NULLs WITHOUT
    /// mutating the private state. No clock is inspected here; the parent
    /// supplies a fresh bounded expiry and checks it.
    pub(super) fn snapshot(&self, valid_until_ms: Option<u64>) -> Snapshot {
        let qualified_now = self.phase == Phase::Qualified
            && self.current_scope.is_some()
            && matches!(valid_until_ms, Some(v) if v > 0 && v <= MAX_SAFE_U53);
        let (phase, cause, scope) = if qualified_now {
            (self.phase, self.cause, self.current_scope.clone())
        } else if self.phase == Phase::Qualified {
            (Phase::Unqualified, Cause::OwnerUnqualified, None)
        } else {
            (self.phase, self.cause, None)
        };
        let expiry = if qualified_now { valid_until_ms } else { None };
        Snapshot {
            schema: SCHEMA,
            owner_instance: self.owner_instance.clone(),
            privacy_epoch: self.privacy_epoch,
            phase,
            cause,
            principal_scope: scope,
            valid_until_ms: expiry,
        }
    }

    fn withdraw_epoch_exhausted(&mut self) {
        self.exhausted = true;
        self.candidate_scope = None;
        self.current_scope = None;
        self.phase = Phase::Withdrawn;
        self.cause = Cause::EpochExhausted;
    }

    /// Increments the epoch without wrap or reuse. Reaching `MAX_SAFE_U53`
    /// permanently withdraws the continuity (fail closed) and returns false.
    fn bump_epoch(&mut self) -> bool {
        if self.exhausted || self.privacy_epoch >= MAX_SAFE_U53 {
            self.withdraw_epoch_exhausted();
            return false;
        }
        self.privacy_epoch += 1;
        if self.privacy_epoch >= MAX_SAFE_U53 {
            self.withdraw_epoch_exhausted();
            return false;
        }
        true
    }
}

/// Emitted continuity view (schema `mastermind.native_draft_continuity.v1`).
/// The private candidate is never a field here.
#[derive(Clone, Debug, Serialize)]
pub(super) struct Snapshot {
    pub(super) schema: &'static str,
    pub(super) owner_instance: String,
    pub(super) privacy_epoch: u64,
    pub(super) phase: Phase,
    pub(super) cause: Cause,
    pub(super) principal_scope: Option<String>,
    pub(super) valid_until_ms: Option<u64>,
}

impl std::fmt::Debug for DraftContinuity {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        // Redacted: private candidate/current scope bytes never reach Debug.
        f.debug_struct("DraftContinuity")
            .field("privacy_epoch", &self.privacy_epoch)
            .field("phase", &self.phase)
            .field("cause", &self.cause)
            .field("qualified_current", &self.current_scope.is_some())
            .field("candidate_quarantined", &self.candidate_scope.is_some())
            .finish()
    }
}

#[cfg(test)]
impl DraftContinuity {
    fn force_epoch_for_test(&mut self, epoch: u64) {
        self.privacy_epoch = epoch;
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    const INSTANCE: &str = "0123456789abcdef0123456789abcdef";

    fn dc() -> DraftContinuity {
        DraftContinuity::new(INSTANCE.to_string())
    }

    fn scope(byte: u8) -> String {
        let c = byte as char;
        std::iter::repeat(c).take(64).collect()
    }

    #[test]
    fn initial_confirm_mints_epoch_one() {
        let mut d = dc();
        assert_eq!(d.snapshot(None).privacy_epoch, 0);
        assert_eq!(d.snapshot(None).phase, Phase::Unqualified);
        assert!(d.confirm(&scope(b'a')));
        let s = d.snapshot(Some(100));
        assert_eq!(s.privacy_epoch, 1);
        assert_eq!(s.phase, Phase::Qualified);
        assert_eq!(s.cause, Cause::OwnerQualified);
        assert_eq!(s.principal_scope.as_deref(), Some(scope(b'a').as_str()));
        assert_eq!(s.valid_until_ms, Some(100));
        assert_eq!(s.schema, "mastermind.native_draft_continuity.v1");
    }

    #[test]
    fn natural_expiry_then_same_principal_keeps_epoch() {
        let mut d = dc();
        assert!(d.confirm(&scope(b'a')));
        d.expire();
        let s = d.snapshot(Some(100));
        assert_eq!(s.phase, Phase::Expired);
        assert_eq!(s.cause, Cause::TokenExpired);
        assert_eq!(s.principal_scope, None);
        assert_eq!(s.valid_until_ms, None);
        assert!(d.confirm(&scope(b'a')));
        let s = d.snapshot(Some(100));
        assert_eq!(s.privacy_epoch, 1); // kept, not re-minted
        assert_eq!(s.phase, Phase::Qualified);
        assert_eq!(s.cause, Cause::OwnerQualified);
        assert_eq!(s.principal_scope.as_deref(), Some(scope(b'a').as_str()));
    }

    #[test]
    fn reauthentication_then_same_principal_keeps_epoch() {
        let mut d = dc();
        assert!(d.confirm(&scope(b'a')));
        d.begin_reauthentication();
        let s = d.snapshot(None);
        assert_eq!(s.phase, Phase::Reauthenticating);
        assert_eq!(s.cause, Cause::Reauthentication);
        assert_eq!(s.principal_scope, None);
        assert!(d.confirm(&scope(b'a')));
        let s = d.snapshot(Some(100));
        assert_eq!(s.privacy_epoch, 1);
        assert_eq!(s.phase, Phase::Qualified);
        assert_eq!(s.principal_scope.as_deref(), Some(scope(b'a').as_str()));
    }

    #[test]
    fn different_principal_increments_epoch_and_marks_principal_changed() {
        let mut d = dc();
        assert!(d.confirm(&scope(b'a')));
        assert!(d.confirm(&scope(b'b')));
        let s = d.snapshot(Some(100));
        assert_eq!(s.privacy_epoch, 2);
        assert_eq!(s.cause, Cause::PrincipalChanged);
        assert_eq!(s.phase, Phase::Qualified);
        assert_eq!(s.principal_scope.as_deref(), Some(scope(b'b').as_str()));
        // Re-confirming the live qualification keeps epoch and provenance.
        assert!(d.confirm(&scope(b'b')));
        let s = d.snapshot(Some(100));
        assert_eq!(s.privacy_epoch, 2);
        assert_eq!(s.cause, Cause::PrincipalChanged);
    }

    #[test]
    fn expiry_then_different_principal_switches_lineage_with_new_epoch() {
        let mut d = dc();
        assert!(d.confirm(&scope(b'a')));
        d.expire();
        assert!(d.confirm(&scope(b'b')));
        let s = d.snapshot(Some(100));
        assert_eq!(s.privacy_epoch, 2);
        assert_eq!(s.cause, Cause::PrincipalChanged);
        assert_eq!(s.principal_scope.as_deref(), Some(scope(b'b').as_str()));
        // Old candidate 'a' is proven different now: another epoch.
        d.expire();
        assert!(d.confirm(&scope(b'a')));
        let s = d.snapshot(Some(100));
        assert_eq!(s.privacy_epoch, 3);
        assert_eq!(s.cause, Cause::PrincipalChanged);
    }

    #[test]
    fn explicit_logout_then_same_principal_gets_new_epoch() {
        let mut d = dc();
        assert!(d.confirm(&scope(b'a')));
        assert_eq!(d.snapshot(None).privacy_epoch, 1);
        d.logout();
        let s = d.snapshot(Some(100));
        assert_eq!(s.phase, Phase::Withdrawn);
        assert_eq!(s.cause, Cause::ExplicitLogout);
        assert_eq!(s.privacy_epoch, 2);
        assert_eq!(s.principal_scope, None);
        assert_eq!(s.valid_until_ms, None);
        // Same principal re-establishes on the post-logout epoch only.
        assert!(d.confirm(&scope(b'a')));
        let s = d.snapshot(Some(100));
        assert_eq!(s.privacy_epoch, 2); // not 1: pre-logout draft not resurrected
        assert_eq!(s.phase, Phase::Qualified);
        assert_eq!(s.cause, Cause::OwnerQualified);
    }

    #[test]
    fn logout_is_idempotent_and_only_explicit_reauth_leaves_withdrawal() {
        let mut d = dc();
        assert!(d.confirm(&scope(b'a')));
        d.logout();
        d.logout();
        assert_eq!(d.snapshot(None).privacy_epoch, 2); // not 3
        d.expire();
        d.unqualified();
        let s = d.snapshot(Some(100));
        assert_eq!(s.phase, Phase::Withdrawn);
        assert_eq!(s.cause, Cause::ExplicitLogout);
        d.begin_reauthentication();
        let hidden=d.snapshot(None);
        assert_eq!(hidden.phase,Phase::Reauthenticating);
        assert!(hidden.principal_scope.is_none());
        assert_eq!(hidden.privacy_epoch,2);
        assert!(d.confirm(&scope(b'a')));
        assert_eq!(d.snapshot(Some(100)).privacy_epoch,2);
    }

    #[test]
    fn malformed_instance_is_permanently_withdrawn() {
        for bad in [
            "".to_string(),
            "0123456789ABCDEF0123456789ABCDEF".to_string(), // uppercase
            "0123456789abcdef".to_string(),                 // 16 chars
            "0123456789abcdef0123456789abcdeg".to_string(), // non-hex 'g'
            "0123456789abcdef0123456789abcdef0".to_string(), // 33 chars
        ] {
            let mut d = DraftContinuity::new(bad);
            let s = d.snapshot(Some(100));
            assert_eq!(s.phase, Phase::Withdrawn);
            assert_eq!(s.cause, Cause::EpochExhausted);
            assert_eq!(s.privacy_epoch, 0);
            assert_eq!(s.principal_scope, None);
            assert_eq!(s.valid_until_ms, None);
            assert!(!d.confirm(&scope(b'a')));
            d.expire();
            d.begin_reauthentication();
            d.unqualified();
            d.logout();
            let s = d.snapshot(Some(100));
            assert_eq!(s.phase, Phase::Withdrawn);
            assert_eq!(s.cause, Cause::EpochExhausted);
            assert_eq!(s.privacy_epoch, 0);
        }
    }

    #[test]
    fn malformed_scope_holds_no_qualified_current_and_keeps_candidate_quarantine() {
        let mut d = dc();
        assert!(d.confirm(&scope(b'a')));
        for bad in [
            String::new(),
            scope(b'A'),       // uppercase
            "a".repeat(63),    // short
            "a".repeat(65),    // long
            scope(b'g'),       // non-hex
        ] {
            assert!(!d.confirm(&bad));
            let s = d.snapshot(Some(100));
            assert_eq!(s.phase, Phase::Unqualified);
            assert_eq!(s.cause, Cause::OwnerUnqualified);
            assert_eq!(s.principal_scope, None);
            assert_eq!(s.valid_until_ms, None);
        }
        // The private candidate survived quarantined: same candidate
        // re-qualifies on the SAME epoch without re-minting.
        assert!(d.confirm(&scope(b'a')));
        let s = d.snapshot(Some(100));
        assert_eq!(s.privacy_epoch, 1);
        assert_eq!(s.phase, Phase::Qualified);
    }

    #[test]
    fn malformed_scope_on_fresh_state_mints_no_epoch() {
        let mut d = dc();
        assert!(!d.confirm(&scope(b'A')));
        let s = d.snapshot(Some(100));
        assert_eq!(s.privacy_epoch, 0);
        assert_eq!(s.phase, Phase::Unqualified);
        // A fresh valid confirmation still mints exactly epoch 1.
        assert!(d.confirm(&scope(b'a')));
        assert_eq!(d.snapshot(Some(100)).privacy_epoch, 1);
    }

    #[test]
    fn invalid_expiry_degrades_emitted_view_without_mutating_state() {
        let mut d = dc();
        assert!(d.confirm(&scope(b'a')));
        for expiry in [None, Some(0), Some(MAX_SAFE_U53 + 1), Some(u64::MAX)] {
            let s = d.snapshot(expiry);
            assert_eq!(s.phase, Phase::Unqualified);
            assert_eq!(s.cause, Cause::OwnerUnqualified);
            assert_eq!(s.principal_scope, None);
            assert_eq!(s.valid_until_ms, None);
        }
        // State was not mutated: a valid expiry still shows Qualified.
        let s = d.snapshot(Some(1));
        assert_eq!(s.phase, Phase::Qualified);
        assert_eq!(s.cause, Cause::OwnerQualified);
        assert_eq!(s.valid_until_ms, Some(1));
        assert_eq!(s.principal_scope.as_deref(), Some(scope(b'a').as_str()));
    }

    #[test]
    fn expiry_boundaries_are_positive_safe_integers() {
        let mut d = dc();
        assert!(d.confirm(&scope(b'a')));
        assert_eq!(d.snapshot(Some(MAX_SAFE_U53)).valid_until_ms, Some(MAX_SAFE_U53));
        assert_eq!(d.snapshot(Some(1)).valid_until_ms, Some(1));
        assert_eq!(d.snapshot(Some(0)).phase, Phase::Unqualified);
        assert_eq!(d.snapshot(Some(MAX_SAFE_U53 + 1)).phase, Phase::Unqualified);
    }

    #[test]
    fn candidates_never_exposed_when_unqualified() {
        let mut d = dc();
        assert!(d.confirm(&scope(b'a')));
        d.unqualified();
        let s = d.snapshot(Some(100));
        assert_eq!(s.phase, Phase::Unqualified);
        assert_eq!(s.cause, Cause::OwnerUnqualified);
        assert_eq!(s.principal_scope, None);
        assert_eq!(s.valid_until_ms, None);
        // Candidate still quarantined privately: same candidate keeps epoch.
        assert!(d.confirm(&scope(b'a')));
        assert_eq!(d.snapshot(Some(100)).privacy_epoch, 1);
        d.expire();
        assert_eq!(d.snapshot(Some(100)).principal_scope, None);
        d.begin_reauthentication();
        assert_eq!(d.snapshot(Some(100)).principal_scope, None);
        // Debug redacts scope bytes entirely.
        let rendered = format!("{:?}", d);
        assert!(!rendered.contains(&scope(b'a')));
        assert!(!rendered.contains(INSTANCE));
    }

    #[test]
    fn epoch_overflow_is_fail_closed() {
        let mut d = dc();
        assert!(d.confirm(&scope(b'a')));
        d.force_epoch_for_test(MAX_SAFE_U53 - 1);
        d.expire();
        // Same candidate re-qualification at MAX-1 is allowed: no bump.
        assert!(d.confirm(&scope(b'a')));
        let s = d.snapshot(Some(7));
        assert_eq!(s.privacy_epoch, MAX_SAFE_U53 - 1);
        assert_eq!(s.phase, Phase::Qualified);
        // A proven-different candidate needs epoch MAX: permanent withdrawal.
        assert!(!d.confirm(&scope(b'b')));
        for expiry in [None, Some(7)] {
            let s = d.snapshot(expiry);
            assert_eq!(s.phase, Phase::Withdrawn);
            assert_eq!(s.cause, Cause::EpochExhausted);
            assert_eq!(s.privacy_epoch, MAX_SAFE_U53);
            assert_eq!(s.principal_scope, None);
            assert_eq!(s.valid_until_ms, None);
        }
        // Nothing restores a permanently exhausted continuity.
        assert!(!d.confirm(&scope(b'a')));
        assert!(!d.confirm(&scope(b'b')));
        d.expire();
        d.begin_reauthentication();
        d.unqualified();
        d.logout();
        let s = d.snapshot(None);
        assert_eq!(s.phase, Phase::Withdrawn);
        assert_eq!(s.cause, Cause::EpochExhausted);
        assert_eq!(s.privacy_epoch, MAX_SAFE_U53);
    }

    #[test]
    fn epoch_at_max_is_never_qualified() {
        let mut d = dc();
        assert!(d.confirm(&scope(b'a')));
        d.force_epoch_for_test(MAX_SAFE_U53);
        assert!(!d.confirm(&scope(b'a')));
        let s = d.snapshot(Some(7));
        assert_eq!(s.phase, Phase::Withdrawn);
        assert_eq!(s.cause, Cause::EpochExhausted);
    }

    #[test]
    fn logout_on_exhausted_stays_exhausted() {
        let mut d = dc();
        assert!(d.confirm(&scope(b'a')));
        d.force_epoch_for_test(MAX_SAFE_U53 - 1);
        // A proven-different candidate needs epoch MAX: the bump withdraws
        // permanently and confirm reports false (fail closed).
        assert!(!d.confirm(&scope(b'b')));
        d.logout();
        let s = d.snapshot(None);
        assert_eq!(s.cause, Cause::EpochExhausted);
        assert_eq!(s.privacy_epoch, MAX_SAFE_U53);
    }
}

#[cfg(test)]
mod json_shape_tests {
    use super::*;
    const INSTANCE: &str = "0123456789abcdef0123456789abcdef";
    fn scope(byte: u8) -> String { std::iter::repeat(byte as char).take(64).collect() }
    // Real installed serde_json, never a stripped derive or a stub serializer.
    fn shape_json<T: Serialize>(value: &T) -> String { serde_json::to_string(value).unwrap() }

    #[test]
    fn phase_serializes_as_screaming_snake_strings() {
        assert_eq!(shape_json(&Phase::Unqualified), "\"UNQUALIFIED\"");
        assert_eq!(shape_json(&Phase::Qualified), "\"QUALIFIED\"");
        assert_eq!(shape_json(&Phase::Expired), "\"EXPIRED\"");
        assert_eq!(shape_json(&Phase::Reauthenticating), "\"REAUTHENTICATING\"");
        assert_eq!(shape_json(&Phase::Withdrawn), "\"WITHDRAWN\"");
    }

    #[test]
    fn cause_serializes_as_screaming_snake_strings() {
        assert_eq!(shape_json(&Cause::OwnerUnqualified), "\"OWNER_UNQUALIFIED\"");
        assert_eq!(shape_json(&Cause::OwnerQualified), "\"OWNER_QUALIFIED\"");
        assert_eq!(shape_json(&Cause::TokenExpired), "\"TOKEN_EXPIRED\"");
        assert_eq!(shape_json(&Cause::Reauthentication), "\"REAUTHENTICATION\"");
        assert_eq!(shape_json(&Cause::ExplicitLogout), "\"EXPLICIT_LOGOUT\"");
        assert_eq!(shape_json(&Cause::PrincipalChanged), "\"PRINCIPAL_CHANGED\"");
        assert_eq!(shape_json(&Cause::EpochExhausted), "\"EPOCH_EXHAUSTED\"");
    }

    #[test]
    fn qualified_snapshot_json_is_exact() {
        let mut d = DraftContinuity::new(INSTANCE.to_string());
        assert!(d.confirm(&scope(b'a')));
        let expected = format!(
            "{{\"schema\":\"mastermind.native_draft_continuity.v1\",\
             \"owner_instance\":\"{}\",\"privacy_epoch\":1,\
             \"phase\":\"QUALIFIED\",\"cause\":\"OWNER_QUALIFIED\",\
             \"principal_scope\":\"{}\",\"valid_until_ms\":1234}}",
            INSTANCE,
            scope(b'a')
        );
        assert_eq!(shape_json(&d.snapshot(Some(1234))), expected);
    }

    #[test]
    fn unqualified_snapshot_json_has_nulls_not_false_or_zero() {
        let mut d = DraftContinuity::new(INSTANCE.to_string());
        assert!(d.confirm(&scope(b'a')));
        d.expire();
        let expected = format!(
            "{{\"schema\":\"mastermind.native_draft_continuity.v1\",\
             \"owner_instance\":\"{}\",\"privacy_epoch\":1,\
             \"phase\":\"EXPIRED\",\"cause\":\"TOKEN_EXPIRED\",\
             \"principal_scope\":null,\"valid_until_ms\":null}}",
            INSTANCE
        );
        assert_eq!(shape_json(&d.snapshot(None)), expected);
    }

    #[test]
    fn json_state_never_carries_candidate_or_boolean_coercion() {
        let mut d = DraftContinuity::new(INSTANCE.to_string());
        assert!(d.confirm(&scope(b'a')));
        let qualified = shape_json(&d.snapshot(Some(1234)));
        assert!(qualified.contains("\"phase\":\"QUALIFIED\""));
        assert!(qualified.contains("\"privacy_epoch\":1"));
        assert!(!qualified.contains("candidate"));
        assert!(!qualified.contains("true"));
        assert!(!qualified.contains("false"));
        d.unqualified();
        let dropped = shape_json(&d.snapshot(None));
        assert!(dropped.contains("\"principal_scope\":null"));
        assert!(dropped.contains("\"valid_until_ms\":null"));
        assert!(!dropped.contains("candidate"));
    }

    #[test]
    fn epoch_is_emitted_as_exact_json_number() {
        let mut d = DraftContinuity::new(INSTANCE.to_string());
        assert!(d.confirm(&scope(b'a')));
        d.force_epoch_for_test(MAX_SAFE_U53 - 1);
        // Expiry 0 is invalid, so the view degrades to unqualified, but the
        // epoch itself must still be emitted exactly (JSON-safe integer).
        let json = shape_json(&d.snapshot(Some(0)));
        assert!(json.contains("\"privacy_epoch\":9007199254740990"));
    }
}
// END_JSON_SHAPE_TESTS
