import { boundedJSON, refuse } from './protocol.mjs';
export function validatePopupMessage(message, sender, extensionId, popupURL) {
  if (sender?.id !== extensionId || sender?.url !== popupURL) refuse('UI_SENDER_REFUSED');
  const value = JSON.parse(boundedJSON(message, 1024));
  if (!value || typeof value !== 'object' || Array.isArray(value)) refuse('INVALID_COMMAND');
  const keys = Object.keys(value).sort().join(',');
  if (['status', 'share_current'].includes(value.kind) && keys === 'kind') return value;
  if (value.kind === 'revoke' && keys === 'kind,tab_id' && Number.isSafeInteger(value.tab_id) && value.tab_id >= 0) return value;
  refuse('INVALID_COMMAND');
}
