---
name: hermes-browser-files
description: Upload host files, track actual Chrome downloads, capture screenshots and export PDFs through the installed Mastermind browser plugin.
---

# Browser files and captures

Use hermes-browser to select the exact browser/tab and own its CDP attachment. Keep the selected host_ref on every call. Upload and download paths refer to the computer running Chrome. A PDF artifact is saved on the Hermes caller computer and includes artifact_host_ref and browser_host_ref; do not treat a remote path as a local file.

## Upload

Check status.upload_file_access_allowed. Chrome's per-extension **Allow access to file URLs** must be enabled for uploads. UPLOAD_FILE_ACCESS_REQUIRED is a Chrome user-permission gate; use the extension Browser controls page's Open Chrome upload permission button and ask for that exact user action. Do not bypass it with command-line flags, another browser carrier, JavaScript file injection or retries.

Locate the actual input[type=file] using locate; for hidden file inputs use include_hidden true with a precise CSS locator. This exposes the real file control without changing the application's styling. Use a fresh snapshot and upload with the observed ref and absolute files array.

The destination bridge only admits regular readable files owned by that host user within its configured upload_roots and passes validated canonical paths to Chrome. Caller-side roots do not grant remote filesystem access. Resolve paths before use; a path on another VPS or in the ChatGPT workspace is not a Mac path. Stage an authorized file through the existing file-transfer capability when needed. Do not change the roots or write to a privileged location to bypass a refusal.

    {"action":"upload","host_ref":"<observed>","browser_id":"<observed>","connection_id":"<observed>","tab_id":123,"url_fingerprint":"<from tabs or snapshot>","snapshot_id":"<fresh>","options":{"ref":"<observed n-ref>","files":["/Users/example/Downloads/document.pdf"]}}

The response lists the selected file names and sizes. This proves file selection. It does not prove that the server accepted or processed the upload. Submit through the application's intended controls when authorized and verify the server/UI result.

## Download

Enable optional downloads access from the extension settings when needed. Use download with an authorized HTTP(S) URL, a simple filename and a fresh snapshot. Track the returned download_id using downloads until state complete or interrupted. Only downloads owned by this attachment are queryable.

Do not call a started download complete. If interrupted, record the actual error. Do not retry automatically when the starting effect is unknown. Chrome's normal download protections remain in effect.

## Screenshots and PDF

capture supports full_page, jpeg/png, quality and bounded max_width/max_height. Images are returned through Hermes' native multimodal tool result. Use a focused crop or DOM evidence when a full-page capture would reveal unrelated private information.

pdf uses Chrome Page.printToPDF when the selected browser supports it. Successful output is written to the Hermes caller’s configured artifact_root with bytes, SHA-256 and host labels in the receipt. Some headed browser builds do not support printing through CDP; report the actual capability result.

Native message budgets are bounded. Large screenshots or PDFs may return SCREENSHOT_TOO_LARGE or PDF_TOO_LARGE. Reduce capture dimensions/quality or choose a smaller document. Do not claim an artifact was saved until its receipt names the real output.

Use the actual path and verification in your final response. Keep files the user needs; do not delete user downloads as cleanup.
