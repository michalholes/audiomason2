from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest


def _run_node_scenario(body: str) -> dict[str, object]:
    node = shutil.which("node")
    if not node:
        pytest.skip("node not installed")
    repo_root = Path(__file__).resolve().parents[1]
    progress_path = repo_root / "scripts" / "patchhub" / "static" / "patchhub_progress_ui.js"
    live_path = repo_root / "scripts" / "patchhub" / "static" / "patchhub_live_ui.js"
    jobs_path = repo_root / "scripts" / "patchhub" / "static" / "app_part_jobs.js"
    script = f"""
const fs = require("fs");
const vm = require("vm");
const progressSrc = fs.readFileSync({json.dumps(str(progress_path))}, "utf8");
const liveSrc = fs.readFileSync({json.dumps(str(live_path))}, "utf8");
const jobsSrc = fs.readFileSync({json.dumps(str(jobs_path))}, "utf8");
const elements = new Map();
const registry = new Map();
function makeClassList() {{
  const items = new Set();
  return {{
    add: (...names) => names.forEach((name) => items.add(String(name))),
    remove: (...names) => names.forEach((name) => items.delete(String(name))),
    toggle: (name, force) => {{
      const key = String(name);
      const enabled = force === undefined ? !items.has(key) : !!force;
      if (enabled) items.add(key);
      else items.delete(key);
      return enabled;
    }},
    contains: (name) => items.has(String(name)),
  }};
}}
function makeNode(id) {{
  return {{
    id,
    innerHTML: "",
    textContent: "",
    value: "",
    parentElement: {{ classList: makeClassList() }},
    classList: makeClassList(),
    addEventListener() {{}},
    removeEventListener() {{}},
    appendChild() {{}},
    focus() {{}},
  }};
}}
const fixedNow = new Date("2026-03-14T08:00:05Z").getTime();
Date.now = () => fixedNow;
global.window = {{
  AMP_PATCHHUB_UI: {{}},
  __ph_last_enqueued_mode: "",
  __ph_last_enqueued_job_id: "",
  PH: {{
    register(name, exports) {{
      registry.set(String(name), exports || {{}});
    }},
    call(name, ...args) {{
      for (const exports of registry.values()) {{
        if (exports && typeof exports[name] === "function") {{
          return exports[name](...args);
        }}
      }}
      return null;
    }},
  }},
  localStorage: {{
    _store: new Map(),
    getItem(key) {{
      return this._store.has(String(key)) ? this._store.get(String(key)) : null;
    }},
    setItem(key, value) {{
      this._store.set(String(key), String(value));
    }},
  }},
}};
global.localStorage = global.window.localStorage;
global.document = {{
  hidden: false,
  getElementById(id) {{
    if (!elements.has(String(id))) elements.set(String(id), makeNode(String(id)));
    return elements.get(String(id));
  }},
}};
global.el = (id) => global.document.getElementById(id);
global.escapeHtml = (value) => String(value)
  .replace(/&/g, "&amp;")
  .replace(/</g, "&lt;")
  .replace(/>/g, "&gt;")
  .replace(/\"/g, "&quot;");
global.cfg = {{ ui: {{ idle_auto_select_last_job: false }} }};
global.selectedJobId = "";
global.suppressIdleOutput = false;
global.idleSigs = {{ jobs: "", runs: "", workspaces: "", hdr: "", snapshot: "" }};
global.autoRefreshTimer = null;
global.idleNextDueMs = 0;
global.IDLE_BACKOFF_MS = [1000];
global.setInterval = () => 1;
global.clearInterval = () => {{}};
global.dirty = {{ issueId: false, commitMsg: false, patchPath: false }};
global.normalizePatchPath = (value) => String(value || "");
global.apiGet = () => Promise.resolve({{ ok: true }});
global.apiGetETag = () => Promise.resolve({{ ok: true, unchanged: true }});
global.setUiStatus = () => {{}};
global.setUiError = () => {{}};
global.setParseHint = () => {{}};
global.clearParsedState = () => {{}};
global.setPre = (id, payload) => {{
  global.document.getElementById(id).textContent = JSON.stringify(payload);
}};
global.fetch = (url) => Promise.resolve({{
  status: 200,
  text: () =>
    Promise.resolve(
      JSON.stringify({{
        ok: true,
        job: {{
          job_id: "job-42",
          status: "running",
          applied_files: [],
        }},
      }}),
    ),
}});
global.EventSource = function() {{
  this.addEventListener = () => {{}};
  this.close = () => {{}};
}};
vm.runInThisContext(progressSrc, {{ filename: {json.dumps(str(progress_path))} }});
vm.runInThisContext(liveSrc, {{ filename: {json.dumps(str(live_path))} }});
vm.runInThisContext(jobsSrc, {{ filename: {json.dumps(str(jobs_path))} }});
const ui = global.window.AMP_PATCHHUB_UI;
(async () => {{
{body}
}})().catch((err) => {{
  console.error(err && err.stack ? err.stack : String(err));
  process.exit(1);
}});
"""
    proc = subprocess.run([node, "-e", script], cwd=repo_root, capture_output=True, text=True)
    if proc.returncode != 0:
        raise AssertionError(proc.stderr or proc.stdout)
    return json.loads(proc.stdout)


def test_progress_skip_surface_and_active_elapsed_timer() -> None:
    result = _run_node_scenario(
        """
ui.saveLiveJobId("job-42");
ui.liveEvents.push(
  {
    type: "log",
    kind: "DO",
    stage: "GATE_JS",
    msg: "DO: GATE_JS",
  },
  {
    type: "log",
    ch: "CORE",
    sev: "WARNING",
    kind: "TEXT",
    msg: "gate_js=SKIP (no_js_touched)",
  },
  {
    type: "log",
    kind: "OK",
    stage: "GATE_JS",
    msg: "OK: GATE_JS",
  },
);
const jobs = [
  {
    job_id: "job-42",
    status: "running",
    mode: "patch",
    issue_id: "322",
    started_utc: "2026-03-14T08:00:00Z",
  },
];
await ui.updateProgressPanelFromEvents({ jobs });
process.stdout.write(
  JSON.stringify({
    progressHtml: document.getElementById("progressSteps").innerHTML,
    summaryText: document.getElementById("progressSummary").textContent,
    activeHtml: document.getElementById("activeJob").innerHTML,
    elapsed: ui.jobSummaryDurationSeconds("2026-03-14T08:00:00Z", ""),
  }),
);
""",
    )
    assert "GATE_JS" in result["progressHtml"]
    assert "SKIPPED (no_js_touched)" in result["progressHtml"]
    assert result["summaryText"] == "SKIP: GATE_JS (no_js_touched)"
    assert "elapsed=5s" in result["activeHtml"]
    assert result["elapsed"] == "5"


def test_jobs_list_elapsed_only_for_tracked_active_row() -> None:
    result = _run_node_scenario(
        """
ui.saveLiveJobId("job-42");
window.PH.call("renderJobsFromResponse", {
  ok: true,
  jobs: [
    {
      job_id: "job-42",
      status: "running",
      mode: "patch",
      issue_id: "322",
      commit_summary: "tracked",
      started_utc: "2026-03-14T08:00:00Z",
    },
    {
      job_id: "job-77",
      status: "queued",
      mode: "patch",
      issue_id: "400",
      commit_summary: "other",
      started_utc: "2026-03-14T08:00:00Z",
    },
    {
      job_id: "job-88",
      status: "success",
      mode: "patch",
      issue_id: "500",
      commit_summary: "finished",
      started_utc: "2026-03-14T08:00:00Z",
      ended_utc: "2026-03-14T08:00:03Z",
    },
  ],
});
process.stdout.write(
  JSON.stringify({
    jobsHtml: document.getElementById("jobsList").innerHTML,
  }),
);
""",
    )
    assert "tracked" in result["jobsHtml"]
    assert "dur=5s" in result["jobsHtml"]
    assert "finished" in result["jobsHtml"]
    assert "dur=3s" in result["jobsHtml"]
    assert 'other</div><div class="job-meta">mode=patch</div>' in result["jobsHtml"]
