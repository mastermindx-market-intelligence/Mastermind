//! Initial publication and claims in the existing credential/pending slots.
//! The same algorithm runs against native exact-item handles and inert tests.

pub(super) enum AddError { Occupied, Unknown }
enum ReserveError { Refused(&'static str), Uncertain(&'static str) }
impl ReserveError {
    fn code(self) -> &'static str { match self { Self::Refused(code) | Self::Uncertain(code) => code } }
}
impl From<&'static str> for ReserveError {
    fn from(code: &'static str) -> Self { Self::Uncertain(code) }
}

pub(super) trait Store {
    type Item;
    fn add(&mut self, name: &str, value: &[u8]) -> Result<(), AddError>;
    fn find(&mut self, name: &str) -> Result<Option<(Vec<u8>, Self::Item)>, &'static str>;
    fn update(&mut self, item: &mut Self::Item, value: &[u8]) -> Result<(), &'static str>;
    fn delete(&mut self, item: Self::Item) -> Result<(), &'static str>;
}

/// Private, non-clone and consumed once. Dropping a receipt never clears a fence.
pub(crate) struct Reservation<I> {
    account: String,
    nonce: Vec<u8>,
    credential: I,
    marker: I,
}

fn marker_name(account: &str) -> String { format!("{account}:pending") }

fn owns<S: Store>(store: &mut S, name: &str, nonce: &[u8]) -> Result<(), &'static str> {
    match store.find(name)? {
        Some((value, _)) if value == nonce => Ok(()),
        _ => Err("INITIAL_RESERVATION_CHANGED"),
    }
}

fn reserve<S: Store>(store: &mut S, account: &str, nonce: Vec<u8>)
    -> Result<Reservation<S::Item>, ReserveError>
{
    // Reservations can never be mistaken for an opaque refresh token.
    if nonce.first() != Some(&0) { return Err(ReserveError::Refused("INITIAL_RESERVATION_INVALID")); }
    let pending = marker_name(account);
    store.add(&pending, &nonce).map_err(|error| match error {
        AddError::Occupied => ReserveError::Refused("REFRESH_OUTCOME_UNCONFIRMED"),
        AddError::Unknown => ReserveError::Uncertain("KEYCHAIN_WRITE_FAILED"),
    })?;
    let (observed, marker) = store.find(&pending)?.ok_or("KEYCHAIN_WRITE_FAILED")?;
    if observed != nonce { return Err("INITIAL_RESERVATION_CHANGED".into()); }
    match store.add(account, &nonce) {
        Ok(()) => (),
        Err(AddError::Occupied) => {
            // This known refusal created no credential. Remove only our captured
            // unpublished marker; never delete the existing account credential.
            store.delete(marker)?;
            if store.find(&pending)?.is_some() { return Err("KEYCHAIN_DELETE_FAILED".into()); }
            return Err(ReserveError::Refused("INITIAL_CREDENTIAL_OCCUPIED"));
        }
        // The add may have taken effect. Preserve the marker and do not retry.
        Err(AddError::Unknown) => return Err("KEYCHAIN_WRITE_FAILED".into()),
    }
    let (observed, credential) = store.find(account)?.ok_or("KEYCHAIN_WRITE_FAILED")?;
    if observed != nonce { return Err("INITIAL_RESERVATION_CHANGED".into()); }
    owns(store, &pending, &nonce)?;
    Ok(Reservation { account: account.to_owned(), nonce, credential, marker })
}

fn rollback_unpublished<S: Store>(store: &mut S, owned: Reservation<S::Item>)
    -> Result<(), &'static str>
{
    owns(store, &marker_name(&owned.account), &owned.nonce)?;
    owns(store, &owned.account, &owned.nonce)?;
    // Immutable invalid reservation bytes cannot be changed by a legitimate
    // rotating writer. Replacement after these reads changes item identities.
    store.delete(owned.credential)?;
    store.delete(owned.marker)?;
    Ok(())
}

pub(super) fn reserve_pair<S: Store>(store: &mut S, accounts: [&str; 2], nonces: [Vec<u8>; 2])
    -> Result<[Reservation<S::Item>; 2], &'static str>
{
    if accounts[0] == accounts[1] || nonces[0] == nonces[1] {
        return Err("INITIAL_RESERVATION_INVALID");
    }
    let [first_nonce, second_nonce] = nonces;
    let first = reserve(store, accounts[0], first_nonce).map_err(ReserveError::code)?;
    match reserve(store, accounts[1], second_nonce) {
        Ok(second) => Ok([first, second]),
        Err(ReserveError::Refused(error)) => {
            // No access has been published, and the second operation is a
            // reconciled refusal. Compensate only the captured first reservation.
            rollback_unpublished(store, first)?;
            Err(error)
        }
        // Preserve both reservations after an uncertain creation/cleanup. No
        // automatic rollback or retry may treat that as a clean empty slot.
        Err(ReserveError::Uncertain(error)) => Err(error),
    }
}

pub(super) fn publish<S: Store>(store: &mut S, account: &str,
    mut owned: Reservation<S::Item>, refresh: Option<&str>) -> Result<(), &'static str>
{
    if owned.account != account { return Err("INITIAL_RESERVATION_CHANGED"); }
    if refresh.is_some_and(|value| !super::valid_refresh(value)) {
        return Err("REFRESH_TOKEN_INVALID");
    }
    let pending = marker_name(account);
    owns(store, &pending, &owned.nonce)?;
    owns(store, account, &owned.nonce)?;
    if let Some(value) = refresh {
        // Never re-look up for writing, delete/re-add, or overwrite by account.
        store.update(&mut owned.credential, value.as_bytes())?;
    }
    // Access-only keeps its invalid reservation in the credential slot. Startup
    // cannot restore another grant through it; live renewal has no admission.
    store.delete(owned.marker)?;
    if store.find(&pending)?.is_some() { return Err("KEYCHAIN_DELETE_FAILED"); }
    Ok(())
}

pub(super) fn claim_rotation<S: Store>(store: &mut S, account: &str, old: &str, marker: &str)
    -> Result<(), &'static str>
{
    if !super::valid_refresh(old) { return Err("REFRESH_TOKEN_INVALID"); }
    let pending = marker_name(account);
    if store.find(&pending)?.is_some() { return Err("REFRESH_OUTCOME_UNCONFIRMED"); }
    if !store.find(account)?.is_some_and(|(value, _)| value == old.as_bytes()) {
        return Err("REFRESH_TOKEN_CHANGED");
    }
    store.add(&pending, marker.as_bytes()).map_err(|error| match error {
        AddError::Occupied => "REFRESH_OUTCOME_UNCONFIRMED",
        AddError::Unknown => "KEYCHAIN_WRITE_FAILED",
    })?;
    // Recheck after the atomic claim. A different process can replace the
    // credential between the first observation and marker creation.
    if !store.find(&pending)?.is_some_and(|(value, _)| value == marker.as_bytes()) {
        return Err("REFRESH_OUTCOME_UNCONFIRMED");
    }
    if !store.find(account)?.is_some_and(|(value, _)| value == old.as_bytes()) {
        return Err("REFRESH_TOKEN_CHANGED");
    }
    Ok(())
}

pub(super) fn claim_bound<S: Store>(store: &mut S, account: &str, expected: &str,
    fingerprint: impl Fn(&str) -> String, marker: impl Fn(&str) -> String) -> Result<String, &'static str>
{
    if store.find(&marker_name(account))?.is_some() { return Err("REFRESH_OUTCOME_UNCONFIRMED"); }
    let (bytes, _) = store.find(account)?.ok_or("AUTHENTICATION_REQUIRED")?;
    let old = String::from_utf8(bytes).map_err(|_| "KEYCHAIN_INVALID")?;
    if !super::valid_refresh(&old) { return Err("KEYCHAIN_INVALID"); }
    if fingerprint(&old) != expected { return Err("REFRESH_TOKEN_CHANGED"); }
    claim_rotation(store, account, &old, &marker(&old))?;
    Ok(old)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::collections::BTreeMap;

    #[derive(Default)]
    struct Fake {
        next: usize,
        rows: BTreeMap<String, (usize, Vec<u8>)>,
        replace_before_update: bool,
        replace_before_marker_add: bool,
        replace_before_delete: bool,
        unknown_add: Option<String>,
        fail_delete: bool,
        writes: usize,
    }
    impl Fake {
        fn seed(&mut self, name: &str, bytes: &[u8]) {
            self.next += 1;
            self.rows.insert(name.to_owned(), (self.next, bytes.to_vec()));
        }
        fn bytes(&self, name: &str) -> Option<&[u8]> {
            self.rows.get(name).map(|(_, bytes)| bytes.as_slice())
        }
    }
    impl Store for Fake {
        type Item = usize;
        fn add(&mut self, name: &str, value: &[u8]) -> Result<(), AddError> {
            if self.replace_before_marker_add && name == "a:pending" {
                self.replace_before_marker_add = false;
                self.seed("a", b"foreign-new-login-credential");
            }
            if self.rows.contains_key(name) { return Err(AddError::Occupied); }
            self.seed(name, value); self.writes += 1;
            if self.unknown_add.as_deref() == Some(name) { return Err(AddError::Unknown); }
            Ok(())
        }
        fn find(&mut self, name: &str) -> Result<Option<(Vec<u8>, usize)>, &'static str> {
            Ok(self.rows.get(name).map(|(id, value)| (value.clone(), *id)))
        }
        fn update(&mut self, item: &mut usize, value: &[u8]) -> Result<(), &'static str> {
            if self.replace_before_update {
                self.replace_before_update = false;
                self.rows.remove("a"); self.rows.remove("a:pending");
                self.seed("a", b"foreign-new-login-credential");
                self.seed("a:pending", b"foreign-new-rotation-marker");
            }
            let row = self.rows.values_mut().find(|(id, _)| id == item)
                .ok_or("KEYCHAIN_WRITE_FAILED")?;
            row.1 = value.to_vec(); self.writes += 1; Ok(())
        }
        fn delete(&mut self, item: usize) -> Result<(), &'static str> {
            if self.fail_delete { return Err("KEYCHAIN_DELETE_FAILED"); }
            if self.replace_before_delete {
                self.replace_before_delete = false;
                self.rows.remove("a"); self.rows.remove("a:pending");
                self.seed("a", b"foreign-new-login-credential");
                self.seed("a:pending", b"foreign-new-rotation-marker");
            }
            let name = self.rows.iter().find(|(_, (id, _))| *id == item)
                .map(|(name, _)| name.clone()).ok_or("KEYCHAIN_DELETE_FAILED")?;
            self.rows.remove(&name); self.writes += 1; Ok(())
        }
    }
    fn nonces() -> [Vec<u8>; 2] { [b"\0initial-a-fixture".to_vec(), b"\0initial-c-fixture".to_vec()] }
    fn pair(store: &mut Fake) -> [Reservation<usize>; 2] {
        reserve_pair(store, ["a", "c"], nonces()).ok().expect("fixture reservation")
    }

    #[test]
    fn both_slots_are_reserved_before_all_four_initial_publication_combinations() {
        for a in [None, Some("acquisition-refresh-successor")] {
            for c in [None, Some("content-refresh-successor")] {
                let mut store = Fake::default(); let [a_receipt, c_receipt] = pair(&mut store);
                assert_eq!(store.rows.len(), 4);
                assert!(!super::super::valid_refresh(std::str::from_utf8(store.bytes("a").unwrap()).unwrap()));
                publish(&mut store, "a", a_receipt, a).unwrap();
                assert!(store.bytes("c:pending").is_some());
                publish(&mut store, "c", c_receipt, c).unwrap();
                assert_eq!(store.rows.len(), 2);
                let values = nonces();
                assert_eq!(store.bytes("a"), Some(a.map(str::as_bytes).unwrap_or(&values[0])));
                assert_eq!(store.bytes("c"), Some(c.map(str::as_bytes).unwrap_or(&values[1])));
            }
        }
    }
    #[test]
    fn existing_credentials_and_pending_owners_are_preserved() {
        for name in ["a", "c", "a:pending", "c:pending"] {
            let mut store = Fake::default(); store.seed(name, b"existing-owner-credential");
            let before = store.rows.clone();
            assert!(reserve_pair(&mut store, ["a", "c"], nonces()).is_err());
            assert_eq!(store.rows, before);
        }
    }
    #[test]
    fn delayed_content_can_consume_only_its_original_account_receipt() {
        let mut store = Fake::default(); let [a, c] = pair(&mut store);
        publish(&mut store, "a", a, None).unwrap();
        assert_eq!(publish(&mut store, "a", c, Some("foreign-content-refresh")), Err("INITIAL_RESERVATION_CHANGED"));
        assert_eq!(store.bytes("c:pending"), Some(nonces()[1].as_slice()));
    }
    #[test]
    fn logout_recreation_after_lookup_cannot_overwrite_or_delete_new_items() {
        let mut store = Fake::default(); let [a, _c] = pair(&mut store);
        store.replace_before_update = true;
        assert_eq!(publish(&mut store, "a", a, Some("old-callback-refresh-value")), Err("KEYCHAIN_WRITE_FAILED"));
        assert_eq!(store.bytes("a"), Some(b"foreign-new-login-credential".as_slice()));
        assert_eq!(store.bytes("a:pending"), Some(b"foreign-new-rotation-marker".as_slice()));
    }
    #[test]
    fn replaced_content_before_publication_is_not_adopted_or_removed() {
        let mut store = Fake::default(); let [a, c] = pair(&mut store);
        publish(&mut store, "a", a, None).unwrap();
        store.seed("c", b"foreign-new-content-credential");
        store.seed("c:pending", b"foreign-new-content-marker");
        let before = store.rows.clone();
        assert_eq!(publish(&mut store, "c", c, None), Err("INITIAL_RESERVATION_CHANGED"));
        assert_eq!(store.rows, before);
    }
    #[test]
    fn unknown_creation_preserves_both_fences_without_automatic_compensation() {
        let mut store = Fake { unknown_add: Some("c".to_owned()), ..Fake::default() };
        assert!(reserve_pair(&mut store, ["a", "c"], nonces()).is_err());
        assert_eq!(store.bytes("a"), Some(nonces()[0].as_slice()));
        assert_eq!(store.bytes("a:pending"), Some(nonces()[0].as_slice()));
        assert_eq!(store.bytes("c"), Some(nonces()[1].as_slice()));
        assert_eq!(store.bytes("c:pending"), Some(nonces()[1].as_slice()));
    }
    #[test]
    fn unconfirmed_marker_release_never_reports_successful_publication() {
        let mut store = Fake::default(); let [a, _c] = pair(&mut store);
        store.fail_delete = true;
        assert_eq!(publish(&mut store, "a", a, Some("acquisition-refresh-successor")), Err("KEYCHAIN_DELETE_FAILED"));
        assert!(store.bytes("a:pending").is_some());
    }
    #[test]
    fn malformed_present_refresh_is_rejected_without_store_mutation() {
        let mut store = Fake::default(); let [a, _c] = pair(&mut store);
        let before = store.rows.clone(); let writes = store.writes;
        assert_eq!(publish(&mut store, "a", a, Some("bad token")), Err("REFRESH_TOKEN_INVALID"));
        assert_eq!(store.rows, before); assert_eq!(store.writes, writes);
    }
    #[test]
    fn access_only_completion_cannot_delete_a_recreated_foreign_marker() {
        let mut store = Fake::default(); let [a, _c] = pair(&mut store);
        store.replace_before_delete = true;
        assert_eq!(publish(&mut store, "a", a, None), Err("KEYCHAIN_DELETE_FAILED"));
        assert_eq!(store.bytes("a"), Some(b"foreign-new-login-credential".as_slice()));
        assert_eq!(store.bytes("a:pending"), Some(b"foreign-new-rotation-marker".as_slice()));
    }
    #[test]
    fn uncertain_second_slot_cleanup_preserves_first_reservation_and_foreign_credential() {
        let mut store = Fake::default(); store.seed("c", b"foreign-existing-credential");
        store.fail_delete = true;
        assert!(reserve_pair(&mut store, ["a", "c"], nonces()).is_err());
        assert_eq!(store.bytes("c"), Some(b"foreign-existing-credential".as_slice()));
        assert_eq!(store.bytes("a"), Some(nonces()[0].as_slice()));
        assert!(store.bytes("a:pending").is_some() && store.bytes("c:pending").is_some());
    }
    fn fp(value: &str) -> String { format!("inert-fingerprint:{value}") }
    fn marker(value: &str) -> String { format!("inert-marker:{value}") }
    #[test]
    fn foreign_credential_after_publication_never_becomes_a_refresh_request() {
        let mut store = Fake::default(); let [a, _c] = pair(&mut store);
        let old = "original-published-refresh-value";
        publish(&mut store, "a", a, Some(old)).unwrap();
        store.rows.remove("a"); store.seed("a", b"foreign-new-login-credential");
        let before = store.rows.clone(); let writes = store.writes;
        let mut sent = Vec::new();
        if let Ok(value) = claim_bound(&mut store, "a", &fp(old), fp, marker) { sent.push(value); }
        assert!(sent.is_empty()); assert_eq!(store.rows, before); assert_eq!(store.writes, writes);
    }
    #[test]
    fn replacement_between_observation_and_marker_claim_refuses_before_send() {
        let mut store = Fake::default(); let old = "original-published-refresh-value";
        store.seed("a", old.as_bytes()); store.replace_before_marker_add = true;
        assert_eq!(claim_bound(&mut store, "a", &fp(old), fp, marker), Err("REFRESH_TOKEN_CHANGED"));
        assert_eq!(store.bytes("a"), Some(b"foreign-new-login-credential".as_slice()));
        assert!(store.bytes("a:pending").is_some());
    }
    #[test]
    fn exact_admitted_predecessor_is_claimed_once_and_unknown_claim_is_never_replayed() {
        let mut store = Fake::default(); let old = "original-published-refresh-value";
        store.seed("a", old.as_bytes());
        assert_eq!(claim_bound(&mut store, "a", &fp(old), fp, marker), Ok(old.to_owned()));
        assert_eq!(claim_bound(&mut store, "a", &fp(old), fp, marker), Err("REFRESH_OUTCOME_UNCONFIRMED"));
        let mut unknown = Fake { unknown_add: Some("a:pending".to_owned()), ..Fake::default() };
        unknown.seed("a", old.as_bytes());
        assert_eq!(claim_bound(&mut unknown, "a", &fp(old), fp, marker), Err("KEYCHAIN_WRITE_FAILED"));
        assert_eq!(claim_bound(&mut unknown, "a", &fp(old), fp, marker), Err("REFRESH_OUTCOME_UNCONFIRMED"));
    }
}
