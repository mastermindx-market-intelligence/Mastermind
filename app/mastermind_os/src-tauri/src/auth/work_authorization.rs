//! Read-only work authorization observation. A local absence cannot establish
//! first use or clear an earlier refusal or unsettled Executive attempt.
use super::*;

#[derive(Serialize)]
pub struct WorkAuthorizationStatus {
    schema: &'static str,
    state: &'static str,
    reason: &'static str,
    generation: u64,
}

impl Inner {
    fn work_authorization_status(&self) -> WorkAuthorizationStatus {
        let (state, reason) = match self.executive_reason {
            ExecutiveReason::AuthorizationRefused => ("ADMIN_ACTION_REQUIRED", "AUTHORIZATION_REFUSED"),
            _ => ("INELIGIBLE", "NOT_ELIGIBLE"),
        };
        WorkAuthorizationStatus {
            schema: "mastermind.native_work_authorization.v1",
            state,
            reason,
            generation: self.generation,
        }
    }
}

#[tauri::command]
pub fn read_work_authorization(state: tauri::State<'_, NativeAuth>) -> Result<WorkAuthorizationStatus> {
    Ok(state.lock()?.work_authorization_status())
}

/// Older clients may still issue this command. Reject without opening an auth
/// transaction or changing the current account.
#[tauri::command]
pub fn sign_in_for_work() -> Result<AuthStatus> {
    Err("WORK_AUTHORIZATION_INELIGIBLE".into())
}

#[cfg(test)]
mod disposition_tests {
    use super::*;

    fn owner() -> Inner {
        Inner::with_executive_resource(Some("public-client"), Some("https://fixture.invalid/executive"))
    }

    fn establish_primary(inner: &mut Inner) {
        inner.begin_primary_for_test().unwrap();
        for resource in [Resource::Acquisition, Resource::Content] {
            let pending = inner.pending.as_ref().unwrap();
            assert_eq!(pending.resource, resource);
            let callback = format!("{CALLBACK}?state={}&code=inert", pending.state);
            let (pending, _, client) = inner.consume(&callback).unwrap();
            inner.primary_exchange_current(&pending, &client).unwrap();
            let next = inner.finish_exchange(&pending, Ok(InitialGrant::fixture(Token {
                value: "inert-same-account".into(),
                expires: Instant::now() + Duration::from_secs(60),
                wall_expires: SystemTime::now() + Duration::from_secs(60),
                executive_send: false,
            })));
            assert_eq!(next.is_some(), resource == Resource::Acquisition);
        }
        assert!(inner.token(Resource::Acquisition).is_some());
        assert!(inner.token(Resource::Content).is_some());
        assert!(inner.executive.is_none() && inner.pending.is_none());
    }

    #[test]
    fn former_command_rejects_without_an_auth_owner() {
        assert_eq!(sign_in_for_work().err().as_deref(), Some("WORK_AUTHORIZATION_INELIGIBLE"));
    }

    #[test]
    fn first_work_remains_unavailable_after_cold_primary_login() {
        let mut inner = owner();
        establish_primary(&mut inner);
        assert_eq!(inner.executive_reason, ExecutiveReason::NotEstablished);
        assert_eq!(inner.work_authorization_status().state, "INELIGIBLE");
    }

    #[test]
    fn first_work_remains_unavailable_after_logout_and_primary_login() {
        for outcome in ["AUTHORIZATION_REFUSED", "TOKEN_EXCHANGE_FAILED"] {
            let mut inner = owner();
            inner.fail_transaction(Resource::Executive, outcome);
            if outcome == "AUTHORIZATION_REFUSED" {
                assert_eq!(inner.work_authorization_status().state, "ADMIN_ACTION_REQUIRED");
            }
            inner.invalidate();
            establish_primary(&mut inner);
            assert_eq!(inner.executive_reason, ExecutiveReason::NotEstablished);
            assert_eq!(inner.work_authorization_status().state, "INELIGIBLE", "{outcome}");
        }
    }
}
