(function () {
  "use strict";

  var Core = window.PatchHubCore || {};
  var el = Core.el;
  var escapeHtml = Core.escapeHtml;

function renderAmpSettings() {
  // amp_settings.js owns AMP settings UI. This module is a stub for compatibility.
  if (window.AmpSettings && typeof window.AmpSettings.render === "function") {
    try { window.AmpSettings.render(); } catch (e) {}
  }
}

function parseProgressFromText(text) {
  var lines = String(text || "").split(/\r?\n/);
  var order = [];
  var state = {};
  var currentRunning = "";

  function normStepName(s) {
    return String(s || "").replace(/\s+/g, " ").trim();
  }

  function ensureStep(name) {
    if (!name) return;
    if (!Object.prototype.hasOwnProperty.call(state, name)) {
      state[name] = "pending";
    }
    if (order.indexOf(name) < 0) order.push(name);
  }

  function setState(name, st) {
    name = normStepName(name);
    if (!name) return;
    ensureStep(name);
    state[name] = st;
  }

  for (var i = 0; i < lines.length; i++) {
    var raw = String(lines[i] || "");
    var s = raw.trim();
    if (!s) continue;

    if (s.indexOf("DO:") === 0) {
      var stepDo = normStepName(s.slice(3));
      setState(stepDo, "running");
      currentRunning = stepDo;
      continue;
    }

    if (s.indexOf("OK:") === 0) {
      var stepOk = normStepName(s.slice(3));
      setState(stepOk, "ok");
      if (currentRunning === stepOk) currentRunning = "";
      continue;
    }

    if (s.indexOf("FAIL:") === 0) {
      var stepFail = normStepName(s.slice(5));
      setState(stepFail, "fail");
      if (currentRunning === stepFail) currentRunning = "";
      continue;
    }

    if (s.indexOf("ERROR:") === 0 || s === "FAIL" || s.indexOf("FAIL ") === 0) {
      if (currentRunning) setState(currentRunning, "fail");
      continue;
    }
  }

  if (currentRunning) {
    for (var j = 0; j < order.length; j++) {
      var nm = order[j];
      if (state[nm] === "running" && nm !== currentRunning) {
        state[nm] = "pending";
      }
    }
  }

  for (var k = 0; k < order.length; k++) {
    var nm2 = order[k];
    if (!Object.prototype.hasOwnProperty.call(state, nm2)) state[nm2] = "pending";
  }

  return { order: order, state: state };
}

function pickProgressSummaryLine(text) {
  var lines = String(text || "").split(/\r?\n/);
  for (var i = lines.length - 1; i >= 0; i--) {
    var s = String(lines[i] || "").trim();
    if (!s) continue;

    if (s.indexOf("RESULT:") === 0) return s;
    if (s.indexOf("STATUS:") === 0) return s;
    if (s.indexOf("FAIL:") === 0) return s;
    if (s.indexOf("OK:") === 0) return s;
    if (s.indexOf("DO:") === 0) return s;
  }
  return "(idle)";
}

function renderProgressSteps(progress) {
  var box = el("progressSteps");
  if (!box) return;

  var order = (progress && progress.order) ? progress.order : [];
  var state = (progress && progress.state) ? progress.state : {};

  if (!order.length) {
    box.innerHTML = "";
    return;
  }

  var html = "";
  for (var i = 0; i < order.length; i++) {
    var name = order[i];
    var st = state[name] || "pending";
    html += "<div class=\"step\">";
    html += "<span class=\"dot " + escapeHtml(st) + "\"></span>";
    html += "<span class=\"step-name\">" + escapeHtml(name) + "</span>";
    if (st === "running") {
      html += "<span class=\"pill running\">RUNNING</span>";
    }
    html += "</div>";
  }

  box.innerHTML = html;
}

function renderProgressSummary(summaryLine) {
  var node = el("progressSummary");
  if (!node) return;
  node.textContent = summaryLine || "(idle)";
}

function updateShortProgressFromText(text) {
  var progress = parseProgressFromText(text);
  renderProgressSteps(progress);
  renderProgressSummary(pickProgressSummaryLine(text));
}

function normStepName(s) {
  return String(s || "").replace(/\s+/g, " ").trim();
}

function deriveProgressFromEvents(events) {
  var order = [];
  var state = {};
  var currentRunning = "";
  var resultStatus = "";

  function ensureStep(name) {
    if (!name) return;
    if (!Object.prototype.hasOwnProperty.call(state, name)) {
      state[name] = "pending";
    }
    if (order.indexOf(name) < 0) order.push(name);
  }

  function setState(name, st) {
    name = normStepName(name);
    if (!name) return;
    ensureStep(name);
    state[name] = st;
  }

  for (var i = 0; i < (events || []).length; i++) {
    var ev = events[i];
    if (!ev || typeof ev !== "object") continue;
    var t = String(ev.type || "");

    if (t === "result") {
      resultStatus = ev.ok ? "success" : "fail";
      continue;
    }

    if (t !== "log") continue;

    var kind = String(ev.kind || "");
    if (kind !== "DO" && kind !== "OK" && kind !== "FAIL") continue;

    var stage = normStepName(ev.stage || "");
    if (!stage) continue;

    if (kind === "DO") {
      setState(stage, "running");
      currentRunning = stage;
      continue;
    }

    if (kind === "OK") {
      setState(stage, "ok");
      if (currentRunning === stage) currentRunning = "";
      continue;
    }

    if (kind === "FAIL") {
      setState(stage, "fail");
      if (currentRunning === stage) currentRunning = "";
      continue;
    }
  }

  if (currentRunning) {
    for (var j = 0; j < order.length; j++) {
      var nm = order[j];
      if (state[nm] === "running" && nm !== currentRunning) {
        state[nm] = "pending";
      }
    }
  }

  for (var k = 0; k < order.length; k++) {
    var nm2 = order[k];
    if (!Object.prototype.hasOwnProperty.call(state, nm2)) state[nm2] = "pending";
  }

  return { order: order, state: state, resultStatus: resultStatus };
}


  window.PatchHubAmpSettings = {
    renderAmpSettings: renderAmpSettings,
    parseProgressFromText: parseProgressFromText,
    updateShortProgressFromText: updateShortProgressFromText,
    deriveProgressFromEvents: deriveProgressFromEvents,
    updateProgressPanelFromEvents: updateProgressPanelFromEvents
  };
})();
