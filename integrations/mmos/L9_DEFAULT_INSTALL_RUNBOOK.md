# L9 default-instance install runbook (principal runs this; the lane did not)

These commands install, verify and remove the `mastermind-core` module in
the **Chairman's default Paperclip instance** (`127.0.0.1:3100`). The lane
proved everything only in the isolated dev instance (`127.0.0.1:3190`); this
page is the exact sequence for the default instance, where
`x-instance-role: local_trusted` applies only if that instance runs in
local-trusted mode — otherwise authenticate as instance admin through the UI
or CLI session.

## 0. Source of the module

A checkout of this repo at the landed revision; the module is
`integrations/paperclip_plugins/mastermind-core` with a committed `dist/`.

## 1. Install

```
curl -s -X POST "http://127.0.0.1:3100/api/plugins/install" \
  -H 'content-type: application/json' -H 'x-instance-role: local_trusted' \
  -d '{"packageName":"<abs-path>/integrations/paperclip_plugins/mastermind-core","isLocalPath":true}'
```

Expect the plugin row back with `"pluginKey":"mastermind.core"`,
`"status":"ready"` within ~90s.

## 2. Verify

```
curl -s "http://127.0.0.1:3100/api/plugins" | grep -o '"pluginKey":"mastermind.core","[^"]*"' # listed, ready
curl -s "http://127.0.0.1:3100/api/plugins/<pluginId>/dashboard"   # worker running, health ready
```

In the UI: sidebar shows "Mastermind — N enrolled agents"; the page
`/<companyPrefix>/mastermind` and the dashboard widget "Roster truth" show
the four counts. Each count names its source; an unreadable source shows
"could not read <source>", never 0.

## 3. Remove

```
curl -s -X DELETE "http://127.0.0.1:3100/api/plugins/<pluginId>" -H 'x-instance-role: local_trusted'
```

Soft-uninstalls (row keeps `status:"uninstalled"`); reinstalling the same
path reactivates the same id.
