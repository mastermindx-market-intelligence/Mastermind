(function () {
  var title = window.__MMX_TITLE;
  var text = window.__MMX_TEXT;
  if (document.title !== title) return "TITLE_MISMATCH";
  var vis = function (e) {
    var r = e.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  };
  var buttons = Array.prototype.slice.call(document.querySelectorAll("button")).filter(vis);
  for (var i = 0; i < buttons.length; i++) {
    var label = buttons[i].getAttribute("aria-label") || "";
    if (label.indexOf("Stop") === 0) return "RUNNING";
  }
  var editors = Array.prototype.slice.call(document.querySelectorAll("div.ProseMirror")).filter(vis);
  var editor = editors.length ? editors[editors.length - 1] : null;
  if (!editor) return "NO_EDITOR";
  var transfer = new DataTransfer();
  transfer.setData("text/plain", text);
  editor.dispatchEvent(new ClipboardEvent("paste", { clipboardData: transfer, bubbles: true, cancelable: true }));
  var send = null;
  for (var j = 0; j < buttons.length; j++) {
    var name = buttons[j].getAttribute("aria-label") || "";
    if (name.indexOf("Send") === 0) { send = buttons[j]; break; }
  }
  if (!send) return "NO_SEND";
  send.click();
  return "SENT";
})();
