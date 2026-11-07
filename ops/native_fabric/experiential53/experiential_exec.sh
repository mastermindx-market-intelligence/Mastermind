#!/bin/sh
# experiential_exec.sh — fail-closed worker scaffold for the Experiential pool.
#
# Invocation shape mirrors the incumbent exec wrappers:
#   experiential_exec.sh <cwd> <model> <prompt_file>
#
# THIS GENERATION NEVER REACHES A PROVIDER.  There is no qualified native
# worker transport through the existing shared Experiential gateway yet (the
# gateway PR #1849 and the Attempt-owned consumer PR #1920 are separate,
# unmerged owners; no enrolled loopback route exists).  Every execution path
# ends in a typed refusal and exit 78.  No false admission.
#
# Hard zero-effect contract:
#   * no network of any kind (no curl/wget/nc/ssh/python socket),
#   * no credential, key or token is read, printed or stored,
#   * nothing is written: no ledger, no state dir, no tmp file, no redirect,
#   * the prompt file is never read; consent is explicit flags only.
#
# Gate flags (all required; each maps to one typed refusal):
#   EXPERIENTIAL_MANUAL_PIN            exact literal "glm-5.3-uncensored"
#   EXPERIENTIAL_PROVIDER_ENABLED      1 only when the registry owner enabled the pool
#   EXPERIENTIAL_ENTITLEMENT_VERIFIED  1 only with an owner-verified entitlement record
#   EXPERIENTIAL_RETENTION_ACKNOWLEDGED 1 (provider retains prompt/response beyond settings-off/account-deletion)
#   EXPERIENTIAL_SENSITIVE_DATA_OPT_IN 1 (explicit disclosure opt-in)
#   EXPERIENTIAL_PROPRIETARY_CODE      1 when the packet carries proprietary code
#   EXPERIENTIAL_CODE_EXPOSURE_OPT_IN  1 (independent explicit opt-in; never automatic)
#   EXPERIENTIAL_ACCOUNT               "b" (a is held: original HTTP 403 stands)
#   EXPERIENTIAL_QUOTA_READBACK        "authenticated" only (account B $1/day cap is NOT readable today)
#   EXPERIENTIAL_GATEWAY_VERIFIED      1 only with an attested loopback gateway route generation

set -u

MODEL_ARG="${2:-}"
PIN="${EXPERIENTIAL_MANUAL_PIN:-}"

refuse() {
  echo "EXPERIENTIAL_REFUSED reason=$1" >&2
  exit 78
}

[ "$#" -eq 3 ] || refuse EXPERIENTIAL_ARGUMENT_SHAPE_INVALID

# Strict exact-slug pin, re-evaluated at the transport boundary.  The pin law
# itself lives in experiential_pin.py; this is the last recheck before any
# effect would occur.  Carrier distinctness first: this slug never rides glm.
case "$PIN" in
  glm-5.3-uncensored) ;;
  glm) refuse EXPERIENTIAL_GLM_CARRIER_REFUSED ;;
  glm-5.3|glm-5.3-flash) refuse EXPERIENTIAL_MODEL_DISTINCT ;;
  "") refuse EXPERIENTIAL_STRICT_PIN_MISSING ;;
  *) refuse EXPERIENTIAL_STRICT_PIN_MISMATCH ;;
esac

case "$MODEL_ARG" in
  glm-5.3-uncensored) ;;
  "") refuse EXPERIENTIAL_MODEL_SLUG_REQUIRED ;;
  *) refuse EXPERIENTIAL_MODEL_SLUG_MISMATCH ;;
esac

[ "${EXPERIENTIAL_PROVIDER_ENABLED:-}" = "1" ] || refuse PROVIDER_DISABLED
[ "${EXPERIENTIAL_ENTITLEMENT_VERIFIED:-}" = "1" ] || refuse ENTITLEMENT_UNVERIFIED
[ "${EXPERIENTIAL_RETENTION_ACKNOWLEDGED:-}" = "1" ] || refuse RETENTION_UNVERIFIED
[ "${EXPERIENTIAL_SENSITIVE_DATA_OPT_IN:-}" = "1" ] || refuse SENSITIVE_DATA_DISCLOSURE_REQUIRED
if [ "${EXPERIENTIAL_PROPRIETARY_CODE:-}" = "1" ]; then
  [ "${EXPERIENTIAL_CODE_EXPOSURE_OPT_IN:-}" = "1" ] || refuse PROPRIETARY_CODE_EXPOSURE_REFUSED
fi

_ACCOUNT=${EXPERIENTIAL_ACCOUNT:-}
case "$_ACCOUNT" in
  "") refuse ACCOUNT_UNRESOLVED ;;
  [Aa]) refuse ACCOUNT_A_HELD_HTTP403 ;;
  [Bb]) ;;
  *) refuse ACCOUNT_UNKNOWN ;;
esac
[ "${EXPERIENTIAL_QUOTA_READBACK:-}" = "authenticated" ] || refuse QUOTA_READBACK_UNAUTHENTICATED

[ "${EXPERIENTIAL_GATEWAY_VERIFIED:-}" = "1" ] || refuse EXPERIENTIAL_GATEWAY_UNVERIFIED

# Final owner gate of this generation: no qualified native worker transport
# exists through the existing shared gateway yet.  Flip this single gate only
# in a later generation that ships the real transport AND its qualification.
refuse EXPERIENTIAL_TRANSPORT_NOT_INSTALLED
