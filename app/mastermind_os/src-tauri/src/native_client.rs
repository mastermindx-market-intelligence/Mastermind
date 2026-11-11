pub const MAX_NATIVE_CLIENT_ID_BYTES: usize = 128;

pub fn validate_native_client_id(value: &str) -> Result<(), &'static str> {
    if value.is_empty() || value.len() > MAX_NATIVE_CLIENT_ID_BYTES {
        return Err("has an invalid length");
    }
    if !value
        .bytes()
        .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'_' | b'-'))
    {
        return Err("contains an invalid character");
    }
    Ok(())
}
