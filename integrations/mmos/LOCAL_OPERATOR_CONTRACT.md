# Local operator contract — L4 (Executive + app) ↔ L8 (launch harness), 2026-11-10

Agreed surface for local operator mode. L8's harness consumes 1–4; L4 implements
1–5. Changes to this file require both lanes. L8 reads it here on the trunk.

1. **Executive config block** — off unless present; absent block ⇒ no socket is
   created:
   `local_operator: {socket_path: <absolute path>, allowed_uids: [<int>, …], operator_subject: <config string>}`
2. **Socket path convention** — production:
   `/Library/Application Support/MastermindExecutive/run/local-operator.sock`;
   proof/dev runs use `<dev root>/local-operator.sock`. Parent dir 0700,
   socket 0600, socket removed on stop.
3. **App switch name** — `MM_LOCAL_OPERATOR=1` at launch enables local mode
   (unset/other ⇒ OAuth path, byte-identical to today). Optional
   `MM_LOCAL_OPERATOR_SOCKET=<absolute path>` selects the socket (default: the
   production path above); proof builds point it at the dev-root socket.
4. **Dev bundle identifier** — `com.mastermind.os.dev` for proof builds; the
   Chairman's `com.mastermind.os` install and its Keychain items stay untouched.
5. **Socket admission** — kernel peer uid ∈ `allowed_uids` only; socket requests
   are attributed to `operator_subject` for OS executive + workspace routes; no
   bearer, no header trust; the TCP listener stays byte-for-byte unchanged (the
   public tunnel must not be able to reach the socket or its privileges).
