//! Offline byte qualification only. No network, extraction, signing or installation.
use base64::{engine::general_purpose::STANDARD, Engine};
use minisign_verify::{PublicKey, Signature};
use sha2::{Digest, Sha256};

pub fn digest(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}

pub fn verify(
    artifact: &[u8],
    public_key: &[u8],
    signature: &[u8],
    expected_artifact: &str,
    expected_key: &str,
) -> Result<(), &'static str> {
    for pin in [expected_artifact, expected_key] {
        if pin.len() != 64
            || !pin
                .bytes()
                .all(|c| c.is_ascii_digit() || (b'a'..=b'f').contains(&c))
        {
            return Err("INVALID_EXPECTED_DIGEST");
        }
    }
    if artifact.is_empty() {
        return Err("EMPTY_ARTIFACT");
    }
    if digest(artifact) != expected_artifact {
        return Err("ARTIFACT_DIGEST_MISMATCH");
    }
    let key_text = decode(public_key)?;
    if digest(key_text.as_bytes()) != expected_key {
        return Err("PUBLIC_KEY_DIGEST_MISMATCH");
    }
    let key = PublicKey::decode(&key_text).map_err(|_| "PUBLIC_KEY_INVALID")?;
    let signature_text = decode(signature)?;
    let signature = Signature::decode(&signature_text).map_err(|_| "SIGNATURE_INVALID")?;
    // Match Tauri's Minisign verification, including the authenticated trusted comment.
    // The independently supplied archive digest pins legacy signatures to exact bytes.
    key.verify(artifact, &signature, true)
        .map_err(|_| "SIGNATURE_VERIFICATION_FAILED")
}

fn decode(encoded: &[u8]) -> Result<String, &'static str> {
    if encoded.len() > 8192 {
        return Err("ENCODING_LIMIT_EXCEEDED");
    }
    let text = std::str::from_utf8(encoded).map_err(|_| "ENCODING_INVALID")?;
    let bytes = STANDARD
        .decode(text.trim())
        .map_err(|_| "ENCODING_INVALID")?;
    String::from_utf8(bytes).map_err(|_| "ENCODING_INVALID")
}

#[cfg(test)]
pub mod tests {
    use super::*;

    // Public, non-production vector from minisign-verify's documented example:
    // https://docs.rs/minisign-verify/0.3.0/minisign_verify/
    // No private key is included or generated.
    pub const KEY: &str = "untrusted comment: minisign public key\nRWQf6LRCGA9i53mlYecO4IzT51TGPpvWucNSCh1CBM0QTaLn73Y7GFO3\n";
    pub const SIGNATURE: &str = "untrusted comment: signature from minisign secret key\nRUQf6LRCGA9i559r3g7V1qNyJDApGip8MfqcadIgT9CuhV3EMhHoN1mGTkUidF/z7SrlQgXdy8ofjb7bNJJylDOocrCo8KLzZwo=\ntrusted comment: timestamp:1633700835\tfile:test\tprehashed\nwLMDjy9FLAuxZ3q4NlEvkgtyhrr0gtTu6KC4KBJdITbbOeAi1zBIYo0v4iTgt8jJpIidRJnp94ABQkJAgAooBQ==\n";

    pub fn key() -> Vec<u8> {
        STANDARD.encode(KEY).into_bytes()
    }
    pub fn signature() -> Vec<u8> {
        STANDARD.encode(SIGNATURE).into_bytes()
    }

    #[test]
    fn accepts_the_independently_published_signed_vector() {
        assert_eq!(
            verify(
                b"test",
                &key(),
                &signature(),
                &digest(b"test"),
                &digest(KEY.as_bytes())
            ),
            Ok(())
        );
    }

    #[test]
    fn rejects_tampering_even_when_the_announced_digest_is_also_changed() {
        assert_eq!(
            verify(
                b"tast",
                &key(),
                &signature(),
                &digest(b"tast"),
                &digest(KEY.as_bytes())
            ),
            Err("SIGNATURE_VERIFICATION_FAILED")
        );
    }

    fn check(
        key: &[u8],
        signature: &[u8],
        artifact_pin: &str,
        key_pin: &str,
    ) -> Result<(), &'static str> {
        verify(b"test", key, signature, artifact_pin, key_pin)
    }

    #[test]
    fn independently_pinned_artifact_and_key_are_both_required() {
        assert_eq!(
            check(
                &key(),
                &signature(),
                &"0".repeat(64),
                &digest(KEY.as_bytes())
            ),
            Err("ARTIFACT_DIGEST_MISMATCH")
        );
        assert_eq!(
            check(&key(), &signature(), &digest(b"test"), &"0".repeat(64)),
            Err("PUBLIC_KEY_DIGEST_MISMATCH")
        );
        for invalid in ["", "abc", &"G".repeat(64), &"0".repeat(63), &"0".repeat(65)] {
            assert_eq!(
                check(&key(), &signature(), invalid, &digest(KEY.as_bytes())),
                Err("INVALID_EXPECTED_DIGEST")
            );
            assert_eq!(
                check(&key(), &signature(), &digest(b"test"), invalid),
                Err("INVALID_EXPECTED_DIGEST")
            );
        }
    }

    #[test]
    fn changing_the_key_cannot_be_hidden_by_repinning_its_digest() {
        let mut packet = STANDARD.decode(KEY.lines().nth(1).unwrap()).unwrap();
        *packet.last_mut().unwrap() ^= 1;
        let altered = format!(
            "untrusted comment: minisign public key\n{}\n",
            STANDARD.encode(packet)
        );
        assert_eq!(
            check(
                STANDARD.encode(&altered).as_bytes(),
                &signature(),
                &digest(b"test"),
                &digest(altered.as_bytes())
            ),
            Err("SIGNATURE_VERIFICATION_FAILED")
        );
    }

    #[test]
    fn authenticated_comment_and_global_signature_are_verified() {
        let altered = SIGNATURE.replace("file:test", "file:another");
        assert_eq!(
            check(
                &key(),
                STANDARD.encode(altered).as_bytes(),
                &digest(b"test"),
                &digest(KEY.as_bytes())
            ),
            Err("SIGNATURE_VERIFICATION_FAILED")
        );
        let altered = SIGNATURE.replacen("wLMD", "ALMD", 1);
        assert_eq!(
            check(
                &key(),
                STANDARD.encode(altered).as_bytes(),
                &digest(b"test"),
                &digest(KEY.as_bytes())
            ),
            Err("SIGNATURE_VERIFICATION_FAILED")
        );
    }

    #[test]
    fn malformed_and_oversized_encodings_are_refused_without_echoing_data() {
        for bad in [
            b"not base64!".to_vec(),
            vec![255],
            STANDARD.encode([255]).into_bytes(),
        ] {
            assert_eq!(
                check(
                    &bad,
                    &signature(),
                    &digest(b"test"),
                    &digest(KEY.as_bytes())
                ),
                Err("ENCODING_INVALID")
            );
            assert_eq!(
                check(&key(), &bad, &digest(b"test"), &digest(KEY.as_bytes())),
                Err("ENCODING_INVALID")
            );
        }
        assert_eq!(
            check(
                &vec![b'A'; 8193],
                &signature(),
                &digest(b"test"),
                &digest(KEY.as_bytes())
            ),
            Err("ENCODING_LIMIT_EXCEEDED")
        );
        assert_eq!(
            check(
                &key(),
                &vec![b'A'; 8193],
                &digest(b"test"),
                &digest(KEY.as_bytes())
            ),
            Err("ENCODING_LIMIT_EXCEEDED")
        );
    }

    #[test]
    fn invalid_minisign_structures_are_refused() {
        assert_eq!(
            check(
                STANDARD.encode("not a public key").as_bytes(),
                &signature(),
                &digest(b"test"),
                &digest(b"not a public key")
            ),
            Err("PUBLIC_KEY_INVALID")
        );
        assert_eq!(
            check(
                &key(),
                STANDARD.encode("not a signature").as_bytes(),
                &digest(b"test"),
                &digest(KEY.as_bytes())
            ),
            Err("SIGNATURE_INVALID")
        );
    }

    #[test]
    fn outer_file_newline_is_accepted_without_changing_the_key_pin() {
        let mut k = key();
        k.push(b'\n');
        let mut s = signature();
        s.push(b'\n');
        assert_eq!(
            check(&k, &s, &digest(b"test"), &digest(KEY.as_bytes())),
            Ok(())
        );
    }

    #[test]
    fn empty_artifact_is_not_a_release_candidate() {
        assert_eq!(
            verify(
                b"",
                &key(),
                &signature(),
                &digest(b""),
                &digest(KEY.as_bytes())
            ),
            Err("EMPTY_ARTIFACT")
        );
    }
}
