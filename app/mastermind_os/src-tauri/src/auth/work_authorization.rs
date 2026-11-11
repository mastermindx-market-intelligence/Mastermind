//! Prospective FIRST work connection through the incumbent full PKCE flow.
//! Never an Executive-refusal/expiry/unknown recovery or A/C bearer-preservation claim.
use super::*;
const INELIGIBLE: &str = "WORK_AUTHORIZATION_INELIGIBLE";
#[derive(Serialize)]
pub struct WorkAuthorizationStatus {
    schema: &'static str,
    state: &'static str,
    reason: &'static str,
    generation: u64,
}
impl Inner {
    fn work_entry_eligible(&self) -> bool {
        !crate::native_refresh::enabled()
            && self.client_id.is_some() && self.executive_resource.is_some()
            && self.generation < MAX_SAFE_GENERATION && self.executive_generation < MAX_SAFE_GENERATION
            && self.token(Resource::Acquisition).is_some() && self.token(Resource::Content).is_some()
            && self.executive.is_none() && self.executive_reason == ExecutiveReason::NotEstablished
            && self.pending.is_none() && !self.exchanging && !self.restoring && self.reason.is_none()
    }
    fn work_authorization_status(&self) -> WorkAuthorizationStatus {
        let refused = self.executive_reason == ExecutiveReason::AuthorizationRefused;
        let eligible = self.work_entry_eligible();
        WorkAuthorizationStatus {schema:"mastermind.native_work_authorization.v1",
            state:if refused {"ADMIN_ACTION_REQUIRED"} else if eligible {"ELIGIBLE"} else {"INELIGIBLE"},
            reason:if refused {"AUTHORIZATION_REFUSED"} else if eligible {"WORK_NOT_ESTABLISHED"} else {"NOT_ELIGIBLE"},
            generation:self.generation}
    }
    fn begin_work_sign_in(&mut self) -> Result<String> {
        // Same mutex critical section as reauthentication. A previous UI read is
        // observation only: no caller ticket/label can authorize this transition.
        if !self.work_entry_eligible() {return Err(INELIGIBLE.into());}
        self.begin_reauthentication();
        self.initial_sign_in_transaction_for(SignInIntent::LegacyFull)
    }
}
#[tauri::command]
pub fn read_work_authorization(state: tauri::State<'_, NativeAuth>) -> Result<WorkAuthorizationStatus> {
    Ok(state.lock()?.work_authorization_status())
}
#[tauri::command]
pub fn sign_in_for_work(app: AppHandle) -> Result<AuthStatus> {
    let state=app.state::<NativeAuth>();
    // Serialize with logout/credential publication but never access a credential.
    // RefreshON remains ineligible; this action cannot delete a saved A/C grant.
    let keychain=state.keychain_lock.lock().map_err(|_| "KEYCHAIN_UNAVAILABLE")?;
    let mut inner=state.lock()?;
    let url=inner.begin_work_sign_in()?;
    let generation=inner.generation;
    drop(inner);drop(keychain);
    emit(&app);open_transaction(&app,url,generation)?;
    let result=state.lock()?.status();Ok(result)
}
#[cfg(test)]
mod tests {
    use super::*;
    fn token(value:&str)->Token {Token{value:value.into(),expires:Instant::now()+Duration::from_secs(60),wall_expires:SystemTime::now()+Duration::from_secs(60),executive_send:false}}
    fn ready()->Inner {let mut i=Inner::with_executive_resource(Some("public-client"),Some("https://fixture.invalid/executive"));i.acquisition=Some(token("old-A"));i.content=Some(token("old-C"));i}
    fn fingerprint(i:&Inner)->Value {serde_json::json!({"generation":i.generation,"e_generation":i.executive_generation,"a":i.acquisition.as_ref().map(|t|t.value.as_str()),"c":i.content.as_ref().map(|t|t.value.as_str()),"e":i.executive.as_ref().map(|t|t.value.as_str()),"reason":format!("{:?}",i.executive_reason),"pending":i.pending.as_ref().map(|p|p.state.as_str())})}
    #[test]
    fn work_status_exports_only_closed_local_observations() {
        let mut i=ready();i.generation=3;
        let initial=serde_json::to_value(i.work_authorization_status()).unwrap();
        assert_eq!(initial["state"],if crate::native_refresh::enabled(){"INELIGIBLE"}else{"ELIGIBLE"});
        i.executive_reason=ExecutiveReason::AuthorizationRefused;
        let refused=serde_json::to_value(i.work_authorization_status()).unwrap();assert_eq!(refused["state"],"ADMIN_ACTION_REQUIRED");
        i.executive_reason=ExecutiveReason::NotEstablished;i.exchanging=true;
        let active=serde_json::to_value(i.work_authorization_status()).unwrap();assert_eq!(active["state"],"INELIGIBLE");
        println!("WORK_STATUS_FIXTURE={}",serde_json::json!({"initial":initial,"refused":refused,"active":active}));
    }
    #[test]
    fn first_work_entry_reuses_explicit_full_flow_and_privacy_boundary() {
        let mut i=ready();
        if crate::native_refresh::enabled(){assert!(i.begin_work_sign_in().is_err());return;}
        assert_eq!(i.work_authorization_status().state,"ELIGIBLE");let g=i.generation;
        let url=i.begin_work_sign_in().unwrap();assert_eq!(i.generation,g+1);assert!(i.acquisition.is_none()&&i.content.is_none()&&i.executive.is_none());
        let u=Url::parse(&url).unwrap();let q:std::collections::BTreeMap<_,_>=u.query_pairs().collect();assert_eq!(q["audience"],Resource::Acquisition.audience());assert_eq!(q["scope"],Resource::Acquisition.scope());assert_eq!(q["prompt"],"login");
        for resource in [Resource::Acquisition,Resource::Content,Resource::Executive] {
            let pending=i.pending.as_ref().unwrap();assert_eq!(pending.resource,resource);assert!(pending.intent==SignInIntent::LegacyFull);
            let raw=format!("{CALLBACK}?state={}&code=inert",pending.state);let(p,_,_)=i.consume(&raw).unwrap();
            let next=i.finish_exchange(&p,Ok(InitialGrant::fixture(token("fresh"))));assert_eq!(next.is_some(),resource!=Resource::Executive);
        }
        assert!(i.token(Resource::Executive).is_some());assert!(i.pending.is_none());
    }
    #[test]
    fn held_refusal_is_administrator_only_and_never_cleared_by_work_gesture() {
        let mut i=ready();i.executive_reason=ExecutiveReason::AuthorizationRefused;let before=fingerprint(&i);
        let s=serde_json::to_value(i.work_authorization_status()).unwrap();assert_eq!(s["state"],"ADMIN_ACTION_REQUIRED");assert_eq!(s["reason"],"AUTHORIZATION_REFUSED");assert_eq!(s.as_object().unwrap().len(),4);
        assert!(i.begin_work_sign_in().is_err());assert_eq!(fingerprint(&i),before);assert!(i.pending.is_none());
    }
    #[test]
    fn all_noninitial_executive_outcomes_refuse_without_mutation() {
        for reason in [ExecutiveReason::Available,ExecutiveReason::Expired,ExecutiveReason::Authorizing,ExecutiveReason::Exchanging,ExecutiveReason::AuthTransactionExpired,ExecutiveReason::TokenExchangeFailed,ExecutiveReason::TokenResponseInvalid,ExecutiveReason::AuthBrowserUnavailable,ExecutiveReason::GenerationExhausted] {
            let mut i=ready();i.executive_reason=reason;let before=fingerprint(&i);assert!(i.begin_work_sign_in().is_err());assert_eq!(fingerprint(&i),before);
        }
    }
    #[test]
    fn live_account_and_current_idle_owner_are_required_atomically() {
        for fault in 0..11 {
            let mut i=ready();match fault {0=>i.acquisition=None,1=>i.content=None,2=>i.acquisition.as_mut().unwrap().expires=Instant::now(),3=>i.content.as_mut().unwrap().wall_expires=SystemTime::UNIX_EPOCH,4=>i.executive=Some(token("old-E")),5=>i.exchanging=true,6=>i.restoring=true,7=>i.reason=Some("TOKEN_EXCHANGE_FAILED"),8=>i.client_id=None,9=>i.executive_resource=None,_=>i.generation=MAX_SAFE_GENERATION};
            let before=fingerprint(&i);assert!(i.begin_work_sign_in().is_err());assert_eq!(fingerprint(&i),before);
        }
    }
    #[test]
    fn pending_and_late_refusal_after_eligible_observation_never_start_another_flow() {
        let mut i=ready();if crate::native_refresh::enabled(){return;}
        assert_eq!(i.work_authorization_status().state,"ELIGIBLE");i.executive_reason=ExecutiveReason::AuthorizationRefused;assert!(i.begin_work_sign_in().is_err());
        let mut i=ready();i.begin_work_sign_in().unwrap();let state=i.pending.as_ref().unwrap().state.clone();assert!(i.begin_work_sign_in().is_err());assert_eq!(i.pending.as_ref().unwrap().state,state);
    }
}
