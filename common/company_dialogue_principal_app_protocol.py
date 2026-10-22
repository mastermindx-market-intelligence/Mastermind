"""App protocol discriminator and byte limits; grants no receiving capability."""

from common.company_dialogue_principal_limits import MAX_REQUEST_BYTES, MAX_RESPONSE_BYTES

APP_REQUEST_SCHEMA = "mastermind.ceo_ingress.principal_dialogue.v1"

# The canonical inner principal result retains its 64 KiB frame bound. Only
# this selected App transport adds the fixed compact success-envelope bytes;
# both serializers use UTF-8, ensure_ascii=False, and one trailing newline.
APP_RESPONSE_ENVELOPE_BYTES = len(b'{"ok":true,"result":}')
MAX_APP_RESPONSE_BYTES = MAX_RESPONSE_BYTES + APP_RESPONSE_ENVELOPE_BYTES
