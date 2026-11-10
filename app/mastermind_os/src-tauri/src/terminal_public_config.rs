//! Public Terminal project-key classification only. This does not authenticate
//! a key, prove provider enrollment, or establish any Terminal user identity.
use base64::{engine::general_purpose::URL_SAFE_NO_PAD, Engine};
const PROJECT: &str = "fsldfzlxyavsuwqbceod";
const ERROR: &str = "Terminal public configuration invalid";

pub fn validate_public_key(value: &str) -> Result<(), &'static str> {
    if value.is_empty()
        || value.len() > 4096
        || !value.is_ascii()
        || value
            .bytes()
            .any(|b| b.is_ascii_whitespace() || b.is_ascii_control())
    {
        return Err(ERROR);
    }
    if let Some(suffix) = value.strip_prefix("sb_publishable_") {
        return if (16..=256).contains(&suffix.len())
            && suffix
                .bytes()
                .all(|b| b.is_ascii_alphanumeric() || b == b'_' || b == b'-')
        {
            Ok(())
        } else {
            Err(ERROR)
        };
    }
    let parts: Vec<_> = value.split('.').collect();
    if parts.len() != 3
        || parts.iter().any(|part| {
            part.is_empty()
                || !part
                    .bytes()
                    .all(|b| b.is_ascii_alphanumeric() || b == b'_' || b == b'-')
        })
    {
        return Err(ERROR);
    }
    let bytes = URL_SAFE_NO_PAD.decode(parts[1]).map_err(|_| ERROR)?;
    let claims: serde_json::Value = serde_json::from_slice(&bytes).map_err(|_| ERROR)?;
    if claims.get("role").and_then(serde_json::Value::as_str) != Some("anon")
        || claims.get("ref").and_then(serde_json::Value::as_str) != Some(PROJECT)
        || claims.get("iss").and_then(serde_json::Value::as_str) != Some("supabase")
    {
        return Err(ERROR);
    }
    Ok(())
}

#[cfg(test)]
mod terminal_public_config_tests {
    use super::*;
    fn legacy(role: &str, project: &str) -> String {
        let claims = serde_json::json!({"role":role,"ref":project,"iss":"supabase"});
        format!(
            "e30.{}.c2ln",
            URL_SAFE_NO_PAD.encode(serde_json::to_vec(&claims).unwrap())
        )
    }
    #[test]
    fn allows_public_key_syntax_without_claiming_provider_authentication() {
        assert!(validate_public_key("sb_publishable_0123456789abcdef0123456789abcdef").is_ok());
        assert!(validate_public_key(&legacy("anon", PROJECT)).is_ok());
    }
    #[test]
    fn prevents_secret_role_cross_project_or_malformed_embedding() {
        for key in [
            "sb_secret_0123456789abcdef".to_owned(),
            legacy("service_role", PROJECT),
            legacy("anon", "differentproject"),
            legacy("authenticated", PROJECT),
            "not-a-public-key".into(),
            "sb_publishable_0123456789abcdef\n".into(),
            "sb_publishable_short".into(),
        ] {
            assert_eq!(validate_public_key(&key), Err(ERROR));
        }
    }
}
