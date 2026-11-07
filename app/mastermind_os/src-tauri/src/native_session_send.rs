//! Closed data grammar for the incumbent Session Bridge continuation. It
//! supplies no target/identity/permission; the native Executive owner and the
//! authenticated fixed BFF independently enforce those current facts.
use serde_json::Value;
pub const PATH:&str="/os/executive/session/send";
const INVALID:&str="REQUEST_INVALID";
fn hex(s:&str,prefix:&str)->bool {s.strip_prefix(prefix).is_some_and(|v|v.len()==64&&v.bytes().all(|b|b.is_ascii_digit()||(b'a'..=b'f').contains(&b)))}
pub fn validate(arguments:&Value)->Result<(),String>{
    let o=arguments.as_object().ok_or(INVALID)?;
    if o.len()!=4 || !["target_ref","instruction","stop_condition","operation_key"].iter().all(|k|o.contains_key(*k)){return Err(INVALID.into())}
    let field=|key:&str|o.get(key).and_then(Value::as_str).ok_or(INVALID);
    if !hex(field("target_ref")?,"fabric_attempt:")||!hex(field("operation_key")?,"session-continue-"){return Err(INVALID.into())}
    for key in ["instruction","stop_condition"] {let text=field(key)?;if text.trim().is_empty()||text.chars().count()>700{return Err(INVALID.into())}}
    Ok(())
}
pub fn body(arguments:Value)->Result<Value,String>{validate(&arguments)?;Ok(serde_json::json!({"arguments":arguments}))}
#[cfg(test)]mod tests{
 use super::*;
 fn args()->Value{serde_json::json!({"target_ref":format!("fabric_attempt:{}","a".repeat(64)),"operation_key":format!("session-continue-{}","b".repeat(64)),"instruction":"Original\n  文本\t\r","stop_condition":"Exact completion\n"})}
 #[test]fn native_session_send_closed_preserves_text(){let a=args();assert_eq!(body(a.clone()).unwrap(),serde_json::json!({"arguments":a}));assert_eq!(PATH,"/os/executive/session/send")}
 #[test]fn native_session_send_scalar_bounds(){for k in ["instruction","stop_condition"]{let mut a=args();a[k]="🦀".repeat(700).into();assert!(validate(&a).is_ok());a[k]="🦀".repeat(701).into();assert_eq!(validate(&a).unwrap_err(),INVALID);for blank in [""," \r\n\t","\u{2003}"]{a[k]=blank.into();assert!(validate(&a).is_err())}}}
 #[test]fn native_session_send_exact_four_keys(){let a=args();for k in ["target_ref","instruction","stop_condition","operation_key"]{let mut v=a.clone();v.as_object_mut().unwrap().remove(k);assert!(validate(&v).is_err());for wrong in [Value::Null,serde_json::json!(1),serde_json::json!([])]{let mut v=a.clone();v[k]=wrong;assert!(validate(&v).is_err())}}for k in ["principal_scope","url","work_ref","root_job_id","permission"]{let mut v=a.clone();v[k]="private must not leak".into();assert_eq!(validate(&v).unwrap_err(),INVALID)}}
 #[test]fn native_session_send_no_implicit_or_foreign_reference(){for (k,p) in [("target_ref","fabric_attempt:"),("operation_key","session-continue-")]{for suffix in ["A".repeat(64),"a".repeat(63),format!("{}\n","a".repeat(64))]{let mut a=args();a[k]=format!("{p}{suffix}").into();assert!(validate(&a).is_err())}let mut a=args();a[k]=format!("foreign:{}","a".repeat(64)).into();assert!(validate(&a).is_err())}}
}
