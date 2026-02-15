(function () {
  "use strict";

  function el(id) { return document.getElementById(id); }

  var netlog = [];
  function logNet(entry) {
    netlog.push(entry);
    if (netlog.length > 200) netlog.shift();
  }

  function apiGet(url) {
    var started = Date.now();
    return fetch(url, { headers: { "Accept": "application/json" } })
      .then(function (r) {
        return r.text().then(function (t) {
          logNet({ method: "GET", url: url, status: r.status, ms: Date.now() - started });
          try { return JSON.parse(t); } catch (e) { return { ok: false, error: "bad json", raw: t }; }
        });
      })
      .catch(function (e) {
        logNet({ method: "GET", url: url, status: 0, ms: Date.now() - started, error: String(e) });
        throw e;
      });
  }

  function apiPost(url, obj) {
    var started = Date.now();
    return fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json", "Accept": "application/json" },
      body: JSON.stringify(obj)
    }).then(function (r) {
      return r.text().then(function (t) {
        logNet({ method: "POST", url: url, status: r.status, ms: Date.now() - started });
        try { return JSON.parse(t); } catch (e) { return { ok: false, error: "bad json", raw: t }; }
      });
    });
  }

  function setPre(id, obj) {
    el(id).textContent = typeof obj === "string" ? obj : JSON.stringify(obj, null, 2);
  }

  function joinRel(base, name) {
    base = (base || "").replace(/^\/+/, "").replace(/\/+$/, "");
    name = (name || "").replace(/^\/+/, "");
    if (!base) return name;
    if (!name) return base;
    return base + "/" + name;
  }

  function parentRel(p) {
    p = (p || "").replace(/^\/+/, "").replace(/\/+$/, "");
    if (!p) return "";
    var idx = p.lastIndexOf("/");
    return idx >= 0 ? p.slice(0, idx) : "";
  }

  function normalizePatchPath(p) {
    p = (p || "").trim();
    if (!p) return "";
    if (p.indexOf("patches/") === 0) return p;
    return "patches/" + p.replace(/^\/+/, "");
  }

  var fsSelected = "";
  var cfg = null;
  var issueRegex = null;
  var runsCache = [];
  var selectedRun = null;


  function setFsHint(msg) {
    var h = el("fsHint");
    if (h) h.textContent = msg || "";
  }

  function refreshFs() {
    var path = el("fsPath").value || "";
    apiGet("/api/fs/list?path=" + encodeURIComponent(path)).then(function (r) {
      if (!r.ok) {
        setPre("fsList", r);
        return;
      }
      var items = r.items || [];
      var html = items.map(function (it) {
        var name = it.name;
        var isDir = it.is_dir;
        var rel = joinRel(path, name);
        var sel = (fsSelected === rel) ? "*" : "";
        var act = "";
        if (!isDir) {
          act += "<a class=\"linklike\" href=\"/api/fs/download?path=" + encodeURIComponent(rel) + "\" title=\"Download\">dl</a>";
        }
        return (
          "<div class=\"item\" data-rel=\"" + rel + "\" data-isdir=\"" + (isDir ? "1" : "0") + "\">" +
          "<span class=\"name\">" + (isDir ? "[d] " : "[f] ") + name + " " + sel + "</span>" +
          "<span class=\"actions\"><span class=\"muted\">" + it.size + "</span>" + act + "</span>" +
          "</div>"
        );
      }).join("");
      el("fsList").innerHTML = html || "<div class=\"muted\">(empty)</div>";

      Array.from(el("fsList").querySelectorAll(".item .name")).forEach(function (node) {
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
          setFsHint("selected: " + rel);
          // If it's a plausible patch file, prefill patchPath.
          if (/\.(zip|patch|diff)$/i.test(rel)) {
            el("patchPath").value = normalizePatchPath(rel);
            // Try to auto-extract issue id.
            var m = null;
            if (issueRegex) {
              try { m = issueRegex.exec(rel); } catch (e) { m = null; }
            }
            if (!m) {
              var m2 = /(?:issue_|#)(\d+)/i.exec(rel) || /(\d{3,6})/.exec(rel);
              m = m2;
            }
            if (m && m[1] && !el("issueId").value.trim()) {
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
    var issue = el("runsIssue").value.trim();
    var res = el("runsResult").value;
    if (issue) q.push("issue_id=" + encodeURIComponent(issue));
    if (res) q.push("result=" + encodeURIComponent(res));
    q.push("limit=80");
    apiGet("/api/runs?" + q.join("&")).then(function (r) {
      if (!r.ok) { setPre("runsList", r); return; }
      runsCache = r.runs || [];
      var html = runsCache.map(function (x, idx) {
        var log = x.log_rel_path || "";
        var link = log ? "<a class="linklike" href="/api/fs/download?path=" + encodeURIComponent(log) + "">log</a>" : "";
        var sel = (selectedRun && selectedRun.issue_id === x.issue_id && selectedRun.mtime_utc === x.mtime_utc) ? " *" : "";
        return (
          "<div class="item runitem" data-idx="" + String(idx) + "">" +
          "<span class="name">#" + x.issue_id + " " + x.result + sel + "</span>" +
          "<span class="actions">" + link + " <span class="muted">" + x.mtime_utc + "</span></span>" +
          "</div>"
        );
      }).join("");
      el("runsList").innerHTML = html || "<div class="muted">(none)</div>";

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

  function refreshTail(lines);
  }

  function refreshTail(lines) {
    apiGet("/api/runner/tail?lines=" + encodeURIComponent(String(lines || 200))).then(function (r) {
      if (!r.ok) { setPre("tail", r); return; }
      var t = r.tail || "";
      setPre("tail", t);
      updateShortProgressFromTail(t);
    });
  }

  function updateShortProgressFromTail(tailText) {
    var lines = String(tailText || "").split(/
?
/);
    var stage = "(idle)";
    for (var i = lines.length - 1; i >= 0; i--) {
      var s = (lines[i] || "").trim();
      if (!s) continue;
      if (s.indexOf("RESULT:") === 0) { stage = s; break; }
      if (s.indexOf("STATUS:") === 0) { stage = s; break; }
      if (s.indexOf("DO:") === 0) { stage = s; break; }
    }
    if (el("progress")) el("progress").textContent = stage;
  }

  function refreshStats()

  function refreshStats() {
    apiGet("/api/debug/diagnostics").then(function (r) {
      if (!r || r.ok === false) {
        el("stats").textContent = JSON.stringify(r, null, 2);
        return;
      }
      var s = (r.stats || {});
      var all = s.all_time || {};
      var lines = [];
      lines.push({ k: "all_time.total", v: String(all.total || 0) });
      lines.push({ k: "all_time.success", v: String(all.success || 0) });
      lines.push({ k: "all_time.fail", v: String(all.fail || 0) });
      lines.push({ k: "all_time.unknown", v: String(all.unknown || 0) });
      (s.windows || []).forEach(function (w) {
        var d = w.days;
        lines.push({ k: "" + d + "d.total", v: String(w.total || 0) });
        lines.push({ k: "" + d + "d.success", v: String(w.success || 0) });
        lines.push({ k: "" + d + "d.fail", v: String(w.fail || 0) });
        lines.push({ k: "" + d + "d.unknown", v: String(w.unknown || 0) });
      });
      el("stats").innerHTML = lines.map(function (x) {
        return "<div class=\"rowline\"><span class=\"k\">" + x.k + "</span><span class=\"v\">" + x.v + "</span></div>";
      }).join("");
    });
  }

  function renderActiveJob(jobs) {
    var active = (jobs || []).find(function (j) { return j.status === "running"; }) || null;
    var queued = (jobs || []).filter(function (j) { return j.status === "queued"; });

    var box = el("activeJob");
    var prog = el("progress");

    if (!box) return;

    if (!active) {
      box.textContent = queued.length ? ("queued: " + queued.length) : "(none)";
      if (prog) prog.textContent = queued.length ? "queued" : "(idle)";
      return;
    }

    var msg = "job " + active.job_id;
    if (active.issue_id) msg += " (issue " + active.issue_id + ")";
    msg += " / " + active.mode;
    box.textContent = msg;
    if (prog) prog.textContent = "running";
  }

  function refreshJobs() {
    apiGet("/api/jobs").then(function (r) {
      if (!r.ok) { setPre("jobsList", r); return; }
      var jobs = r.jobs || [];
      renderActiveJob(jobs);

      var html = jobs.map(function (j) {
        var cancel = (j.status === "queued" || j.status === "running") ? "<button class=\"btn btn-small\" data-cancel=\"" + j.job_id + "\">Cancel</button>" : "";
        var tail = "<button class=\"btn btn-small\" data-tail=\"" + j.job_id + "\">Tail</button>";
        return "<div class=\"item\"><span>" + j.job_id + " " + j.status + "</span><span>" + tail + " " + cancel + "</span></div>";
      }).join("");
      el("jobsList").innerHTML = html || "<div class=\"muted\">(none)</div>";

      Array.from(el("jobsList").querySelectorAll("button[data-cancel]"))
        .forEach(function (b) {
          b.addEventListener("click", function () {
            var id = b.getAttribute("data-cancel");
            apiPost("/api/jobs/" + id + "/cancel", {}).then(function () {
              refreshJobs();
            });
          });
        });

      Array.from(el("jobsList").querySelectorAll("button[data-tail]"))
        .forEach(function (b) {
          b.addEventListener("click", function () {
            var id = b.getAttribute("data-tail");
            apiGet("/api/jobs/" + id + "/log_tail?lines=200").then(function (x) {
              setPre("preview", x.tail || "");
            });
          });
        });
    });
  }

  function renderIssueDetail() {
    var title = el("issueDetailTitle");
    var tabs = el("issueTabs");
    var content = el("issueTabContent");
    var links = el("issueTabLinks");
    var body = el("issueTabBody");

    if (!selectedRun) {
      if (title) title.textContent = "Select a run on the left.";
      if (tabs) tabs.style.display = "none";
      if (content) content.style.display = "none";
      return;
    }

    if (title) title.textContent = "Issue " + selectedRun.issue_id + " / " + selectedRun.result + " / " + selectedRun.mtime_utc;
    if (tabs) tabs.style.display = "flex";
    if (content) content.style.display = "block";

    function link(label, rel) {
      if (!rel) return "";
      return "<a class="linklike" href="/api/fs/download?path=" + encodeURIComponent(rel) + "">" + label + "</a>";
    }

    function setTab(name) {
      ["Overview", "Logs", "Patch", "Diff", "Files"].forEach(function (n) {
        var b = el("tab" + n);
        if (!b) return;
        if (n === name) b.classList.add("active");
        else b.classList.remove("active");
      });

      if (!links || !body) return;

      var logRel = selectedRun.log_rel_path || "";
      var archived = selectedRun.archived_patch_rel_path || "";
      var diffb = selectedRun.diff_bundle_rel_path || "";
      var successZip = selectedRun.success_zip_rel_path || (cfg && cfg.runner ? cfg.runner.success_archive_rel : "");

      if (name === "Overview") {
        links.innerHTML = [
          link("log", logRel),
          link("archived patch", archived),
          link("issue diff", diffb),
          link("latest success zip", successZip)
        ].filter(Boolean).join(" | ");
        body.textContent = JSON.stringify(selectedRun, null, 2);
        return;
      }

      if (name === "Logs") {
        links.innerHTML = [link("download log", logRel)].filter(Boolean).join(" | ");
        body.textContent = "Log is downloadable via link above.

For live runner tail, use the right panel.";
        return;
      }

      if (name === "Patch") {
        links.innerHTML = [link("download archived patch", archived)].filter(Boolean).join(" | ");
        body.textContent = archived ? ("Archived patch: " + archived) : "No archived patch found.";
        return;
      }

      if (name === "Diff") {
        links.innerHTML = [link("download issue diff bundle", diffb)].filter(Boolean).join(" | ");
        body.textContent = diffb ? ("Issue diff bundle: " + diffb) : "No issue diff bundle found.";
        return;
      }

      if (name === "Files") {
        links.innerHTML = "";
        body.textContent = "Use the Files panel above to browse patches/.";
        return;
      }
    }

    setTab("Overview");

    if (el("tabOverview")) el("tabOverview").onclick = function () { setTab("Overview"); };
    if (el("tabLogs")) el("tabLogs").onclick = function () { setTab("Logs"); };
    if (el("tabPatch")) el("tabPatch").onclick = function () { setTab("Patch"); };
    if (el("tabDiff")) el("tabDiff").onclick = function () { setTab("Diff"); };
    if (el("tabFiles")) el("tabFiles").onclick = function () { setTab("Files"); };
  }

  function rawLooksLikeRunnerCommand(raw) {
    raw = (raw || "").trim();
    if (!raw) return false;
    if (raw.indexOf("scripts/am_patch.py") >= 0) return true;
    if (/\bam_patch\.py\b/.test(raw)) return true;
    return false;
  }

  function validateAndPreview() {
    var mode = el("mode").value;
    var raw = el("rawCommand") ? el("rawCommand").value.trim() : "";

    if (raw && rawLooksLikeRunnerCommand(raw)) {
      apiPost("/api/parse_command", { raw: raw }).then(function (r) {
        setPre("preview", r);
        el("enqueueBtn").disabled = !r.ok;
        var hint = el("enqueueHint");
        if (hint) hint.textContent = r.ok ? "" : (r.error || "invalid");
      });
      return;
    }

    var issueId = el("issueId").value.trim();
    var commitMsg = el("commitMsg").value.trim();
    var patchPath = normalizePatchPath(el("patchPath").value);
    el("patchPath").value = patchPath;

    var ok = true;
    if (mode === "patch" || mode === "repair") {
      ok = !!commitMsg && !!patchPath;
    }

    var preview = { mode: mode, issue_id: issueId, commit_message: commitMsg, patch_path: patchPath };
    setPre("preview", preview);
    el("enqueueBtn").disabled = !ok;
    var hint2 = el("enqueueHint");
    if (hint2) hint2.textContent = ok ? "" : "missing fields";
  }

  function enqueue() {
    var body = {
      mode: el("mode").value,
      issue_id: el("issueId").value.trim(),
      commit_message: el("commitMsg").value.trim(),
      patch_path: normalizePatchPath(el("patchPath").value.trim()),
      raw_command: (el("rawCommand") ? el("rawCommand").value.trim() : "")
    };
    apiPost("/api/jobs/enqueue", body).then(function (r) {
      setPre("preview", r);
      refreshJobs();
    });
  }

  function setupUpload() {
    var zone = el("uploadZone");
    var input = el("uploadInput");

    function doUpload(file) {
      var fd = new FormData();
      fd.append("file", file);
      fetch("/api/upload/patch", { method: "POST", body: fd, headers: { "Accept": "application/json" } })
        .then(function (r) {
          return r.text().then(function (t) {
            try { return JSON.parse(t); } catch (e) { return { ok: false, error: "bad json", raw: t }; }
          });
        })
        .then(function (j) {
          setPre("uploadResult", j);
          if (j && j.stored_rel_path) {
            el("patchPath").value = String(j.stored_rel_path);
            var up = String(j.stored_rel_path || "");
            var parent = parentRel(up.replace(/^patches\//, ""));
            if ((el("fsPath").value || "") === "") {
              el("fsPath").value = parent;
            }
          }
          refreshFs();
          validateAndPreview();
        })
        .catch(function (e) { setPre("uploadResult", String(e)); });
    }

    zone.addEventListener("click", function () { input.click(); });
    input.addEventListener("change", function () {
      if (input.files && input.files[0]) doUpload(input.files[0]);
    });

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
      if (f) doUpload(f);
    });

    // Prevent the browser from opening the file when dropped outside the zone.
    window.addEventListener("dragover", function (e) { e.preventDefault(); });
    window.addEventListener("drop", function (e) { e.preventDefault(); });
  }

  function loadConfig() {
    return apiGet("/api/config").then(function (r) {
      cfg = r || null;
      if (cfg && cfg.issue && cfg.issue.default_regex) {
        try { issueRegex = new RegExp(cfg.issue.default_regex); } catch (e) { issueRegex = null; }
      }
      if (cfg && cfg.server && cfg.server.host && cfg.server.port) {
        var meta = "server: " + cfg.server.host + ":" + cfg.server.port;
        if (cfg.paths && cfg.paths.patches_root) meta += " | patches: " + cfg.paths.patches_root;
        if (el("hdrMeta")) el("hdrMeta").textContent = meta;
      }
      return cfg;
    }).catch(function () { return null; });
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

  function wireButtons() {
    el("fsRefresh").addEventListener("click", refreshFs);
    el("fsUp").addEventListener("click", function () {
      var p = el("fsPath").value || "";
      el("fsPath").value = parentRel(p);
      fsSelected = "";
      setFsHint("");
      refreshFs();
    });
    el("fsMkdir").addEventListener("click", function () {
      var base = el("fsPath").value || "";
      var name = window.prompt("mkdir name (ASCII)", "new_dir");
      if (!name) return;
      apiPost("/api/fs/mkdir", { path: joinRel(base, name) }).then(function (r) {
        setFsHint(r.ok ? "mkdir ok" : (r.error || "mkdir failed"));
        refreshFs();
      });
    });
    el("fsRename").addEventListener("click", function () {
      if (!fsSelected) { setFsHint("select a file or dir"); return; }
      var dst = window.prompt("rename to (relative to patches root)", fsSelected);
      if (!dst) return;
      apiPost("/api/fs/rename", { src: fsSelected, dst: dst }).then(function (r) {
        setFsHint(r.ok ? "rename ok" : (r.error || "rename failed"));
        if (r.ok) fsSelected = dst;
        refreshFs();
      });
    });
    el("fsDelete").addEventListener("click", function () {
      if (!fsSelected) { setFsHint("select a file or dir"); return; }
      if (!window.confirm("delete " + fsSelected + " ?")) return;
      apiPost("/api/fs/delete", { path: fsSelected }).then(function (r) {
        setFsHint(r.ok ? "delete ok" : (r.error || "delete failed"));
        fsSelected = "";
        refreshFs();
      });
    });
    el("fsUnzip").addEventListener("click", function () {
      if (!fsSelected) { setFsHint("select a zip file"); return; }
      var dest = window.prompt("unzip dest dir (relative)", parentRel(fsSelected) || "");
      if (dest === null) return;
      apiPost("/api/fs/unzip", { zip_path: fsSelected, dest_dir: dest }).then(function (r) {
        setFsHint(r.ok ? "unzip ok" : (r.error || "unzip failed"));
        refreshFs();
      });
    });

    el("runsRefresh").addEventListener("click", refreshRuns);
    el("tailRefresh").addEventListener("click", function () { refreshTail(200); });
    el("tailMore").addEventListener("click", function () { refreshTail(el("toggleVerbose") && el("toggleVerbose").checked ? 5000 : 1200); });
    el("jobsRefresh").addEventListener("click", refreshJobs);

    if (el("parseBtn")) el("parseBtn").addEventListener("click", validateAndPreview);
    el("enqueueBtn").addEventListener("click", enqueue);

    ["mode", "issueId", "commitMsg", "patchPath"].forEach(function (id) {
      el(id).addEventListener("input", validateAndPreview);
      el(id).addEventListener("change", validateAndPreview);
    });

    if (el("rawCommand")) {
      el("rawCommand").addEventListener("input", validateAndPreview);
      el("rawCommand").addEventListener("change", validateAndPreview);
    }

    if (el("browsePatch")) {
      el("browsePatch").addEventListener("click", function () {
        if (!fsSelected) {
          setFsHint("select a patch file in file manager first");
          return;
        }
        if (!/\.(zip|patch|diff)$/i.test(fsSelected)) {
          setFsHint("selected file is not .zip/.patch/.diff");
          return;
        }
        el("patchPath").value = normalizePatchPath(fsSelected);
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
        refreshHeader();
        renderIssueDetail();
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

    loadConfig().then(function () {
      refreshFs();
      refreshRuns();
      refreshTail(200);
      refreshStats();
      refreshJobs();
      refreshHeader();
      renderIssueDetail();
      validateAndPreview();

      setInterval(function () {
        refreshJobs();
      }, 2000);

      setInterval(function () {
        refreshHeader();
      }, 5000);
    });
  }

  window.addEventListener("load", init);
})();
