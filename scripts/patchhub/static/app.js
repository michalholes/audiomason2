"use strict";

var activeJobId = null;
var autoRefreshTimer = null;

var uiStatusLatest = "";

var selectedJobId = null;
var liveStreamJobId = null;
var liveES = null;
var liveEvents = [];
var liveLevel = "normal";

var previewVisible = false;
var runsVisible = false;
var jobsVisible = false;

var cfg = null;
var issueRegex = null;
var fsSelected = "";
var fsChecked = {};
var fsLastRels = [];
var fsLastIsDir = {};
var runsCache = [];
var selectedRun = null;
var tailLines = 200;

var dirty = { issueId: false, commitMsg: false, patchPath: false };
var latestToken = "";
var lastAutofillClearedToken = "";
var autofillTimer = null;

var patchStatTimer = null;
var patchStatInFlight = false;

var suppressIdleOutput = false;

var lastParsedRaw = "";
var lastParsed = null;
var parseInFlight = false;
var parseTimer = null;
var parseSeq = 0;


var PatchHubCore = window.PatchHubCore || {};
var PatchHubFs = window.PatchHubFs || {};
var PatchHubRefresh = window.PatchHubRefresh || {};
var PatchHubAmpSettings = window.PatchHubAmpSettings || {};
var PatchHubEvents = window.PatchHubEvents || {};
var PatchHubWiring = window.PatchHubWiring || {};

var el = PatchHubCore.el;
var apiGet = PatchHubCore.apiGet;
var apiPost = PatchHubCore.apiPost;
var escapeHtml = PatchHubCore.escapeHtml;
var formatLocalTime = PatchHubCore.formatLocalTime;
var isNearBottom = PatchHubCore.isNearBottom;
var joinRel = PatchHubCore.joinRel;
var normalizePatchPath = PatchHubCore.normalizePatchPath;
var parentRel = PatchHubCore.parentRel;
var pushApiStatus = PatchHubCore.pushApiStatus;
var setFsHint = PatchHubFs.setFsHint;
var setPre = PatchHubCore.setPre;
var setPreviewVisible = PatchHubCore.setPreviewVisible;
var setText = PatchHubCore.setText;
var setUiError = PatchHubCore.setUiError;
var setUiStatus = PatchHubCore.setUiStatus;
var tickMissingPatchClear = PatchHubCore.tickMissingPatchClear;

var refreshFs = PatchHubRefresh.refreshFs;
var refreshHeader = PatchHubRefresh.refreshHeader;
var refreshJobs = PatchHubRefresh.refreshJobs;
var refreshLastRunLog = PatchHubRefresh.refreshLastRunLog;
var refreshRuns = PatchHubRefresh.refreshRuns;
var refreshStats = PatchHubRefresh.refreshStats;
var refreshTail = PatchHubRefresh.refreshTail;

var closeLiveStream = PatchHubEvents.closeLiveStream;
var filterLiveEvent = PatchHubEvents.filterLiveEvent;
var formatLiveEvent = PatchHubEvents.formatLiveEvent;
var getLiveJobId = PatchHubEvents.getLiveJobId;
var renderLiveLog = PatchHubEvents.renderLiveLog;
var setLiveStreamStatus = PatchHubEvents.setLiveStreamStatus;
var updateProgressFromEvents = PatchHubEvents.updateProgressFromEvents;

var updateProgressPanelFromEvents = PatchHubAmpSettings.updateProgressPanelFromEvents;
var updateShortProgressFromText = PatchHubAmpSettings.updateShortProgressFromText;
function loadUiVisibility() {
  if (window.PatchHubEvents && typeof window.PatchHubEvents.loadUiVisibility === "function") {
    return window.PatchHubEvents.loadUiVisibility();
  }
  return null;
}

function setRunsVisible(v) {
  if (window.PatchHubEvents && typeof window.PatchHubEvents.setRunsVisible === "function") {
    return window.PatchHubEvents.setRunsVisible(v);
  }
  return null;
}

function setJobsVisible(v) {
  if (window.PatchHubEvents && typeof window.PatchHubEvents.setJobsVisible === "function") {
    return window.PatchHubEvents.setJobsVisible(v);
  }
  return null;
}

function loadLiveLevel() {
  if (window.PatchHubEvents && typeof window.PatchHubEvents.loadLiveLevel === "function") {
    return window.PatchHubEvents.loadLiveLevel();
  }
  return null;
}

function loadLiveJobId() {
  if (window.PatchHubEvents && typeof window.PatchHubEvents.loadLiveJobId === "function") {
    return window.PatchHubEvents.loadLiveJobId();
  }
  return null;
}

function saveLiveJobId(jobId) {
  if (window.PatchHubEvents && typeof window.PatchHubEvents.saveLiveJobId === "function") {
    return window.PatchHubEvents.saveLiveJobId(jobId);
  }
  return null;
}


function openLiveStream(jobId) {
  if (!jobId) {
    closeLiveStream();
    liveEvents = [];
    renderLiveLog();
    updateProgressPanelFromEvents();
    setLiveStreamStatus("");
    return;
  }
  jobId = String(jobId);

  if (liveStreamJobId === jobId && liveES) return;

  closeLiveStream();
  liveStreamJobId = jobId;
  liveEvents = [];
  renderLiveLog();
  updateProgressPanelFromEvents();
  setLiveStreamStatus("connecting...");

  var url = "/api/jobs/" + encodeURIComponent(jobId) + "/events";
  var es = new EventSource(url);
  liveES = es;

  es.onmessage = function (e) {
    if (!e || !e.data) return;
    var obj = null;
    try { obj = JSON.parse(String(e.data)); } catch (err) { obj = null; }
    if (!obj) return;
    liveEvents.push(obj);
    if (filterLiveEvent(obj)) {
      renderLiveLog();
    }
    updateProgressPanelFromEvents();
    setLiveStreamStatus("streaming");
  };

  es.addEventListener("end", function (e) {
    var reason = "";
    var status = "";
    if (e && e.data) {
      try {
        var p = JSON.parse(String(e.data));
        if (p && typeof p === "object") {
          reason = String(p.reason || "");
          status = String(p.status || "");
        }
      } catch (err) {}
    }
    var msg = "ended";
    if (status) msg += " (" + status + ")";
    if (reason) msg += " [" + reason + "]";
    setLiveStreamStatus(msg);
    try { es.close(); } catch (e2) {}
    if (liveES === es) {
      liveES = null;
    }
  });

  es.onerror = function () {
    apiGet("/api/jobs/" + encodeURIComponent(jobId)).then(function (r) {
      if (!r || r.ok === false) {
        closeLiveStream();
        setLiveStreamStatus("ended [job_not_found]");
        return;
      }
      var j = r.job || {};
      var st = String(j.status || "");
      if (st && st !== "running" && st !== "queued") {
        closeLiveStream();
        setLiveStreamStatus("ended (" + st + ") [job_completed]");
        return;
      }
      setLiveStreamStatus("reconnecting...");
    });
  };
}


function jobSummaryCommit(msg) {
  msg = String(msg || "");
  msg = msg.replace(/\s+/g, " ").trim();
  if (!msg) return "";
  if (msg.length <= 60) return msg;
  return msg.slice(0, 57) + "...";
}

function jobSummaryPatchName(p) {
  p = String(p || "").trim();
  if (!p) return "";
  p = p.replace(/\\/g, "/");
  var idx = p.lastIndexOf("/");
  if (idx >= 0) return p.slice(idx + 1);
  return p;
}

function jobSummaryDurationSeconds(startUtc, endUtc) {
  if (!startUtc || !endUtc) return "";
  var a = new Date(String(startUtc));
  var b = new Date(String(endUtc));
  if (isNaN(a.getTime()) || isNaN(b.getTime())) return "";
  var sec = (b.getTime() - a.getTime()) / 1000;
  if (sec < 0) return "";
  var s = Math.round(sec * 10) / 10;
  return String(s);
}


function ensureAutoRefresh(jobs) {
  var id = getLiveJobId();
  var st = "";
  if (id && jobs && jobs.length) {
    var j = jobs.find(function (x) { return String(x.job_id || "") === String(id); }) || null;
    st = j ? String(j.status || "") : "";
  }
  if (st === "running" || st === "queued") openLiveStream(id);
  else closeLiveStream();

  if (activeJobId) {
    if (!autoRefreshTimer) {
      autoRefreshTimer = setInterval(function () {
        refreshJobs();
        refreshRuns();
      }, 1500);
    }
    return;
  }
  if (autoRefreshTimer) {
    clearInterval(autoRefreshTimer);
    autoRefreshTimer = null;
  }
}

function computeCanonicalPreview(mode, issueId, commitMsg, patchPath) {
  var prefix = (cfg && cfg.runner && cfg.runner.command) ? cfg.runner.command : ["python3", "scripts/am_patch.py"];
  var argv = prefix.slice();

  if (mode === "finalize_live") {
    argv.push("-f");
    argv.push(String(commitMsg || ""));
    return argv;
  }
  if (mode === "finalize_workspace") {
    argv.push("-w");
    argv.push(String(issueId || ""));
    return argv;
  }
  if (mode === "rerun_latest") {
    argv.push("-l");
    return argv;
  }

  argv.push(String(issueId || ""));
  argv.push(String(commitMsg || ""));
  argv.push(String(patchPath || ""));
  return argv;
}


function setStartFormState(state) {
var issueEnabled = !!(state && state.issue_id);
var msgEnabled = !!(state && state.commit_message);
var patchEnabled = !!(state && state.patch_path);

el("issueId").disabled = !issueEnabled;
el("commitMsg").disabled = !msgEnabled;
el("patchPath").disabled = !patchEnabled;
var browse = el("browsePatch");
if (browse) browse.disabled = !patchEnabled;
}

function validateAndPreview() {
  var mode = String(el("mode").value || "patch");
  var issueId = String(el("issueId").value || "").trim();
  var commitMsg = String(el("commitMsg").value || "").trim();
  var patchPath = normalizePatchPath(String(el("patchPath").value || ""));
  el("patchPath").value = patchPath;

  var raw = getRawCommand();


var modeRules = null;
if (mode === "patch" || mode === "repair") {
modeRules = { issue_id: true, commit_message: true, patch_path: true };
} else if (mode === "finalize_live") {
modeRules = { issue_id: false, commit_message: true, patch_path: false };
} else if (mode === "finalize_workspace") {
modeRules = { issue_id: true, commit_message: false, patch_path: false };
} else if (mode === "rerun_latest") {
modeRules = { issue_id: false, commit_message: false, patch_path: false };
} else {
modeRules = { issue_id: true, commit_message: true, patch_path: true };
}
setStartFormState(modeRules);

var ok = true;

  var canonical = null;
  var preview = null;

  if (raw) {
    ok = !parseInFlight && !!lastParsed && (lastParsedRaw === raw);
    if (ok) {
      var p = lastParsed.parsed || {};
      var c = lastParsed.canonical || {};
      canonical = c.argv ? c.argv : [];
      var pMode = p.mode ? p.mode : mode;
      var pIssue = p.issue_id ? p.issue_id : issueId;
      var pMsg = p.commit_message ? p.commit_message : commitMsg;
      var pPatch = p.patch_path ? p.patch_path : patchPath;
      preview = {
        mode: pMode,
        issue_id: pIssue,
        commit_message: pMsg,
        patch_path: pPatch,
        canonical_argv: canonical,
        raw_command: raw
      };
    } else {
      canonical = [];
      preview = {
        mode: mode,
        issue_id: issueId,
        commit_message: commitMsg,
        patch_path: patchPath,
        canonical_argv: canonical,
        raw_command: raw,
        parse_status: parseInFlight ? "parsing" : "needs_parse"
      };
    }

} else {
if (mode === "patch" || mode === "repair") {
  ok = !!commitMsg && !!patchPath;
} else if (mode === "finalize_live") {
  ok = !!commitMsg;
} else if (mode === "finalize_workspace") {
  ok = !!issueId && (/^[0-9]+$/.test(issueId));
} else if (mode === "rerun_latest") {
  ok = true;
}

canonical = computeCanonicalPreview(mode, issueId, commitMsg, patchPath);
preview = {
  mode: mode,
  issue_id: issueId,
  commit_message: commitMsg,
  patch_path: patchPath,
  canonical_argv: canonical
};
}
  setPre("previewRight", preview);
  el("enqueueBtn").disabled = !ok;

  var hint2 = el("enqueueHint");
  if (hint2) {
    if (raw) {
      hint2.textContent = "";

} else {
if (ok) {
  hint2.textContent = "";
} else if (mode === "finalize_live") {
  hint2.textContent = "missing message";
} else if (mode === "finalize_workspace") {
  hint2.textContent = "missing issue id";
} else if (mode === "patch" || mode === "repair") {
  hint2.textContent = "missing commit message or patch path";
} else {
  hint2.textContent = "missing fields";
}
}    }
}

function enqueue() {
  var mode = String(el("mode").value || "patch");
  var body = {
    mode: mode,
    raw_command: (el("rawCommand") ? String(el("rawCommand").value || "").trim() : "")
  };

  setUiStatus("enqueue: started mode=" + mode);


if (mode === "patch" || mode === "repair") {
body.issue_id = String(el("issueId").value || "").trim();
body.commit_message = String(el("commitMsg").value || "").trim();
body.patch_path = normalizePatchPath(String(el("patchPath").value || "").trim());
} else if (mode === "finalize_live") {
body.commit_message = String(el("commitMsg").value || "").trim();
} else if (mode === "finalize_workspace") {
body.issue_id = String(el("issueId").value || "").trim();
}

  apiPost("/api/jobs/enqueue", body).then(function (r) {
    pushApiStatus(r);
    setPre("previewRight", r);
    if (r && r.ok !== false && r.job_id) {
      setUiStatus("enqueue: ok job_id=" + String(r.job_id));
      selectedJobId = String(r.job_id);
      saveLiveJobId(selectedJobId);
      suppressIdleOutput = false;
      openLiveStream(selectedJobId);
      refreshTail(tailLines);
    } else {
      setUiError(String((r && r.error) || "enqueue failed"));
    }
    refreshJobs();
  });
}

function uploadFile(file) {
  var fd = new FormData();
  fd.append("file", file);
  setUiStatus("upload: started " + String((file && file.name) || ""));
  fetch("/api/upload/patch", {
    method: "POST",
    body: fd,
    headers: { "Accept": "application/json" }
  })
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
    })
    .then(function (j) {
      pushApiStatus(j);
      setText(
        "uploadHint",
        (j && j.ok)
          ? ("Uploaded: " + String(j.stored_rel_path || ""))
          : ("Upload failed: " + String((j && j.error) || ""))
      );
      if (j && j.ok) {
        setUiStatus("upload: ok");
      } else {
        setUiError(String((j && j.error) || "upload failed"));
      }
      if (j && j.stored_rel_path) {
        var stored = String(j.stored_rel_path);
        var n = el("patchPath");
        if (n && shouldOverwrite("patchPath", n)) {
          n.value = stored;
        }

        var relUnderRoot = stripPatchesPrefix(stored);
        var parent = parentRel(relUnderRoot);
        if (String(el("fsPath").value || "") === "") {
          el("fsPath").value = parent;
        }
      }
      applyAutofillFromPayload(j);
      refreshFs();
    })
    .catch(function (e) {
      setPre("uploadResult", String(e));
      setUiError(String(e));
    });
}

function enableGlobalDropOverlay() {
  var counter = 0;

  function show() { document.body.classList.add("dragging"); }
  function hide() { document.body.classList.remove("dragging"); }

  document.addEventListener("dragenter", function (e) {
    e.preventDefault();
    counter += 1;
    show();
  });

  document.addEventListener("dragover", function (e) {
    e.preventDefault();
    show();
  });

  document.addEventListener("dragleave", function (e) {
    e.preventDefault();
    counter -= 1;
    if (counter <= 0) {
      counter = 0;
      hide();
    }
  });

  document.addEventListener("drop", function (e) {
    e.preventDefault();
    counter = 0;
    hide();
    var f = e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0];
    if (f) uploadFile(f);
  });
}

function setupUpload() {
  var zone = el("uploadZone");
  var browse = el("uploadBrowse");
  var input = el("uploadInput");

  function openPicker() {
    if (!input) return;
    input.value = "";
    input.click();
  }

  if (browse) {
    browse.addEventListener("click", function () { openPicker(); });
  }
  if (zone) {
    zone.addEventListener("click", function () { openPicker(); });

    function setDrag(on) {
      if (on) zone.classList.add("dragover");
      else zone.classList.remove("dragover");
    }

    zone.addEventListener("dragenter", function (e) { e.preventDefault(); setDrag(true); });
    zone.addEventListener("dragleave", function (e) { e.preventDefault(); setDrag(false); });
    zone.addEventListener("dragover", function (e) { e.preventDefault(); setDrag(true); });
    zone.addEventListener("drop", function (e) {
      e.preventDefault();
      setDrag(false);
      var f = e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0];
      if (f) uploadFile(f);
    });
  }

  if (input) {
    input.addEventListener("change", function () {
      if (input.files && input.files[0]) uploadFile(input.files[0]);
    });
  }

  window.addEventListener("dragover", function (e) { e.preventDefault(); });
  window.addEventListener("drop", function (e) { e.preventDefault(); });
}

function loadConfig() {
  return apiGet("/api/config").then(function (r) {
    cfg = r || null;
    if (cfg && cfg.issue && cfg.issue.default_regex) {
      try { issueRegex = new RegExp(cfg.issue.default_regex); } catch (e) { issueRegex = null; }
    }
    if (cfg && cfg.meta && cfg.meta.version) {
      setText("ampWebVersion", "v" + String(cfg.meta.version));
    }
    refreshHeader();
    if (cfg && cfg.ui) {
      if (cfg.ui.base_font_px) {
        document.documentElement.style.fontSize = String(cfg.ui.base_font_px) + "px";
      }
      if (cfg.ui.drop_overlay_enabled) {
        enableGlobalDropOverlay();
      }
    }
    return cfg;
  }).catch(function () {
    cfg = null;
    return null;
  });
}

function shouldOverwrite(fieldKey, node) {
  if (!cfg || !cfg.autofill) return String(node.value || "").trim() === "";
  var pol = String(cfg.autofill.overwrite_policy || "");
  if (pol === "only_if_empty") return String(node.value || "").trim() === "";
  if (pol === "if_not_dirty") return !dirty[fieldKey];
  return false;
}

function applyAutofillFromPayload(p) {
  if (!cfg || !cfg.autofill || !p) return;

  if (cfg.autofill.fill_patch_path && p.stored_rel_path) {
    var n1 = el("patchPath");
    if (n1 && shouldOverwrite("patchPath", n1)) {
      n1.value = String(p.stored_rel_path);
    }
  }

  if (cfg.autofill.fill_issue_id && p.derived_issue != null) {
    var n2 = el("issueId");
    if (n2 && shouldOverwrite("issueId", n2)) {
      n2.value = String(p.derived_issue || "");
    }
  }

  if (cfg.autofill.fill_commit_message && p.derived_commit_message != null) {
    var n3 = el("commitMsg");
    if (n3 && shouldOverwrite("commitMsg", n3)) {
      n3.value = String(p.derived_commit_message || "");
    }
  }

  validateAndPreview();
}

function resetOutputForNewPatch() {
  selectedJobId = null;
  saveLiveJobId("");

  openLiveStream(null);
  setPre("tail", "");
  updateShortProgressFromText("");

  suppressIdleOutput = true;

  if (cfg && cfg.ui && cfg.ui.show_autofill_clear_status) {
    setUiStatus("autofill: loaded new patch, output cleared");
  }
}

function pollLatestPatchOnce() {
  if (!cfg || !cfg.autofill || !cfg.autofill.enabled) return;
  apiGet("/api/patches/latest").then(function (r) {
    if (!r || r.ok === false) {
      setUiError(String((r && r.error) || "autofill scan failed"));
      return;
    }

    pushApiStatus(r);
    if (!r.found) return;
    var token = String(r.token || "");
    if (!token || token === latestToken) return;
    latestToken = token;
    applyAutofillFromPayload(r);

    if (cfg && cfg.ui && cfg.ui.clear_output_on_autofill) {
      if (token !== lastAutofillClearedToken) {
        resetOutputForNewPatch();
        lastAutofillClearedToken = token;
      }
    }
  });
}

function startAutofillPolling() {
  if (autofillTimer) {
    clearInterval(autofillTimer);
    autofillTimer = null;
  }
  if (!cfg || !cfg.autofill || !cfg.autofill.enabled) return;
  var sec = parseInt(String(cfg.autofill.poll_interval_seconds || "10"), 10);
  if (isNaN(sec) || sec < 1) sec = 10;
  autofillTimer = setInterval(pollLatestPatchOnce, sec * 1000);
  pollLatestPatchOnce();
}

function stopAutofillPolling() {
  if (autofillTimer) {
    clearInterval(autofillTimer);
    autofillTimer = null;
  }
}

function setTabActive(which) {
  var tabs = ["Overview", "Logs", "Patch", "Diff", "Files"];
  tabs.forEach(function (t) {
    var btn = el("tab" + t);
    if (btn) {
      if (t === which) btn.classList.add("active");
      else btn.classList.remove("active");
    }
  });
}

function renderIssueDetail() {
  var cardTitle = el("issueDetailTitle");
  var tabs = el("issueTabs");
  var content = el("issueTabContent");
  var links = el("issueTabLinks");
  var body = el("issueTabBody");

  if (!selectedRun) {
    if (cardTitle) cardTitle.textContent = "Select a run on the left.";
    if (tabs) tabs.style.display = "none";
    if (content) content.style.display = "none";
    return;
  }

  if (cardTitle) {
    cardTitle.textContent = "Issue #" + String(selectedRun.issue_id) + " (" + String(selectedRun.result || "") + ")";
  }
  if (tabs) tabs.style.display = "flex";
  if (content) content.style.display = "block";

  function renderLinks() {
    var parts = [];

    function add(label, rel) {
      if (!rel) return;
      parts.push("<a class=\"linklike\" href=\"/api/fs/download?path=" + encodeURIComponent(rel) + "\">" + escapeHtml(label) + "</a>");
    }

    add("log", selectedRun.log_rel_path);
    add("archived patch", selectedRun.archived_patch_rel_path);
    add("diff bundle", selectedRun.diff_bundle_rel_path);
    add("latest success zip", selectedRun.success_zip_rel_path);

    links.innerHTML = parts.join(" ");
  }

  function renderOverview() {
    setTabActive("Overview");
    renderLinks();
    setPre("issueTabBody", selectedRun);
  }

  function renderLogs() {
    setTabActive("Logs");
    renderLinks();
    if (!selectedRun.log_rel_path) {
      setPre("issueTabBody", "(no log path)");
      return;
    }
    var p = String(selectedRun.log_rel_path);
    var url = "/api/fs/read_text?path=" + encodeURIComponent(p) + "&tail_lines=2000";
    apiGet(url).then(function (r) {
      if (!r || r.ok === false) {
        setPre("issueTabBody", r);
        return;
      }
      var t = String(r.text || "");
      if (r.truncated) {
        t += "\n\n[TRUNCATED]";
      }
      setPre("issueTabBody", t);
    });
  }

  function renderPatch() {
    setTabActive("Patch");
    renderLinks();
    if (selectedRun.archived_patch_rel_path) {
      setPre("issueTabBody", "Download: /api/fs/download?path=" + selectedRun.archived_patch_rel_path);
    } else {
      setPre("issueTabBody", "(no archived patch)");
    }
  }

  function renderDiff() {
    setTabActive("Diff");
    renderLinks();
    if (selectedRun.diff_bundle_rel_path) {
      setPre("issueTabBody", "Download: /api/fs/download?path=" + selectedRun.diff_bundle_rel_path);
    } else {
      setPre("issueTabBody", "(no diff bundle)");
    }
  }

  function renderFiles() {
    setTabActive("Files");
    renderLinks();
    // Convenience: jump file manager to the issue directory if possible.
    var p = "";
    if (selectedRun.log_rel_path) {
      p = parentRel(stripPatchesPrefix(selectedRun.log_rel_path));
    }
    if (p) {
      el("fsPath").value = p;
      fsSelected = "";
      setFsHint("");
      refreshFs();
    }
    setPre("issueTabBody", "File manager path set to: " + String(el("fsPath").value || ""));
  }

  el("tabOverview").onclick = renderOverview;
  el("tabLogs").onclick = renderLogs;
  el("tabPatch").onclick = renderPatch;
  el("tabDiff").onclick = renderDiff;
  el("tabFiles").onclick = renderFiles;

  // Default to overview when switching run.
  renderOverview();
}

function init() {
  setupUpload();
  PatchHubWiring.wireButtons();
  setPreviewVisible(false);
  loadUiVisibility();
  setRunsVisible(runsVisible);
  setJobsVisible(jobsVisible);

  loadLiveLevel();
  var savedJobId = loadLiveJobId();
  if (savedJobId) selectedJobId = savedJobId;
  if (el("liveLevel")) {
    el("liveLevel").value = liveLevel;
  }

  loadConfig().then(function () {
    if (window.AmpSettings && typeof window.AmpSettings.init === "function") {
      try {
        window.AmpSettings.init();
      } catch (e) {
        // Best-effort: do not break main UI if AMP settings init fails.
      }
    }

    var ctx = {
      tailLines: tailLines,
      refreshFs: refreshFs,
      refreshRuns: refreshRuns,
      refreshStats: refreshStats,
      refreshJobs: refreshJobs,
      refreshTail: refreshTail,
      refreshHeader: refreshHeader,
      renderIssueDetail: renderIssueDetail,
      validateAndPreview: validateAndPreview,
      startAutofillPolling: startAutofillPolling,
      stopAutofillPolling: stopAutofillPolling,
      tickMissingPatchClear: tickMissingPatchClear,
      closeLiveStream: closeLiveStream
    };

    PatchHubWiring.installVisibilityGating(ctx);
  });
}

window.addEventListener("load", init);
