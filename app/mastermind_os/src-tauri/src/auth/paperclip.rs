//! Fixed Workspace company transport. Paperclip credentials never enter the webview.
use super::{
    bounded_json, ensure_native_token, read_json_body, AppHandle, Manager, NativeAuth, Resource,
    Result, Value, ORIGIN,
};
use reqwest::Url;
use std::time::Duration;

const READ_PATH: &str = "/workspace/company/current";
const COMMAND_PATH: &str = "/workspace/company/command";
const READ_SCHEMA: &str = "mastermind.paperclip_workspace.v1";
const COMMAND_SCHEMA: &str = "mastermind.paperclip_command.v1";
const CAP: usize = 2_097_152;

fn uuid(value: &str) -> bool {
    value.len() == 36
        && value.bytes().enumerate().all(|(i, c)| {
            if [8, 13, 18, 23].contains(&i) {
                c == b'-'
            } else {
                c.is_ascii_hexdigit()
            }
        })
}
fn digest(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|c| c.is_ascii_hexdigit() && !c.is_ascii_uppercase())
}
fn target(selection: &Value) -> Result<Url> {
    let fields = selection.as_object().ok_or("REQUEST_INVALID")?;
    if fields.keys().any(|key| {
        ![
            "view",
            "itemId",
            "projectId",
            "status",
            "offset",
            "cursor",
            "requestId",
        ]
        .contains(&key.as_str())
    }) {
        return Err("REQUEST_INVALID".into());
    }
    let view = fields
        .get("view")
        .and_then(Value::as_str)
        .ok_or("REQUEST_INVALID")?;
    if ![
        "overview",
        "people",
        "projects",
        "goals",
        "work",
        "routines",
        "artifacts",
        "activity",
        "task",
        "routine",
        "runtime",
        "receipt",
    ]
    .contains(&view)
    {
        return Err("REQUEST_INVALID".into());
    }
    if ["task", "routine", "runtime"].contains(&view) != fields.contains_key("itemId")
        || (view == "receipt") != fields.contains_key("requestId")
    {
        return Err("REQUEST_INVALID".into());
    }
    for key in ["itemId", "projectId", "requestId"] {
        if fields.contains_key(key) && !fields[key].as_str().is_some_and(uuid) {
            return Err("REQUEST_INVALID".into());
        }
    }
    if fields.contains_key("projectId") && !["work", "routines", "artifacts"].contains(&view) {
        return Err("REQUEST_INVALID".into());
    }
    if let Some(status) = fields.get("status") {
        if view != "work"
            || !status.as_str().is_some_and(|s| {
                [
                    "backlog",
                    "todo",
                    "in_progress",
                    "in_review",
                    "done",
                    "blocked",
                    "cancelled",
                ]
                .contains(&s)
            })
        {
            return Err("REQUEST_INVALID".into());
        }
    }
    if let Some(offset) = fields.get("offset") {
        if !["people", "projects", "goals", "work", "routines"].contains(&view)
            || !offset.as_u64().is_some_and(|n| n <= 100_000)
        {
            return Err("REQUEST_INVALID".into());
        }
    }
    if let Some(cursor) = fields.get("cursor") {
        if view != "artifacts"
            || !cursor.as_str().is_some_and(|s| {
                !s.is_empty() && s.len() <= 2048 && !s.chars().any(char::is_control)
            })
        {
            return Err("REQUEST_INVALID".into());
        }
    }
    let mut url = Url::parse(&format!("{ORIGIN}{READ_PATH}")).map_err(|_| "REQUEST_INVALID")?;
    for (key, value) in fields {
        let text = if key == "offset" {
            value.as_u64().ok_or("REQUEST_INVALID")?.to_string()
        } else {
            value.as_str().ok_or("REQUEST_INVALID")?.to_owned()
        };
        url.query_pairs_mut().append_pair(key, &text);
    }
    Ok(url)
}
fn command_bytes(payload: &Value) -> Result<Vec<u8>> {
    let fields = payload.as_object().ok_or("REQUEST_INVALID")?;
    if ![5, 6].contains(&fields.len())
        || fields.keys().any(|key| {
            ![
                "operation",
                "requestId",
                "bindingRevision",
                "title",
                "description",
                "projectId",
            ]
            .contains(&key.as_str())
        })
    {
        return Err("REQUEST_INVALID".into());
    }
    if payload["operation"] != "create_backlog"
        || !payload["requestId"].as_str().is_some_and(uuid)
        || !payload["bindingRevision"].as_str().is_some_and(digest)
        || !payload["title"]
            .as_str()
            .is_some_and(|s| !s.trim().is_empty() && s.chars().count() <= 300 && !s.contains('\0'))
        || !payload["description"]
            .as_str()
            .is_some_and(|s| s.chars().count() <= 16000 && !s.contains('\0'))
        || fields.contains_key("projectId") && !payload["projectId"].as_str().is_some_and(uuid)
    {
        return Err("REQUEST_INVALID".into());
    }
    let bytes = serde_json::to_vec(payload).map_err(|_| "REQUEST_INVALID")?;
    if bytes.len() > 32768 {
        return Err("REQUEST_BOUND".into());
    }
    Ok(bytes)
}
async fn exchange(app: AppHandle, url: Url, payload: Option<Value>) -> Result<Value> {
    let bytes = payload.as_ref().map(command_bytes).transpose()?;
    let state = app.state::<NativeAuth>();
    let before = state.lock()?.generation;
    let (token, generation) = ensure_native_token(&app, Resource::Acquisition).await?;
    if before != generation
        || !state
            .lock()?
            .release_allowed(generation, Resource::Acquisition)
    {
        return Err("AUTHENTICATION_CHANGED".into());
    }
    let request = if let Some(body) = bytes {
        state
            .http
            .post(url)
            .header("Content-Type", "application/json")
            .body(body)
    } else {
        state.http.get(url)
    };
    let response = request
        .bearer_auth(token)
        .header("Accept", "application/json")
        .header("Cache-Control", "no-store")
        .timeout(Duration::from_secs(30))
        .send()
        .await
        .map_err(|_| "SOURCE_UNAVAILABLE")?;
    let result = if response.status().as_u16() == 503 {
        read_json_body(response, CAP).await
    } else {
        bounded_json(response, CAP).await
    };
    if !state
        .lock()?
        .release_allowed(generation, Resource::Acquisition)
    {
        return Err("AUTHENTICATION_CHANGED".into());
    }
    let value = result?;
    let schema = if payload.is_some() {
        COMMAND_SCHEMA
    } else {
        READ_SCHEMA
    };
    if value["schema"].as_str() != Some(schema) {
        return Err("RESPONSE_INVALID".into());
    }
    if let Some(original) = payload {
        if value["operation"] != original["operation"]
            || value["requestId"] != original["requestId"]
            || value["bindingRevision"] != original["bindingRevision"]
        {
            return Err("RESPONSE_INVALID".into());
        }
    }
    Ok(value)
}
#[tauri::command]
pub async fn read_company_workspace(app: AppHandle, selection: Value) -> Result<Value> {
    exchange(app, target(&selection)?, None).await
}
#[tauri::command]
pub async fn create_company_backlog(app: AppHandle, payload: Value) -> Result<Value> {
    exchange(
        app,
        Url::parse(&format!("{ORIGIN}{COMMAND_PATH}")).map_err(|_| "REQUEST_INVALID")?,
        Some(payload),
    )
    .await
}
