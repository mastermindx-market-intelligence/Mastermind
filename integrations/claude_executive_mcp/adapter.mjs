#!/opt/homebrew/bin/node
import fs from "node:fs";
import http from "node:http";

const LISTEN_HOST = "127.0.0.1";
const LISTEN_PORT = 8444;
const UPSTREAM_HOST = "127.0.0.1";
const UPSTREAM_PORT = 8443;
const EXECUTIVE_CONFIG =
  "/Library/Application Support/MastermindExecutive/config/executive-mcp.json";

const installed = JSON.parse(fs.readFileSync(EXECUTIVE_CONFIG, "utf8"));
const readPolicy = installed?.policies?.read;
const submitPolicy = installed?.policies?.submit;
if (!readPolicy || !submitPolicy ||
    readPolicy.resource !== submitPolicy.resource ||
    readPolicy.issuer !== submitPolicy.issuer) {
  throw new Error("Executive OAuth policies are absent or divergent");
}

const CANONICAL_RESOURCE = readPolicy.resource;
const AUTH_ISSUER = readPolicy.issuer.endsWith("/")
  ? readPolicy.issuer : readPolicy.issuer + "/";
const LOCAL_ORIGIN = "http://" + LISTEN_HOST + ":" + LISTEN_PORT;
const LOCAL_RESOURCE = LOCAL_ORIGIN + "/mcp";
const METADATA_PATH = "/.well-known/oauth-protected-resource";
const AS_METADATA_PATH = "/.well-known/oauth-authorization-server";
const LOCAL_METADATA = LOCAL_ORIGIN + METADATA_PATH;
const ALLOWED_PROXY_PATHS = new Set(["/mcp", METADATA_PATH]);
const MAX_OAUTH_BODY = 128 * 1024;

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
  const upstream = await fetch(target, {
    headers: { accept: "application/json" },
    redirect: "error",
  });
  if (!upstream.ok) throw new Error("auth_metadata_unavailable");
  const body = await upstream.json();
  body.issuer = LOCAL_ORIGIN;
  body.authorization_endpoint = LOCAL_ORIGIN + "/authorize";
  body.token_endpoint = LOCAL_ORIGIN + "/oauth/token";
  if (body.revocation_endpoint) {
    body.revocation_endpoint = LOCAL_ORIGIN + "/oauth/revoke";
  }
  delete body.registration_endpoint;
  delete body.client_id_metadata_document_supported;
  sendJson(res, 200, body);
}

function translateResource(params) {
  const resources = params.getAll("resource");
  if (resources.length) {
    if (resources.length !== 1 || resources[0] !== LOCAL_RESOURCE) {
      throw new Error("unexpected_resource");
    }
    params.set("resource", CANONICAL_RESOURCE);
  }
}

function authorizeRedirect(res, parsed) {
  const params = new URLSearchParams(parsed.searchParams);
  translateResource(params);
  const target = new URL("authorize", AUTH_ISSUER);
  target.search = params.toString();
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

  const target = new URL(endpoint, AUTH_ISSUER);
  const upstream = await fetch(target, {
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
  const upstream = http.request({
    host: UPSTREAM_HOST,
    port: UPSTREAM_PORT,
    method: req.method,
    path: parsed.pathname + parsed.search,
    headers: cleanHeaders(req.headers, { upstream: true }),
  }, (upstreamRes) => {
    const headers = cleanHeaders(upstreamRes.headers);
    if (headers["www-authenticate"]) {
      headers["www-authenticate"] = rewriteChallenge(headers["www-authenticate"]);
    }

    if (parsed.pathname === METADATA_PATH &&
        (upstreamRes.statusCode || 500) < 300) {
      const chunks = [];
      upstreamRes.on("data", (chunk) => chunks.push(chunk));
      upstreamRes.on("end", () => {
        try {
          const body = JSON.parse(Buffer.concat(chunks).toString("utf8"));
          body.resource = LOCAL_RESOURCE;
          body.authorization_servers = [LOCAL_ORIGIN];
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

    res.writeHead(upstreamRes.statusCode || 502, headers);
    upstreamRes.pipe(res);
  });

  upstream.on("error", () => {
    if (!res.headersSent) {
      res.writeHead(502, {"content-type":"application/json"});
    }
    res.end('{"error":"executive_upstream_unavailable"}');
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
    if (ALLOWED_PROXY_PATHS.has(parsed.pathname)) {
      proxyExecutive(req, res, parsed);
      return;
    }
    if (parsed.pathname === AS_METADATA_PATH && req.method === "GET") {
      await authMetadata(res);
      return;
    }
    if (parsed.pathname === "/authorize" && req.method === "GET") {
      authorizeRedirect(res, parsed);
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
server.listen(LISTEN_PORT, LISTEN_HOST, () => {
  process.stdout.write("mastermind-claude-executive-mcp-adapter ready\n");
});
for (const signal of ["SIGTERM", "SIGINT"]) {
  process.on(signal, () => server.close(() => process.exit(0)));
}
