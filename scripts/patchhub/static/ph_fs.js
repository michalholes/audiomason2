(function () {
  "use strict";

  var Core = window.PatchHubCore || {};
  var el = Core.el;
  var apiGet = Core.apiGet;
  var apiPost = Core.apiPost;
  var joinRel = Core.joinRel;
  var parentRel = Core.parentRel;
  var escapeHtml = Core.escapeHtml;
  var normalizePatchPath = Core.normalizePatchPath;
  var setPre = Core.setPre;

function setFsHint(msg) {
  var h = el("fsHint");
  if (h) h.textContent = msg || "";
}

function fsUpdateSelCount() {
  var n = 0;
  for (var k in fsChecked) {
    if (Object.prototype.hasOwnProperty.call(fsChecked, k)) n += 1;
  }
  var node = el("fsSelCount");
  if (node) {
    node.textContent = n ? ("selected: " + String(n)) : "";
  }
  return n;
}

function fsClearSelection() {
  fsChecked = {};
  fsUpdateSelCount();
}

function fsDownloadSelected() {
  var paths = [];
  for (var k in fsChecked) {
    if (Object.prototype.hasOwnProperty.call(fsChecked, k)) paths.push(k);
  }
  if (!paths.length) {
    setFsHint("select at least one item");
    return;
  }
  paths.sort();

  fetch("/api/fs/archive", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ paths: paths })
  }).then(function (r) {
    if (!r.ok) {
      return r.text().then(function (t) {
        setFsHint("archive failed: " + String(t || r.status));
      });
    }
    return r.blob().then(function (blob) {
      var url = URL.createObjectURL(blob);
      var a = document.createElement("a");
      a.href = url;
      a.download = "selection.zip";
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(function () { URL.revokeObjectURL(url); }, 1000);
    });
  }).catch(function (e) {
    setFsHint("archive failed: " + String(e));
  });
}

function setParseHint(msg) {
  setText("parseHint", msg || "");
}

function getRawCommand() {
  var n = el("rawCommand");
  if (!n) return "";
  return String(n.value || "").trim();
}

function clearParsedState() {
  lastParsedRaw = "";
  lastParsed = null;
  parseInFlight = false;
}

function triggerParse(raw) {
  raw = String(raw || "").trim();
  if (!raw) {
    clearParsedState();
    setParseHint("");
    validateAndPreview();
    return;
  }

  parseInFlight = true;
  lastParsedRaw = "";
  lastParsed = null;
  setParseHint("Parsing...");
  setUiStatus("parse_command: started");
  validateAndPreview();

  parseSeq += 1;
  var mySeq = parseSeq;
  apiPost("/api/parse_command", { raw: raw }).then(function (r) {
    if (mySeq !== parseSeq) return;
    parseInFlight = false;

    if (!r || r.ok === false) {
      clearParsedState();
      setParseHint("Parse failed: " + String((r && r.error) || ""));
      setUiError(String((r && r.error) || "parse failed"));
      validateAndPreview();
      return;
    }

    pushApiStatus(r);

    lastParsedRaw = raw;
    lastParsed = r;
    setParseHint("");
    if (r.parsed && typeof r.parsed === "object") {
      if (r.parsed.mode) el("mode").value = String(r.parsed.mode);
      if (r.parsed.issue_id != null) {
        el("issueId").value = String(r.parsed.issue_id || "");
      }
      if (r.parsed.commit_message != null) {
        el("commitMsg").value = String(r.parsed.commit_message || "");
      }
      if (r.parsed.patch_path != null) {
        el("patchPath").value = String(r.parsed.patch_path || "");
      }
    }

    validateAndPreview();
  });
}

function scheduleParseDebounced(raw) {
  if (parseTimer) {
    clearTimeout(parseTimer);
    parseTimer = null;
  }
  parseTimer = setTimeout(function () {
    parseTimer = null;
    triggerParse(raw);
  }, 350);
}


  window.PatchHubFs = {
    setFsHint: setFsHint,
    fsDownloadSelected: fsDownloadSelected,
    fsOpenSelectedDir: fsOpenSelectedDir,
    triggerParse: triggerParse,
    refreshPatchStat: refreshPatchStat,
    uploadFile: uploadFile,
    scheduleParseDebounced: scheduleParseDebounced
  };
})();
