//! Closed request grammar for the incumbent fresh conversation composition.
//!
//! Source-only mirror of `common.fresh_conversation_contract.validate_request`
//! and `validate_reference`. Pure data selectors: authentication stays in the
//! incumbent native owner, and effects stay in the incumbent executor. No
//! preview digest, request, or response grants admission. Response decoders
//! are intentionally out of scope; the parent composes auth and registration.
//!
//! Every rejection carries only the fixed generic `REQUEST_INVALID` reason.
//! Arguments, messages, digests, and bearer material are never echoed into
//! errors, logs, or assertions.

use serde_json::Value;

/// Fixed generic rejection reason; carries no request detail.
pub const REQUEST_INVALID: &str = "REQUEST_INVALID";

/// Exactly the ten source-owned route paths, literal only.
const ROUTES: [(&str, &str); 10] = [
    ("/os/executive/conversation/preview", "preview"),
    ("/os/executive/conversation/create", "create"),
    ("/os/executive/conversation/status", "status"),
    ("/os/executive/conversation/read", "read"),
    ("/os/executive/conversation/consume", "consume"),
    ("/os/executive/conversation/turn", "turn"),
    ("/os/executive/conversation/turn/status", "turn_status"),
    ("/os/executive/conversation/turn/read", "turn_read"),
    ("/os/executive/conversation/consume/status", "consume_status"),
    ("/os/executive/conversation/turn/preview", "turn_preview"),
];

/// Route path to operation name; exact literal match only.
pub fn operation(path: &str) -> Option<&'static str> {
    ROUTES.iter().chain(NATIVE_ROUTES.iter()).find(|(p, _)| *p == path).map(|(_, o)| *o)
}

/// Operation name to its single route path; exact literal match only.
pub fn path(operation: &str) -> Option<&'static str> {
    ROUTES.iter().find(|(_, o)| *o == operation).map(|(p, _)| *p)
}

/// `_WORK`: `WS:` + 1..=69 ASCII alnum start and 0..=68 alnum/`._-` rest
/// (4..=72 bytes total).
fn work_valid(s: &str) -> bool {
    let b = s.as_bytes();
    b.len() >= 4
        && b.len() <= 72
        && b.starts_with(b"WS:")
        && b[3].is_ascii_alphanumeric()
        && b[4..].iter().all(|&c| {
            c.is_ascii_alphanumeric() || matches!(c, b'.' | b'_' | b'-')
        })
}

/// 1..=`max` bytes; first byte ASCII alnum, rest ASCII alnum or `._:-`.
fn key_like(s: &str, max: usize) -> bool {
    let b = s.as_bytes();
    !b.is_empty()
        && b.len() <= max
        && b[0].is_ascii_alphanumeric()
        && b[1..].iter().all(|&c| {
            c.is_ascii_alphanumeric() || matches!(c, b'.' | b'_' | b':' | b'-')
        })
}

/// `_KEY`: 1..=96 for operation keys and turn keys.
fn key_valid(s: &str) -> bool {
    key_like(s, 96)
}

/// Reference `root_job_id`: 1..=128 with the same character class as `_KEY`.
fn job_id_valid(s: &str) -> bool {
    key_like(s, 128)
}

/// `_HEX`: exactly 64 lowercase hex bytes.
fn digest_valid(s: &str) -> bool {
    let b = s.as_bytes();
    b.len() == 64 && b.iter().all(|&c| c.is_ascii_digit() || (b'a'..=b'f').contains(&c))
}

/// Python `str.strip()` whitespace: Unicode `White_Space` plus U+001C..U+001F.
/// Those four file/group/record/unit separators have bidi classes B/S, which
/// Python counts as space; Rust `char::is_whitespace` omits them. No
/// `White_Space` character is missed, so the sets match exactly. A message of
/// only these characters is blank, matching `not message.strip()`.
fn py_space(c: char) -> bool {
    c.is_whitespace() || ('\u{1c}'..='\u{1f}').contains(&c)
}

/// `type(x) is int and x >= 1`: JSON integers only; bool, float, and string
/// are different `Value` variants and reject.
fn positive_int(v: &Value) -> bool {
    v.as_u64().is_some_and(|n| n >= 1)
}

/// Message grammar. Non-blank after Python strip, at most 700 Unicode scalar
/// values (Python `len`), no C0 control except tab/newline/carriage return,
/// no DEL or C1 range (U+007F..U+009F), and at most 2800 UTF-8 bytes
/// (`str::len`). A `&str` is always valid UTF-8, so the Python
/// `UnicodeEncodeError` path has no Rust analogue and both reject the same
/// inputs. The 2800-byte cap is dominated by the 700-character cap only for
/// inputs that fit; it is kept for exact contract fidelity.
fn message_valid(m: &str) -> bool {
    m.chars().count() <= 700
        && m.len() <= 2800
        && !m.chars().all(py_space)
        && m.chars().all(|c| {
            let o = c as u32;
            !((o < 32 && !matches!(c, '\t' | '\n' | '\r')) || (127..=159).contains(&o))
        })
}

/// Closed reference shape. Returns the validated `work_ref` so the caller can
/// enforce the foreign-work comparison.
fn reference_valid(value: &Value) -> Result<&str, String> {
    const KEYS: [&str; 6] = [
        "schema",
        "work_ref",
        "root_job_id",
        "root_event_id",
        "root_event_sha256",
        "principal_scope_sha256",
    ];
    let invalid = || REQUEST_INVALID.to_owned();
    let obj = value.as_object().ok_or_else(invalid)?;
    if obj.len() != KEYS.len() || KEYS.iter().any(|k| !obj.contains_key(*k)) {
        return Err(invalid());
    }
    if obj.get("schema").and_then(Value::as_str)
        != Some("mastermind.fresh_conversation_reference.v1")
    {
        return Err(invalid());
    }
    let work = obj.get("work_ref").and_then(Value::as_str).ok_or_else(invalid)?;
    if !work_valid(work) {
        return Err(invalid());
    }
    if !obj.get("root_job_id").and_then(Value::as_str).is_some_and(job_id_valid) {
        return Err(invalid());
    }
    let event = obj.get("root_event_id").ok_or_else(invalid)?;
    if !positive_int(event) {
        return Err(invalid());
    }
    for key in ["root_event_sha256", "principal_scope_sha256"] {
        if !obj.get(key).and_then(Value::as_str).is_some_and(digest_valid) {
            return Err(invalid());
        }
    }
    Ok(work)
}

/// Closed fixed-request validation for one operation name. Accepts the exact
/// per-operation key set and grammar; anything else is `REQUEST_INVALID`.
pub fn validate(operation: &str, value: &Value) -> Result<(), String> {
    const OPS: [&str; 10] = [
        "preview",
        "create",
        "status",
        "read",
        "consume",
        "turn",
        "turn_status",
        "turn_read",
        "consume_status",
        "turn_preview",
    ];
    let invalid = || REQUEST_INVALID.to_owned();
    if !OPS.contains(&operation) {
        return Err(invalid());
    }
    let obj = value.as_object().ok_or_else(invalid)?;
    let reference_mode = obj.contains_key("reference");
    if reference_mode && !matches!(operation, "consume" | "turn" | "turn_status" | "turn_read" | "consume_status" | "turn_preview") {
        return Err(invalid());
    }
    let mut keys: Vec<&str> =
        vec!["work_ref", if reference_mode { "reference" } else { "operation_key" }];
    if matches!(operation, "preview" | "create" | "turn" | "turn_preview") {
        keys.push("message");
    }
    if matches!(operation, "consume" | "turn" | "consume_status" | "turn_preview") {
        keys.push("initial_digest");
    }
    if matches!(operation, "turn" | "turn_status" | "turn_read" | "turn_preview") {
        keys.push("turn_key");
    }
    if operation == "create" || (operation == "turn" && obj.contains_key("preview_digest")) {
        keys.push("preview_digest");
    }
    if obj.len() != keys.len() || keys.iter().any(|k| !obj.contains_key(*k)) {
        return Err(invalid());
    }
    let work = obj.get("work_ref").and_then(Value::as_str).ok_or_else(invalid)?;
    if !work_valid(work) {
        return Err(invalid());
    }
    if !reference_mode {
        if !obj.get("operation_key").and_then(Value::as_str).is_some_and(key_valid) {
            return Err(invalid());
        }
    } else {
        let reference_work = reference_valid(obj.get("reference").ok_or_else(invalid)?)?;
        if reference_work != work {
            return Err(invalid());
        }
    }
    if keys.contains(&"turn_key")
        && !obj.get("turn_key").and_then(Value::as_str).is_some_and(key_valid)
    {
        return Err(invalid());
    }
    if keys.contains(&"initial_digest")
        && !obj.get("initial_digest").and_then(Value::as_str).is_some_and(digest_valid)
    {
        return Err(invalid());
    }
    if keys.contains(&"message")
        && !obj.get("message").and_then(Value::as_str).is_some_and(message_valid)
    {
        return Err(invalid());
    }
    if keys.contains(&"preview_digest")
        && !obj.get("preview_digest").and_then(Value::as_str).is_some_and(digest_valid)
    {
        return Err(invalid());
    }
    Ok(())
}


pub const NATIVE_REQUEST_CAP: usize = 512 * 1024;
pub const NATIVE_RESPONSE_CAP: usize = 32 * 1024;
const NATIVE_ROUTES: [(&str, &str); 17] = [
    ("/os/executive/conversation/v2/preview", "preview"),
    ("/os/executive/conversation/v2/create", "create"),
    ("/os/executive/conversation/v2/status", "status"),
    ("/os/executive/conversation/v2/read", "read"),
    ("/os/executive/conversation/v2/recover", "recover"),
    ("/os/executive/conversation/v2/consume", "consume"),
    ("/os/executive/conversation/v2/consume/status", "consume_status"),
    ("/os/executive/conversation/v2/turn/preview", "turn_preview"),
    ("/os/executive/conversation/v2/turn", "turn"),
    ("/os/executive/conversation/v2/turn/status", "turn_status"),
    ("/os/executive/conversation/v2/turn/read", "turn_read"),
    ("/os/executive/conversation/v2/turn/recover", "turn_recover"),
    ("/os/executive/conversation/v2/resume/preview", "resume_preview"),
    ("/os/executive/conversation/v2/resume", "resume"),
    ("/os/executive/conversation/v2/resume/status", "resume_status"),
    ("/os/executive/conversation/v2/stop", "stop"),
    ("/os/executive/conversation/v2/stop/status", "stop_status"),
];

pub fn is_native_path(path: &str) -> bool {
    NATIVE_ROUTES.iter().any(|(candidate, _)| *candidate == path)
}
pub fn path_for(operation: &str, contract: Option<&str>) -> Option<&'static str> {
    match contract {
        None | Some("legacy-v1") => path(operation),
        Some("native-v2") => NATIVE_ROUTES.iter().find(|(_, o)| *o == operation).map(|(p, _)| *p),
        _ => None,
    }
}
pub fn validate_for(operation: &str, value: &Value, native: bool) -> Result<(), String> {
    if native { validate_native(operation, value) } else { validate(operation, value) }
}
fn native_message_valid(value: &str) -> bool {
    value.len() <= 128 * 1024 && !value.chars().all(py_space) && value.chars().all(|c| {
        let o = c as u32;
        !((o < 32 && !matches!(c, '\t' | '\n' | '\r')) || (127..=159).contains(&o))
    })
}
pub fn validate_native(operation: &str, value: &Value) -> Result<(), String> {
    let invalid = || REQUEST_INVALID.to_owned();
    if !NATIVE_ROUTES.iter().any(|(_, o)| *o == operation) { return Err(invalid()); }
    let obj = value.as_object().ok_or_else(invalid)?;
    let reference_mode = obj.contains_key("reference");
    if reference_mode && matches!(operation, "preview" | "create") { return Err(invalid()); }
    let mut keys = vec!["work_ref", if reference_mode { "reference" } else { "operation_key" }];
    if matches!(operation, "preview" | "create" | "turn_preview" | "turn") { keys.push("message"); }
    if matches!(operation, "consume" | "consume_status" | "turn_preview" | "turn") { keys.push("initial_digest"); }
    if matches!(operation, "turn_preview" | "turn" | "turn_status" | "turn_read" | "turn_recover") { keys.push("turn_key"); }
    if matches!(operation, "resume_preview" | "resume" | "resume_status") { keys.push("resume_key"); }
    if matches!(operation, "stop" | "stop_status") { keys.push("stop_key"); }
    if matches!(operation, "create" | "turn" | "resume") { keys.push("preview_digest"); }
    if matches!(operation, "resume_preview" | "resume") { keys.push("expected_result_digest"); }
    if operation == "stop" { keys.extend(["turn_id", "binding_digest"]); }
    if obj.len() != keys.len() || keys.iter().any(|key| !obj.contains_key(*key)) { return Err(invalid()); }
    let work = obj.get("work_ref").and_then(Value::as_str).ok_or_else(invalid)?;
    if !work_valid(work) { return Err(invalid()); }
    if reference_mode {
        if reference_valid(&obj["reference"])? != work { return Err(invalid()); }
    } else if !obj["operation_key"].as_str().is_some_and(key_valid) { return Err(invalid()); }
    for key in ["turn_key", "resume_key", "stop_key"] {
        if keys.contains(&key) && !obj[key].as_str().is_some_and(key_valid) { return Err(invalid()); }
    }
    for key in ["preview_digest", "initial_digest", "expected_result_digest", "binding_digest"] {
        if keys.contains(&key) && !obj[key].as_str().is_some_and(digest_valid) { return Err(invalid()); }
    }
    if keys.contains(&"turn_id") && !obj["turn_id"].as_str().is_some_and(job_id_valid) { return Err(invalid()); }
    if keys.contains(&"message") && !obj["message"].as_str().is_some_and(native_message_valid) { return Err(invalid()); }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn hex64(c: char) -> String {
        std::iter::repeat(c).take(64).collect()
    }

    fn reference(work: &str) -> Value {
        json!({
            "schema": "mastermind.fresh_conversation_reference.v1",
            "work_ref": work,
            "root_job_id": "JOB-root-0001",
            "root_event_id": 7,
            "root_event_sha256": hex64('a'),
            "principal_scope_sha256": hex64('b')
        })
    }

    fn accepts(operation: &str, value: Value) -> bool {
        validate(operation, &value).is_ok()
    }

    fn rejects(operation: &str, value: Value) -> bool {
        validate(operation, &value).is_err()
    }

    #[test]
    fn routes_are_closed_and_exact() {
        let ops = [
            "preview",
            "create",
            "status",
            "read",
            "consume",
            "turn",
            "turn_status",
            "turn_read",
        ];
        for op in ops {
            let route = path(op).expect("every operation maps to one literal route");
            assert_eq!(operation(route), Some(op), "route inverse must round trip");
        }
        assert_eq!(path("turn"), Some("/os/executive/conversation/turn"));
        assert_eq!(path("turn_status"), Some("/os/executive/conversation/turn/status"));
        assert_eq!(path("turn_read"), Some("/os/executive/conversation/turn/read"));
        assert_eq!(operation("/os/executive/conversation/turn"), Some("turn"));
        assert_eq!(operation("/os/executive/conversation/turn/status"), Some("turn_status"));
        assert_eq!(operation("/os/executive/conversation/turn/read"), Some("turn_read"));
        assert_eq!(operation("/os/executive/conversation/nope"), None, "unknown literal path denied");
        assert_eq!(operation("/os/executive/conversation/previewx"), None, "extended path denied");
        assert_eq!(operation("/os/executive/conversation/turn/statusx"), None, "extended turn path denied");
        assert_eq!(operation("/os/executive/conversation/PREVIEW"), None, "case-variant path denied");
        assert_eq!(operation("https://other/submit"), None, "foreign route denied");
        assert_eq!(operation(""), None, "empty path denied");
        assert_eq!(path("delete"), None, "unknown operation denied");
        assert_eq!(path("../preview"), None, "traversal operation denied");
        assert_eq!(path(""), None, "empty operation denied");
    }

    #[test]
    fn rejection_reason_is_fixed_and_generic() {
        let err = validate("delete", &json!({})).expect_err("unknown operation must reject");
        assert_eq!(err, REQUEST_INVALID, "rejection must be the fixed generic reason");
        let err = validate("preview", &json!([])).expect_err("non-object request must reject");
        assert_eq!(err, REQUEST_INVALID, "rejection must be the fixed generic reason");
        let err = validate("status", &Value::Null).expect_err("null request must reject");
        assert_eq!(err, REQUEST_INVALID, "rejection must be the fixed generic reason");
    }

    #[test]
    fn recovery_status_and_pure_turn_preflight_keep_distinct_closed_shapes() {
        let selector=json!({"work_ref":"WS:EXAMPLE","operation_key":"original","initial_digest":hex64('a')});
        assert_eq!(path("consume_status"),Some("/os/executive/conversation/consume/status"));
        assert_eq!(operation("/os/executive/conversation/turn/preview"),Some("turn_preview"));
        assert!(validate("consume_status",&selector).is_ok());
        let mut mixed=selector.clone();mixed["turn_key"]="new-key".into();
        assert!(validate("consume_status",&mixed).is_err());
        let mut preview=selector.clone();preview["turn_key"]="original-turn".into();preview["message"]="Bounded follow-up".into();
        assert!(validate("turn_preview",&preview).is_ok());
        preview["preview_digest"]=hex64('b').into();
        assert!(validate("turn_preview",&preview).is_err());
        assert!(validate("turn",&preview).is_ok());
        preview["preview_digest"]="bad".into();assert!(validate("turn",&preview).is_err());
    }

    #[test]
    fn every_operation_accepts_its_closed_shape() {
        let w = "WS:EXAMPLE";
        let k = "op-key-1";
        let m = "hello world";
        let d = || hex64('a');
        assert!(accepts("preview", json!({"work_ref": w, "operation_key": k, "message": m})), "preview original positive");
        assert!(accepts("create", json!({"work_ref": w, "operation_key": k, "message": m, "preview_digest": d()})), "create positive");
        assert!(accepts("status", json!({"work_ref": w, "operation_key": k})), "status positive");
        assert!(accepts("read", json!({"work_ref": w, "operation_key": k})), "read positive");
        assert!(accepts("consume", json!({"work_ref": w, "operation_key": k, "initial_digest": d()})), "consume original positive");
        assert!(accepts("consume", json!({"work_ref": w, "reference": reference(w), "initial_digest": d()})), "consume reference positive");
        assert!(accepts("turn", json!({"work_ref": w, "operation_key": k, "message": m, "initial_digest": d(), "turn_key": k})), "turn original positive");
        assert!(accepts("turn", json!({"work_ref": w, "reference": reference(w), "message": m, "initial_digest": d(), "turn_key": k})), "turn reference positive");
        assert!(accepts("turn_status", json!({"work_ref": w, "operation_key": k, "turn_key": k})), "turn_status original positive");
        assert!(accepts("turn_status", json!({"work_ref": w, "reference": reference(w), "turn_key": k})), "turn_status reference positive");
        assert!(accepts("turn_read", json!({"work_ref": w, "operation_key": k, "turn_key": k})), "turn_read original positive");
        assert!(accepts("turn_read", json!({"work_ref": w, "reference": reference(w), "turn_key": k})), "turn_read reference positive");
    }

    #[test]
    fn grammar_bounds_reject_one_over() {
        let w = "WS:EXAMPLE";
        let key96 = || "a".repeat(96);
        let key97 = || "a".repeat(97);
        let d = || hex64('a');
        let d_bad = || hex64('A');
        let long = || "a".repeat(700);
        let long_over = || "a".repeat(701);
        assert!(accepts("preview", json!({"work_ref": w, "operation_key": key96(), "message": long()})), "key and message upper bounds accept");
        assert!(rejects("preview", json!({"work_ref": w, "operation_key": key97(), "message": long()})), "97-byte operation key rejects");
        assert!(rejects("preview", json!({"work_ref": w, "operation_key": key96(), "message": long_over()})), "701-character message rejects");
        assert!(rejects("preview", json!({"work_ref": "WS:", "operation_key": key96(), "message": long()})), "work prefix without suffix rejects");
        assert!(accepts("preview", json!({"work_ref": "WS:a", "operation_key": key96(), "message": long()})), "shortest work reference accepts");
        let w_max = format!("WS:{}", "a".repeat(69));
        let w_over = format!("WS:{}", "a".repeat(70));
        assert!(accepts("status", json!({"work_ref": w_max, "operation_key": key96()})), "72-byte work reference accepts");
        assert!(rejects("status", json!({"work_ref": w_over, "operation_key": key96()})), "73-byte work reference rejects");
        assert!(rejects("status", json!({"work_ref": "ws:a", "operation_key": key96()})), "lowercase prefix rejects");
        assert!(rejects("status", json!({"work_ref": "WS:a:b", "operation_key": key96()})), "colon in work suffix rejects");
        assert!(rejects("status", json!({"work_ref": "WS:a/b", "operation_key": key96()})), "slash in work suffix rejects");
        assert!(rejects("status", json!({"work_ref": 5, "operation_key": key96()})), "non-string work reference rejects");
        assert!(rejects("status", json!({"work_ref": w, "operation_key": ":lead"})), "leading separator operation key rejects");
        assert!(rejects("status", json!({"work_ref": w, "operation_key": ""})), "empty operation key rejects");
        assert!(rejects("status", json!({"work_ref": w, "operation_key": 42})), "non-string operation key rejects");
        assert!(rejects("turn_status", json!({"work_ref": w, "operation_key": key96(), "turn_key": key97()})), "97-byte turn key rejects");
        assert!(rejects("consume", json!({"work_ref": w, "operation_key": key96(), "initial_digest": d()[..63].to_string()})), "63-byte digest rejects");
        assert!(rejects("consume", json!({"work_ref": w, "operation_key": key96(), "initial_digest": format!("{}x", d())})), "65-byte digest rejects");
        assert!(rejects("consume", json!({"work_ref": w, "operation_key": key96(), "initial_digest": d_bad()})), "uppercase digest rejects");
        assert!(rejects("create", json!({"work_ref": w, "operation_key": key96(), "message": long(), "preview_digest": d_bad()})), "uppercase preview digest rejects");
    }

    #[test]
    fn message_grammar_is_exact() {
        let base = json!({"work_ref": "WS:EXAMPLE", "operation_key": "op-key-1"});
        let holds = |m: Value| {
            let mut obj = base.clone();
            if let Some(map) = obj.as_object_mut() {
                map.insert("message".to_string(), m);
            }
            validate("preview", &obj)
        };
        assert!(holds(json!("ok")).is_ok(), "plain message accepts");
        assert!(holds(json!("\t\n\r ok")).is_ok(), "tab newline carriage return accept");
        assert!(holds(json!("ok \u{00a0} ok")).is_ok(), "non-breaking space inside text accepts");
        assert!(holds(json!("ok\u{2028}\u{2029}")).is_ok(), "line and paragraph separators accept");
        assert!(holds(json!("\u{1f980}")).is_ok(), "four-byte character accepts");
        assert!(holds(json!("\u{1}")).is_err(), "C0 control rejects");
        assert!(holds(json!("\u{7f}")).is_err(), "DEL rejects");
        assert!(holds(json!("\u{85}")).is_err(), "C1 rejects");
        assert!(holds(json!("\u{9f}")).is_err(), "C1 upper bound rejects");
        assert!(holds(json!("")).is_err(), "empty message rejects");
        assert!(holds(json!("   ")).is_err(), "ascii blank message rejects");
        assert!(holds(json!("\u{a0}")).is_err(), "non-breaking-space-only message rejects");
        assert!(holds(json!("\u{3000}")).is_err(), "ideographic-space-only message rejects");
        assert!(holds(json!("\u{2028}\u{2029}")).is_err(), "separator-only message rejects");
        assert!(holds(json!("\u{1c}")).is_err(), "file-separator-only message rejects");
        assert!(holds(json!("a\u{1d}b")).is_err(), "group separator inside text rejects");
        assert!(holds(json!("\u{200b}")).is_ok(), "zero-width space is content, not strip whitespace");
        assert!(holds(json!(42)).is_err(), "non-string message rejects");
        assert!(holds(json!(true)).is_err(), "boolean message rejects");
        assert!(holds(json!("\u{1f980}".repeat(700))).is_ok(), "700 four-byte characters equal the 2800-byte cap and accept");
        assert!(holds(json!("\u{1f980}".repeat(701))).is_err(), "701 four-byte characters reject");
        assert!(holds(json!(format!("{}{}", "a".repeat(699), "\u{1f980}"))).is_ok(), "700 mixed-width characters accept");
    }

    #[test]
    fn reference_mode_is_closed_to_reference_operations() {
        let w = "WS:EXAMPLE";
        let k = "op-key-1";
        let d = || hex64('a');
        assert!(rejects("preview", json!({"work_ref": w, "reference": reference(w), "message": "m"})), "preview must not take a reference");
        assert!(rejects("create", json!({"work_ref": w, "reference": reference(w), "message": "m", "preview_digest": d()})), "create must not take a reference");
        assert!(rejects("status", json!({"work_ref": w, "reference": reference(w)})), "status must not take a reference");
        assert!(rejects("read", json!({"work_ref": w, "reference": reference(w)})), "read must not take a reference");
        assert!(rejects("consume", json!({"work_ref": w, "reference": reference(w), "operation_key": k, "initial_digest": d()})), "reference and operation key are mutually exclusive");
        assert!(rejects("consume", json!({"work_ref": w, "initial_digest": d()})), "consume without any selector rejects");
        assert!(rejects("turn_status", json!({"work_ref": w, "reference": reference("WS:OTHER"), "turn_key": k})), "foreign work reference rejects");
        assert!(rejects("turn_read", json!({"work_ref": w, "reference": reference("WS:OTHER"), "turn_key": k})), "foreign work reference on turn_read rejects");
        let mut miss = reference(w);
        if let Some(map) = miss.as_object_mut() {
            map.remove("root_event_id");
        }
        assert!(rejects("turn_status", json!({"work_ref": w, "reference": miss, "turn_key": k})), "reference missing a field rejects");
        let mut extra = reference(w);
        if let Some(map) = extra.as_object_mut() {
            map.insert("job_id".to_string(), json!("JOB-extra"));
        }
        assert!(rejects("turn_status", json!({"work_ref": w, "reference": extra, "turn_key": k})), "reference with an extra field rejects");
        let mut schema = reference(w);
        if let Some(map) = schema.as_object_mut() {
            map.insert("schema".to_string(), json!("mastermind.other.v1"));
        }
        assert!(rejects("turn_status", json!({"work_ref": w, "reference": schema, "turn_key": k})), "reference with wrong schema rejects");
        let mut event = reference(w);
        if let Some(map) = event.as_object_mut() {
            map.insert("root_event_id".to_string(), json!(0));
        }
        assert!(rejects("turn_status", json!({"work_ref": w, "reference": event, "turn_key": k})), "zero root event id rejects");
        let mut bool_event = reference(w);
        if let Some(map) = bool_event.as_object_mut() {
            map.insert("root_event_id".to_string(), json!(true));
        }
        assert!(rejects("turn_status", json!({"work_ref": w, "reference": bool_event, "turn_key": k})), "boolean root event id rejects");
        let mut float_event = reference(w);
        if let Some(map) = float_event.as_object_mut() {
            map.insert("root_event_id".to_string(), json!(7.0));
        }
        assert!(rejects("turn_status", json!({"work_ref": w, "reference": float_event, "turn_key": k})), "float root event id rejects");
        let mut hexes = reference(w);
        if let Some(map) = hexes.as_object_mut() {
            map.insert("root_event_sha256".to_string(), json!(hex64('A')));
        }
        assert!(rejects("turn_status", json!({"work_ref": w, "reference": hexes, "turn_key": k})), "uppercase reference digest rejects");
        let mut job = reference(w);
        if let Some(map) = job.as_object_mut() {
            map.insert("root_job_id".to_string(), json!(":lead"));
        }
        assert!(rejects("turn_status", json!({"work_ref": w, "reference": job, "turn_key": k})), "malformed root job id rejects");
        let mut job_long = reference(w);
        if let Some(map) = job_long.as_object_mut() {
            map.insert("root_job_id".to_string(), json!("a".repeat(128)));
        }
        assert!(accepts("turn_status", json!({"work_ref": w, "reference": job_long, "turn_key": k})), "128-byte root job id accepts");
        let mut job_over = reference(w);
        if let Some(map) = job_over.as_object_mut() {
            map.insert("root_job_id".to_string(), json!("a".repeat(129)));
        }
        assert!(rejects("turn_status", json!({"work_ref": w, "reference": job_over, "turn_key": k})), "129-byte root job id rejects");
        assert!(rejects("turn_status", json!({"work_ref": w, "reference": "not-an-object", "turn_key": k})), "non-object reference rejects");
        assert!(rejects("turn_status", json!({"work_ref": w, "reference": 7, "turn_key": k})), "numeric reference rejects");
    }

    #[test]
    fn per_operation_key_sets_are_exact() {
        let w = "WS:EXAMPLE";
        let k = "op-key-1";
        let m = "m";
        let d = || hex64('a');
        let r = || reference("WS:EXAMPLE");
        assert!(rejects("preview", json!({"work_ref": w, "operation_key": k})), "preview without message rejects");
        assert!(rejects("preview", json!({"work_ref": w, "operation_key": k, "message": m, "preview_digest": d()})), "preview with preview digest rejects");
        assert!(rejects("create", json!({"work_ref": w, "operation_key": k, "message": m})), "create without preview digest rejects");
        assert!(rejects("create", json!({"work_ref": w, "operation_key": k, "preview_digest": d()})), "create without message rejects");
        assert!(rejects("consume", json!({"work_ref": w, "operation_key": k})), "consume without initial digest rejects");
        assert!(rejects("turn", json!({"work_ref": w, "operation_key": k, "message": m, "initial_digest": d()})), "turn without turn key rejects");
        assert!(rejects("turn", json!({"work_ref": w, "operation_key": k, "initial_digest": d(), "turn_key": k})), "turn without message rejects");
        assert!(rejects("turn", json!({"work_ref": w, "operation_key": k, "message": m, "turn_key": k})), "turn without initial digest rejects");
        assert!(rejects("turn_status", json!({"work_ref": w, "operation_key": k})), "turn_status without turn key rejects");
        assert!(rejects("turn_status", json!({"work_ref": w, "operation_key": k, "turn_key": k, "initial_digest": d()})), "turn_status with initial digest rejects");
        assert!(rejects("turn_read", json!({"work_ref": w, "reference": r(), "turn_key": k, "message": m})), "turn_read with message rejects");
        assert!(rejects("status", json!({"work_ref": w})), "status without operation key rejects");
        assert!(rejects("status", json!({"operation_key": k})), "request without work reference rejects");
        assert!(rejects("status", json!({"work_ref": w, "operation_key": k, "extra": 1})), "extra key rejects");
        assert!(rejects("unknown-op", json!({"work_ref": w, "operation_key": k})), "unknown operation rejects");
        assert!(rejects("", json!({"work_ref": w, "operation_key": k})), "empty operation rejects");
        assert!(rejects("PREVIEW", json!({"work_ref": w, "operation_key": k, "message": m})), "case-variant operation rejects");
        assert!(rejects("status", json!("WS:EXAMPLE")), "string request rejects");
        assert!(rejects("status", json!(42)), "numeric request rejects");
        assert!(rejects("status", Value::Array(vec![json!({"work_ref": w, "operation_key": k})])), "array request rejects");
    }
}

#[cfg(test)]
mod native_tests {
    use super::*;
    use serde_json::json;
    #[test]
    fn native_message_bound_and_explicit_contract_do_not_relax_v1() {
        let input=json!({"work_ref":"WS:Original.Project","operation_key":"original-create","message":"x".repeat(131072)});
        assert!(validate_native("preview",&input).is_ok());assert!(validate("preview",&input).is_err());
        for message in ["x".repeat(131073),"😀".repeat(32769)," \n".into(),"x\0".into()] {
            let mut bad=input.clone();bad["message"]=message.into();assert!(validate_native("preview",&bad).is_err());
        }
        let mut emoji=input.clone();emoji["message"]="😀".repeat(32768).into();assert!(validate_native("preview",&emoji).is_ok());
        assert!(path_for("stop",None).is_none());assert!(path_for("stop",Some("unknown")).is_none());
        assert!(operation("/os/executive/conversation/v2/read/").is_none());
    }
    #[test]
    fn native_turn_requires_actual_preview_and_controls_keep_closed_identity() {
        let input=json!({"work_ref":"WS:Original.Project","operation_key":"original-create",
            "turn_key":"original-turn","initial_digest":"a".repeat(64),"message":"exact original"});
        assert!(validate_native("turn_preview",&input).is_ok());assert!(validate_native("turn",&input).is_err());
        let mut prepared=input.clone();prepared["preview_digest"]="b".repeat(64).into();assert!(validate_native("turn",&prepared).is_ok());
        for extra in ["permission","model","url","retry"] {
            let mut foreign=prepared.clone();foreign[extra]=true.into();assert!(validate_native("turn",&foreign).is_err());
        }
        let stop=json!({"work_ref":"WS:Original.Project","operation_key":"original-create","stop_key":"original-stop",
            "turn_id":"original-native-turn","binding_digest":"b".repeat(64)});
        assert!(validate_native("stop",&stop).is_ok());assert!(validate_native("stop_status",&stop).is_err());
    }

    #[test]
    fn signed_native_recovery_selects_only_its_existing_original_operation() {
        let fixture: Value=serde_json::from_str(include_str!("../../src/fixtures/native-fresh-recovery-owner.json")).unwrap();
        for sample in fixture["samples"].as_array().unwrap() {
            let op=sample["operation"].as_str().unwrap();
            let arguments=&sample["arguments"];
            assert!(validate_native(op,arguments).is_ok());
            assert!(path(op).is_none());
            assert_eq!(path_for(op,Some("native-v2")).unwrap(),
                format!("/os/executive/conversation/v2/{}",op.replace('_',"/")));
            for extra in ["message","preview_digest","initial_digest","binding_digest","session_id","retry"] {
                let mut changed=arguments.clone();changed[extra]="foreign".into();
                assert!(validate_native(op,&changed).is_err());
            }
            let mut changed=arguments.clone();
            if op=="turn_recover" {changed.as_object_mut().unwrap().remove("turn_key");}
            else {changed["turn_key"]="foreign".into();}
            assert!(validate_native(op,&changed).is_err());
        }
    }
}
