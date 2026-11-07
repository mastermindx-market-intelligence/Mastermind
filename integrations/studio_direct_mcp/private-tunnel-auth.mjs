#!/usr/bin/env node
// Private Studio Direct tunnel auth: injected middleware ONLY.
//
// This module deliberately does not import ./auth.mjs. Production auth mounts
// RFC 9728/8414 metadata and the DCR contract; a ChatGPT "No Auth" connector
// must see none of that, so the private tunnel ships an empty `mount()` and a
// `middleware()` that answers identity from the loopback socket alone.
//
// Identity model: the Mac user already owns Desktop Commander, so the trust
// boundary is "the peer is on this machine". That is expressed as an exact
// socket address check, never as a shared static bearer, and never from
// Forwarded / X-Forwarded-* headers (any client can set those).
//
// Every request is bound to the fixed principal `tunnel:<accountLabel>`, so
// the gateway's existing invariants hold unchanged: per-principal session
// binding (principalKeyOf), 4+4 per-session limiter, duplicate-id 409 and
// EFFECT_UNKNOWN taint.

/** Fixed OAuth client id advertised on the private listener. */
export const TUNNEL_CLIENT_ID = 'studio-private-tunnel';

/** Fixed scope carried by the tunnel principal. */
export const TUNNEL_SCOPE = 'studio.control';

/**
 * Socket addresses a peer may present. Exactly these, with no normalization:
 * anything else — including a missing address — is refused. `::ffff:127.0.0.1`
 * is the IPv4-mapped spelling Node reports when a server accepts an IPv4 peer
 * through a dual-stack socket.
 */
const LOOPBACK_REMOTE_ADDRESSES = new Set(['127.0.0.1', '::1', '::ffff:127.0.0.1']);

/**
 * Labels are operator-chosen names for one owned account, not secrets and not
 * free-form strings: they become the principal `tunnel:<label>`, which is
 * stored per session and written to logs. The pattern therefore admits only
 * DNS-safe characters, caps the length, and rejects the ':' separator,
 * whitespace, control characters and path/brace noise outright.
 */
const ACCOUNT_LABEL_PATTERN = /^[A-Za-z0-9](?:[A-Za-z0-9._-]{0,63})?$/;

/** Same server-defined JSON-RPC error range the gateway answers with. */
const TUNNEL_REJECTED_CODE = -32000;

/** Thrown for a tunnel auth configuration that would weaken the listener. */
export class TunnelAuthConfigError extends TypeError {}

function assertFixedOption(options, key, expected, describe) {
  const actual = options[key];
  if (actual === undefined || actual === null) return;
  const matches = Array.isArray(expected)
    ? Array.isArray(actual) &&
      actual.length === expected.length &&
      expected.every((v, i) => actual[i] === v)
    : actual === expected;
  if (!matches) {
    throw new TunnelAuthConfigError(
      `createTunnelAuth: ${key} is fixed for the private tunnel ` +
      `(got ${JSON.stringify(actual) ?? String(actual)}, want ${describe})`);
  }
}

/**
 * Build the auth object a dedicated `startGateway` accepts.
 *
 * @param {object} options
 * @param {string} options.accountLabel Operator label for one owned account
 *        (trimmed; 1..64 chars of [A-Za-z0-9._-], no leading/trailing '-._').
 * @param {string} [options.clientId] Must stay 'studio-private-tunnel' or be
 *        omitted: the listener has exactly one client id.
 * @param {string[]} [options.scopes] Must stay ['studio.control'] or be
 *        omitted: the tunnel never carries a narrower or wider scope.
 * @returns {{accountLabel:string, principal:string, clientId:string,
 *            scopes:string[], mount:Function, middleware:Function}}
 */
export function createTunnelAuth(options = {}) {
  if (options === null || typeof options !== 'object' || Array.isArray(options)) {
    throw new TunnelAuthConfigError('createTunnelAuth: options object required');
  }
  assertFixedOption(options, 'clientId', TUNNEL_CLIENT_ID, `'${TUNNEL_CLIENT_ID}'`);
  assertFixedOption(options, 'scopes', [TUNNEL_SCOPE], `['${TUNNEL_SCOPE}']`);

  // Trim is deliberate (operator configs pick up stray spaces); everything the
  // trim does not remove is refused rather than stripped or encoded.
  const rawLabel = options.accountLabel;
  if (typeof rawLabel !== 'string') {
    throw new TunnelAuthConfigError(
      `createTunnelAuth: accountLabel must be a nonempty string (got ${typeof rawLabel})`);
  }
  const accountLabel = rawLabel.trim();
  if (accountLabel.length === 0) {
    throw new TunnelAuthConfigError(
      'createTunnelAuth: accountLabel must be a nonempty string (got empty/whitespace)');
  }
  if (!ACCOUNT_LABEL_PATTERN.test(accountLabel)) {
    throw new TunnelAuthConfigError(
      'createTunnelAuth: accountLabel must match ' +
      `${ACCOUNT_LABEL_PATTERN.source} (got ${JSON.stringify(accountLabel)})`);
  }

  const principal = `tunnel:${accountLabel}`;

  /**
   * Empty on purpose. The gateway calls `mount(app)` only when it is a
   * function; an empty body registers no route, so the listener publishes no
   * protected-resource metadata and no authorization-server document. The
   * caller must not pass production `createAuth()` here.
   */
  function mount() {
    /* no OAuth/PRMD/DCR routes on a No Auth private listener */
  }

  /**
   * Answers identity from the socket only. Fails closed when the peer address
   * is missing (a unit-test stub, a UNIX socket, or an oddly-bound server) or
   * is anything but the exact loopback set above.
   *
   * @param {import('express').Request} req
   * @param {import('express').Response} res
   * @param {Function} next
   */
  function middleware(req, res, next) {
    const remoteAddress = req?.socket?.remoteAddress;
    if (typeof remoteAddress !== 'string' || !LOOPBACK_REMOTE_ADDRESSES.has(remoteAddress)) {
      res.status(403);
      res.setHeader('Cache-Control', 'no-store');
      res.setHeader('Content-Type', 'application/json');
      res.end(JSON.stringify({
        jsonrpc: '2.0',
        error: {
          code: TUNNEL_REJECTED_CODE,
          message: 'Private tunnel: loopback peers only',
        },
        id: null,
      }));
      return;
    }
    // Record protocol method names after parsing, without reading the stream
    // early or retaining arguments, headers, tokens, or returned contents.
    res.once?.('finish', () => {
      const method = req.body?.method;
      if (typeof method === 'string' && /^[A-Za-z_/-]{1,96}$/.test(method)) {
        process.stderr.write(JSON.stringify({ ts: new Date().toISOString(),
          event: 'private_rpc', method, status: res.statusCode }) + '\n');
      }
    });
    // Fresh object per request: the gateway derives the session principal from
    // req.auth on every call, so one request can never mutate another's.
    req.auth = Object.freeze({
      principal,
      clientId: TUNNEL_CLIENT_ID,
      scopes: Object.freeze([TUNNEL_SCOPE]),
    });
    next();
  }

  return {
    accountLabel,
    principal,
    clientId: TUNNEL_CLIENT_ID,
    scopes: [TUNNEL_SCOPE],
    mount,
    middleware,
  };
}
