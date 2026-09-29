# Managed macOS Screen Sharing

This package makes Apple Screen Sharing safe for unattended Mastermind operations without putting Mac login passwords in model-visible commands, files, logs, or Git.

## Contract

- Fleet VNC connections use the existing authenticated SSH tunnel on loopback ports.
- A connection starts only when the exact loopback route is live and a matching VNC credential is already present in the user's login Keychain.
- Keychain checks inspect metadata only; the wrapper never reads or prints password material.
- Screen Sharing is single-flight. An unowned Screen Sharing process blocks a new managed connection instead of reusing the wrong application instance.
- Every managed connection has a PID-bound lease and expires after 30 minutes by default (maximum four hours). A credential-enrollment window is also leased and auto-closes after 15 minutes.
- The janitor closes only the PID recorded by the managed lease. It never uses global `killall`.
- A login/password prompt opened outside the wrapper is tracked and cancelled after five minutes when GUI inspection is available.
- `enroll` is the only intentional interactive credential path. It gives the human 15 minutes to enter the remote Mac password once and select **Remember password**.

## Install

Run on the controlling Mac:

```sh
ops/macos_screen_share/install.sh
```

The installer writes `~/.local/bin/mmx-screen-share` and loads the per-user LaunchAgent `com.mastermind.screen-share-janitor`.

## Usage

```sh
mmx-screen-share doctor
mmx-screen-share open mini2
mmx-screen-share status
mmx-screen-share close mini2
mmx-screen-share enroll mini3
```

Supported targets are `mini1`, `mini2`, `mini3`, `mini4`, `m1studio`, and `m2studio`.

`doctor` checks the RFB handshake, confirms that the exact VNC and SSH loopback listeners belong to the same tunnel process, verifies that tunnel configuration pins both forwards to the expected host, and compares the tunneled SSH endpoint's Ed25519 host key with an already trusted entry in `~/.ssh/known_hosts`. `open` and `enroll` enforce the same route/identity gate before Screen Sharing can launch. The wrapper does not trust-on-first-use or execute a remote command merely to identify the Mac. It also reports whether the exact VNC Keychain entry is seeded.

A missing Keychain entry is a human enrollment gate, not permission to weaken authentication or place a password in an agent prompt.
