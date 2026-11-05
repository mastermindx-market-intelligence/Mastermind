(function () {
  var title = window.__MMX_TITLE;
  var label = window.__MMX_LABEL;
  var allowed = ["Allow once", "Allow for this conversation", "Always allow", "Deny", "See details"];
  if (document.title !== title) return "TITLE_MISMATCH";
  if (allowed.indexOf(label) < 0) return "LABEL_REFUSED";
  var vis = function (e) {
    var r = e.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  };
  var nodes = Array.prototype.slice.call(document.querySelectorAll("button,[role=menuitem],[role=menuitemradio]")).filter(vis);
  var exact = null;
  for (var i = 0; i < nodes.length; i++) {
    if ((nodes[i].innerText || "").trim() === label) { exact = nodes[i]; break; }
  }
  if (!exact) return "NO_MATCH";
  exact.click();
  return "CLICKED " + label;
})();
