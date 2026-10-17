//! M2-local machine-owner *retained history*, never the public Workspace reader.
//! Only explicit NativeAuth-acquired desktop commands may invoke this function.
//! The machine-owner ledger is not a per-principal user grant or current fleet.
use serde_json::{json, Value};
use std::fs::{File, OpenOptions};
use std::io::{Read, Seek, SeekFrom};
use std::os::unix::fs::{MetadataExt, OpenOptionsExt};
use std::path::{Path, PathBuf};
use std::time::{SystemTime, UNIX_EPOCH};

const ACCOUNT: &str = "fabric-c3-570f6f34";
const PROFILE_REL: &str = ".local/share/studio-direct-mcp/private/fabric-c3-570f6f34/config.json";
const LEDGER_REL: &str = ".claude/projects/-Users-chriswong-Documents-Cluade-Macro-Dashboard/handoff_kits/meta-ceo-b-2026-09-08/orch/fabric/ledger.jsonl";
const MAX_PROFILE_BYTES: u64 = 8192;
const MAX_LEDGER_TAIL_BYTES: u64 = 262_144;
const MAX_LINE_BYTES: usize = 8192;
const MAX_RUN_ROWS: usize = 32;

fn refuse() -> String {
    "LOCAL_FABRIC_OWNER_UNAVAILABLE".to_owned()
}

/// No WebView-supplied path, query, PID, account, provider or tool selector.
fn owned_file(path: &Path, uid: u32) -> Result<File, String> {
    let file = OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_NOFOLLOW | libc::O_CLOEXEC)
        .open(path)
        .map_err(|_| refuse())?;
    let meta = file.metadata().map_err(|_| refuse())?;
    if !meta.file_type().is_file() || meta.uid() != uid || meta.nlink() != 1 {
        return Err(refuse());
    }
    Ok(file)
}

fn fixed_profile(path: &Path, uid: u32) -> Result<(), String> {
    let mut file = owned_file(path, uid)?;
    if file.metadata().map_err(|_| refuse())?.len() > MAX_PROFILE_BYTES {
        return Err(refuse());
    }
    let mut raw = Vec::new();
    file.read_to_end(&mut raw).map_err(|_| refuse())?;
    let profile: Value = serde_json::from_slice(&raw).map_err(|_| refuse())?;
    // The existing installed C3 profile is the machine owner's service.
    // Do not select another account or expose a generic M2 tool passthrough.
    if profile.get("accountLabel").and_then(Value::as_str) != Some(ACCOUNT)
        || profile.get("fabricOnly").and_then(Value::as_bool) != Some(true)
        || profile.get("modernFabricProtocol").and_then(Value::as_bool) != Some(true)
        || profile.get("host").and_then(Value::as_str) != Some("127.0.0.1")
        || profile.get("port").and_then(Value::as_u64) != Some(45280)
        || profile.get("testMode").and_then(Value::as_bool) != Some(false)
        || profile.get("gitPublish").and_then(Value::as_bool) != Some(false)
        || profile.get("paperDesign").and_then(Value::as_bool) != Some(false)
    {
        return Err(refuse());
    }
    Ok(())
}

fn safe_id(value: Option<&Value>) -> Option<String> {
    let s = value?.as_str()?;
    if s.is_empty()
        || s.len() > 128
        || !s.bytes().enumerate().all(|(i, b)| {
            b.is_ascii_alphanumeric() || (i > 0 && matches!(b, b'_' | b'.' | b':' | b'-'))
        })
    {
        return None;
    }
    Some(s.to_owned())
}

fn safe_label(value: Option<&Value>, max: usize) -> Option<String> {
    let s = value?.as_str()?;
    if s.is_empty()
        || s.len() > max
        || !s
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || matches!(b, b'_' | b'.' | b':' | b'-' | b' '))
    {
        return None;
    }
    Some(s.to_owned())
}

/// Only metadata fields explicitly safe for a locally signed-in machine owner.
/// Never expose ledger key, task text, raw stdout, billing, tokens or acceptance.
fn project_record(raw: &Value) -> Option<Value> {
    let o = raw.as_object()?;
    let run_id = safe_id(o.get("run_id"))?;
    let rc = o
        .get("rc")
        .and_then(Value::as_i64)
        .filter(|v| (-1024..=1024).contains(v));
    let timestamp = o
        .get("ts")
        .and_then(Value::as_u64)
        .filter(|v| *v > 1_600_000_000 && *v < 5_000_000_000);
    Some(json!({
        "run_id": run_id,
        "root_id": safe_id(o.get("root_id")),
        "parent_run_id": safe_id(o.get("parent_run_id")),
        "pool": safe_label(o.get("pool"), 32),
        "model": safe_label(o.get("model"), 80),
        "signal": safe_label(o.get("signal"), 32),
        "rc": rc,
        "recorded_at_unix_s": timestamp
    }))
}

fn retained_rows_from_tail(data: &[u8], partial_first_line: bool) -> Vec<Value> {
    let mut lines = data.split(|b| *b == b'\n');
    if partial_first_line {
        lines.next();
    }
    let mut visible = Vec::new();
    let mut candidate = Vec::new();
    for l in lines {
        if l.len() > MAX_LINE_BYTES || l.is_empty() {
            continue;
        }
        if let Ok(raw) = serde_json::from_slice::<Value>(l) {
            if let Some(record) = project_record(&raw) {
                candidate.push(record);
            }
        }
    }
    let mut seen = std::collections::HashSet::new();
    for value in candidate.into_iter().rev() {
        let Some(id) = value.get("run_id").and_then(Value::as_str) else {
            continue;
        };
        if !seen.insert(id.to_owned()) {
            continue;
        }
        visible.push(value);
        if visible.len() == MAX_RUN_ROWS {
            break;
        }
    }
    visible
}

fn owned_snapshot(
    profile: &Path,
    ledger: &Path,
    uid: u32,
    observed_at: u64,
) -> Result<Value, String> {
    fixed_profile(profile, uid)?;
    let mut file = owned_file(ledger, uid)?;
    let first = file.metadata().map_err(|_| refuse())?;
    let start = first.len().saturating_sub(MAX_LEDGER_TAIL_BYTES);
    file.seek(SeekFrom::Start(start)).map_err(|_| refuse())?;
    let mut bytes = Vec::with_capacity((first.len() - start) as usize);
    file.take(MAX_LEDGER_TAIL_BYTES + 1)
        .read_to_end(&mut bytes)
        .map_err(|_| refuse())?;
    let after = owned_file(ledger, uid)?.metadata().map_err(|_| refuse())?;
    if after.len() != first.len()
        || after.ino() != first.ino()
        || after.dev() != first.dev()
        || after.mtime() != first.mtime()
        || after.mtime_nsec() != first.mtime_nsec()
        || bytes.len() != (first.len() - start) as usize
    {
        return Err("LOCAL_FABRIC_SOURCE_CHANGED".into());
    }
    let rows = retained_rows_from_tail(&bytes, start > 0);
    Ok(json!({
        "schema": "mastermind.local_fabric_owner_runs.v1",
        "scope": "LOCAL_MACHINE_OWNER",
        "basis": "RETAINED_LEDGER_OUTCOMES_ONLY",
        "observed_at_unix_s": observed_at,
        "coverage": {
            "machine_wide_fleet_complete": false,
            "source_records_complete": start == 0,
            "file_tail_bytes": bytes.len(),
            "total_records": null,
            "active_workers": null
        },
        "rows": rows
    }))
}

pub fn read_installed_machine_owner() -> Result<Value, String> {
    if !cfg!(target_os = "macos") {
        return Err(refuse());
    }
    let home = PathBuf::from(std::env::var_os("HOME").ok_or_else(refuse)?);
    let uid = unsafe { libc::geteuid() };
    if uid == 0 {
        return Err(refuse());
    }
    let timestamp = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map_err(|_| refuse())?
        .as_secs();
    owned_snapshot(
        &home.join(PROFILE_REL),
        &home.join(LEDGER_REL),
        uid,
        timestamp,
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn projection_refuses_secret_fields_and_false_acceptance() {
        let original = json!({
            "run_id":"run-1", "root_id":"root-1", "parent_run_id":"root-1",
            "pool":"glm", "model":"glm-5.3-flash", "rc":0, "signal":"ok", "ts":1792243499,
            "key":"VERY_PRIVATE", "accepted_by":"owner", "prompt":"SECRET", "tokens":12345
        });
        let clean = project_record(&original).unwrap();
        assert_eq!(clean["run_id"], "run-1");
        assert_eq!(clean["rc"], 0);
        let wire = clean.to_string();
        for secret in ["VERY_PRIVATE", "accepted_by", "SECRET", "prompt", "tokens"] {
            assert!(!wire.contains(secret), "{secret}");
        }
        assert!(clean.get("accepted").is_none());
        assert!(clean.get("state").is_none());
    }

    #[test]
    fn malformed_or_html_identifiers_never_leave_native_side() {
        assert!(project_record(&json!({"run_id":"<script>","rc":0})).is_none());
        assert!(project_record(&json!({"run_id":"x".repeat(129)})).is_none());
        let label =
            project_record(&json!({"run_id":"ok","model":"<img onerror=alert(1)>"})).unwrap();
        assert!(label["model"].is_null());
        assert!(label["root_id"].is_null());
    }

    #[test]
    fn selection_is_bounded_and_newest_first_without_claiming_live_status() {
        let input: String = (0..180).map(|i| format!(
            "{{\"run_id\":\"run-{i}\",\"root_id\":\"root-x\",\"rc\":0,\"signal\":\"ok\",\"ts\":1792244006}}\n"
        )).collect();
        let result = retained_rows_from_tail(input.as_bytes(), false);
        assert_eq!(result.len(), 32);
        assert_eq!(result[0]["run_id"], "run-179");
        assert_eq!(result[31]["run_id"], "run-148");
        assert!(result[0].get("status").is_none());
    }

    #[test]
    fn partial_first_line_and_corrupt_and_oversized_rows_are_discarded() {
        let mut bytes = b"orrupt-partial-first-line\ninvalid\n".to_vec();
        bytes.extend(vec![b'X'; MAX_LINE_BYTES + 1]);
        bytes.extend(b"\n{\"run_id\":\"kept\"}\n");
        let result = retained_rows_from_tail(&bytes, true);
        assert_eq!(result.len(), 1);
        assert_eq!(result[0]["run_id"], "kept");
    }

    #[test]
    fn repeated_controller_ledger_rows_keep_only_the_newest_record_per_run() {
        let source = b"{\"run_id\":\"same\",\"rc\":79,\"ts\":1792242000}\n{\"run_id\":\"another\",\"rc\":0,\"ts\":1792242500}\n{\"run_id\":\"same\",\"rc\":0,\"ts\":1792244000}\n";
        let rows = retained_rows_from_tail(source, false);
        assert_eq!(rows.len(), 2);
        assert_eq!(rows[0]["run_id"], "same");
        assert_eq!(rows[0]["rc"], 0);
        assert_eq!(rows[1]["run_id"], "another");
    }

    #[test]
    fn configuration_or_file_owner_failure_is_closed() {
        let nonexistent = Path::new("/not-an-existing-c3-owner-profile");
        assert!(fixed_profile(nonexistent, unsafe { libc::geteuid() }).is_err());
        assert!(owned_file(nonexistent, unsafe { libc::geteuid() }).is_err());
    }
}
