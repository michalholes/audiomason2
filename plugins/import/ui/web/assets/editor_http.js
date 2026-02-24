(function () {
  "use strict";

  async function requestJSON(url, opts) {
    const r = await fetch(url, opts || {});
    const text = await r.text();
    let data = null;
    try {
      data = JSON.parse(text || "{}");
    } catch {
      data = { text: text || "" };
    }
    return { ok: r.ok, status: r.status, data };
  }

  function pretty(obj) {
    return JSON.stringify(obj, null, 2);
  }

  function renderError(node, payload) {
    if (!node) return;
    if (!payload) {
      node.textContent = "";
      return;
    }
    const err = payload && payload.error ? payload.error : null;
    if (err && typeof err === "object") {
      node.textContent = pretty(payload);
      return;
    }
    node.textContent = String(payload && payload.text ? payload.text : payload);
  }

  window.AM2EditorHTTP = {
    requestJSON,
    pretty,
    renderError,
  };
})();
