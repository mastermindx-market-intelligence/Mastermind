# T1W — native Mastermind window on T3

2026-11-10; lane branch `t3/mmos-v4-t1w`. Evidence: `~/.mastermind/mmos_evidence/t1w-20261110/`.
The dev window paired to an isolated T3 0.1.7 server, retained sign-in across app restart, and sent one real turn with a model reply. Two-view propagation and native-open server-restart persistence are **NOT DONE**.

## Reproduce (dev only)

```sh
# Run from the lane checkout. First initialization only, with the Capacity
# Fabric route variables already present in this shell (never printed):
export MMOS_T3_DEV_ROOT="$HOME/.mastermind/mmos-dev/t3-w" MMOS_T3_DEV_PORT=3796
MMOS_T3_DEV_MODEL=glm-5.3-flash python3 - <<'PY'
import os, sys
sys.path.insert(0, "tools/mmos_dev/t3")
import seed_dev_home as seed
seed.DEV_ROOT = os.environ["MMOS_T3_DEV_ROOT"]
raise SystemExit(seed.main())
PY
# For an already seeded home, skip initialization; start reuses its 0600 fabric.env.
 tools/mmos_dev/t3_dev.sh selftest
 tools/mmos_dev/t3_dev.sh start            # writes run/access.txt as 0600
mkdir -p "$HOME/.mastermind/mmos_dev/t1w"
python3 -I - "$MMOS_T3_DEV_ROOT/run/access.txt" \
  "$HOME/.mastermind/mmos_dev/t1w/t3-w-pairing-new.txt" <<'PY'
import os, sys
value = next(x[12:].strip() for x in open(sys.argv[1]) if x.startswith("Pairing URL:"))
with os.fdopen(os.open(sys.argv[2], os.O_WRONLY|os.O_CREAT|os.O_EXCL, 0o600), "w") as f:
    f.write(value + "\n")
PY
(umask 077; printf '%s\n' 'http://127.0.0.1:3796/' > "$HOME/.mastermind/mmos_dev/t1w/t3-w-base-url.txt")
APP="/Volumes/Mastermind/build-cache/t3-t1w-cargo-target/debug/bundle/macos/Mastermind OS Dev.app/Contents/MacOS/mastermind-os"
MM_SHELL_URL_FILE="$HOME/.mastermind/mmos_dev/t1w/t3-w-pairing-new.txt" \
  MMOS_DEV_ROOT="$HOME/.mastermind/mmos_dev" "$APP"
# After pairing, later launches use only the credential-free base URL:
MM_SHELL_URL_FILE="$HOME/.mastermind/mmos_dev/t1w/t3-w-base-url.txt" \
  MMOS_DEV_ROOT="$HOME/.mastermind/mmos_dev" "$APP"
# Stop only this lane: tools/mmos_dev/t3_dev.sh stop
```

`MM_SHELL_URL_FILE` is preferred to `MM_SHELL_URL`: its sole line is the URL, and the one-time fragment never enters argv or the process environment. The loader requires a user-owned regular file, exact mode 0600, and no symlinks; it accepts only HTTP on exact/normalized `127.0.0.1` or `localhost`, rejects userinfo, and logs fixed input-free refusal codes. A set-but-refused file does not fall through to the legacy variable. Tests cover missing/wrong-owner/wrong-mode/non-regular/invalid files and no-echo logging. Remote pages receive no native IPC because no capability grants a remote context.

## Persistence and real turn

- App restart: **PASS**. A fresh process using only the credential-free base URL opened the signed-in client, not `/pair`.
- Server restart with native window open: **NOT DONE**. Two attempts stopped before restart because the composer/draft could not be observed during accessibility-tree rebuilds. Do not count the later browser-pairing restart as this proof.
- Native turn: **PASS**. Real keyboard typing and Enter produced one user message and one assistant reply; server projection showed exactly one thread, two messages, one provider turn, and one provider session. A second native turn on a new thread also succeeded.
- Answer text arrived in one block at turn end on stock 0.1.7/claudeAgent. T1s owns streaming; this is not a T1W failure.
- Dev cookie/store: `~/Library/HTTPStorages/com.mastermind.os.dev.binarycookies` and `~/Library/WebKit/com.mastermind.os.dev/WebsiteData`. Bundle `com.mastermind.os.dev` is separate from installed `com.mastermind.os`.

## Keyboard observations

| Action | Result | Observation |
|---|---|---|
| Typing | Works | Real accessibility keystrokes reached the composer; server recorded exact sent text |
| Enter | Works | Sent one turn; read-only server projection confirmed no duplicate |
| Shift+Enter | Not proven | Issued during a keyboard attempt, but textarea readback returned `NO_TEXTAREA` |
| Cmd+A/C/V | Not proven | Issued; no reliable value/clipboard readback, so no success claim |
| Cmd+R | Not proven | Issued on a blank direct-thread window; only shell chrome appeared |
| Cmd+W | Closes process | In ordinary non-shell mode, window/process exited with code 0 |
| Cmd+Q | Works in shell mode | Issued to the dev bundle during cleanup; exact process was gone |

## Two views

A separately paired isolated Chromium reached the native-created second thread, but the native window never displayed that same thread; a shared browser/native thread view was not established. **Live propagation was not tested**, so `TWO VIEWS=neither`: the one native-to-browser send attempt on the first thread failed at AppleScript parsing before typing, and the earlier two-native-process/direct-thread launches rendered blank. That failed attempt added no messages and no provider session. Frames were not pursued; browser plus native window is the intended comparison. A successful second view still needs live propagation, cookie/focus observations, and a provider-session count.

## Surprises and limits

- **Pairing tokens are accessibility-readable on the pairing page.** The page places the one-time fragment into a text field. Pair only from a 0600 file at launch; never take an accessibility dump or image on that page.
- A pairing token minted about 1h37m earlier was rejected; pair promptly after the dev-server start. Tokens rotate on server restart, while an existing session cookie is expected to persist.
- Direct-thread launches and in-window thread opens sometimes rendered blank; the base URL reliably reached the signed-in client. React accessibility trees intermittently became empty or timed out.
- Ordinary non-shell mode still rendered the Mastermind frontend with both shell settings unset. Gate/no-remote-IPC tests passed; full crate: 323 passed, 0 failed, 8 ignored; frontend typecheck passed. Vitest not run (no frontend files changed).
- Evidence contains no credentials. Three later captures show only the dev window; the earlier `s1_window_loaded_classic.png` is not used as proof.

## Principal pairing, not performed here

Use the separate Mastermind-owned team server in `PROGRAM_PLAN_V4.md` section 11 and `T6_TEAM_SERVER.md`, never the Chairman's T3 Code app. On the same Mac, read the team server's current 0600 `~/.mastermind/t3-team/run/access.txt`, copy only its `Pairing URL:` value without printing it into a new user-owned 0600 one-line file, and launch the intended Mastermind dev window with `MM_SHELL_URL_FILE` pointing to that file. Complete pairing immediately, then relaunch using a credential-free file containing the team server's loopback thread URL. The installed team server is `127.0.0.1:3780`; its launchd label is `com.mastermind.t3-team`. Verify the actual intended bundle and pairing state yourself; this lane did not read, pair, restart, or reconfigure that server.
