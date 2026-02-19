(function () {
  "use strict";

  var errors = [];
  var net = [];

  function el(id) { return document.getElementById(id); }
  function setPre(id, obj) {
    el(id).textContent = typeof obj === "string" ? obj : JSON.stringify(obj, null, 2);
  }

  window.addEventListener("error", function (e) {
    errors.push({ message: String(e.message || "error"), source: String(e.filename || ""), line: e.lineno || 0, col: e.colno || 0 });
    if (errors.length > 200) errors.shift();
    setPre("clientErrors", errors);
  });

  var origFetch = window.fetch;
  window.fetch = function (url, opts) {
    var started = Date.now();
    return origFetch(url, opts).then(function (r) {
      net.push({ method: (opts && opts.method) || "GET", url: String(url), status: r.status, ms: Date.now() - started });
      if (net.length > 200) net.shift();
      setPre("clientNet", net);
      return r;
    }).catch(function (e) {
      net.push({ method: (opts && opts.method) || "GET", url: String(url), status: 0, ms: Date.now() - started, error: String(e) });
      if (net.length > 200) net.shift();
      setPre("clientNet", net);
      throw e;
    });
  };

  function apiGet(url) {
    return fetch(url, { headers: { "Accept": "application/json" } }).then(function (r) { return r.json(); });
  }
  function apiPost(url, obj) {
    return fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json", "Accept": "application/json" },
      body: JSON.stringify(obj)
    }).then(function (r) { return r.json(); });
  }

  function refreshDiag() {
    apiGet("/api/debug/diagnostics").then(function (r) { setPre("serverDiag", r); });
  }

  function refreshTail() {
    apiGet("/api/runner/tail?lines=200").then(function (r) { setPre("tail", r.events || []); });
  }

  function parseCmd() {
    var raw = el("raw").value;
    apiPost("/api/parse_command", { raw: raw }).then(function (r) { setPre("parsed", r); });
  }

  function init() {
    setPre("clientErrors", errors);
    setPre("clientNet", net);

    el("diagRefresh").addEventListener("click", refreshDiag);
    el("tailRefresh").addEventListener("click", refreshTail);
    el("parse").addEventListener("click", parseCmd);

    refreshDiag();
    refreshTail();
  }

  window.addEventListener("load", init);
})();
