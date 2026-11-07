//! Bounded public observations only. No grant, token, identity, URL, error text,
//! request body or external effect is represented by this module.
use serde::Serialize;

#[derive(Clone, Copy, Debug, Default, PartialEq, Eq, Serialize)]
#[serde(rename_all = "SCREAMING_SNAKE_CASE")]
pub(super) enum ExecutiveReason {
    Unconfigured,
    #[default]
    NotEstablished,
    Authorizing,
    Exchanging,
    Available,
    Expired,
    AuthorizationRefused,
    TokenExchangeFailed,
    TokenResponseInvalid,
    AuthBrowserUnavailable,
    AuthTransactionExpired,
    GenerationExhausted,
}
impl ExecutiveReason {
    pub(super) fn failure(code: &str) -> Self {
        match code {
            "AUTHORIZATION_REFUSED" => Self::AuthorizationRefused,
            "TOKEN_RESPONSE_INVALID" => Self::TokenResponseInvalid,
            "AUTH_BROWSER_UNAVAILABLE" => Self::AuthBrowserUnavailable,
            "AUTH_TRANSACTION_EXPIRED" => Self::AuthTransactionExpired,
            _ => Self::TokenExchangeFailed,
        }
    }
}

#[derive(Clone, Copy, Debug, Default, PartialEq, Eq, Serialize)]
#[serde(rename_all = "SCREAMING_SNAKE_CASE")]
pub(super) enum ProgramsPhase {
    #[default]
    NotObserved,
    Pending,
    Ready,
    AuthUnavailable,
    HttpFailure,
    NetworkFailure,
    Timeout,
    BodyFailure,
    InvalidResponse,
}
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq, Serialize)]
pub(super) struct ProgramsRead {
    pub(super) phase: ProgramsPhase,
    pub(super) http_status: Option<u16>,
}
impl ProgramsRead {
    pub(super) fn pending() -> Self { Self { phase: ProgramsPhase::Pending, http_status: None } }
    pub(super) fn auth_unavailable() -> Self { Self { phase: ProgramsPhase::AuthUnavailable, http_status: None } }
    pub(super) fn network(timeout: bool) -> Self {
        Self { phase: if timeout { ProgramsPhase::Timeout } else { ProgramsPhase::NetworkFailure }, http_status: None }
    }
    pub(super) fn response(status: u16, failure: Option<&str>) -> Self {
        // An observation outside this closed public vocabulary is omitted;
        // it never changes the actual READ's eligibility/result.
        if !(100..=599).contains(&status) { return Self::default(); }
        let phase = if !(200..=299).contains(&status) { ProgramsPhase::HttpFailure }
            else { match failure {
                None => ProgramsPhase::Ready,
                Some("RESPONSE_INVALID" | "RESPONSE_BOUND") => ProgramsPhase::InvalidResponse,
                _ => ProgramsPhase::BodyFailure,
            }};
        Self { phase, http_status: Some(status) }
    }
}

#[derive(Serialize)]
pub(super) struct ExecutiveObservation {
    pub(super) schema: &'static str,
    pub(super) generation: u64,
    pub(super) available: bool,
    pub(super) configured: bool,
    pub(super) reason: ExecutiveReason,
    pub(super) programs_read: ProgramsRead,
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn native_diagnostic_observations_are_closed_and_do_not_echo_errors() {
        assert_eq!(ProgramsRead::response(503, Some("private-secret")), ProgramsRead {
            phase: ProgramsPhase::HttpFailure, http_status: Some(503) });
        assert_eq!(ProgramsRead::network(false).phase, ProgramsPhase::NetworkFailure);
        assert_eq!(ProgramsRead::network(true).phase, ProgramsPhase::Timeout);
        assert_eq!(ProgramsRead::response(200, Some("SOURCE_UNAVAILABLE")).phase, ProgramsPhase::BodyFailure);
        assert_eq!(ProgramsRead::response(200, Some("RESPONSE_INVALID")).phase, ProgramsPhase::InvalidResponse);
        assert_eq!(ProgramsRead::response(200, None).phase, ProgramsPhase::Ready);
        assert_eq!(ProgramsRead::response(999, None), ProgramsRead::default());
        let observed = ExecutiveObservation { schema: "mastermind.native_executive_status.v1",
            generation: 3, available: false, configured: true,
            reason: ExecutiveReason::failure("private-secret"), programs_read: ProgramsRead::response(503, None) };
        let raw = serde_json::to_value(observed).unwrap();
        assert_eq!(raw.as_object().unwrap().len(), 6);
        assert_eq!(raw["reason"], "TOKEN_EXCHANGE_FAILED");
        assert!(!raw.to_string().contains("private-secret"));
    }
}
