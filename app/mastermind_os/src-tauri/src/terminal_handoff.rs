//! Native terminal sharing-review handoff.
//!
//! Pure standard-library module: it validates a canonical delivery UUID,
//! composes the fixed sharing-review URL and hands that URL to an injected
//! opener closure. It performs no Tauri, OS, network, browser, filesystem,
//! credential, timer, persistence or global-state work of its own; there is
//! no `static` mutable state and no retry loop. The parent crate owns the
//! real Tauri/`OpenerExt` wiring and injects the opener closure, and the
//! caller separately obtains the persisted delivery UUID through the fixed
//! producer invocation: this module proves safe navigation syntax only and
//! never establishes producer authenticity. The terminal authenticates its
//! actual user independently of this handoff.

/// Fixed schema marker carried on every [`HandoffReceipt`].
pub const RECEIPT_SCHEMA: &str = "mastermind.terminal_navigation.v1";

/// Fixed outcome marker: navigation was requested. This claims nothing
/// beyond the request itself — not that a browser loaded, the user signed
/// in, team access exists, or any share was granted.
pub const RECEIPT_OUTCOME: &str = "HANDOFF_REQUESTED";

/// Fixed sharing-review URL prefix; the canonical UUID is inserted between
/// this and [`SHARING_URL_SUFFIX`]. No other URL shape exists in this module.
pub const SHARING_URL_PREFIX: &str = "https://app.mastermind-x.com/briefs/";

/// Fixed sharing-review URL suffix.
pub const SHARING_URL_SUFFIX: &str = "/sharing";

/// The existing authenticated Alerts page contains Terminal's Briefs inbox.
/// This landing carries no selected delivery or claim about its contents.
pub const BRIEFS_LANDING_URL: &str = "https://app.mastermind-x.com/alerts";

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct LandingHandoffReceipt {
    pub schema: &'static str,
    pub destination: &'static str,
    pub outcome: &'static str,
}

/// Request the fixed Briefs landing once. Terminal owns authentication and
/// authorization; this receipt does not qualify a selected delivery.
pub fn request_briefs_landing<F>(open: F) -> Result<LandingHandoffReceipt, HandoffError>
where
    F: FnOnce(&str) -> Result<(), ()>,
{
    open(BRIEFS_LANDING_URL).map_err(|()| HandoffError::OpenUnavailable)?;
    Ok(LandingHandoffReceipt {
        schema: RECEIPT_SCHEMA,
        destination: "TERMINAL_BRIEFS",
        outcome: RECEIPT_OUTCOME,
    })
}

/// Canonical lowercase UUID length in bytes.
const UUID_LEN: usize = 36;

/// Why a sharing-review handoff could not be completed.
///
/// Variants carry no OS, path, process or credential detail by construction;
/// [`HandoffError::code`] is the only stable surface for terminal display.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum HandoffError {
    /// Input was not a canonical lowercase UUID (version 1..=8, RFC variant).
    InvalidReference,
    /// The injected opener refused the single navigation request.
    OpenUnavailable,
}

impl HandoffError {
    /// Fixed, safe, non-sensitive code for terminal output and telemetry.
    pub fn code(&self) -> &'static str {
        match self {
            HandoffError::InvalidReference => "HANDOFF_INVALID_REFERENCE",
            HandoffError::OpenUnavailable => "HANDOFF_OPEN_UNAVAILABLE",
        }
    }
}

impl std::fmt::Display for HandoffError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str(self.code())
    }
}

impl std::error::Error for HandoffError {}

/// Receipt returned after the opener accepted the navigation request.
///
/// Acceptance means navigation requested only; it is never evidence that a
/// browser loaded, the user signed in, team access exists, or a share was
/// granted. It is an in-memory value: nothing is persisted anywhere.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct HandoffReceipt {
    pub schema: &'static str,
    pub delivery_id: String,
    pub outcome: &'static str,
}

/// True for the four hyphen slots of a canonical UUID string.
fn is_hyphen_slot(index: usize) -> bool {
    index == 8 || index == 13 || index == 18 || index == 23
}

/// True for lowercase ASCII hex digits only; uppercase and non-ASCII fail.
fn is_lower_hex(byte: u8) -> bool {
    matches!(byte, b'0'..=b'9' | b'a'..=b'f')
}

/// Strict canonical-lowercase-UUID check.
///
/// Accepts exactly 36 ASCII bytes with hyphens in the 8/13/18/23 slots,
/// lowercase hex elsewhere, a version nibble in 1..=8 at index 14 and an
/// RFC 4122 variant nibble (8/9/a/b) at index 19. The byte allowlist
/// structurally refuses uppercase, leading/trailing whitespace and
/// newlines, control bytes, non-ASCII text, and the URL metacharacters
/// `?`, `#`, `%`, `/` and `\` (including any alternate or double encoding
/// built from them) — none of those bytes are lowercase hex or hyphen.
fn is_canonical_delivery_uuid(raw: &str) -> bool {
    let bytes = raw.as_bytes();
    if bytes.len() != UUID_LEN {
        return false;
    }
    for (index, &byte) in bytes.iter().enumerate() {
        let allowed = if is_hyphen_slot(index) {
            byte == b'-'
        } else {
            is_lower_hex(byte)
        };
        if !allowed {
            return false;
        }
    }
    matches!(bytes[14], b'1'..=b'8') && matches!(bytes[19], b'8' | b'9' | b'a' | b'b')
}

/// Compose the fixed sharing-review URL for a delivery.
///
/// Returns exactly `https://app.mastermind-x.com/briefs/<UUID>/sharing`,
/// or [`HandoffError::InvalidReference`]. This function is pure: it opens
/// nothing, allocates only the returned `String`, and takes no options.
pub fn sharing_review_url(delivery_id: &str) -> Result<String, HandoffError> {
    if !is_canonical_delivery_uuid(delivery_id) {
        return Err(HandoffError::InvalidReference);
    }
    let mut url =
        String::with_capacity(SHARING_URL_PREFIX.len() + UUID_LEN + SHARING_URL_SUFFIX.len());
    url.push_str(SHARING_URL_PREFIX);
    url.push_str(delivery_id);
    url.push_str(SHARING_URL_SUFFIX);
    Ok(url)
}

/// Request a sharing review for one persisted delivery.
///
/// `delivery_id` is fully validated before `open` is considered, and the
/// validated URL is handed to `open` at most once: no retries, no fallbacks,
/// no persistence, no queue, no timers. The caller injects the real opener
/// (for example a Tauri `OpenerExt` closure wired by the parent); an
/// `Err(())` from it maps to [`HandoffError::OpenUnavailable`] with no
/// underlying OS or credential detail attached.
pub fn request_sharing_review<F>(
    delivery_id: &str,
    open: F,
) -> Result<HandoffReceipt, HandoffError>
where
    F: FnOnce(&str) -> Result<(), ()>,
{
    let url = sharing_review_url(delivery_id)?;
    open(&url).map_err(|()| HandoffError::OpenUnavailable)?;
    Ok(HandoffReceipt {
        schema: RECEIPT_SCHEMA,
        // Validated canonical lowercase above, so this is the same input.
        delivery_id: delivery_id.to_string(),
        outcome: RECEIPT_OUTCOME,
    })
}

#[cfg(test)]
mod tests {
    use super::{
        request_sharing_review, sharing_review_url, HandoffError, HandoffReceipt,
        RECEIPT_OUTCOME, RECEIPT_SCHEMA, SHARING_URL_PREFIX, SHARING_URL_SUFFIX,
    };
    use std::cell::{Cell, RefCell};

    #[test]
    fn briefs_landing_has_fixed_destination_without_delivery_identity() {
        let calls = Cell::new(0);
        let receipt = super::request_briefs_landing(|url| {
            calls.set(calls.get() + 1);
            assert_eq!(url, "https://app.mastermind-x.com/alerts");
            Ok(())
        }).unwrap();
        assert_eq!(calls.get(), 1);
        assert_eq!(receipt.destination, "TERMINAL_BRIEFS");
        assert_eq!(receipt.outcome, RECEIPT_OUTCOME);
        assert_eq!(receipt.schema, RECEIPT_SCHEMA);
    }

    #[test]
    fn briefs_landing_failure_has_no_fallback_or_retry() {
        let calls = Cell::new(0);
        let result = super::request_briefs_landing(|_| {
            calls.set(calls.get() + 1);
            Err(())
        });
        assert_eq!(result, Err(HandoffError::OpenUnavailable));
        assert_eq!(calls.get(), 1);
    }

    /// Canonical positive fixture: version 4, RFC variant 9, 36 bytes.
    const GOOD: &str = "5f0c9a12-7b34-4e8d-9c2f-a1b3d4e5f607";
    const EXPECTED_URL: &str =
        "https://app.mastermind-x.com/briefs/5f0c9a12-7b34-4e8d-9c2f-a1b3d4e5f607/sharing";

    /// Records every entry into the injected opener; nothing else in this
    /// pure module can produce effects, so this counter is the effect log.
    struct Probe {
        calls: Cell<usize>,
        urls: RefCell<Vec<String>>,
        fail: bool,
    }

    impl Probe {
        fn new(fail: bool) -> Self {
            Probe {
                calls: Cell::new(0),
                urls: RefCell::new(Vec::new()),
                fail,
            }
        }
        fn count(&self) -> usize {
            self.calls.get()
        }
        fn urls(&self) -> Vec<String> {
            self.urls.borrow().clone()
        }
    }

    /// Drive the public API with a counting opener closure.
    fn run(probe: &Probe, delivery_id: &str) -> Result<HandoffReceipt, HandoffError> {
        let fail = probe.fail;
        request_sharing_review(delivery_id, move |url| {
            probe.calls.set(probe.calls.get() + 1);
            probe.urls.borrow_mut().push(url.to_string());
            if fail {
                Err(())
            } else {
                Ok(())
            }
        })
    }

    #[test]
    fn positive_uuid_builds_exact_fixed_url() {
        assert_eq!(sharing_review_url(GOOD), Ok(EXPECTED_URL.to_string()));
    }

    #[test]
    fn every_allowed_version_and_variant_is_accepted() {
        for version in b'1'..=b'8' {
            for variant in [b'8', b'9', b'a', b'b'] {
                let mut id = GOOD.as_bytes().to_vec();
                id[14] = version;
                id[19] = variant;
                let id = String::from_utf8(id).expect("fixture stays ASCII");
                let url = sharing_review_url(&id).expect("canonical uuid accepted");
                assert_eq!(
                    url,
                    format!("{}{}{}", SHARING_URL_PREFIX, id, SHARING_URL_SUFFIX)
                );
            }
        }
    }

    #[test]
    fn negative_reference_classes_refuse_with_zero_opener_calls() {
        let negatives: Vec<String> = vec![
            String::new(),                                          // empty
            "5f0c9a12-7b34-4e8d-9c2f-a1b3d4e5f60".to_string(),      // 35 bytes
            "5f0c9a12-7b34-4e8d-9c2f-a1b3d4e5f6077".to_string(),    // 37 bytes
            GOOD.to_ascii_uppercase(),                              // uppercase
            format!(" {}", GOOD),                                   // leading space
            format!("{} ", GOOD),                                   // trailing space
            format!("{}\n", GOOD),                                  // trailing newline
            format!("{}\r\n", GOOD),                                // CRLF
            format!("\t{}", GOOD),                                  // leading tab
            format!("{}\u{7}", GOOD),                               // control BEL
            format!("\u{0}{}", GOOD),                               // NUL prefix
            "5f0c9a1g-7b34-4e8d-9c2f-a1b3d4e5f607".to_string(),     // non-hex letter
            "5f0c9a12x7b34-4e8d-9c2f-a1b3d4e5f607".to_string(),     // hyphen slot wrong
            "5f0c9a12--b34-4e8d-9c2f-a1b3d4e5f607".to_string(),     // doubled hyphen
            "5f0c9a12-7b34-0e8d-9c2f-a1b3d4e5f607".to_string(),     // version 0
            "5f0c9a12-7b34-9e8d-9c2f-a1b3d4e5f607".to_string(),     // version 9
            "5f0c9a12-7b34-fe8d-9c2f-a1b3d4e5f607".to_string(),     // version f
            "5f0c9a12-7b34-4e8d-0c2f-a1b3d4e5f607".to_string(),     // variant 0
            "5f0c9a12-7b34-4e8d-7c2f-a1b3d4e5f607".to_string(),     // variant 7
            "5f0c9a12-7b34-4e8d-cc2f-a1b3d4e5f607".to_string(),     // variant c
            "5f0c9a12-7b34-4e8d-fc2f-a1b3d4e5f607".to_string(),     // variant f
            "00000000-0000-0000-0000-000000000000".to_string(),     // nil uuid
            "5f0c9a12-7b34-4e8d-%c2f-a1b3d4e5f607".to_string(),     // percent encoding
            format!("%35{}", &GOOD[1..]),                           // double encoding
            "5f0c9a12-7b34-4e8d-/c2f-a1b3d4e5f607".to_string(),     // path separator
            "5f0c9a12-7b34-4e8d-\\c2f-a1b3d4e5f607".to_string(),    // backslash separator
            "5f0c9a12-7b34-4e8d-?c2f-a1b3d4e5f607".to_string(),     // query marker
            "5f0c9a12-7b34-4e8d-#c2f-a1b3d4e5f607".to_string(),     // fragment marker
            format!("{}/sharing", GOOD),                            // appended path
            format!("{}?x=1", GOOD),                                // appended query
            format!("{}#frag", GOOD),                               // appended fragment
            "5f0c9a12-7b34-4e8d-9c2f-a1b3d4e5f60\u{430}".to_string(), // Cyrillic а
            "5f0c9a1\u{e9}-7b34-4e8d-9c2f-a1b3d4e5f6077".to_string(), // non-ASCII inside
        ];

        for id in &negatives {
            let probe = Probe::new(false);
            assert_eq!(
                run(&probe, id),
                Err(HandoffError::InvalidReference),
                "case {:?} must be refused",
                id
            );
            assert_eq!(
                sharing_review_url(id),
                Err(HandoffError::InvalidReference),
                "pure path must refuse {:?}",
                id
            );
            assert_eq!(probe.count(), 0, "opener must not run for {:?}", id);
            assert!(probe.urls().is_empty(), "no url may reach opener for {:?}", id);
        }
    }

    #[test]
    fn opener_refusal_maps_to_open_unavailable_with_single_call() {
        let probe = Probe::new(true);
        let result = run(&probe, GOOD);
        assert_eq!(result, Err(HandoffError::OpenUnavailable));
        assert_eq!(result.unwrap_err().code(), "HANDOFF_OPEN_UNAVAILABLE");
        assert_eq!(probe.count(), 1);
        assert_eq!(probe.urls(), vec![EXPECTED_URL.to_string()]);
    }

    #[test]
    fn success_receipt_is_navigation_only_with_single_call() {
        let probe = Probe::new(false);
        let result = run(&probe, GOOD);
        assert_eq!(
            result,
            Ok(HandoffReceipt {
                schema: RECEIPT_SCHEMA,
                delivery_id: GOOD.to_string(),
                outcome: RECEIPT_OUTCOME,
            })
        );
        let receipt = result.expect("success case");
        assert_eq!(receipt.schema, "mastermind.terminal_navigation.v1");
        assert_eq!(receipt.outcome, "HANDOFF_REQUESTED");
        assert_eq!(receipt.delivery_id, GOOD);
        assert_eq!(probe.count(), 1);
        assert_eq!(probe.urls(), vec![EXPECTED_URL.to_string()]);
    }

    #[test]
    fn invalid_reference_carries_fixed_safe_code() {
        let error = sharing_review_url("not-a-uuid").unwrap_err();
        assert_eq!(error.code(), "HANDOFF_INVALID_REFERENCE");
        assert_eq!(error.to_string(), "HANDOFF_INVALID_REFERENCE");
    }

    #[test]
    fn url_composition_is_pure_fixed_and_unencoded() {
        let url = sharing_review_url(GOOD).expect("canonical fixture");
        assert_eq!(url, EXPECTED_URL);
        assert_eq!(
            url.len(),
            SHARING_URL_PREFIX.len() + 36 + SHARING_URL_SUFFIX.len()
        );
        assert!(url.starts_with("https://app.mastermind-x.com/briefs/"));
        assert!(url.ends_with("/sharing"));
        assert!(!url.chars().any(|c| matches!(c, '?' | '#' | '%')));
        let inner = &url[SHARING_URL_PREFIX.len()..url.len() - SHARING_URL_SUFFIX.len()];
        assert_eq!(inner, GOOD);
    }
}
