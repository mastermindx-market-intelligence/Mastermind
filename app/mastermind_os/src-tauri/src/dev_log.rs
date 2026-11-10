//! Structured JSONL dev log with structural secret redaction.
//!
//! This module gives the Mastermind OS dev harness a small, dependency-free record
//! sink for request, auth-transition and native-failure events. It is deliberately
//! inert: nothing happens at module load, no file is opened until [`DevLog::open`],
//! and wiring it into the runtime is a later slice.
//!
//! Handle choice: [`DevLog`] stores only the target path and re-opens the file in
//! append mode (`O_APPEND`) for every record. The dev log is a low-frequency
//! diagnostic instrument, so the extra `open` is negligible; re-opening per write
//! avoids holding a shared mutable file handle across threads or long idle periods
//! and keeps each record a single append.
//!
//! Secret safety is structural: no record field accepts headers, tokens or subjects,
//! and every free-form string is passed through [`redact`] before serialization. The
//! redactor is intentionally conservative and over-redacts rather than risk a leak.

#![allow(dead_code)]

use std::fs::{self, OpenOptions};
use std::io::{self, Write};
use std::path::{Path, PathBuf};
use std::time::{SystemTime, UNIX_EPOCH};

use serde_json::Value;

/// Append-only JSONL log handle.
pub struct DevLog {
    path: PathBuf,
}

impl DevLog {
    /// Open (creating parent directories and the file if needed) an append-mode log.
    pub fn open(path: &Path) -> io::Result<DevLog> {
        if let Some(parent) = path.parent() {
            if !parent.as_os_str().is_empty() {
                fs::create_dir_all(parent)?;
            }
        }
        // Touch the file so creation/permission errors surface at open time.
        OpenOptions::new().create(true).append(true).open(path)?;
        Ok(DevLog {
            path: path.to_path_buf(),
        })
    }

    /// Record an outbound request outcome. `status`/`error_code` are optional.
    pub fn request(
        &self,
        method: &str,
        path: &str,
        status: Option<u16>,
        error_code: Option<&str>,
    ) -> io::Result<()> {
        let mut record = serde_json::Map::new();
        record.insert("ts".into(), Value::String(iso8601_utc_now()));
        record.insert("kind".into(), Value::String("request".into()));
        record.insert("method".into(), Value::String(redact(method)));
        record.insert("path".into(), Value::String(redact(path)));
        record.insert(
            "status".into(),
            status.map(|value| Value::from(value)).unwrap_or(Value::Null),
        );
        record.insert(
            "error_code".into(),
            error_code
                .map(|value| Value::String(redact(value)))
                .unwrap_or(Value::Null),
        );
        self.write_record(Value::Object(record))
    }

    /// Record an auth state transition. Both endpoints are redacted.
    pub fn auth_transition(&self, from: &str, to: &str) -> io::Result<()> {
        let mut record = serde_json::Map::new();
        record.insert("ts".into(), Value::String(iso8601_utc_now()));
        record.insert("kind".into(), Value::String("auth_transition".into()));
        record.insert("from".into(), Value::String(redact(from)));
        record.insert("to".into(), Value::String(redact(to)));
        self.write_record(Value::Object(record))
    }

    /// Record a native command failure with a short code. Both strings are redacted.
    pub fn native_failure(&self, command: &str, code: &str) -> io::Result<()> {
        let mut record = serde_json::Map::new();
        record.insert("ts".into(), Value::String(iso8601_utc_now()));
        record.insert("kind".into(), Value::String("native_failure".into()));
        record.insert("command".into(), Value::String(redact(command)));
        record.insert("code".into(), Value::String(redact(code)));
        self.write_record(Value::Object(record))
    }

    fn write_record(&self, value: Value) -> io::Result<()> {
        let line = serde_json::to_string(&value)
            .map_err(|err| io::Error::new(io::ErrorKind::Other, err))?;
        let mut file = OpenOptions::new()
            .create(true)
            .append(true)
            .open(&self.path)?;
        file.write_all(line.as_bytes())?;
        file.write_all(b"\n")?;
        Ok(())
    }
}

/// Conservative, over-redacting scrubber for free-form text.
///
/// Removes bearer credentials, `Authorization:` values, `"subject":"..."` values and
/// any standalone base64url/JWT-like run of 20 or more characters. Pure std.
pub fn redact(input: &str) -> String {
    let step = redact_key_value(input, b"authorization");
    let step = redact_key_value(&step, b"subject");
    let step = redact_bearer(&step);
    redact_b64_runs(&step)
}

/// Replace the value that follows `key` (`key: value`, with optional quotes) with
/// `[REDACTED]`, preserving the surrounding structure.
fn redact_key_value(input: &str, key: &[u8]) -> String {
    let bytes = input.as_bytes();
    let len = bytes.len();
    let mut out: Vec<u8> = Vec::with_capacity(len);
    let mut i = 0;
    while i < len {
        if i + key.len() <= len && bytes[i..i + key.len()].eq_ignore_ascii_case(key) {
            out.extend_from_slice(&bytes[i..i + key.len()]);
            let mut j = i + key.len();
            // Optional quote closing the key name, e.g. `"Authorization": ...`.
            if j < len && bytes[j] == b'"' {
                out.push(b'"');
                j += 1;
            }
            while j < len && (bytes[j] == b' ' || bytes[j] == b'\t') {
                out.push(bytes[j]);
                j += 1;
            }
            if j < len && bytes[j] == b':' {
                out.push(b':');
                j += 1;
                while j < len && (bytes[j] == b' ' || bytes[j] == b'\t') {
                    out.push(bytes[j]);
                    j += 1;
                }
                let quoted = j < len && bytes[j] == b'"';
                if quoted {
                    out.push(b'"');
                    j += 1;
                }
                while j < len {
                    let c = bytes[j];
                    if c == b'\n' {
                        break;
                    }
                    if quoted {
                        if c == b'"' {
                            break;
                        }
                    } else if c == b',' || c == b';' || c == b'"' {
                        break;
                    }
                    j += 1;
                }
                out.extend_from_slice(b"[REDACTED]");
                if quoted && j < len && bytes[j] == b'"' {
                    out.push(b'"');
                    j += 1;
                }
                i = j;
                continue;
            }
            i = j;
            continue;
        }
        out.push(bytes[i]);
        i += 1;
    }
    String::from_utf8(out).unwrap_or_else(|_| input.to_string())
}

/// Replace `Bearer <token>` (any case) with `[REDACTED]`, consuming the token run.
fn redact_bearer(input: &str) -> String {
    let bytes = input.as_bytes();
    let len = bytes.len();
    let key = b"bearer";
    let mut out: Vec<u8> = Vec::with_capacity(len);
    let mut i = 0;
    while i < len {
        if i + key.len() <= len && bytes[i..i + key.len()].eq_ignore_ascii_case(key) {
            out.extend_from_slice(b"[REDACTED]");
            let mut j = i + key.len();
            while j < len && (bytes[j] == b' ' || bytes[j] == b'\t') {
                j += 1;
            }
            while j < len && (is_b64url(bytes[j]) || bytes[j] == b'.') {
                j += 1;
            }
            i = j;
            continue;
        }
        out.push(bytes[i]);
        i += 1;
    }
    String::from_utf8(out).unwrap_or_else(|_| input.to_string())
}

/// Replace any standalone base64url run of 20+ bytes with `[REDACTED]`.
fn redact_b64_runs(input: &str) -> String {
    let bytes = input.as_bytes();
    let len = bytes.len();
    let mut out: Vec<u8> = Vec::with_capacity(len);
    let mut i = 0;
    while i < len {
        if is_b64url(bytes[i]) {
            let start = i;
            while i < len && is_b64url(bytes[i]) {
                i += 1;
            }
            if i - start >= 20 {
                out.extend_from_slice(b"[REDACTED]");
            } else {
                out.extend_from_slice(&bytes[start..i]);
            }
        } else {
            out.push(bytes[i]);
            i += 1;
        }
    }
    String::from_utf8(out).unwrap_or_else(|_| input.to_string())
}

fn is_b64url(byte: u8) -> bool {
    byte.is_ascii_alphanumeric() || byte == b'_' || byte == b'-'
}

/// ISO-8601 UTC timestamp at second precision, derived from `SystemTime` (no chrono).
fn iso8601_utc_now() -> String {
    let secs = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|duration| duration.as_secs())
        .unwrap_or(0);
    let days = (secs / 86_400) as i64;
    let rem = secs % 86_400;
    let (year, month, day) = civil_from_days(days);
    let hour = rem / 3_600;
    let minute = (rem % 3_600) / 60;
    let second = rem % 60;
    format!("{year:04}-{month:02}-{day:02}T{hour:02}:{minute:02}:{second:02}Z")
}

/// Days since the Unix epoch to a proleptic Gregorian civil date (Howard Hinnant's
/// `civil_from_days` algorithm).
fn civil_from_days(days_since_epoch: i64) -> (i64, u32, u32) {
    let z = days_since_epoch + 719_468;
    let era = if z >= 0 { z } else { z - 146_096 } / 146_097;
    let doe = (z - era * 146_097) as u64; // [0, 146096]
    let yoe = (doe - doe / 1_460 + doe / 36_524 - doe / 146_096) / 365; // [0, 399]
    let year = yoe as i64 + era * 400;
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100); // [0, 365]
    let mp = (5 * doy + 2) / 153; // [0, 11]
    let day = (doy - (153 * mp + 2) / 5 + 1) as u32; // [1, 31]
    let month = (if mp < 10 { mp + 3 } else { mp - 9 }) as u32;
    (if month <= 2 { year + 1 } else { year }, month, day)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;

    fn fake_token() -> (String, [String; 3]) {
        let header = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9".to_string();
        let payload =
            "eyJzdWIiOiJzeW50aGV0aWMtc3ViamVjdCIsImlzcyI6Im1tb3MtdGVzdCJ9".to_string();
        let signature = "c2lnbmF0dXJlLXN5bnRoZXRpYy1tb3MtZGV2LWxvZy0wMDE".to_string();
        let token = format!("{header}.{payload}.{signature}");
        (token, [header, payload, signature])
    }

    fn unique_temp_dir() -> PathBuf {
        let nanos = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        std::env::temp_dir().join(format!("mmos-devlog-{}-{}", std::process::id(), nanos))
    }

    #[test]
    fn civil_calendar_matches_known_dates() {
        assert_eq!(civil_from_days(0), (1970, 1, 1));
        assert_eq!(civil_from_days(1), (1970, 1, 2));
        assert_eq!(civil_from_days(19_723), (2024, 1, 1));
        assert_eq!(civil_from_days(19_783), (2024, 3, 1)); // leap year
    }

    #[test]
    fn redact_removes_all_credential_shapes() {
        let (token, segments) = fake_token();
        let subject = "synthetic subject value 0001";
        let cases = vec![
            format!("Authorization: Bearer {token}"),
            format!("bearer {token}"),
            token.clone(),
            format!("prefix {token} suffix"),
            format!("{{\"subject\":\"{subject}\"}}"),
        ];
        for case in &cases {
            let redacted = redact(case);
            assert!(
                !redacted.to_ascii_lowercase().contains("bearer "),
                "bearer leak: {redacted:?}"
            );
            assert!(!redacted.contains(&token), "token leak: {redacted:?}");
            for segment in &segments {
                assert!(
                    !redacted.contains(segment.as_str()),
                    "segment leak {segment} in {redacted:?}"
                );
            }
            assert!(
                !redacted.contains(subject),
                "subject leak: {redacted:?}"
            );
        }
        // Ordinary short text is preserved verbatim.
        assert_eq!(redact("native_failure"), "native_failure");
        assert_eq!(redact("OK"), "OK");
    }

    #[test]
    fn dev_log_writes_redacted_jsonl() {
        let dir = unique_temp_dir();
        let path = dir.join("nested").join("dev.jsonl");
        let log = DevLog::open(&path).expect("open dev log");

        let (token, segments) = fake_token();
        let subject = "synthetic subject value 0001";
        let bearer = format!("Authorization: Bearer {token}");
        let subject_json = format!("{{\"subject\":\"{subject}\"}}");

        log.request(
            "POST",
            &format!("/api/dev?access={token}"),
            Some(503),
            Some(&bearer),
        )
        .unwrap();
        log.auth_transition(&bearer, &subject_json).unwrap();
        log.native_failure(&token, &subject_json).unwrap();

        let contents = fs::read_to_string(&path).expect("read dev log");

        assert!(
            !contents.to_ascii_lowercase().contains("bearer "),
            "bearer leak: {contents:?}"
        );
        assert!(!contents.contains(&token), "token leak: {contents:?}");
        for segment in &segments {
            assert!(
                !contents.contains(segment.as_str()),
                "segment leak {segment}: {contents:?}"
            );
        }
        assert!(!contents.contains(subject), "subject leak: {contents:?}");

        let mut kinds = Vec::new();
        for line in contents.lines() {
            let value: Value = serde_json::from_str(line).expect("each line parses as JSON");
            let timestamp = value
                .get("ts")
                .and_then(Value::as_str)
                .expect("ts string");
            assert!(timestamp.ends_with('Z'), "utc timestamp: {timestamp}");
            let kind = value
                .get("kind")
                .and_then(Value::as_str)
                .expect("kind string");
            kinds.push(kind.to_string());
        }
        assert_eq!(
            kinds,
            vec![
                "request".to_string(),
                "auth_transition".to_string(),
                "native_failure".to_string()
            ]
        );

        fs::remove_dir_all(&dir).ok();
    }
}
