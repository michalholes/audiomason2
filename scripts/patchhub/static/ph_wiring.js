(function () {
  "use strict";

  var Core = window.PatchHubCore || {};
  var Fs = window.PatchHubFs || {};
  var Refresh = window.PatchHubRefresh || {};
  var Events = window.PatchHubEvents || {};
  var Amp = window.PatchHubAmpSettings || {};
  var el = Core.el;
  var apiGet = Core.apiGet;
  var apiPost = Core.apiPost;
  var normalizePatchPath = Core.normalizePatchPath;
  var parentRel = Core.parentRel;
  var setPre = Core.setPre;
  var setText = Core.setText;
  var setUiStatus = Core.setUiStatus;
  var setUiError = Core.setUiError;
  var setPreviewVisible = Core.setPreviewVisible;
  var tickMissingPatchClear = Core.tickMissingPatchClear;
  var setFsHint = Fs.setFsHint;
  var refreshFs = Refresh.refreshFs;
  var refreshRuns = Refresh.refreshRuns;
  var refreshStats = Refresh.refreshStats;
  var refreshJobs = Refresh.refreshJobs;
  var refreshTail = Refresh.refreshTail;
  var refreshHeader = Refresh.refreshHeader;
  var getLiveJobId = Events.getLiveJobId;
  var closeLiveStream = Events.closeLiveStream;
  var renderLiveLog = Events.renderLiveLog;
  var updateProgressFromEvents = Events.updateProgressFromEvents;
  var updateProgressPanelFromEvents = Amp.updateProgressPanelFromEvents;


function wireButtons(ctx) {
  ctx = ctx || {};
  var renderIssueDetail = ctx.renderIssueDetail;
  var validateAndPreview = ctx.validateAndPreview;
  var openLiveStream = ctx.openLiveStream;
  var startAutofillPolling = ctx.startAutofillPolling;

  function requireFn(fn, name) {
    if (typeof fn !== "function") {
      setUiError("internal wiring error: missing " + name);
      return false;
    }
    return true;
  }


  el("fsRefresh").addEventListener("click", refreshFs);
  el("fsUp").addEventListener("click", function () {
    var p = el("fsPath").value || "";
    el("fsPath").value = parentRel(p);
    fsSelected = "";
    setFsHint("");
    refreshFs();
  });


  if (el("fsSelectAll")) {
    el("fsSelectAll").addEventListener("click", function () {
      fsLastRels.forEach(function (rel) { fsChecked[rel] = true; });
      fsUpdateSelCount();
      refreshFs();
    });
  }
  if (el("fsClear")) {
    el("fsClear").addEventListener("click", function () {
      fsClearSelection();
      refreshFs();
    });
  }
  if (el("fsDownloadSelected")) {
    el("fsDownloadSelected").addEventListener("click", function () {
      fsDownloadSelected();
    });
  }

  if (el("fsMkdir")) {
    el("fsMkdir").addEventListener("click", function () {
      var base = String(el("fsPath").value || "");
      var name = prompt("New directory name");
      if (!name) return;
      var rel = joinRel(base, name);
      apiPost("/api/fs/mkdir", { path: rel }).then(function (r) {
        if (!r || r.ok === false) {
          setFsHint("mkdir failed");
          return;
        }
        refreshFs();
      });
    });
  }

  if (el("fsRename")) {
    el("fsRename").addEventListener("click", function () {
      if (!fsSelected) {
        setFsHint("focus an item first");
        return;
      }
      var base = parentRel(fsSelected);
      var curName = fsSelected.split("/").pop();
      var dstName = prompt("New name", curName || "");
      if (!dstName) return;
      var dst = joinRel(base, dstName);
      apiPost("/api/fs/rename", { src: fsSelected, dst: dst }).then(function (r) {
        if (!r || r.ok === false) {
          setFsHint("rename failed");
          return;
        }
        fsSelected = dst;
        refreshFs();
      });
    });
  }

  if (el("fsDelete")) {
    el("fsDelete").addEventListener("click", function () {
      var paths = [];
      for (var k in fsChecked) {
        if (Object.prototype.hasOwnProperty.call(fsChecked, k)) paths.push(k);
      }
      if (!paths.length && fsSelected) paths = [fsSelected];
      if (!paths.length) {
        setFsHint("select at least one item");
        return;
      }
      if (!confirm("Delete selected item(s)?")) return;

      var seq = Promise.resolve();
      paths.sort().forEach(function (p) {
        seq = seq.then(function () {
          return apiPost("/api/fs/delete", { path: p }).then(function (r) {
            if (!r || r.ok !== true) {
              var err = (r && r.error) ? String(r.error) : "unknown error";
              setFsHint("delete failed: " + err);
              throw new Error(err);
            }
            return r;
          });
        });
      });
      seq.then(function () {
        fsClearSelection();
        fsSelected = "";
        refreshFs();
      }).catch(function (e) {
        if (e && e.message) {
          setFsHint("delete failed: " + String(e.message));
        } else {
          setFsHint("delete failed");
        }
      });
    });
  }

  if (el("fsUnzip")) {
    el("fsUnzip").addEventListener("click", function () {
      if (!fsSelected || !/\.zip$/i.test(fsSelected)) {
        setFsHint("focus a .zip file first");
        return;
      }
      var base = parentRel(fsSelected);
      var dst = prompt("Destination directory", base || "");
      if (dst === null) return;
      apiPost("/api/fs/unzip", { zip_path: fsSelected, dest_dir: String(dst || "") })
        .then(function (r) {
          if (!r || r.ok === false) {
            setFsHint("unzip failed");
            return;
          }
          refreshFs();
        });
    });
  }
  el("runsRefresh").addEventListener("click", refreshRuns);

  if (el("runsCollapse")) {
    el("runsCollapse").addEventListener("click", function () {
      setRunsVisible(!runsVisible);
      saveRunsVisible(runsVisible);
    });
  }

      if (el("previewToggle")) {
    el("previewToggle").addEventListener("click", function () {
      setPreviewVisible(!previewVisible);
    });
  }
  if (el("previewCollapse")) {
    el("previewCollapse").addEventListener("click", function () {
      setPreviewVisible(!previewVisible);
    });
  }

  el("jobsRefresh").addEventListener("click", refreshJobs);

  if (el("jobsCollapse")) {
    el("jobsCollapse").addEventListener("click", function () {
      setJobsVisible(!jobsVisible);
      saveJobsVisible(jobsVisible);
    });
  }

  if (el("liveLevel")) {
    el("liveLevel").addEventListener("change", function () {
      liveLevel = String(el("liveLevel").value || "normal");
      try { localStorage.setItem("amp.liveLogLevel", liveLevel); } catch (e) {}
      renderLiveLog();
      updateProgressFromEvents();
    });
  }

  if (el("jobsList")) {
    el("jobsList").addEventListener("click", function (e) {
      var t = e && e.target ? e.target : null;
      while (t && t !== el("jobsList")) {
        var jobId = t.getAttribute && t.getAttribute("data-jobid");
        if (jobId) {
          selectedJobId = String(jobId);
          saveLiveJobId(selectedJobId);
          suppressIdleOutput = false;
          refreshJobs();
          openLiveStream(getLiveJobId());
          refreshTail(tailLines);
          return;
        }
        t = t.parentElement;
      }
    });
  }

  el("enqueueBtn").addEventListener("click", enqueue);

  if (el("parseBtn")) {
    el("parseBtn").addEventListener("click", function () {
      triggerParse(getRawCommand());
    });
  }

  if (el("rawCommand")) {
    el("rawCommand").addEventListener("input", function () {
      var raw = getRawCommand();
      if (raw !== lastParsedRaw) {
        lastParsed = null;
        lastParsedRaw = "";
      }
      if (!raw) {
        clearParsedState();
        setParseHint("");
        validateAndPreview();
        return;
      }
      scheduleParseDebounced(raw);
    });

    el("rawCommand").addEventListener("paste", function () {
      setTimeout(function () {
        triggerParse(getRawCommand());
      }, 0);
    });
  }

  // Functions provided by app.js; validate presence before wiring handlers.
  if (!requireFn(validateAndPreview, "validateAndPreview")) return;
  if (!requireFn(renderIssueDetail, "renderIssueDetail")) return;
  if (!requireFn(openLiveStream, "openLiveStream")) return;
  if (typeof startAutofillPolling !== "function") startAutofillPolling = null;

  el("mode").addEventListener("change", validateAndPreview);
  el("issueId").addEventListener("input", function () {
    dirty.issueId = true;
    validateAndPreview();
  });
  el("commitMsg").addEventListener("input", function () {
    dirty.commitMsg = true;
    validateAndPreview();
  });
  el("patchPath").addEventListener("input", function () {
    dirty.patchPath = true;
    validateAndPreview();
  });

  var browse = el("browsePatch");
  if (browse) {
    browse.addEventListener("click", function () {
      if (!fsSelected) {
        setFsHint("select a patch file first");
        return;
      }
      el("patchPath").value = normalizePatchPath(fsSelected);
      dirty.patchPath = true;
      validateAndPreview();
    });
  }

  if (el("refreshAll")) {
    el("refreshAll").addEventListener("click", function () {
      refreshFs();
      refreshRuns();
      refreshStats();
      refreshJobs();
          refreshHeader();
      renderIssueDetail();
      validateAndPreview();
    });
  }
}


var _timers = { patchStat: null, jobs: null, header: null };

function stopTimers() {
  if (_timers.patchStat) { clearInterval(_timers.patchStat); _timers.patchStat = null; }
  if (_timers.jobs) { clearInterval(_timers.jobs); _timers.jobs = null; }
  if (_timers.header) { clearInterval(_timers.header); _timers.header = null; }
}

function startTimers(ctx) {
  stopTimers();
  if (ctx && typeof ctx.tickMissingPatchClear === "function") {
    _timers.patchStat = setInterval(ctx.tickMissingPatchClear, 1000);
  }
  if (ctx && typeof ctx.refreshJobs === "function" && typeof ctx.refreshTail === "function") {
    _timers.jobs = setInterval(function () {
      ctx.refreshJobs();
      ctx.refreshTail(ctx.tailLines || 200);
    }, 2000);
  }
  if (ctx && typeof ctx.refreshHeader === "function") {
    _timers.header = setInterval(function () {
      ctx.refreshHeader();
    }, 5000);
  }
}

function pauseBackgroundActivity(ctx) {
  stopTimers();
  if (ctx && typeof ctx.stopAutofillPolling === "function") ctx.stopAutofillPolling();
  if (ctx && typeof ctx.closeLiveStream === "function") ctx.closeLiveStream();
}

function resumeForegroundActivity(ctx) {
  if (!ctx) return;
  if (typeof ctx.refreshFs === "function") ctx.refreshFs();
  if (typeof ctx.refreshRuns === "function") ctx.refreshRuns();
  if (typeof ctx.refreshStats === "function") ctx.refreshStats();
  if (typeof ctx.refreshJobs === "function") ctx.refreshJobs();
  if (typeof ctx.refreshTail === "function") ctx.refreshTail(ctx.tailLines || 200);
  if (typeof ctx.refreshHeader === "function") ctx.refreshHeader();
  if (typeof ctx.renderIssueDetail === "function") ctx.renderIssueDetail();
  if (typeof ctx.validateAndPreview === "function") ctx.validateAndPreview();
  if (typeof ctx.startAutofillPolling === "function") ctx.startAutofillPolling();
  startTimers(ctx);
}

function installVisibilityGating(ctx) {
  function onVis() {
    if (document.hidden) pauseBackgroundActivity(ctx);
    else resumeForegroundActivity(ctx);
  }
  document.addEventListener("visibilitychange", onVis);
  onVis();
}

  window.PatchHubWiring = {
    wireButtons: wireButtons,
    installVisibilityGating: installVisibilityGating,
    pauseBackgroundActivity: pauseBackgroundActivity,
    resumeForegroundActivity: resumeForegroundActivity,
    startTimers: startTimers,
    stopTimers: stopTimers
  };
})();
