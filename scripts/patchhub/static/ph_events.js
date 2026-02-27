(function () {
  "use strict";

  var Core = window.PatchHubCore || {};
  var Amp = window.PatchHubAmpSettings || {};
  var el = Core.el;
  var escapeHtml = Core.escapeHtml;
  var setPre = Core.setPre;
  var setText = Core.setText;
  var apiGet = Core.apiGet;
  var apiPost = Core.apiPost;
  var formatLocalTime = Core.formatLocalTime;
  var ampUpdateProgressPanelFromEvents = Amp.updateProgressPanelFromEvents;

  function deriveProgressSummaryFromEvents(events, progress) {
    var lastResult = null;
    var lastLog = null;
    for (var i = (events || []).length - 1; i >= 0; i--) {
      var ev = events[i];
      if (!ev || typeof ev !== "object") continue;
      var t = String(ev.type || "");
      if (t === "result") {
        lastResult = ev;
        break;
      }
      if (t === "log") {
        var kind = String(ev.kind || "");
        if (kind === "DO" || kind === "OK" || kind === "FAIL") {
          lastLog = ev;
          break;
        }
      }
    }

    if (lastResult) {
      return {
        text: lastResult.ok ? "RESULT: SUCCESS" : "RESULT: FAIL",
        status: lastResult.ok ? "success" : "fail"
      };
    }

    if (lastLog) {
      var stage = normStepName(lastLog.stage || "");
      var kind = String(lastLog.kind || "");
      if (kind === "FAIL") {
        return { text: "FAIL: " + stage, status: "fail" };
      }
      if (kind === "OK") {
        return { text: "OK: " + stage, status: "running" };
      }
      if (kind === "DO") {
        return { text: "DO: " + stage, status: "running" };
      }
    }

    if (progress && progress.order && progress.order.length) {
      return { text: "STATUS: RUNNING", status: "running" };
    }
    return { text: "(idle)", status: "idle" };
  }

  function setProgressSummaryState(summary) {
    var node = el("progressSummary");
    if (!node) return;
    var st = (summary && summary.status) ? String(summary.status) : "idle";
    node.classList.remove("success", "fail", "running", "idle", "muted");
    node.classList.add(st);
    if (st === "idle") node.classList.add("muted");
  }

  function updateProgressPanelFromEvents() {
    var progress = deriveProgressFromEvents(liveEvents);
    renderProgressSteps(progress);
    var summary = deriveProgressSummaryFromEvents(liveEvents, progress);
    renderProgressSummary(summary.text);
    setProgressSummaryState(summary);
  }

  function renderActiveJob(jobs) {
    var active = (jobs || []).find(function (j) { return j.status === "running"; }) || null;
    activeJobId = active ? String(active.job_id || "") : null;
    var queued = (jobs || []).filter(function (j) { return j.status === "queued"; });

    var box = el("activeJob");
    if (!box) return;

    if (!active && queued.length === 0) {
      box.innerHTML = "<div class=\"muted\">(none)</div>";
      return;
    }

    var html = "";
    if (active) {
      html += "<div><b>running</b> " + escapeHtml(active.job_id || "") + "</div>";
      html += "<div class=\"muted\">mode=" + escapeHtml(active.mode || "") + " issue=" + escapeHtml(active.issue_id || "") + "</div>";
      html += "<div class=\"row\"><button class=\"btn btn-small\" id=\"cancelActive\">Cancel</button>";
      html += "<a class=\"linklike\" href=\"/api/jobs/log_tail?job_id=" + encodeURIComponent(active.job_id || "") + "\">log</a></div>";
    }

    if (queued.length) {
      html += "<div style=\"margin-top:6px\"><b>queued</b>: " + String(queued.length) + "</div>";
    }

    box.innerHTML = html;

    var cancelBtn = el("cancelActive");
    if (cancelBtn && active && active.job_id) {
      cancelBtn.addEventListener("click", function () {
        apiPost("/api/jobs/cancel", { job_id: active.job_id }).then(function () {
          if (window.PatchHubRefresh && window.PatchHubRefresh.refreshJobs) window.PatchHubRefresh.refreshJobs();
        });
      });
    }
  }


  function loadLiveJobId() {
  var v = null;
  try { v = localStorage.getItem("amp.liveJobId"); } catch (e) { v = null; }
  if (!v) return null;
  return String(v);
}

function saveLiveJobId(jobId) {
  try { localStorage.setItem("amp.liveJobId", String(jobId || "")); } catch (e) {}
}

function loadLiveLevel() {
    var v = null;
    try { v = localStorage.getItem("amp.liveLogLevel"); } catch (e) { v = null; }
    if (!v) return;
    v = String(v);
    if (["quiet", "normal", "warning", "verbose", "debug"].indexOf(v) >= 0) {
      liveLevel = v;
    }
  }

  function loadUiVisibility() {
    var v = null;
    try { v = localStorage.getItem("amp.ui.runsVisible"); } catch (e) { v = null; }
    if (v === "1") runsVisible = true;
    else if (v === "0") runsVisible = false;

    v = null;
    try { v = localStorage.getItem("amp.ui.jobsVisible"); } catch (e) { v = null; }
    if (v === "1") jobsVisible = true;
    else if (v === "0") jobsVisible = false;
  }

  function saveRunsVisible(v) {
    try { localStorage.setItem("amp.ui.runsVisible", v ? "1" : "0"); } catch (e) {}
  }

  function saveJobsVisible(v) {
    try { localStorage.setItem("amp.ui.jobsVisible", v ? "1" : "0"); } catch (e) {}
  }

  function setRunsVisible(v) {
    runsVisible = !!v;
    var wrap = el("runsWrap");
    var btn = el("runsCollapse");
    if (wrap) wrap.classList.toggle("hidden", !runsVisible);
    if (btn) btn.textContent = runsVisible ? "Hide" : "Show";
  }

  function setJobsVisible(v) {
    jobsVisible = !!v;
    var wrap = el("jobsWrap");
    var btn = el("jobsCollapse");
    if (wrap) wrap.classList.toggle("hidden", !jobsVisible);
    if (btn) btn.textContent = jobsVisible ? "Hide" : "Show";
  }

  function setLiveStreamStatus(text) {
    var box = el("liveStreamStatus");
    if (!box) return;
    box.textContent = String(text || "");
  }

  function getLiveJobId() {
    return selectedJobId || activeJobId || null;
  }

  function closeLiveStream() {
    if (liveES) {
      try { liveES.close(); } catch (e) {}
    }
    liveES = null;
    liveStreamJobId = null;
  }

  function filterLiveEvent(ev) {
    if (!ev) return false;
    var t = String(ev.type || "");
    if (t === "result") return true;
    if (t === "hello") return liveLevel === "debug";
    if (t !== "log") return liveLevel === "debug";

    if (ev.bypass === true) return true;

    var ch = String(ev.ch || "");
    var sev = String(ev.sev || "");
    var summary = ev.summary === true;

    if (liveLevel === "quiet") return summary;
    if (liveLevel === "debug") return true;

    if (ch === "CORE") return true;

    if (liveLevel === "normal") return false;

    if (liveLevel === "warning") return ch === "DETAIL" && sev === "WARNING";
    if (liveLevel === "verbose") {
      if (ch !== "DETAIL") return false;
      return sev === "WARNING" || sev === "INFO";
    }
    return false;
  }


  function formatLiveEvent(ev) {
    var t = String(ev.type || "");
    if (t === "hello") {
      return "HELLO protocol=" + String(ev.protocol || "") +
        " mode=" + String(ev.runner_mode || "") +
        " issue=" + String(ev.issue_id || "");
    }
    if (t === "result") {
      var ok = ev.ok ? "SUCCESS" : "FAIL";
      return "RESULT: " + ok + " rc=" + String(ev.return_code);
    }

    var showPrefixes = liveLevel === "debug";
    var line = "";

    if (showPrefixes) {
      var parts = [];
      var stage = String(ev.stage || "");
      var kind = String(ev.kind || "");
      var sev = String(ev.sev || "");
      var msg = String(ev.msg || "");
      if (stage) parts.push(stage);
      if (kind) parts.push(kind);
      if (sev) parts.push(sev);
      parts.push(msg);
      line = parts.join(" | ");
    } else {
      line = String(ev.msg || "");
    }

    if (ev.stdout || ev.stderr) {
      var out = [];
      out.push(line);
      if (ev.stdout) out.push("STDOUT:\n" + String(ev.stdout));
      if (ev.stderr) out.push("STDERR:\n" + String(ev.stderr));
      return out.join("\n");
    }
    return line;
  }

  function renderLiveLog() {
    var box = el("liveLog");
    if (!box) return;
    var lines = [];
    for (var i = 0; i < liveEvents.length; i++) {
      var ev = liveEvents[i];
      if (!filterLiveEvent(ev)) continue;
      lines.push(formatLiveEvent(ev));
    }
    box.textContent = lines.join("\n");
    var wrap = box.parentElement;
    if (wrap && wrap.classList && wrap.classList.contains("card-tight")) {
      // no-op
    }
  }

  function updateProgressFromEvents() {
    var box = el("activeStage");
    if (!box) return;
    for (var i = liveEvents.length - 1; i >= 0; i--) {
      var ev = liveEvents[i];
      if (!ev) continue;
      if (String(ev.type || "") === "result") {
        box.textContent = (ev.ok ? "RESULT: SUCCESS" : "RESULT: FAIL");
        return;
      }
      if (String(ev.type || "") === "log") {
        var stage = String(ev.stage || "");
        var kind = String(ev.kind || "");
        if (stage || kind) {
          box.textContent = (stage ? stage : "") + (kind ? " / " + kind : "");
          return;
        }
      }
    }
  }


  function isJobActive(jobId) {
    if (!jobId) return false;
    return String(jobId) === String(activeJobId || "");
  }

  window.PatchHubEvents = {
    deriveProgressSummaryFromEvents: deriveProgressSummaryFromEvents,
    formatLiveEvent: formatLiveEvent,
    isJobActive: isJobActive,
    closeLiveStream: closeLiveStream,
    renderLiveLog: renderLiveLog,
    renderActiveJob: renderActiveJob,
    saveLiveJobId: saveLiveJobId,
    updateProgressFromEvents: updateProgressFromEvents,
    updateProgressPanelFromEvents: updateProgressPanelFromEvents,
    filterLiveEvent: filterLiveEvent,
    setLiveStreamStatus: setLiveStreamStatus,
    getLiveJobId: getLiveJobId,
    loadUiVisibility: loadUiVisibility,
    setRunsVisible: setRunsVisible,
    setJobsVisible: setJobsVisible,
    saveRunsVisible: saveRunsVisible,
    saveJobsVisible: saveJobsVisible,
    loadLiveLevel: loadLiveLevel,
    loadLiveJobId: loadLiveJobId,
    saveLiveJobId: saveLiveJobId
  };
})();
