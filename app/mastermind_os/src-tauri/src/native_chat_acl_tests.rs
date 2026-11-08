//! Exercise the real generated capability resolver before any application
//! handler can run. No native state, network, credentials or model effects.
use tauri::{test::{mock_builder, get_ipc_response, INVOKE_KEY}, WebviewUrl, WebviewWindowBuilder};
#[path = "../application_commands.rs"]
mod application_commands;

#[test]
fn only_the_local_main_view_can_reach_application_commands() {
    let app = mock_builder().invoke_handler(|invoke| {
        invoke.resolver.resolve("HANDLER_REACHED"); true
    }).build(crate::application_context()).expect("qualified generated context");
    let local = WebviewWindowBuilder::new(&app, "main", WebviewUrl::App("index.html".into())).build().unwrap();
    let remote = WebviewWindowBuilder::new(&app, "deepseek-chat", WebviewUrl::External("https://chat.mastermind-x.com/".parse().unwrap())).build().unwrap();
    for command in application_commands::APPLICATION_COMMANDS {
        let request = |url: &str| tauri::webview::InvokeRequest {
            cmd: (*command).into(), callback: tauri::ipc::CallbackFn(0), error: tauri::ipc::CallbackFn(1),
            url: url.parse().unwrap(), body: tauri::ipc::InvokeBody::default(),
            headers: Default::default(), invoke_key: INVOKE_KEY.to_string(),
        };
        let allowed = get_ipc_response(&local, request("tauri://localhost"))
            .expect("local main must retain its incumbent command access");
        assert_eq!(allowed.deserialize::<String>().unwrap(), "HANDLER_REACHED");
        for (view, origin) in [(&remote, "https://chat.mastermind-x.com/"),
            (&remote, "tauri://localhost"), (&local, "https://chat.mastermind-x.com/")] {
            assert!(get_ipc_response(view, request(origin)).is_err(), "remote command reached a handler: {command}");
        }
    }
    let listen = |origin: &str| tauri::webview::InvokeRequest {
        cmd: "plugin:event|listen".into(), callback: tauri::ipc::CallbackFn(0), error: tauri::ipc::CallbackFn(1),
        url: origin.parse().unwrap(),
        body: tauri::ipc::InvokeBody::Json(serde_json::json!({"event":"mastermind-auth-state","target":{"kind":"Any"},"handler":0})),
        headers: Default::default(), invoke_key: INVOKE_KEY.to_string(),
    };
    get_ipc_response(&local, listen("tauri://localhost")).expect("local event subscription proves the request and fixture are valid");
    assert!(get_ipc_response(&remote, listen("https://chat.mastermind-x.com/")).is_err(), "remote native event subscription must be denied");
}
