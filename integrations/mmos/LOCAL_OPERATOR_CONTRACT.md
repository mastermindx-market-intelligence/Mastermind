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

---

**Amendment 2026-11-10 (PROGRAM_PLAN_V3):** the native app screens are frozen;
Paperclip is the shell. The socket consumer is a Paperclip module worker process
running as the Chairman's user, not the frozen app. §1/§2/§5 are unchanged and
binding; §3/§4 now serve L8's thin-window/dev builds only — L4 builds no
app-side client code.

**Amendment 2026-11-10 (b) — production socket mode (defect fix, L4; flag to
L8).** Activation-memo verification proved §2's `0600` socket is
**unconnectable across uids in production**: file permissions gate `connect()`
before the kernel peer-uid check runs (a socket created by gateway uid 458 at
`0600` admits uid 458 only), and a `0700` parent blocks directory traversal for
the operator uid. Dev/proof runs are same-uid and never hit this. Corrected
rule, replacing the modes in §2: the socket and its parent must be
**connectable/traversable by the operator uid** (socket `0660` with a shared
group or `0666`; parent with traverse for the operator), and **admission is
enforced solely by the kernel peer-uid check** — file permissions never carry
admission authority (launchd/socket-activation discipline: connectable socket,
kernel-credential admission). Security is unchanged in substance: the peer-uid
check is unforgeable and unreachable from the TCP tunnel (different address
family); permissions only ever excluded *attempts*, and a wrong-uid attempt is
refused in-process by the check. §2's "removed on stop" and stale-socket rules
are unchanged.
