#!/opt/homebrew/bin/node
import fs from "node:fs";
import http from "node:http";
import { pathToFileURL } from "node:url";
import path from "node:path";

const LISTEN_HOST = "127.0.0.1";
const LISTEN_PORT = 8444;
const UPSTREAM_HOST = "127.0.0.1";
const UPSTREAM_PORT = 8443;
const EXECUTIVE_CONFIG =
  "/Library/Application Support/MastermindExecutive/config/executive-mcp.json";

// Pure construction is the test seam; the executable retains fixed installation paths.
export function createAdapter(installed, { requestExecutive = http.request, fetchOAuth = fetch } = {}) {
const readPolicy = installed?.policies?.read;
const cooPolicy = installed?.coo?.policy;
const COO_SCOPES = ["mastermind.executive.coo.act", "mastermind.executive.read"];
if (!readPolicy || !cooPolicy ||
    JSON.stringify(readPolicy.required_scopes) !== JSON.stringify([COO_SCOPES[1]]) ||
    JSON.stringify(cooPolicy.required_scopes) !== JSON.stringify(COO_SCOPES) ||
    readPolicy.resource !== cooPolicy.resource || readPolicy.issuer !== cooPolicy.issuer ||
    readPolicy.resource_metadata_url !== cooPolicy.resource_metadata_url) {
  throw new Error("role-correct Executive COO policy is unavailable");
}
function secureUrl(value) {
  const parsed = new URL(value);
  if (parsed.protocol !== "https:" || parsed.username || parsed.password || parsed.search || parsed.hash) {
    throw new Error("Executive policy URL is invalid");
  }
  return parsed;
}
secureUrl(readPolicy.resource);
secureUrl(readPolicy.issuer);
const UPSTREAM_COO_PATH = "/mcp/coo";
const UPSTREAM_METADATA_PATH = secureUrl(cooPolicy.resource_metadata_url).pathname;
if (!/^\/[A-Za-z0-9._/-]*$/.test(UPSTREAM_METADATA_PATH) ||
    UPSTREAM_METADATA_PATH.includes("//") || UPSTREAM_METADATA_PATH.split("/").some(x => x === "." || x === "..") ||
    ["/mcp", UPSTREAM_COO_PATH].includes(UPSTREAM_METADATA_PATH)) {
  throw new Error("Executive metadata route is invalid");
}

const CANONICAL_RESOURCE = readPolicy.resource;
const AUTH_ISSUER = readPolicy.issuer.endsWith("/")
  ? readPolicy.issuer : readPolicy.issuer + "/";
const LOCAL_ORIGIN = "http://" + LISTEN_HOST + ":" + LISTEN_PORT;
const LOCAL_RESOURCE = LOCAL_ORIGIN + "/mcp";
const METADATA_PATH = "/.well-known/oauth-protected-resource";
const AS_METADATA_PATH = "/.well-known/oauth-authorization-server";
const LOCAL_METADATA = LOCAL_ORIGIN + METADATA_PATH;
const CLIENT_CALLBACK = "http://localhost:8774/callback";
const ADAPTER_CALLBACK_PATH = "/oauth/callback";
const ADAPTER_CALLBACK = LOCAL_ORIGIN + ADAPTER_CALLBACK_PATH;
const ALLOWED_PROXY_PATHS = new Set(["/mcp", METADATA_PATH]);
const MAX_OAUTH_BODY = 128 * 1024;
const MAX_CALLBACK_VALUE = 8 * 1024;

function cleanHeaders(headers, { upstream = false } = {}) {
  const out = { ...headers };
  for (const name of ["connection", "keep-alive", "proxy-authenticate",
                      "proxy-authorization", "te", "trailer",
                      "transfer-encoding", "upgrade"]) {
    delete out[name];
  }
  if (upstream) out.host = UPSTREAM_HOST + ":" + UPSTREAM_PORT;
  return out;
}

function rewriteChallenge(value) {
  if (Array.isArray(value)) return value.map(rewriteChallenge);
  if (typeof value !== "string") return value;
  const scopeFields = [...value.matchAll(/(?:^|[,\s])scope="([^"]*)"/gi)];
  if (scopeFields.length > 1 || scopeFields.some(match =>
      match[1].split(" ").some(scope => !COO_SCOPES.includes(scope)))) {
    throw new Error("upstream role challenge refused");
  }
  if (/resource_metadata="[^"]*"/i.test(value)) {
    return value.replace(/resource_metadata="[^"]*"/i,
      'resource_metadata="' + LOCAL_METADATA + '"');
  }
  return value;
}

function sendJson(res, status, body) {
  const encoded = Buffer.from(JSON.stringify(body));
  res.writeHead(status, {
    "content-type": "application/json",
    "content-length": String(encoded.length),
    "cache-control": "no-store",
  });
  res.end(encoded);
}

async function readBody(req) {
  const chunks = [];
  let total = 0;
  for await (const chunk of req) {
    total += chunk.length;
    if (total > MAX_OAUTH_BODY) throw new Error("oauth_body_too_large");
    chunks.push(chunk);
  }
  return Buffer.concat(chunks);
}

async function authMetadata(res) {
  const target = new URL(".well-known/oauth-authorization-server", AUTH_ISSUER);
  const upstream = await fetchOAuth(target, {
    headers: { accept: "application/json" },
    redirect: "error",
  });
  if (!upstream.ok) throw new Error("auth_metadata_unavailable");
  const body = await upstream.json();
  body.issuer = LOCAL_ORIGIN;
  body.authorization_endpoint = LOCAL_ORIGIN + "/authorize";
  body.token_endpoint = LOCAL_ORIGIN + "/oauth/token";
  body.authorization_response_iss_parameter_supported = true;
  if (body.revocation_endpoint) {
    body.revocation_endpoint = LOCAL_ORIGIN + "/oauth/revoke";
  }
  delete body.registration_endpoint;
  delete body.client_id_metadata_document_supported;
  sendJson(res, 200, body);
}

function translateResource(params) {
  const scopes = params.getAll("scope");
  if (scopes.length > 1 || (scopes.length === 1 &&
      scopes[0].split(" ").some(scope => ![...COO_SCOPES, "offline_access"].includes(scope)))) {
    throw new Error("unexpected_scope");
  }
  const resources = params.getAll("resource");
  if (resources.length) {
    if (resources.length !== 1 || resources[0] !== LOCAL_RESOURCE) {
      throw new Error("unexpected_resource");
    }
    params.set("resource", CANONICAL_RESOURCE);
  }
}

function validateClientCallback(params) {
  const callbacks = params.getAll("redirect_uri");
  if (callbacks.length > 1 || (callbacks.length === 1 && callbacks[0] !== CLIENT_CALLBACK)) {
    throw new Error("unexpected_redirect_uri");
  }
  return callbacks.length === 1;
}

function authorizeRedirect(res, parsed) {
  const params = new URLSearchParams(parsed.searchParams);
  translateResource(params);
  const hasClientCallback = validateClientCallback(params);
  if (!params.has("scope")) params.set("scope", COO_SCOPES.join(" "));
  if (hasClientCallback) params.set("redirect_uri", ADAPTER_CALLBACK);
  const target = new URL("authorize", AUTH_ISSUER);
  target.search = params.toString();
  res.writeHead(302, {
    location: target.toString(),
    "cache-control": "no-store",
  });
  res.end();
}

function callbackRedirect(res, parsed) {
  const params = new URLSearchParams(parsed.searchParams);
  const names = [...new Set(params.keys())];
  const allowedSuccess = new Set(["code", "state", "iss"]);
  const allowedError = new Set(["error", "error_description", "error_uri", "state", "iss"]);
  const isError = params.has("error");
  const allowed = isError ? allowedError : allowedSuccess;

  if (names.some(name => !allowed.has(name)) ||
      [...allowed].some(name => params.getAll(name).length > 1) ||
      params.getAll("iss").length !== 1 ||
      params.get("iss") !== AUTH_ISSUER ||
      params.getAll("state").length !== 1 ||
      !params.get("state") ||
      (isError ? (params.getAll("error").length !== 1 || !params.get("error") || params.has("code"))
               : (params.getAll("code").length !== 1 || !params.get("code")))) {
    throw new Error("invalid_authorization_response");
  }
  for (const value of params.values()) {
    if (Buffer.byteLength(value, "utf8") > MAX_CALLBACK_VALUE) {
      throw new Error("authorization_response_too_large");
    }
  }
  if (params.has("error_uri")) {
    const errorUri = secureUrl(params.get("error_uri"));
    if (errorUri.origin !== new URL(AUTH_ISSUER).origin) {
      throw new Error("foreign_error_uri");
    }
  }

  const outgoing = new URLSearchParams();
  for (const name of isError
    ? ["error", "error_description", "error_uri", "state"]
    : ["code", "state"]) {
    if (params.has(name)) outgoing.set(name, params.get(name));
  }
  outgoing.set("iss", LOCAL_ORIGIN);
  const target = new URL(CLIENT_CALLBACK);
  target.search = outgoing.toString();
  res.writeHead(302, {
    location: target.toString(),
    "cache-control": "no-store",
  });
  res.end();
}

async function proxyOAuthPost(req, res, endpoint) {
  const contentType = String(req.headers["content-type"] || "");
  if (!contentType.toLowerCase().startsWith("application/x-www-form-urlencoded")) {
    sendJson(res, 415, { error: "unsupported_media_type" });
    return;
  }
  const raw = await readBody(req);
  const params = new URLSearchParams(raw.toString("utf8"));
  translateResource(params);
  if (endpoint === "oauth/token" && params.get("grant_type") === "authorization_code") {
    try {
      if (!validateClientCallback(params)) throw new Error("missing_redirect_uri");
    } catch {
      sendJson(res, 400, { error: "invalid_token_request" });
      return;
    }
    params.set("redirect_uri", ADAPTER_CALLBACK);
  }

  const target = new URL(endpoint, AUTH_ISSUER);
  const upstream = await fetchOAuth(target, {
    method: "POST",
    headers: {
      "content-type": "application/x-www-form-urlencoded",
      accept: "application/json",
    },
    body: params.toString(),
    redirect: "manual",
  });
  const body = Buffer.from(await upstream.arrayBuffer());
  const headers = {
    "content-type": upstream.headers.get("content-type") || "application/json",
    "content-length": String(body.length),
    "cache-control": upstream.headers.get("cache-control") || "no-store",
  };
  const retryAfter = upstream.headers.get("retry-after");
  if (retryAfter) headers["retry-after"] = retryAfter;
  res.writeHead(upstream.status, headers);
  res.end(body);
}

function proxyExecutive(req, res, parsed) {
  const upstream = requestExecutive({
    host: UPSTREAM_HOST,
    port: UPSTREAM_PORT,
    method: req.method,
    path: parsed.pathname === "/mcp" ? UPSTREAM_COO_PATH : UPSTREAM_METADATA_PATH,
    headers: cleanHeaders(req.headers, { upstream: true }),
  }, (upstreamRes) => {
    const headers = cleanHeaders(upstreamRes.headers);
    if (headers["www-authenticate"]) {
      try { headers["www-authenticate"] = rewriteChallenge(headers["www-authenticate"]); }
      catch {
        sendJson(res, 502, { error: "upstream_role_refused" });
        upstreamRes.destroy(); return;
      }
    }

    if (parsed.pathname === METADATA_PATH &&
        (upstreamRes.statusCode || 500) < 300) {
      const chunks = [];
      let total = 0;
      upstreamRes.on("data", (chunk) => {
        total += chunk.length;
        if (total > MAX_OAUTH_BODY) {
          if (!res.writableEnded) sendJson(res, 502, { error: "invalid_upstream_metadata" });
          upstreamRes.destroy(); return;
        }
        chunks.push(chunk);
      });
      upstreamRes.on("error", () => {
        if (!res.writableEnded) sendJson(res, 502, { error: "invalid_upstream_metadata" });
      });
      upstreamRes.on("end", () => {
        if (res.writableEnded) return;
        try {
          const body = JSON.parse(Buffer.concat(chunks).toString("utf8"));
          if (body.resource !== CANONICAL_RESOURCE || !Array.isArray(body.scopes_supported) ||
              !COO_SCOPES.every(scope => body.scopes_supported.includes(scope))) {
            throw new Error("upstream COO metadata is unavailable");
          }
          body.resource = LOCAL_RESOURCE;
          body.authorization_servers = [LOCAL_ORIGIN];
          body.scopes_supported = [...COO_SCOPES];
          const encoded = Buffer.from(JSON.stringify(body));
          headers["content-length"] = String(encoded.length);
          delete headers["content-encoding"];
          res.writeHead(upstreamRes.statusCode || 200, headers);
          res.end(encoded);
        } catch {
          if (!res.headersSent) {
            res.writeHead(502, {"content-type":"application/json"});
          }
          res.end('{"error":"invalid_upstream_metadata"}');
        }
      });
      return;
    }

    upstreamRes.on("error", () => res.destroy());
    res.writeHead(upstreamRes.statusCode || 502, headers);
    upstreamRes.pipe(res);
  });

  upstream.on("error", () => {
    if (!res.headersSent) {
      sendJson(res, 502, { error: "executive_upstream_unavailable", effect: "UNKNOWN",
        reconcile_original_operation: true });
    } else {
      res.destroy();
    }
  });
  req.on("aborted", () => upstream.destroy());
  req.pipe(upstream);
}

const server = http.createServer(async (req, res) => {
  let parsed;
  try {
    parsed = new URL(req.url || "/", LOCAL_ORIGIN);
  } catch {
    sendJson(res, 400, { error: "invalid_request" });
    return;
  }

  try {
    const rawHeaders = req.rawHeaders.filter((_, i) => i % 2 === 0).map(name => name.toLowerCase());
    if (rawHeaders.filter(name => name === "authorization").length > 1) {
      sendJson(res, 401, { error: "ambiguous_authorization" }); return;
    }
    if (rawHeaders.filter(name => name === "host").length !== 1 ||
        req.headers.host !== LISTEN_HOST + ":" + LISTEN_PORT ||
        (req.headers.origin && req.headers.origin !== LOCAL_ORIGIN)) {
      sendJson(res, 403, { error: "local_transport_refused" }); return;
    }
    const methods = { "/mcp": "POST", [METADATA_PATH]: "GET", [AS_METADATA_PATH]: "GET",
      "/authorize": "GET", [ADAPTER_CALLBACK_PATH]: "GET",
      "/oauth/token": "POST", "/oauth/revoke": "POST" };
    if (req.url !== parsed.pathname + parsed.search || methods[parsed.pathname] !== req.method ||
        (parsed.search && !["/authorize", ADAPTER_CALLBACK_PATH].includes(parsed.pathname))) {
      sendJson(res, 404, { error: "not_found" }); return;
    }
    if (ALLOWED_PROXY_PATHS.has(parsed.pathname)) {
      proxyExecutive(req, res, parsed);
      return;
    }
    if (parsed.pathname === AS_METADATA_PATH && req.method === "GET") {
      await authMetadata(res);
      return;
    }
    if (parsed.pathname === "/authorize" && req.method === "GET") {
      try { authorizeRedirect(res, parsed); }
      catch { sendJson(res, 400, { error: "invalid_authorization_request" }); }
      return;
    }
    if (parsed.pathname === ADAPTER_CALLBACK_PATH && req.method === "GET") {
      try { callbackRedirect(res, parsed); }
      catch { sendJson(res, 400, { error: "invalid_authorization_response" }); }
      return;
    }
    if (parsed.pathname === "/oauth/token" && req.method === "POST") {
      await proxyOAuthPost(req, res, "oauth/token");
      return;
    }
    if (parsed.pathname === "/oauth/revoke" && req.method === "POST") {
      await proxyOAuthPost(req, res, "oauth/revoke");
      return;
    }
    sendJson(res, 404, { error: "not_found" });
  } catch {
    if (!res.headersSent) {
      sendJson(res, 502, { error: "oauth_transport_failed" });
    } else {
      res.end();
    }
  }
});

server.requestTimeout = 0;
server.keepAliveTimeout = 70000;
server.headersTimeout = 71000;
return server;
}

if (process.argv[1] && import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href) {
const installed = JSON.parse(fs.readFileSync(EXECUTIVE_CONFIG, "utf8"));
const server = createAdapter(installed);
server.listen(LISTEN_PORT, LISTEN_HOST, () => {
  process.stdout.write("mastermind-claude-executive-mcp-adapter ready\n");
});
for (const signal of ["SIGTERM", "SIGINT"]) {
  process.on(signal, () => server.close(() => process.exit(0)));
}

}
