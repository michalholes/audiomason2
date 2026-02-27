(function () {
  "use strict";

function setPreviewVisible(v) {
  previewVisible = !!v;
  var wrap = el("previewWrapRight");
  var btn1 = el("previewToggle");
  var btn2 = el("previewCollapse");
  if (wrap) wrap.classList.toggle("hidden", !previewVisible);
  var t = previewVisible ? "Hide" : "Show";
  if (btn1) btn1.textContent = previewVisible ? "Hide preview" : "Preview";
  if (btn2) btn2.textContent = t;
}

function isNearBottom(node, slack) {
  if (!node) return true;
  slack = (slack == null) ? 20 : slack;
  return (node.scrollTop + node.clientHeight) >= (node.scrollHeight - slack);
}

function el(id) { return document.getElementById(id); }

function setUiStatus(message) {
  var node = el("uiStatusBar");
  if (!node) return;

  var msg = String(message || "");
  msg = msg.replace(/\s*\n\s*/g, " ").trim();
  uiStatusLatest = msg;
  node.textContent = uiStatusLatest;
}

function setUiError(errorText) {
  setUiStatus("ERROR: " + String(errorText || ""));
}

function pushApiStatus(payload) {
  if (!payload || !payload.status || !Array.isArray(payload.status)) return;
  if (!payload.status.length) return;
  setUiStatus(String(payload.status[payload.status.length - 1] || ""));
}

function setPre(id, obj) {
  var node = el(id);
  if (!node) return;
  if (typeof obj === "string") {
    node.textContent = obj;
    return;
  }
  try {
    node.textContent = JSON.stringify(obj, null, 2);
  } catch (e) {
    node.textContent = String(obj);
  }
}

function setText(id, text) {
  var node = el(id);
  if (!node) return;
  node.textContent = String(text || "");
}

function formatLocalTime(isoUtc) {
  if (!isoUtc) return "";
  var d = new Date(String(isoUtc));
  if (isNaN(d.getTime())) return String(isoUtc);
  return d.toLocaleString(undefined, {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit"
  });
}

function apiGet(path) {
  return fetch(path, { headers: { "Accept": "application/json" } })
    .then(function (r) {
      return r.text().then(function (t) {
        try {
          return JSON.parse(t);
        } catch (e) {
          return {
            ok: false,
            error: "bad json",
            raw: t,
            status: r.status
          };
        }
      });
    });
}

function apiPost(path, body) {
  return fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json", "Accept": "application/json" },
    body: JSON.stringify(body || {})
  }).then(function (r) {
    return r.text().then(function (t) {
      try {
        return JSON.parse(t);
      } catch (e) {
        return {
          ok: false,
          error: "bad json",
          raw: t,
          status: r.status
        };
      }
    });
  });
}

function joinRel(a, b) {
  a = String(a || "").replace(/\/+$/, "");
  b = String(b || "").replace(/^\/+/, "");
  if (!a) return b;
  if (!b) return a;
  return a + "/" + b;
}

function parentRel(p) {
  p = String(p || "").replace(/\/+$/, "");
  var idx = p.lastIndexOf("/");
  if (idx < 0) return "";
  return p.slice(0, idx);
}

function escapeHtml(s) {
  return String(s || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/\"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function patchesRootRel() {
  var p = (cfg && cfg.paths && cfg.paths.patches_root) ? String(cfg.paths.patches_root) : "patches";
  return p.replace(/\/+$/, "");
}

function stripPatchesPrefix(path) {
  var pfx = patchesRootRel();
  var p = String(path || "").replace(/^\/+/, "");
  if (p === pfx) return "";
  if (p.indexOf(pfx + "/") === 0) return p.slice(pfx.length + 1);
  return p;
}

function normalizePatchPath(p) {
  p = String(p || "").trim().replace(/^\/+/, "");
  if (!p) return "";

  var pfx = patchesRootRel();
  if (p === pfx) return pfx;
  if (p.indexOf(pfx + "/") === 0) return p;
  return joinRel(pfx, p);
}

function clearRunFieldsBecauseMissingPatch() {
  if (el("issueId")) el("issueId").value = "";
  if (el("commitMsg")) el("commitMsg").value = "";
  if (el("patchPath")) el("patchPath").value = "";
  validateAndPreview();
}

function tickMissingPatchClear() {
  if (patchStatInFlight) return;
  if (!el("patchPath")) return;

  var full = normalizePatchPath(String(el("patchPath").value || ""));
  var rel = stripPatchesPrefix(full);

  patchStatInFlight = true;
  apiGet("/api/fs/stat?path=" + encodeURIComponent(rel)).then(function (r) {
    patchStatInFlight = false;
    if (!r || r.ok === false) return;
    if (r.exists === false) clearRunFieldsBecauseMissingPatch();
  }).catch(function () {
    patchStatInFlight = false;
  });
}


  window.PatchHubCore = {
    setPreviewVisible: setPreviewVisible,
    isNearBottom: isNearBottom,
    el: el,
    setUiStatus: setUiStatus,
    setUiError: setUiError,
    pushApiStatus: pushApiStatus,
    setPre: setPre,
    setText: setText,
    formatLocalTime: formatLocalTime,
    apiGet: apiGet,
    apiPost: apiPost,
    joinRel: joinRel,
    parentRel: parentRel,
    escapeHtml: escapeHtml,
    patchesRootRel: patchesRootRel,
    stripPatchesPrefix: stripPatchesPrefix,
    normalizePatchPath: normalizePatchPath,
    clearRunFieldsBecauseMissingPatch: clearRunFieldsBecauseMissingPatch,
    tickMissingPatchClear: tickMissingPatchClear
  };
})();
