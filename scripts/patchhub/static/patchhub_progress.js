(() => {
  function el(id) {
    return document.getElementById(String(id));
  }

  function escapeHtml(s) {
    s = String(s == null ? "" : s);
    return s.replace(/[&<>"']/g, (c) => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      "\"": "&quot;",
      "'": "&#39;",
    }[c] || c));
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
        if (!Object.hasOwn(state, name)) {
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

      for (let i = 0; i < lines.length; i++) {
        const raw = String(lines[i] || "");
        const s = raw.trim();
        if (!s) continue;

        if (s.indexOf("DO:") === 0) {
          const stepDo = normStepName(s.slice(3));
          setState(stepDo, "running");
          currentRunning = stepDo;
          continue;
        }

        if (s.indexOf("OK:") === 0) {
          const stepOk = normStepName(s.slice(3));
          setState(stepOk, "ok");
          if (currentRunning === stepOk) currentRunning = "";
          continue;
        }

        if (s.indexOf("FAIL:") === 0) {
          const stepFail = normStepName(s.slice(5));
          setState(stepFail, "fail");
          if (currentRunning === stepFail) currentRunning = "";
          continue;
        }

        if (s.indexOf("ERROR:") === 0 || s === "FAIL" || s.indexOf("FAIL ") === 0) {
          if (currentRunning) setState(currentRunning, "fail");
        }
      }

      if (currentRunning) {
        for (let j = 0; j < order.length; j++) {
          const nm = order[j];
          if (state[nm] === "running" && nm !== currentRunning) {
            state[nm] = "pending";
          }
        }
      }

      for (let k = 0; k < order.length; k++) {
        const nm2 = order[k];
        if (!Object.hasOwn(state, nm2)) state[nm2] = "pending";
      }

      return { order: order, state: state };
    }

    function pickProgressSummaryLine(text) {
      var lines = String(text || "").split(/\r?\n/);
      for (let i = lines.length - 1; i >= 0; i--) {
        const s = String(lines[i] || "").trim();
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

      var order = (progress?.order) ? progress.order : [];
      var state = (progress?.state) ? progress.state : {};

      if (!order.length) {
        box.innerHTML = "";
        return;
      }

      var html = "";
      for (let i = 0; i < order.length; i++) {
        const name = order[i];
        const st = state[name] || "pending";
        html += "<div class=\"step\">";
        html += `<span class="dot ${escapeHtml(st)}"></span>`;
        html += `<span class="step-name">${escapeHtml(name)}</span>`;
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
        if (!Object.hasOwn(state, name)) {
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

      for (let i = 0; i < (events || []).length; i++) {
        const ev = events[i];
        if (!ev || typeof ev !== "object") continue;
        const t = String(ev.type || "");

        if (t === "result") {
          resultStatus = ev.ok ? "success" : "fail";
          continue;
        }

        if (t !== "log") continue;

        const kind = String(ev.kind || "");
        if (kind !== "DO" && kind !== "OK" && kind !== "FAIL") continue;

        const stage = normStepName(ev.stage || "");
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
        }
      }

      if (currentRunning) {
        for (let j = 0; j < order.length; j++) {
          const nm = order[j];
          if (state[nm] === "running" && nm !== currentRunning) {
            state[nm] = "pending";
          }
        }
      }

      for (let k = 0; k < order.length; k++) {
        const nm2 = order[k];
        if (!Object.hasOwn(state, nm2)) state[nm2] = "pending";
      }

      return { order: order, state: state, resultStatus: resultStatus };
    }

    function deriveProgressSummaryFromEvents(events, progress) {
      var lastResult = null;
      var lastLog = null;
      for (let i = (events || []).length - 1; i >= 0; i--) {
        const ev = events[i];
        if (!ev || typeof ev !== "object") continue;
        const t = String(ev.type || "");
        if (t === "result") {
          lastResult = ev;
          break;
        }
        if (t === "log") {
          const kind = String(ev.kind || "");
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
        const stage = normStepName(lastLog.stage || "");
        const kind = String(lastLog.kind || "");
        if (kind === "FAIL") {
          return { text: `FAIL: ${stage}`, status: "fail" };
        }
        if (kind === "OK") {
          return { text: `OK: ${stage}`, status: "running" };
        }
        if (kind === "DO") {
          return { text: `DO: ${stage}`, status: "running" };
        }
      }

      if (progress?.order?.length) {
        return { text: "STATUS: RUNNING", status: "running" };
      }
      return { text: "(idle)", status: "idle" };
    }

    function setProgressSummaryState(summary) {
      var node = el("progressSummary");
      if (!node) return;
      var st = (summary?.status) ? String(summary.status) : "idle";
      node.classList.remove("success", "fail", "running", "idle", "muted");
      node.classList.add(st);
      if (st === "idle") node.classList.add("muted");
    }

    function updateProgressPanelFromEvents(events) {
      var progress = deriveProgressFromEvents(events);
      renderProgressSteps(progress);
      var summary = deriveProgressSummaryFromEvents(events, progress);
      renderProgressSummary(summary.text);
      setProgressSummaryState(summary);
    }

  window.PatchHubProgress = {
    parseProgressFromText: parseProgressFromText,
    pickProgressSummaryLine: pickProgressSummaryLine,
    renderProgressSteps: renderProgressSteps,
    renderProgressSummary: renderProgressSummary,
    updateShortProgressFromText: updateShortProgressFromText,
    deriveProgressFromEvents: deriveProgressFromEvents,
    deriveProgressSummaryFromEvents: deriveProgressSummaryFromEvents,
    setProgressSummaryState: setProgressSummaryState,
    updateProgressPanelFromEvents: updateProgressPanelFromEvents,
  };
})();
