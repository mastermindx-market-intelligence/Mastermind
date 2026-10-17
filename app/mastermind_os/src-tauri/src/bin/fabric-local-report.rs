//! Local machine-owner only. Not an OS web API, identity service, or M2 action.
//! Run on the authorized M2 Mac account: cargo run --bin fabric-local-report
#[path = "../local_fabric_owner.rs"]
mod local_fabric_owner;

fn main() {
    match local_fabric_owner::read_installed_machine_owner() {
        Ok(value) => {
            let rows = value["rows"].as_array().map_or(0, Vec::len);
            eprintln!(
                "M2 local operator · {rows} retained outcome records · NOT live fleet state or browser entitlement"
            );
            // Output contains only allowlisted metadata; never API keys,
            // prompts, output text or machine-wide activation controls.
            println!(
                "{}",
                serde_json::to_string_pretty(&value)
                    .expect("sanitized local Fabric metadata serialization")
            );
        }
        Err(code) => {
            eprintln!("{code}");
            std::process::exit(1);
        }
    }
}
