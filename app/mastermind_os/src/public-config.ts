// Public, build-time configuration constants for the Mastermind OS web client.
//
// These values are fixed for the approved deployment. Only the public web
// client ID comes from Vite build input; the native ID is compiled by Rust.
//
// This module intentionally contains no business logic. It is a small surface
// that the auth controller and tests both depend on so neither one has to
// hardcode the issuer, origin, or callback path twice.

export const ISSUER = "https://dev-eo0jf8us5mup7wd5.us.auth0.com/";
export const ORIGIN = "https://mcp.mastermind-x.com";
export const CALLBACK_PATH = "/os/auth/callback";
export const CALLBACK_URL = `${ORIGIN}${CALLBACK_PATH}`;

export const ACQUISITION_AUDIENCE =
  "https://mcp.mastermind-x.com/workspace/read";
export const ACQUISITION_SCOPE = "mastermind.workspace.read";

export const CONTENT_AUDIENCE =
  "https://mcp.mastermind-x.com/workspace/window/current";
export const CONTENT_SCOPE = "mastermind.workspace.content.read";

// PKCE transactions expire if the user does not complete the authorize hop in
// the popup within this many milliseconds.
export const TRANSACTION_TTL_MS = 5 * 60 * 1000;

// Fixed public HTTP body cap; token exchange has a separate smaller cap.
export const MAX_RESPONSE_BYTES = 2_000_000;
export const TOKEN_RESPONSE_BYTES = 32_768;

// Network timeouts for the controller's outbound calls.
export const TOKEN_TIMEOUT_MS = 15 * 1000;
export const READ_TIMEOUT_MS = 15 * 1000;

// The controller retains one popup WindowProxy for both transactions.
export const POPUP_FEATURES = [
  "width=520",
  "height=720",
  "left=120",
  "top=120",
  "resizable=yes",
  "scrollbars=yes",
  "noopener=no",
].join(",");

export interface WebAuthConfig {
  readonly issuer: string;
  readonly origin: string;
  readonly callbackUrl: string;
  readonly acquisitionAudience: string;
  readonly acquisitionScope: string;
  readonly contentAudience: string;
  readonly contentScope: string;
  readonly webClientId: string | null;
  readonly nativeClientId: string | null;
}

// `webClientId` is the only non-secret value that a non-secret build input
// (`VITE_MM_WEB_CLIENT_ID`) is allowed to override. The native client is not
// registered in this web surface; Rust reads MM_NATIVE_CLIENT_ID separately.
export function readWebAuthConfig(): WebAuthConfig {
  const web = readStringEnv("VITE_MM_WEB_CLIENT_ID");

  return {
    issuer: ISSUER,
    origin: ORIGIN,
    callbackUrl: CALLBACK_URL,
    acquisitionAudience: ACQUISITION_AUDIENCE,
    acquisitionScope: ACQUISITION_SCOPE,
    contentAudience: CONTENT_AUDIENCE,
    contentScope: CONTENT_SCOPE,
    webClientId: web && web.length > 0 ? web : null,
    nativeClientId: null,
  };
}

// `import.meta.env` is provided by Vite. In tests we fall back to a plain
// object so the controller can be exercised without a build chain.
declare global {
  interface ImportMetaEnv {
    readonly VITE_MM_WEB_CLIENT_ID?: string;
  }
  interface ImportMeta {
    readonly env: ImportMetaEnv;
  }
}

function readStringEnv(name: keyof ImportMetaEnv): string | null {
  try {
    const value = import.meta.env?.[name];
    return typeof value === "string" && value.length > 0 ? value : null;
  } catch {
    return null;
  }
}
