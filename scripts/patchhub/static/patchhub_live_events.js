(() => {
  var FT = (window.PatchHubFT || null);
  try {


  function noop() {}

  function nowMs() {
    try {
      return Date.now();
    } catch {
      return 0;
    }
  }

  function createRing(maxLen) {
    var buf = [];
    return {
      push: (x) => {
        buf.push(x);
        if (buf.length > maxLen) {
          buf.splice(0, buf.length - maxLen);
        }
      },
      clear: () => { buf = []; },
      list: () => buf.slice(),
      size: () => buf.length,
    };
  }

  function createThrottler(maxHz) {
    var intervalMs = 1000;
    if (maxHz && maxHz > 0) intervalMs = Math.max(50, Math.floor(1000 / maxHz));

    var last = 0;
    var scheduled = false;

    function schedule(fn) {
      if (scheduled) return;
      var t = nowMs();
      var wait = Math.max(0, intervalMs - (t - last));
      scheduled = true;
      setTimeout(() => {
        scheduled = false;
        last = nowMs();
        try { fn(); } catch (e) { if (FT) FT.report(e, "live.render"); }
      }, wait);
    }

    return { schedule: schedule };
  }

  function openLiveStream(jobId, ctx) {
    ctx = ctx || {};
    var setStatus = (typeof ctx.setStatus === "function") ? ctx.setStatus : noop;
    var onLogMaybe = (typeof ctx.onLogMaybe === "function") ? ctx.onLogMaybe : noop;
    var onProgress = (typeof ctx.onProgress === "function") ? ctx.onProgress : noop;
    var filterEvent = (typeof ctx.filterEvent === "function") ? ctx.filterEvent : (() => true);
    var fetchJob = (typeof ctx.fetchJob === "function") ? ctx.fetchJob : (() => Promise.resolve(null));

    var maxEvents = 2000;
    if (ctx.maxEvents && Number.isFinite(ctx.maxEvents) && ctx.maxEvents > 10) {
      maxEvents = Math.min(10000, Math.floor(ctx.maxEvents));
    }

    var maxHz = 8;
    if (ctx.renderMaxHz && Number.isFinite(ctx.renderMaxHz) && ctx.renderMaxHz > 0) {
      maxHz = Math.min(30, Math.floor(ctx.renderMaxHz));
    }

    var ring = createRing(maxEvents);
    var throttle = createThrottler(maxHz);

    function closeStream() {
      try {
        if (ctx.es) {
          try { ctx.es.close(); } catch {}
        }
      } finally {
        ctx.es = null;
        ctx.jobId = "";
      }
    }

    function resetUi() {
      ring.clear();
      onLogMaybe(ring.list());
      onProgress(ring.list());
    }

    if (!jobId) {
      closeStream();
      resetUi();
      setStatus("");
      return { close: closeStream, getEvents: ring.list };
    }

    jobId = String(jobId);
    if (ctx.jobId === jobId && ctx.es) {
      return { close: closeStream, getEvents: ring.list };
    }

    closeStream();
    ctx.jobId = jobId;
    resetUi();
    setStatus("connecting...");

    var url = `/api/jobs/${encodeURIComponent(jobId)}/events`;
    var es = new EventSource(url);
    ctx.es = es;

    es.onmessage = (e) => {
      if (!e || !e.data) return;
      var obj = null;
      try {
        obj = JSON.parse(String(e.data));
      } catch {
        obj = null;
      }
      if (!obj) return;

      ring.push(obj);

      var events = ring.list();
      if (filterEvent(obj)) {
        throttle.schedule(() => onLogMaybe(events));
      }
      throttle.schedule(() => onProgress(events));
      setStatus("streaming");
    };

    es.addEventListener("end", (e) => {
      let reason = "";
      let status = "";
      if (e?.data) {
        try {
          const p = JSON.parse(String(e.data));
          if (p && typeof p === "object") {
            reason = String(p.reason || "");
            status = String(p.status || "");
          }
        } catch {
          // best-effort
        }
      }
      let msg = "ended";
      if (status) msg += ` (${status})`;
      if (reason) msg += ` [${reason}]`;
      setStatus(msg);
      try { es.close(); } catch {}
      if (ctx.es === es) {
        ctx.es = null;
      }
    });

    es.onerror = () => {
      fetchJob(jobId).then((r) => {
        if (!r || r.ok === false) {
          closeStream();
          setStatus("ended [job_not_found]");
          return;
        }
        var j = r.job || {};
        var st = String(j.status || "");
        if (st && st !== "running" && st !== "queued") {
          closeStream();
          setStatus(`ended (${st}) [job_completed]`);
          return;
        }
        setStatus("reconnecting...");
      }).catch((e) => {
        if (FT) FT.report(e, "live.fetchJob");
        setStatus("reconnecting...");
      });
    };

    return { close: closeStream, getEvents: ring.list };
  }

  function installSafe() {
    try {
      window.PatchHubLive = {
        openLiveStream: openLiveStream,
      };
    } catch (e) {
      if (FT) FT.report(e, "live.install");
      window.PatchHubLive = { openLiveStream: () => ({ close: noop, getEvents: () => [] }) };
    }
  }

  try {
    installSafe();
  } catch (e) {
    if (FT) FT.report(e, "live.install_outer");
    window.PatchHubLive = { openLiveStream: () => ({ close: noop, getEvents: () => [] }) };
  }

  } catch (e) {
    if (FT) FT.report(e, "patchhub_live_events.js");
    try { console.error(e); } catch {}
    function noop() {}
    window.PatchHubLive = { openLiveStream: () => ({ close: noop, getEvents: () => [] }) };
  }
})();