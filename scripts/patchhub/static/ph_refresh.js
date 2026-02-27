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
    var html = items.map(function (it) {
      var name = it.name;
      var isDir = !!it.is_dir;
      var rel = joinRel(path, name);
      fsLastRels.push(rel);

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
