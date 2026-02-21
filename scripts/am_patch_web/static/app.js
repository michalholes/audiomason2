(function () {
  "use strict";

  var activeJobId = null;
  var autoRefreshTimer = null;

    var previewVisible = false;

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

  var cfg = null;
  var issueRegex = null;
  var fsSelected = "";
  var fsChecked = {};
  var fsLastRels = [];
  var runsCache = [];
  var selectedRun = null;
  var tailLines = 200;

  var dirty = { issueId: false, commitMsg: false, patchPath: false };
  var latestToken = "";
  var autofillTimer = null;

  var lastParsedRaw = "";
  var lastParsed = null;
  var parseInFlight = false;
  var parseTimer = null;
  var parseSeq = 0;

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
    validateAndPreview();

    parseSeq += 1;
    var mySeq = parseSeq;
    apiPost("/api/parse_command", { raw: raw }).then(function (r) {
      if (mySeq !== parseSeq) return;
      parseInFlight = false;

      if (!r || r.ok === false) {
        clearParsedState();
        setParseHint("Parse failed: " + String((r && r.error) || ""));
        validateAndPreview();
        return;
      }

      lastParsedRaw = raw;
      lastParsed = r;
      setParseHint("");

      setPreviewVisible(true);

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
    var linesQ = encodeURIComponent(String(tailLines));
    var url = "/api/runner/tail?lines=" + linesQ;
    if (activeJobId) {
      url = "/api/jobs/" + encodeURIComponent(String(activeJobId)) + "/log_tail?lines=" + linesQ;
    }
    apiGet(url).then(function (r) {
      if (!r || r.ok === false) {
        setPre("tail", r);
        return;
      }
      var t = String(r.tail || "");
      setPre("tail", t);
      updateShortProgressFromText(t);
    });
  }

  function updateShortProgressFromText(text) {
    var lines = String(text || "").split(/\r?\n/);
    var stage = "(idle)";
    for (var i = lines.length - 1; i >= 0; i--) {
      var s = String(lines[i] || "").trim();
      if (!s) continue;
      if (s.indexOf("RESULT:") === 0) { stage = s; break; }
      if (s.indexOf("STATUS:") === 0) { stage = s; break; }
      if (s.indexOf("DO:") === 0) { stage = s; break; }
    }
    setText("progress", stage);
  }

  function refreshStats() {
    apiGet("/api/debug/diagnostics").then(function (r) {
      if (!r || r.ok === false) {
        setPre("stats", r);
        return;
      }
      var s = (r.stats || {});
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

      el("stats").innerHTML = lines.map(function (x) {
        return "<div class=\"rowline\"><span class=\"k\">" + escapeHtml(x.k) + "</span><span class=\"v\">" + escapeHtml(x.v) + "</span></div>";
      }).join("");
    });
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
          refreshJobs();
        });
      });
    }
  }

  function refreshJobs() {
    apiGet("/api/jobs").then(function (r) {
      if (!r || r.ok === false) {
        setPre("jobsList", r);
        renderActiveJob([]);
        return;
      }
      var jobs = r.jobs || [];
      renderActiveJob(jobs);
      ensureAutoRefresh();

      var html = jobs.map(function (j) {
        var line = "<div class=\"item\">";
        line += "<span class=\"name\">" + escapeHtml(j.status || "") + " " + escapeHtml(j.job_id || "") + "</span>";
        line += "<span class=\"actions\"><span class=\"muted\">" + escapeHtml(j.mode || "") + "</span></span>";
        line += "</div>";
        return line;
      }).join("");

      el("jobsList").innerHTML = html || "<div class=\"muted\">(none)</div>";
    });
  }


  function ensureAutoRefresh() {
    if (activeJobId) {
      if (!autoRefreshTimer) {
        autoRefreshTimer = setInterval(function () {
          refreshTail(tailLines);
          refreshJobs();
          refreshRuns();
        }, 1000);
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
      return argv;
    }
    if (mode === "finalize_workspace") {
      argv.push("-w");
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

  function setStartFormEnabled(enabled) {
    el("issueId").disabled = !enabled;
    el("commitMsg").disabled = !enabled;
    el("patchPath").disabled = !enabled;
    var browse = el("browsePatch");
    if (browse) browse.disabled = !enabled;
  }

  function validateAndPreview() {
    var mode = String(el("mode").value || "patch");
    var issueId = String(el("issueId").value || "").trim();
    var commitMsg = String(el("commitMsg").value || "").trim();
    var patchPath = normalizePatchPath(String(el("patchPath").value || ""));
    el("patchPath").value = patchPath;

    var raw = getRawCommand();

    var needsFields = (mode === "patch" || mode === "repair");
    setStartFormEnabled(needsFields);

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
      if (needsFields) {
        ok = !!commitMsg && !!patchPath;
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
        hint2.textContent = ok ? "" : "missing fields";
      }
    }
  }

  function enqueue() {
    var mode = String(el("mode").value || "patch");
    var body = {
      mode: mode,
      raw_command: (el("rawCommand") ? String(el("rawCommand").value || "").trim() : "")
    };

    if (mode === "patch" || mode === "repair") {
      body.issue_id = String(el("issueId").value || "").trim();
      body.commit_message = String(el("commitMsg").value || "").trim();
      body.patch_path = normalizePatchPath(String(el("patchPath").value || "").trim());
    }

    apiPost("/api/jobs/enqueue", body).then(function (r) {
      setPre("previewRight", r);
      setPreviewVisible(true);
      refreshJobs();
    });
  }

  function uploadFile(file) {
    var fd = new FormData();
    fd.append("file", file);
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
        setText(
          "uploadHint",
          (j && j.ok)
            ? ("Uploaded: " + String(j.stored_rel_path || ""))
            : ("Upload failed: " + String((j && j.error) || ""))
        );
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

  function pollLatestPatchOnce() {
    if (!cfg || !cfg.autofill || !cfg.autofill.enabled) return;
    apiGet("/api/patches/latest").then(function (r) {
      if (!r || r.ok === false) return;
      if (!r.found) return;
      var token = String(r.token || "");
      if (!token || token === latestToken) return;
      latestToken = token;
      applyAutofillFromPayload(r);
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
      if (cfg && cfg.paths && cfg.paths.patches_root) meta += " | patches: " + cfg.paths.patches_root;
      meta += " | " + held;
      if (pct) meta += " | " + pct;

      if (el("hdrMeta")) el("hdrMeta").textContent = meta;
    });
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

  function wireButtons() {
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
            return apiPost("/api/fs/delete", { path: p });
          });
        });
        seq.then(function () {
          fsClearSelection();
          fsSelected = "";
          refreshFs();
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
    el("tailRefresh").addEventListener("click", function () { refreshTail(tailLines); });
    el("tailMore").addEventListener("click", function () { refreshTail((tailLines || 200) + 200); });

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
        refreshTail(200);
        refreshLastRunLog();
        refreshHeader();
        renderIssueDetail();
        validateAndPreview();
      });
    }

    function quickOpen(path) {
      el("fsPath").value = path;
      fsSelected = "";
      setFsHint("");
      refreshFs();
    }

    if (el("qaIncoming")) el("qaIncoming").addEventListener("click", function () { quickOpen("incoming"); });
    if (el("qaLogs")) el("qaLogs").addEventListener("click", function () { quickOpen("logs"); });
    if (el("qaSuccessful")) el("qaSuccessful").addEventListener("click", function () { quickOpen("successful"); });
    if (el("qaArtifacts")) el("qaArtifacts").addEventListener("click", function () { quickOpen("artifacts"); });
  }

  function init() {
    setupUpload();
    wireButtons();
    setPreviewVisible(false);

    loadConfig().then(function () {
      refreshFs();
      refreshRuns();
      refreshLastRunLog();
      refreshTail(200);
      refreshStats();
      refreshJobs();
      refreshHeader();
      renderIssueDetail();
      validateAndPreview();
      startAutofillPolling();

      setInterval(function () {
        refreshJobs();
        refreshLastRunLog();
      }, 2000);

      setInterval(function () {
        refreshHeader();
      }, 5000);
    });
  }

  window.addEventListener("load", init);
})();
