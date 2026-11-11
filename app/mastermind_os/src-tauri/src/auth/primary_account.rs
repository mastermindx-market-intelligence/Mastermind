//! Explicit primary-account action in the incumbent PKCE owner.
//! A/C success is account access only; it never establishes Executive/work access.
use super::*;

impl Inner {
    fn begin_primary_sign_in(&mut self) -> Result<String> {
        if self.client_id.is_none() { return Err("NATIVE_CLIENT_ID_MISSING".into()); }
        if self.pending.is_some() || self.exchanging || self.restoring {
            return Err("AUTH_TRANSACTION_PENDING".into());
        }
        let refused = self.executive_reason == ExecutiveReason::AuthorizationRefused;
        // Same privacy boundary as the existing explicit reauthentication path:
        // unsent same-principal text is held, while old resource authority ends.
        self.begin_reauthentication();
        if refused && self.executive_reason != ExecutiveReason::GenerationExhausted {
            self.executive_reason = ExecutiveReason::AuthorizationRefused;
        }
        self.initial_sign_in_transaction_for(SignInIntent::PrimaryAccount)
    }

    #[cfg(test)]
    pub(super) fn begin_primary_for_test(&mut self) -> Result<String> {
        self.begin_primary_sign_in()
    }

    pub(super) fn primary_exchange_current(&mut self, pending: &Pending, client: &str) -> Result<()> {
        if pending.intent != SignInIntent::PrimaryAccount
            || !matches!(pending.resource, Resource::Acquisition | Resource::Content)
            || pending.generation != self.generation || !self.exchanging
            || pending.expires <= Instant::now()
            || self.client_id.as_deref() != Some(client) {
            if pending.intent == SignInIntent::PrimaryAccount && pending.generation == self.generation {
                self.exchanging = false;
                self.reason = Some("AUTHENTICATION_CHANGED");
            }
            return Err("AUTHENTICATION_CHANGED".into());
        }
        Ok(())
    }
}

#[tauri::command]
pub fn sign_in_primary(app: AppHandle) -> Result<AuthStatus> {
    let state = app.state::<NativeAuth>();
    // Serialize with incumbent logout/credential publication, without reading,
    // deleting or creating any credential merely to choose this action.
    let _keychain = state.keychain_lock.lock().map_err(|_| "KEYCHAIN_UNAVAILABLE")?;
    let mut inner = state.lock()?;
    if inner.client_id.is_none() { return Ok(inner.status()); }
    let url = inner.begin_primary_sign_in()?;
    let generation = inner.generation;
    drop(inner);
    drop(_keychain);
    emit(&app);
    open_transaction(&app, url, generation)?;
    let status = state.lock()?.status();
    Ok(status) // Browser handoff, never a claim that account/work access completed.
}

#[cfg(test)]
mod tests {
    use super::*;
    fn inner() -> Inner {
        Inner::with_executive_resource(Some("public-client"), Some("https://fixture.invalid/executive"))
    }
    fn token() -> Token {
        Token { value: "inert-private-access".into(), expires: Instant::now()+Duration::from_secs(60),
            wall_expires: SystemTime::now()+Duration::from_secs(60), executive_send: false }
    }
    fn callback(state: &str) -> String { format!("{CALLBACK}?state={state}&code=inert-code") }
    fn consume(inner: &mut Inner) -> Pending {
        let raw = callback(&inner.pending.as_ref().unwrap().state);
        inner.consume(&raw).unwrap().0
    }
    fn complete(inner: &mut Inner) -> Option<String> {
        let p = consume(inner);
        inner.primary_exchange_current(&p,"public-client").unwrap();
        inner.finish_exchange(&p,Ok(InitialGrant::fixture(token())))
    }
    #[test]
    fn primary_account_stops_after_content_and_preserves_executive_refusal() {
        let mut i=inner(); i.executive_reason=ExecutiveReason::AuthorizationRefused;
        let first=i.begin_primary_sign_in().unwrap();
        let a=i.pending.as_ref().unwrap();
        assert!(a.intent==SignInIntent::PrimaryAccount);
        let a_state=a.state.clone(); let a_verifier=a.verifier.clone();
        let u=Url::parse(&first).unwrap(); let q:std::collections::BTreeMap<_,_>=u.query_pairs().collect();
        assert_eq!(u.origin().ascii_serialization(),Url::parse(ISSUER).unwrap().origin().ascii_serialization());
        assert_eq!(q["client_id"],"public-client"); assert_eq!(q["audience"],Resource::Acquisition.audience());
        let expected_a_scope = if crate::native_refresh::enabled() { "mastermind.workspace.read offline_access" } else { "mastermind.workspace.read" };
        assert_eq!(q["scope"],expected_a_scope); assert_eq!(q["prompt"],"login");
        assert_eq!(i.executive_reason,ExecutiveReason::AuthorizationRefused);
        let second=complete(&mut i).unwrap();
        let c=i.pending.as_ref().unwrap(); assert!(c.intent==SignInIntent::PrimaryAccount);
        assert_ne!(c.state,a_state); assert_ne!(c.verifier,a_verifier);
        let u=Url::parse(&second).unwrap();let q:std::collections::BTreeMap<_,_>=u.query_pairs().collect();
        assert_eq!(q["audience"],Resource::Content.audience());let expected_c_scope = if crate::native_refresh::enabled() { "mastermind.workspace.content.read offline_access" } else { "mastermind.workspace.content.read" };
        assert_eq!(q["scope"],expected_c_scope);
        assert!(!q.contains_key("prompt"));
        assert!(complete(&mut i).is_none());
        assert!(i.token(Resource::Acquisition).is_some() && i.token(Resource::Content).is_some());
        assert!(i.pending.is_none() && i.executive.is_none());
        assert_eq!(i.executive_reason,ExecutiveReason::AuthorizationRefused);
        assert!(!i.executive_observation().available);
    }
    #[test]
    fn primary_reauthentication_withdraws_old_executive_authority_before_new_account() {
        let mut i=inner();i.executive=Some(token());i.executive_reason=ExecutiveReason::Available;
        i.acquisition=Some(token());i.content=Some(token());
        let old_generation=i.generation;let old_executive=i.executive_generation;
        i.begin_primary_sign_in().unwrap();
        assert_ne!(i.generation,old_generation);assert_ne!(i.executive_generation,old_executive);
        assert!(i.acquisition.is_none() && i.content.is_none() && i.executive.is_none());
        assert!(!i.executive_observation().available);
        complete(&mut i).unwrap();assert!(complete(&mut i).is_none());
        assert!(i.acquisition.is_some() && i.content.is_some() && i.executive.is_none());
    }
    #[test]
    fn primary_late_token_is_withheld_at_original_pending_deadline() {
        for resource in [Resource::Acquisition,Resource::Content] {
            let mut i=inner();i.executive_reason=ExecutiveReason::AuthorizationRefused;
            i.begin_primary_sign_in().unwrap();if resource==Resource::Content {complete(&mut i).unwrap();}
            let mut p=consume(&mut i);p.expires=Instant::now()-Duration::from_secs(1);
            assert!(i.finish_exchange(&p,Ok(InitialGrant::fixture(token()))).is_none());
            assert!(i.token(resource).is_none() && i.pending.is_none() && !i.exchanging);
            assert_eq!(i.reason,Some("AUTH_TRANSACTION_EXPIRED"));
            assert_eq!(i.executive_reason,ExecutiveReason::AuthorizationRefused);
        }
    }
    #[test]
    fn preexchange_refusal_closes_only_same_original_primary_exchange() {
        let mut i=inner();i.executive_reason=ExecutiveReason::AuthorizationRefused;
        i.begin_primary_sign_in().unwrap();let p=consume(&mut i);
        assert!(i.primary_exchange_current(&p,"foreign-client").is_err());
        assert!(!i.exchanging && i.pending.is_none());
        assert_eq!(i.reason,Some("AUTHENTICATION_CHANGED"));
        assert_eq!(i.executive_reason,ExecutiveReason::AuthorizationRefused);
        i.begin_primary_sign_in().unwrap();let replacement=i.pending.as_ref().unwrap().state.clone();
        assert!(i.primary_exchange_current(&p,"public-client").is_err());
        assert_eq!(i.pending.as_ref().unwrap().state,replacement);
    }
    #[test]
    fn original_legacy_full_purpose_remains_explicit_and_chains_executive() {
        let mut i=inner();i.initial_sign_in_transaction().unwrap();
        for resource in [Resource::Acquisition,Resource::Content] {
            let p=consume(&mut i);assert_eq!(p.resource,resource);assert!(p.intent==SignInIntent::LegacyFull);
            assert!(i.finish_exchange(&p,Ok(InitialGrant::fixture(token()))).is_some());
        }
        assert_eq!(i.pending.as_ref().unwrap().resource,Resource::Executive);
        assert!(i.pending.as_ref().unwrap().intent==SignInIntent::LegacyFull);
    }
    #[test]
    fn primary_purpose_cannot_construct_consume_or_publish_executive() {
        let mut i=inner();i.executive_reason=ExecutiveReason::AuthorizationRefused;
        assert!(i.transaction_for(Resource::Executive,SignInIntent::PrimaryAccount).is_err());
        assert!(i.pending.is_none());assert_eq!(i.executive_reason,ExecutiveReason::AuthorizationRefused);
        i.begin_primary_sign_in().unwrap();i.pending.as_mut().unwrap().resource=Resource::Executive;
        let raw=callback(&i.pending.as_ref().unwrap().state);assert!(i.consume(&raw).is_err());
        assert!(i.executive.is_none());assert_eq!(i.executive_reason,ExecutiveReason::AuthorizationRefused);
        i.begin_primary_sign_in().unwrap();let mut p=consume(&mut i);p.resource=Resource::Executive;
        assert!(i.primary_exchange_current(&p,"public-client").is_err());
        assert!(i.finish_exchange(&p,Ok(InitialGrant::fixture(token()))).is_none());assert!(i.executive.is_none());
    }
    #[test]
    fn duplicate_primary_gesture_does_not_replace_original_pkce() {
        let mut i=inner();i.begin_primary_sign_in().unwrap();let state=i.pending.as_ref().unwrap().state.clone();
        assert!(i.begin_primary_sign_in().is_err());assert_eq!(i.pending.as_ref().unwrap().state,state);
        let p=consume(&mut i);assert!(i.begin_primary_sign_in().is_err());
        assert!(i.primary_exchange_current(&p,"public-client").is_ok());
    }
    #[test]
    fn foreign_expired_denied_and_duplicate_callbacks_never_advance_primary_chain() {
        let mut i=inner();i.executive_reason=ExecutiveReason::AuthorizationRefused;
        i.begin_primary_sign_in().unwrap();let state=i.pending.as_ref().unwrap().state.clone();
        assert!(i.consume(&callback("foreign-state")).is_err());assert_eq!(i.pending.as_ref().unwrap().state,state);
        i.pending.as_mut().unwrap().expires=Instant::now()-Duration::from_secs(1);
        assert!(i.consume(&callback(&state)).is_err());assert!(i.pending.is_none() && i.acquisition.is_none());
        i.begin_primary_sign_in().unwrap();let state=i.pending.as_ref().unwrap().state.clone();
        assert!(i.consume(&format!("{CALLBACK}?state={state}&error=access_denied")).is_err());
        assert!(i.consume(&callback(&state)).is_err());assert!(i.pending.is_none());
        assert_eq!(i.executive_reason,ExecutiveReason::AuthorizationRefused);
    }
    #[test]
    fn late_primary_results_cannot_publish_after_cancel_or_replacement() {
        for resource in [Resource::Acquisition,Resource::Content] {
            let mut i=inner();i.begin_primary_sign_in().unwrap();
            if resource==Resource::Content { complete(&mut i).unwrap(); }
            let p=consume(&mut i);i.invalidate();i.begin_primary_sign_in().unwrap();
            let replacement=i.pending.as_ref().unwrap().state.clone();
            assert!(i.finish_exchange(&p,Ok(InitialGrant::fixture(token()))).is_none());
            assert_eq!(i.pending.as_ref().unwrap().state,replacement);
            assert!(i.acquisition.is_none() && i.content.is_none() && i.executive.is_none());
        }
    }
    #[test]
    fn primary_final_preexchange_fence_checks_captured_client_generation_and_deadline() {
        for fault in 0..5 {
            let mut i=inner();i.begin_primary_sign_in().unwrap();let mut p=consume(&mut i);
            match fault {0=>i.generation+=1,1=>i.client_id=Some("foreign-client".into()),
                2=>p.expires=Instant::now()-Duration::from_secs(1),3=>i.exchanging=false,
                _=>p.intent=SignInIntent::LegacyFull}
            assert!(i.primary_exchange_current(&p,"public-client").is_err());
        }
    }
    #[test]
    fn primary_token_failure_is_not_executive_refusal_clearance_or_automatic_retry() {
        for resource in [Resource::Acquisition,Resource::Content] {
            let mut i=inner();i.executive_reason=ExecutiveReason::AuthorizationRefused;i.begin_primary_sign_in().unwrap();
            if resource==Resource::Content { complete(&mut i).unwrap(); }
            let p=consume(&mut i);assert!(i.finish_exchange(&p,Err("inert-token-error".into())).is_none());
            assert!(i.pending.is_none() && i.executive.is_none());assert_eq!(i.executive_reason,ExecutiveReason::AuthorizationRefused);
        }
        assert!(!Resource::Executive.persistent());
    }
}
