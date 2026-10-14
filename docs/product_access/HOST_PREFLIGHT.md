# Fleet browser readiness — read-only evidence

Observed during the 2026-10-09 commission. These are current read-only host observations, not BrowserResource admission, placement decisions or production acceptance. Existing Capacity/Runtime/Browser owners remain authoritative.

## Method and permissions

Protected source `control_plane/external_pool_binding.py` contains historical bounded-route evidence naming `ubuntu1` and `ubuntu2`; those records were used only for navigation, not as a current routing registry. Current local SSH configuration resolved both aliases. Each host was queried using its existing configured account with BatchMode, strict host-key checking, one connection attempt and a five-second connect deadline. No alternate identity, host-key override, credentials, cookie contents or browser profile contents were used.

Reads were limited to OS/architecture, CPU/memory, disk metadata, executable paths, Node version, package metadata, top-level Chromium cache version directory names, global MCP-package metadata and default profile-directory metadata. No package installation, browser launch, process retirement, profile mutation, production API request or live product navigation occurred. These are independent of the explicitly refused production HTTPS probe; that probe remains unexecuted.

## Host observations

| Observation | ubuntu1 | ubuntu2 |
|---|---|---|
| OS reported by host | Ubuntu 24.04.5 LTS | Ubuntu 24.04.5 LTS |
| Architecture / logical CPUs | x86_64 / 24 | x86_64 / 32 |
| MemTotal / MemAvailable, kB | 65,530,456 / 61,794,080 | 31,874,856 / 29,775,816 |
| Root filesystem usage | 39% | 20% |
| Root available, 1 KiB blocks | 806,543,728 | 716,250,128 |
| Default Node | v18.19.1 | v22.23.3 |
| Google Chrome executable/package | `/usr/bin/google-chrome`; 154.0.8037.57-1 | Not found by the selected executable/package probes |
| Chromium cache versions present | 1187, 1228, 1243; corresponding headless-shell directories | 1228, 1243; corresponding headless-shell directories |
| Global `@playwright/mcp` reported by npm | Not listed | Not listed |
| Default `~/.cache/ms-playwright-mcp` | Absent | Absent |

The first Chrome-version formatting command produced a blank value because the remote shell expanded the format variable. A corrected package-metadata query on the same host returned the version above. This was a read-command correction, not a failed installation or permission bypass.

## What these facts establish — and do not

Both configured hosts are reachable and have substantial unallocated memory/disk at the observation point. Ubuntu1 already has an observed Chrome executable. Ubuntu2 has Chromium cache artifacts, but cache presence is not a validated runnable browser or pinned release. Neither the absence of a global package nor the absence of a default profile directory proves that no owner-selected local package/custom profile exists.

No current owner-admitted BrowserResource lease, exact runtime binding, browser process identity, product-scoped origin policy, qualified Node/MCP/browser combination or persistent authenticated application profile was established. Do not choose a host or declare browser capacity available based on this table alone. The existing deployment/admission owner must provide the canonical runtime and profile paths and qualify them against the pinned Playwright MCP 0.0.79 contract before launch.

## VPS and plugin boundary

The retrieved Macro deployment tree identifies existing API/service/Caddy owners but did not establish a current authorized VPS SSH carrier for this operation. No host was guessed from a domain/IP, and an unrelated configured desktop alias was not treated as the VPS. VPS capacity and listener placement remain unverified; this program has not placed Chrome or a new daemon there.

Plugin discovery for `Mastermind Browser` returned generic third-party browser products, not a Mastermind Browser entry. Search is not an exhaustive private-plugin inventory. No third-party browser was suggested or installed as a substitute for existing resource ownership or the original permission holds. The current selected Workbench profile still exposes canary files/recipes rather than the required product/browser profile.

## Next admitted host action

Obtain the exact current Browser/Capacity owner lease and canonical runtime/profile binding for the chosen host. Qualify the pinned runtime, product-only network/file/viewport policy, isolated versus persistent mode and native image-integrity boundary; only then perform the human-approved application login/capture journey. Preserve #1259's separate denied upload and administrator installation holds. No source or SSH connectivity observation clears those gates.
