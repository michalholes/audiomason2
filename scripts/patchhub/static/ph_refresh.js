(function () {
  "use strict";

  var Core = window.PatchHubCore || {};
  var Fs = window.PatchHubFs || {};
  var el = Core.el;
  var apiGet = Core.apiGet;
  var apiPost = Core.apiPost;
  var escapeHtml = Core.escapeHtml;
  var formatLocalTime = Core.formatLocalTime;
  var isNearBottom = Core.isNearBottom;
  var joinRel = Core.joinRel;
  var normalizePatchPath = Core.normalizePatchPath;
  var parentRel = Core.parentRel;
  var setPre = Core.setPre;
  var setText = Core.setText;
  var setUiStatus = Core.setUiStatus;
  var setFsHint = Fs.setFsHint;

function refreshFs() {
  var path = el("fsPath").value || "";
  apiGet("/api/fs/list?path=" + encodeURIComponent(path)).then(function (r) {
    if (!r || r.ok === false) {
      setPre("fsList", r);
      return;
    }
    var items = r.items || [];
    fsLastRels = [];
    fsLastIsDir = {};
    var html = items.map(function (it) {
      var name = it.name;
      var isDir = !!it.is_dir;
      var rel = joinRel(path, name);
      fsLastRels.push(rel);
      fsLastIsDir[rel] = isDir;

      var displayName = isDir ? (name + "/") : name;
      var isSelected = (fsSelected === rel);
      var cls = "item fsitem" + (isSelected ? " selected" : "");
      var checked = fsChecked[rel] ? " checked" : "";

      var dl = "";
      if (!isDir) {
        dl = "<button class=\"btn btn-small btn-inline fsDl\" data-rel=\"" +
          escapeHtml(rel) + "\">Download</button>";
      }

      return (
        "<div class=\"" + cls + "\" data-rel=\"" + escapeHtml(rel) +
          "\" data-isdir=\"" + (isDir ? "1" : "0") + "\">" +
        "<input class=\"fsChk\" type=\"checkbox\" data-rel=\"" +
          escapeHtml(rel) + "\" aria-label=\"Select\" " + checked + " />" +
        "<span class=\"name\">" + escapeHtml(displayName) + "</span>" +
        "<span class=\"actions\"><span class=\"muted\">" +
          String(it.size || 0) + "</span>" + dl + "</span>" +
        "</div>"
      );
    }).join("");

    el("fsList").innerHTML = html || "<div class=\"muted\">(empty)</div>";
    fsUpdateSelCount();

    Array.from(el("fsList").querySelectorAll(".fsChk")).forEach(function (node) {
      node.addEventListener("click", function (ev) {
        ev.stopPropagation();
        var rel = node.getAttribute("data-rel") || "";
        if (!rel) return;
        if (node.checked) {
          fsChecked[rel] = true;
        } else {
          delete fsChecked[rel];
        }
        fsUpdateSelCount();
      });
    });

    Array.from(el("fsList").querySelectorAll(".fsDl")).forEach(function (node) {
      node.addEventListener("click", function (ev) {
        ev.stopPropagation();
        var rel = node.getAttribute("data-rel") || "";
        if (!rel) return;
        window.location.href = "/api/fs/download?path=" + encodeURIComponent(rel);
      });
    });

    Array.from(el("fsList").querySelectorAll(".fsitem .name")).forEach(function (node) {
      node.addEventListener("click", function () {
        var item = node.parentElement;
        var rel = item.getAttribute("data-rel") || "";
        var isDir = (item.getAttribute("data-isdir") || "0") === "1";
        if (isDir) {
          el("fsPath").value = rel;
          fsSelected = "";
          setFsHint("");
          refreshFs();
          return;
        }

        fsSelected = rel;
        setFsHint("focused: " + rel);

        if (/\.(zip|patch|diff)$/i.test(rel)) {
          el("patchPath").value = normalizePatchPath(rel);

          var m = null;
          if (issueRegex) {
            try { m = issueRegex.exec(rel); } catch (e) { m = null; }
          }
          if (!m) {
            m = /(?:issue_|#)(\d+)/i.exec(rel) || /(\d{3,6})/.exec(rel);
          }
          if (m && m[1] && !String(el("issueId").value || "").trim()) {
            el("issueId").value = String(m[1]);
          }
          validateAndPreview();
        }

        refreshFs();
      });
    });
  });
}

function refreshRuns() {
  var q = [];
  var issue = String(el("runsIssue").value || "").trim();
  var res = String(el("runsResult").value || "");
  if (issue) q.push("issue_id=" + encodeURIComponent(issue));
  if (res) q.push("result=" + encodeURIComponent(res));
  q.push("limit=80");

  apiGet("/api/runs?" + q.join("&")).then(function (r) {
    if (!r || r.ok === false) {
      setPre("runsList", r);
      return;
    }
    runsCache = r.runs || [];

    var html = runsCache.map(function (x, idx) {
      var log = x.log_rel_path || "";
      var link = log ? "<a class=\"linklike\" href=\"/api/fs/download?path=" + encodeURIComponent(log) + "\">log</a>" : "";
      var sel = (selectedRun && selectedRun.issue_id === x.issue_id && selectedRun.mtime_utc === x.mtime_utc) ? " *" : "";
      return (
        "<div class=\"item runitem\" data-idx=\"" + String(idx) + "\">" +
        "<span class=\"name\">#" + String(x.issue_id) + " " + escapeHtml(String(x.result || "")) + sel + "</span>" +
        "<span class=\"actions\">" + link + " <span class=\"muted\">" + formatLocalTime(x.mtime_utc || "") + "</span></span>" +
        "</div>"
      );
    }).join("");

    el("runsList").innerHTML = html || "<div class=\"muted\">(none)</div>";

    Array.from(el("runsList").querySelectorAll(".runitem .name")).forEach(function (node) {
      node.addEventListener("click", function () {
        var item = node.parentElement;
        var idx = parseInt(item.getAttribute("data-idx") || "-1", 10);
        if (idx >= 0 && idx < runsCache.length) {
          selectedRun = runsCache[idx];
          renderIssueDetail();
          refreshRuns();
        }
      });
    });
  });
}

function refreshLastRunLog() {
  apiGet("/api/runs?limit=1").then(function (r) {
    if (!r || r.ok === false) {
      setPre("lastRunLog", r);
      return;
    }
    var runs = r.runs || [];
    if (!runs.length) {
      lastRunLogPath = "";
      setPre("lastRunLog", "");
      return;
    }
    var logRel = String(runs[0].log_rel_path || "");
    if (!logRel) {
      lastRunLogPath = "";
      setPre("lastRunLog", "(no log path)");
      return;
    }

    lastRunLogPath = logRel;
    var box = el("lastRunLog");
    var wantFollow = isNearBottom(box, 24);
    var url = "/api/fs/read_text?path=" + encodeURIComponent(logRel) + "&tail_lines=2000";
    apiGet(url).then(function (rt) {
      if (!rt || rt.ok === false) {
        setPre("lastRunLog", rt);
        return;
      }
      var t = String(rt.text || "");
      if (rt.truncated) t += "\n\n[TRUNCATED]";
      setPre("lastRunLog", t);
      if (wantFollow && box) box.scrollTop = box.scrollHeight;
    });
  });
}

function refreshTail(lines) {
  tailLines = lines || tailLines || 200;

  var idleGuardOn = !!(cfg && cfg.ui && cfg.ui.clear_output_on_autofill);
  var jid = getLiveJobId();
  if (!jid && suppressIdleOutput && idleGuardOn) {
    setPre("tail", "");
    updateProgressPanelFromEvents();
    return;
  }

  var linesQ = encodeURIComponent(String(tailLines));
  var url = "/api/runner/tail?lines=" + linesQ;
  if (jid) {
    url = "/api/jobs/" + encodeURIComponent(String(jid)) + "/log_tail?lines=" + linesQ;
  }
  apiGet(url).then(function (r) {
    if (!r || r.ok === false) {
      setPre("tail", r);
      return;
    }
    var t = String(r.tail || "");
    setPre("tail", t);
  });
}


function refreshHeader() {
  var base = "";
  if (cfg && cfg.server && cfg.server.host && cfg.server.port) {
    base = "server: " + cfg.server.host + ":" + cfg.server.port;
  }

  apiGet("/api/debug/diagnostics").then(function (d) {
    if (!d || d.ok === false) return;
    var lock = d.lock || {};
    var disk = d.disk || {};
    var held = lock.held ? "LOCK:held" : "LOCK:free";
    var pct = "";
    if (disk.total && disk.used) {
      pct = "disk:" + String(Math.round((disk.used / disk.total) * 100)) + "%";
    }

    var meta = base;
    if (cfg && cfg.paths && cfg.paths.patches_root) {
      meta += " | patches: " + cfg.paths.patches_root;
    }
    meta += " | " + held;
    if (pct) meta += " | " + pct;

    setText("hdrMeta", meta);
  });
}

function refreshStats() {
  apiGet("/api/debug/diagnostics").then(function (r) {
    if (!r || r.ok === false) {
      setPre("stats", r);
      return;
    }
    var s = r.stats || {};
    var all = s.all_time || {};
    var lines = [];
    lines.push({ k: "all_time.total", v: String(all.total || 0) });
    lines.push({ k: "all_time.success", v: String(all.success || 0) });
    lines.push({ k: "all_time.fail", v: String(all.fail || 0) });
    lines.push({ k: "all_time.unknown", v: String(all.unknown || 0) });
    lines.push({ k: "all_time.canceled", v: String(all.canceled || 0) });

    (s.windows || []).forEach(function (w) {
      var d = w.days;
      lines.push({ k: String(d) + "d.total", v: String(w.total || 0) });
      lines.push({ k: String(d) + "d.success", v: String(w.success || 0) });
      lines.push({ k: String(d) + "d.fail", v: String(w.fail || 0) });
      lines.push({ k: String(d) + "d.unknown", v: String(w.unknown || 0) });
      lines.push({ k: String(d) + "d.canceled", v: String(w.canceled || 0) });
    });

    var html = lines.map(function (x) {
      return (
        "<div class=\"rowline\">" +
          "<span class=\"k\">" + escapeHtml(x.k) + "</span>" +
          "<span class=\"v\">" + escapeHtml(x.v) + "</span>" +
        "</div>"
      );
    }).join("");
    el("stats").innerHTML = html;
  });
}

function refreshJobs() {
  apiGet("/api/jobs").then(function (r) {
    if (!r || r.ok === false) {
      setPre("jobsList", r);
      renderActiveJob([]);
      return;
    }
    var jobs = r.jobs || [];

    var active = jobs.find(function (j) {
      return j.status === "running";
    }) || null;
    var activeId = active ? String(active.job_id || "") : "";

    var idleAutoSelect = !!(cfg && cfg.ui && cfg.ui.idle_auto_select_last_job);

    if (!selectedJobId) {
      var saved = loadLiveJobId();
      if (saved) selectedJobId = saved;
    }

    if (!selectedJobId && activeId) {
      selectedJobId = activeId;
      saveLiveJobId(selectedJobId);
      suppressIdleOutput = false;
    }

    if (!selectedJobId && jobs.length && idleAutoSelect) {
      jobs.sort(function (a, b) {
        return String(a.created_utc || "").localeCompare(String(b.created_utc || ""));
      });
      selectedJobId = String(jobs[jobs.length - 1].job_id || "");
      if (selectedJobId) saveLiveJobId(selectedJobId);
      suppressIdleOutput = false;
    }
    renderActiveJob(jobs);
    ensureAutoRefresh(jobs);

    var html = jobs.map(function (j) {
      var jobId = String(j.job_id || "");
      var isSel = selectedJobId && String(selectedJobId) === jobId;
      var cls = "item job-item" + (isSel ? " selected" : "");

      var issueId = String(j.issue_id || "").trim();
      var issueText = issueId ? ("#" + issueId) : "(no issue)";

      var stRaw = String(j.status || "").trim().toLowerCase();
      var statusText = stRaw ? stRaw.toUpperCase() : "UNKNOWN";
      var statusCls = "job-status st-" + (stRaw || "unknown");

      var commit = jobSummaryCommit(j.commit_message || "");
      var patchName = jobSummaryPatchName(j.patch_path || "");

      var metaParts = [];
      metaParts.push("mode=" + String(j.mode || ""));
      if (patchName) metaParts.push("patch=" + patchName);

      var dur = jobSummaryDurationSeconds(j.started_utc, j.ended_utc);
      if (dur) metaParts.push("dur=" + dur + "s");

      var meta = metaParts.join(" | ");

      var line = "<div class=\"" + cls + "\">";
      line += (
        "<div class=\"name job-name\" data-jobid=\"" +
          escapeHtml(jobId) +
          "\">"
      );
      line += "<div class=\"job-lines\">";
      line += "<div class=\"job-top\">";
      line += "<span class=\"job-issue\">" + escapeHtml(issueText) + "</span>";
      line += (
        "<span class=\"" + statusCls + "\">" +
          escapeHtml(statusText) +
          "</span>"
      );
      line += "</div>";
      line += "<div class=\"job-mid\">";
      if (commit) {
        line += "<span class=\"job-commit\">" + escapeHtml(commit) + "</span>";
      }
      line += "</div>";
      line += "<div class=\"job-bot\">";
      line += "<span class=\"job-meta\">" + escapeHtml(meta) + "</span>";
      line += "</div>";
      line += "</div>";
      line += "</div>";

      line += "<div class=\"actions\">";
      line += (
        "<a class=\"linklike\" href=\"/api/jobs/" +
          encodeURIComponent(jobId) +
          "/events\">events</a>"
      );
      line += " ";
      line += (
        "<a class=\"linklike\" href=\"/api/jobs/" +
          encodeURIComponent(jobId) +
          "/log_tail\">log</a>"
      );
      line += "</div>";
      line += "</div>";
      return line;
    }).join("");

    el("jobsList").innerHTML = html || "<div class=\"muted\">(none)</div>";

    Array.from(el("jobsList").querySelectorAll(".job-name")).forEach(function (n) {
      n.addEventListener("click", function () {
        var jid = n.getAttribute("data-jobid") || "";
        if (!jid) return;
        selectedJobId = String(jid);
        saveLiveJobId(selectedJobId);
        suppressIdleOutput = false;
        openLiveStream(selectedJobId);
        refreshTail();
        refreshJobs();
      });
    });
  });
}




  window.PatchHubRefresh = {
    refreshFs: refreshFs,
    refreshRuns: refreshRuns,
    refreshLastRunLog: refreshLastRunLog,
    refreshTail: refreshTail,
    refreshStats: refreshStats,
    refreshHeader: refreshHeader,
    refreshJobs: refreshJobs
  };
})();
