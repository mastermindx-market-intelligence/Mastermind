# Slack -> Google Drive Retention Archive

## Purpose

`Mastermind Slack Archive` is a read-only retention mirror for Slack Free. One bounded run reads the Slack conversations visible to an authorized user, preserves message/thread snapshots and observed edit versions, downloads Slack-hosted files, and upserts daily JSON bundles plus file binaries into app-owned Google Drive content.

It is **not** an Executive/Agent OS truth store, lifecycle database, queue, compliance export, or Slack write bot. Google Drive is the durable retention destination for this capability only.

## Coverage and limitations

The archive uses a Slack **user OAuth token** so the same app can read all public conversations plus private channels, DMs, and group DMs that the authorizing user can access, subject to Slack scopes and workspace policy. It cannot read another member's private conversations that the authorized user cannot see.

The implementation deliberately polls instead of adding an inbound Events API/control surface. A recurring run preserves each message version it actually observes, but Slack Free does not retain an edit/deletion audit trail. An edit or deletion that happens entirely between archive sweeps cannot be reconstructed later. This is a retention backup, not a forensic/compliance archive.

Files are stored once per Slack workspace and Slack file ID under a workspace-level `files` folder. Message bundle records reference the Drive file ID and SHA-256, so sharing the same Slack file in multiple conversations does not duplicate the binary.

## Archive layout

```text
Mastermind Slack Archive/
  workspace--T.../
    files/
      F...--original-name.ext
    channel-name--C.../
      2026/
        09/
          2026-09-18.json
    dm--U...--D.../
      2026/
        09/
          2026-09-18.json
```

Daily JSON is the canonical human/machine-readable message archive. Existing records are merged, not replaced, so a message that later falls outside Slack's visible history remains in Drive.

## Slack app setup

1. In Slack app management, create an app **from manifest** using `config/slack_drive_archive_app_manifest.yaml`.
2. Inspect the preview before installation. It must request only these **user** scopes:
   - `channels:history`, `channels:read`
   - `groups:history`, `groups:read`
   - `im:history`, `im:read`
   - `mpim:history`, `mpim:read`
   - `files:read`
3. There must be no bot scopes, Slack write scopes, Events API subscriptions, Socket Mode, interactivity, slash commands, or incoming webhooks.
4. Install/authorize the app as the Slack member whose accessible history should be archived.
5. Put the resulting Slack **user token** in a local secret file and restrict the file to the owner, for example:

```sh
mkdir -p "$HOME/.mastermind/secrets"
printf '%s\n' 'xoxp-REDACTED' > "$HOME/.mastermind/secrets/slack_archive_user_token"
chmod 600 "$HOME/.mastermind/secrets/slack_archive_user_token"
```

Never commit, paste into Slack, or place the token directly in a launchd plist or command argument.

## Google Drive OAuth setup

Use a Google Cloud OAuth client controlled by the company/user account that should own the archive. Authorize only:

```text
https://www.googleapis.com/auth/drive.file
```

That scope lets this archive create and manage its own Drive files without broad read access to unrelated Drive content.

Store the refresh credentials in an owner-only JSON file:

```json
{
  "client_id": "...apps.googleusercontent.com",
  "client_secret": "...",
  "refresh_token": "...",
  "token_uri": "https://oauth2.googleapis.com/token"
}
```

Then:

```sh
chmod 600 "$HOME/.mastermind/secrets/google_drive_oauth.json"
```

The runtime refreshes access tokens in memory. It never writes OAuth tokens back to disk and never logs them.

## First backfill

Run the manifest checker first:

```sh
python3 scripts/check_slack_drive_archive_app_manifest.py \
  --manifest config/slack_drive_archive_app_manifest.yaml
```

Then run a broad first sweep:

```sh
python3 scripts/slack_drive_archive.py \
  --slack-token-file "$HOME/.mastermind/secrets/slack_archive_user_token" \
  --google-oauth-file "$HOME/.mastermind/secrets/google_drive_oauth.json" \
  --lookback-days 370
```

`370` is intentionally wider than Slack Free's normal visible-history window. The archive can only copy history that Slack actually returns to the token at execution time; it cannot resurrect data that Slack already hides or deleted.

A successful run emits one compact `mastermind.slack_drive_archive.run.v1` JSON receipt with workspace ID, Drive root folder ID, timestamps, and counts. It emits no message content or credentials.

## Recurring operation on macOS

`ops/slack_archive/com.mastermind.slack-drive-archive.plist.template` runs a 100-day overlap sweep every 15 minutes. The overlap is deliberate: it captures new replies and later-observed edits without introducing a cursor database.

Before loading it, replace:

- `__REPO_ROOT__`
- `__SECRETS_DIR__`
- `__LOG_DIR__`

Create the log directory, keep the secret files mode `0600`, validate the rendered plist with `plutil -lint`, then install it as a LaunchAgent through the existing host-management procedure. The plist contains secret **paths**, never secret values.

## Failure semantics

Slack reads are safe to retry within the bounded client. `not_in_channel` and `channel_not_found` are conversation-local and do not stop accessible conversations from being archived. `missing_scope` is a setup defect and fails the run rather than silently producing a partial archive.

Drive creates/updates are not blindly retried after an ambiguous response. The client first reconciles the exact app-owned logical key/checksum. If it cannot prove whether the write applied, it returns a `DRIVE_*_EFFECT_UNKNOWN` failure so the same Drive carrier can be reconciled before another write.

## Verification

For the first live run verify all of the following:

- receipt has `ok=true` and the expected Slack workspace ID;
- the Drive root contains one workspace folder plus a single workspace-level `files` folder;
- at least one public-channel daily bundle contains expected thread messages;
- a Slack-uploaded file opens from Drive and its bundle record has `status=ARCHIVED`;
- a second run does not create a second copy of that file;
- editing a test Slack message, waiting for the next sweep, and rerunning leaves both observed text versions in the same message record;
- no Slack messages/channels/files are modified by the app.

Do not call the capability `PROVEN_LIVE` until a real Slack token and real Google Drive OAuth credential complete this production-path check.
