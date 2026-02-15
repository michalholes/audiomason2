(function () {
  "use strict";

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

  function el(id) { return document.getElementById(id); }

  var fsSelected = "";

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

  function setFsHint(msg) {
    el("fsHint").textContent = msg || "";
  }

  function setPre(id, obj) {
    el(id).textContent = typeof obj === "string" ? obj : JSON.stringify(obj, null, 2);
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
    q.push("limit=50");
    apiGet("/api/runs?" + q.join("&")).then(function (r) {
      if (!r.ok) { setPre("runsList", r); return; }
      var runs = r.runs || [];
      var html = runs.map(function (x) {
        var log = x.log_rel_path || "";
        var link = log ? "<a class=\"linklike\" href=\"/api/fs/download?path=" + encodeURIComponent(log) + "\">log</a>" : "";
        return "<div class=\"item\"><span>#" + x.issue_id + " " + x.result + " " + link + "</span><span class=\"muted\">" + x.mtime_utc + "</span></div>";
      }).join("");
      el("runsList").innerHTML = html || "<div class=\"muted\">(none)</div>";
    });
  }

  function refreshTail(lines) {
    apiGet("/api/runner/tail?lines=" + encodeURIComponent(String(lines || 200))).then(function (r) {
      if (!r.ok) { setPre("tail", r); return; }
      setPre("tail", r.tail || "");
    });
  }

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

  function refreshJobs() {
    apiGet("/api/jobs").then(function (r) {
      if (!r.ok) { setPre("jobsList", r); return; }
      var jobs = r.jobs || [];
      var html = jobs.map(function (j) {
        var cancel = (j.status === "queued" || j.status === "running") ? "<button class=\"btn\" data-cancel=\"" + j.job_id + "\">Cancel</button>" : "";
        var tail = "<button class=\"btn\" data-tail=\"" + j.job_id + "\">Tail</button>";
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

  function validateAndPreview() {
    var mode = el("mode").value;
    var raw = el("rawCommand").value.trim();

    if (raw) {
      apiPost("/api/parse_command", { raw: raw }).then(function (r) {
        setPre("preview", r);
        el("enqueueBtn").disabled = !r.ok;
        el("enqueueHint").textContent = r.ok ? "" : (r.error || "invalid");
      });
      return;
    }

    var issueId = el("issueId").value.trim();
    var commitMsg = el("commitMsg").value.trim();
    var patchPath = el("patchPath").value.trim();

    var ok = true;
    if (mode === "patch" || mode === "repair") {
      ok = !!commitMsg && !!patchPath;
    }

    var preview = { mode: mode, issue_id: issueId, commit_message: commitMsg, patch_path: patchPath };
    setPre("preview", preview);
    el("enqueueBtn").disabled = !ok;
    el("enqueueHint").textContent = ok ? "" : "missing fields";
  }

  function enqueue() {
    var body = {
      mode: el("mode").value,
      issue_id: el("issueId").value.trim(),
      commit_message: el("commitMsg").value.trim(),
      patch_path: el("patchPath").value.trim(),
      raw_command: el("rawCommand").value.trim()
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
      fetch("/api/upload/patch", { method: "POST", body: fd })
        .then(function (r) { return r.json(); })
        .then(function (j) {
          setPre("uploadResult", j);
          if (j && j.stored_rel_path) {
            el("patchPath").value = j.stored_rel_path;
            var up = (j.stored_rel_path || "");
            var parent = parentRel(up.replace(/^patches\//, ""));
            if (el("fsPath").value === "") {
              el("fsPath").value = parent;
            }
          }
          refreshFs();
        })
        .catch(function (e) { setPre("uploadResult", String(e)); });
    }

    zone.addEventListener("click", function () { input.click(); });
    input.addEventListener("change", function () {
      if (input.files && input.files[0]) doUpload(input.files[0]);
    });

    zone.addEventListener("dragover", function (e) { e.preventDefault(); });
    zone.addEventListener("drop", function (e) {
      e.preventDefault();
      var f = e.dataTransfer.files && e.dataTransfer.files[0];
      if (f) doUpload(f);
    });
  }

  function init() {
    setupUpload();

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
    el("tailMore").addEventListener("click", function () { refreshTail(1200); });
    el("jobsRefresh").addEventListener("click", refreshJobs);

    el("parseBtn").addEventListener("click", validateAndPreview);
    el("enqueueBtn").addEventListener("click", enqueue);

    ["mode", "rawCommand", "issueId", "commitMsg", "patchPath"].forEach(function (id) {
      el(id).addEventListener("input", validateAndPreview);
      el(id).addEventListener("change", validateAndPreview);
    });

    refreshFs();
    refreshRuns();
    refreshTail(200);
    refreshStats();
    refreshJobs();
    validateAndPreview();

    setInterval(function () {
      refreshJobs();
    }, 2000);
  }

  window.addEventListener("load", init);
})();
