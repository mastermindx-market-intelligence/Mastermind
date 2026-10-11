#[path = "../update_signature.rs"]
mod update_signature;

use serde::Serialize;
#[cfg(unix)]
use std::os::unix::fs::{MetadataExt, OpenOptionsExt};
use std::{
    collections::BTreeMap,
    fs::OpenOptions,
    io::{Read, Write},
    path::{Path, PathBuf},
};

#[derive(Debug, Serialize)]
struct Receipt {
    schema: &'static str,
    qualification: &'static str,
    artifact_sha256: String,
    public_key_sha256: String,
    artifact_bytes: usize,
    release_authorized: bool,
    apple_qualification: bool,
    bundle_contents_verified: bool,
    installed_journey_qualified: bool,
}

fn arguments(args: impl Iterator<Item = String>) -> Result<BTreeMap<String, String>, &'static str> {
    let names = [
        "--artifact",
        "--signature",
        "--public-key",
        "--expected-artifact-sha256",
        "--expected-public-key-sha256",
        "--out",
    ];
    let mut args = args;
    let mut values = BTreeMap::new();
    while let Some(key) = args.next() {
        if !names.contains(&key.as_str()) || values.contains_key(&key) {
            return Err("INVALID_ARGUMENTS");
        }
        let value = args.next().ok_or("INVALID_ARGUMENTS")?;
        if value.is_empty() || value.starts_with("--") {
            return Err("INVALID_ARGUMENTS");
        }
        values.insert(key, value);
    }
    if values.len() != names.len() {
        return Err("INVALID_ARGUMENTS");
    }
    Ok(values)
}

fn read_bounded(path: &Path, limit: u64) -> Result<Vec<u8>, &'static str> {
    #[cfg(not(unix))]
    {
        let _ = (path, limit);
        Err("UNIX_REQUIRED")
    }
    #[cfg(unix)]
    {
        let file = OpenOptions::new()
            .read(true)
            .custom_flags(libc::O_NOFOLLOW | libc::O_NONBLOCK)
            .open(path)
            .map_err(|_| "INPUT_UNAVAILABLE")?;
        let before = file.metadata().map_err(|_| "INPUT_UNAVAILABLE")?;
        if !before.is_file() {
            return Err("REGULAR_FILE_REQUIRED");
        }
        if before.len() > limit {
            return Err("INPUT_TOO_LARGE");
        }
        let mut bytes = Vec::new();
        (&file)
            .take(limit + 1)
            .read_to_end(&mut bytes)
            .map_err(|_| "INPUT_UNAVAILABLE")?;
        if bytes.len() as u64 > limit {
            return Err("INPUT_TOO_LARGE");
        }
        let after = file.metadata().map_err(|_| "INPUT_UNAVAILABLE")?;
        let now = std::fs::symlink_metadata(path).map_err(|_| "INPUT_CHANGED")?;
        let identity = |m: &std::fs::Metadata| {
            (
                m.dev(),
                m.ino(),
                m.len(),
                m.mtime(),
                m.mtime_nsec(),
                m.ctime(),
                m.ctime_nsec(),
            )
        };
        if identity(&before) != identity(&after)
            || identity(&after) != identity(&now)
            || now.file_type().is_symlink()
        {
            return Err("INPUT_CHANGED");
        }
        Ok(bytes)
    }
}

fn run(args: BTreeMap<String, String>) -> Result<Receipt, &'static str> {
    let artifact = read_bounded(Path::new(&args["--artifact"]), 256 * 1024 * 1024)?;
    let key = read_bounded(Path::new(&args["--public-key"]), 8192)?;
    let signature = read_bounded(Path::new(&args["--signature"]), 8192)?;
    update_signature::verify(
        &artifact,
        &key,
        &signature,
        &args["--expected-artifact-sha256"],
        &args["--expected-public-key-sha256"],
    )?;
    let receipt = Receipt {
        schema: "mastermind.os_update_signature_qualification.v1",
        qualification: "ARTIFACT_SIGNATURE_AND_DIGEST_VERIFIED",
        artifact_sha256: args["--expected-artifact-sha256"].clone(),
        public_key_sha256: args["--expected-public-key-sha256"].clone(),
        artifact_bytes: artifact.len(),
        release_authorized: false,
        apple_qualification: false,
        bundle_contents_verified: false,
        installed_journey_qualified: false,
    };
    let json = serde_json::to_vec_pretty(&receipt).map_err(|_| "RECEIPT_ENCODING_FAILED")?;
    let mut output = OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(PathBuf::from(&args["--out"]))
        .map_err(|_| "RECEIPT_NOT_CREATED")?;
    output
        .write_all(&json)
        .and_then(|_| output.write_all(b"\n"))
        .and_then(|_| output.sync_all())
        .map_err(|_| "RECEIPT_WRITE_FAILED")?;
    Ok(receipt)
}

fn main() {
    let args: Vec<_> = std::env::args().skip(1).collect();
    if args == ["--help"] {
        println!("Offline Tauri update-byte verification. Required: --artifact PATH --signature PATH --public-key PATH --expected-artifact-sha256 HEX --expected-public-key-sha256 HEX --out NEW_PATH. Expected digests must come from the approved release record. Does not sign, extract, install or authorize release.");
        return;
    }
    match arguments(args.into_iter()).and_then(run) {
        Ok(receipt) => println!(
            "{}",
            serde_json::to_string(&receipt).expect("fixed receipt")
        ),
        Err(code) => {
            eprintln!(
                "{}",
                serde_json::json!({"qualification":"REFUSED","code":code})
            );
            std::process::exit(1);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::atomic::{AtomicU64, Ordering};
    static SEQUENCE: AtomicU64 = AtomicU64::new(0);
    struct Fixture(PathBuf);
    impl Fixture {
        fn new() -> Self {
            let p = std::env::temp_dir().join(format!(
                "mm-update-signature-{}-{}",
                std::process::id(),
                SEQUENCE.fetch_add(1, Ordering::Relaxed)
            ));
            std::fs::create_dir(&p).unwrap();
            Self(p)
        }
        fn args(&self) -> BTreeMap<String, String> {
            std::fs::write(self.0.join("artifact"), b"test").unwrap();
            std::fs::write(self.0.join("key"), update_signature::tests::key()).unwrap();
            std::fs::write(
                self.0.join("signature"),
                update_signature::tests::signature(),
            )
            .unwrap();
            BTreeMap::from([
                (
                    "--artifact".into(),
                    self.0.join("artifact").to_str().unwrap().into(),
                ),
                (
                    "--public-key".into(),
                    self.0.join("key").to_str().unwrap().into(),
                ),
                (
                    "--signature".into(),
                    self.0.join("signature").to_str().unwrap().into(),
                ),
                (
                    "--out".into(),
                    self.0.join("receipt.json").to_str().unwrap().into(),
                ),
                (
                    "--expected-artifact-sha256".into(),
                    update_signature::digest(b"test"),
                ),
                (
                    "--expected-public-key-sha256".into(),
                    update_signature::digest(update_signature::tests::KEY.as_bytes()),
                ),
            ])
        }
    }
    impl Drop for Fixture {
        fn drop(&mut self) {
            std::fs::remove_dir_all(&self.0).unwrap();
        }
    }

    #[test]
    fn real_files_produce_only_a_bounded_non_release_receipt() {
        let f = Fixture::new();
        let args = f.args();
        let before = std::fs::read(&args["--artifact"]).unwrap();
        let receipt = run(args.clone()).unwrap();
        assert_eq!(receipt.artifact_bytes, 4);
        for name in [
            "release_authorized",
            "apple_qualification",
            "bundle_contents_verified",
            "installed_journey_qualified",
        ] {
            assert_eq!(serde_json::to_value(&receipt).unwrap()[name], false);
        }
        assert_eq!(std::fs::read(&args["--artifact"]).unwrap(), before);
        assert_eq!(run(args).unwrap_err(), "RECEIPT_NOT_CREATED");
    }

    #[test]
    fn refused_input_never_creates_a_receipt_or_changes_the_input() {
        let f = Fixture::new();
        let mut args = f.args();
        std::fs::write(&args["--artifact"], b"tast").unwrap();
        args.insert(
            "--expected-artifact-sha256".into(),
            update_signature::digest(b"tast"),
        );
        assert_eq!(run(args).unwrap_err(), "SIGNATURE_VERIFICATION_FAILED");
        assert!(!f.0.join("receipt.json").exists());
        assert_eq!(std::fs::read(f.0.join("artifact")).unwrap(), b"tast");
    }

    #[test]
    fn read_limits_and_regular_file_requirement_are_enforced() {
        let f = Fixture::new();
        let args = f.args();
        assert_eq!(
            read_bounded(Path::new(&args["--artifact"]), 3),
            Err("INPUT_TOO_LARGE")
        );
        assert_eq!(read_bounded(&f.0, 8192), Err("REGULAR_FILE_REQUIRED"));
        assert_eq!(
            read_bounded(&f.0.join("missing"), 8192),
            Err("INPUT_UNAVAILABLE")
        );
    }

    #[cfg(unix)]
    #[test]
    fn input_and_output_symlinks_do_not_follow_another_file() {
        let f = Fixture::new();
        let mut args = f.args();
        std::os::unix::fs::symlink(f.0.join("artifact"), f.0.join("link")).unwrap();
        assert_eq!(
            read_bounded(&f.0.join("link"), 8192),
            Err("INPUT_UNAVAILABLE")
        );
        std::os::unix::fs::symlink(f.0.join("artifact"), f.0.join("receipt.json")).unwrap();
        assert_eq!(run(args.clone()).unwrap_err(), "RECEIPT_NOT_CREATED");
        args.insert("--out".into(), args["--artifact"].clone());
        assert_eq!(run(args).unwrap_err(), "RECEIPT_NOT_CREATED");
        assert_eq!(std::fs::read(f.0.join("artifact")).unwrap(), b"test");
    }

    #[test]
    fn incomplete_unknown_or_duplicate_cli_arguments_are_refused() {
        for args in [
            vec![],
            vec!["--artifact"],
            vec!["--unknown", "a"],
            vec!["--artifact", "a", "--artifact", "b"],
            vec!["--artifact", "--signature"],
        ] {
            assert_eq!(
                arguments(args.into_iter().map(String::from)),
                Err("INVALID_ARGUMENTS")
            );
        }
    }
}
