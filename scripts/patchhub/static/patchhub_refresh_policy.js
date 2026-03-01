(() => {
  var FT = (window.PatchHubFT || null);

  function noop() {}

  function safeCall(fn) {
    try {
      if (typeof fn === "function") return fn();
    } catch (e) {
      if (FT) FT.report(e, "refresh.safeCall");
    }
    return undefined;
  }

  function _safeCall1(fn, a1) {
    try {
      if (typeof fn === "function") return fn(a1);
    } catch (e) {
      if (FT) FT.report(e, "refresh.safeCall1");
    }
    return undefined;
  }

  function _safeCall2(fn, a1, a2) {
    try {
      if (typeof fn === "function") return fn(a1, a2);
    } catch (e) {
      if (FT) FT.report(e, "refresh.safeCall2");
    }
    return undefined;
  }

  function buildUrlWithToken(path, token) {
    if (!token) return path;
    var sep = path.includes("?") ? "&" : "?";
    return `${path}${sep}last_token=${encodeURIComponent(String(token))}`;
  }

  function createTokenClient() {
    var tokens = Object.create(null);
    var inflight = Object.create(null);
    var seq = Object.create(null);
    var lastGood = Object.create(null);

    function tokenGetJson(path, key) {
      key = String(key || path);
      if (inflight[key]) return inflight[key];

      var s = (seq[key] || 0) + 1;
      seq[key] = s;

      var t = tokens[key] || "";
      var url = buildUrlWithToken(String(path), t);

      inflight[key] = fetch(url, { headers: { "Accept": "application/json" } })
        .then((r) => r.text().then((txt) => {
          var data = null;
          try {
            data = JSON.parse(String(txt));
          } catch {
            data = { ok: false, error: "bad json", raw: txt, status: r.status };
          }
          return { data: data, seq: s };
        }))
        .catch((e) => {
          return { data: { ok: false, error: "fetch failed", detail: String(e) }, seq: s };
        })
        .then((res) => {
          if (seq[key] !== res.seq) return { stale: true, data: null };

          var data = res.data;
          let newToken = "";
          if (data && data.ok !== false) {
            try {
              newToken = String(data.token || "");
            } catch {
              newToken = "";
            }
            if (newToken) tokens[key] = newToken;
          }

          if (data && data.unchanged === true) {
            const prev = lastGood[key] || null;
            return { stale: false, data: prev };
          }
          if (data && data.ok !== false) lastGood[key] = data;
          return { stale: false, data: data };
        })
        .finally(() => {
          inflight[key] = null;
        });

      return inflight[key];
    }

    function getToken(key) {
      return String(tokens[String(key || "")] || "");
    }

    return { tokenGetJson: tokenGetJson, getToken: getToken };
  }

  function createDomGuard() {
    var sig = Object.create(null);

    function setHtmlIfChanged(node, html, key) {
      if (!node) return false;
      key = String(key || "");
      html = String(html == null ? "" : html);
      if (key && sig[key] === html) return false;
      if (key) sig[key] = html;
      node.innerHTML = html;
      return true;
    }

    function setTextIfChanged(node, text, key) {
      if (!node) return false;
      key = String(key || "");
      text = String(text == null ? "" : text);
      if (key && sig[key] === text) return false;
      if (key) sig[key] = text;
      node.textContent = text;
      return true;
    }

    return { setHtmlIfChanged: setHtmlIfChanged, setTextIfChanged: setTextIfChanged };
  }

  function createScheduler() {
    var visible = true;
    var timer = null;
    var mode = "IDLE";
    var _lastTickMs = 0;

    var intervalIdleMs = 10000;
    var intervalActiveMs = 1500;

    var ctx = null;

    function clearTimer() {
      if (!timer) return;
      try { clearTimeout(timer); } catch {}
      timer = null;
    }

    function computeMode() {
      if (!ctx) return "IDLE";
      var isActive = false;
      try {
        if (typeof ctx.isActive === "function") {
          isActive = !!ctx.isActive();
        } else {
          isActive = !!(ctx.getActiveJobId?.());
        }
      } catch {
        isActive = false;
      }
      return isActive ? "ACTIVE" : "IDLE";
    }

    function scheduleNext(delayMs) {
      clearTimer();
      timer = setTimeout(tick, Math.max(0, delayMs));
    }

    function tick() {
      if (!ctx) return;
      if (!visible) return;

      mode = computeMode();
      _lastTickMs = Date.now();

      // ACTIVE prefers event-driven updates; polling is best-effort.
      safeCall(ctx.tickMissingPatchClear);

      if (mode === "ACTIVE") {
        safeCall(ctx.refreshJobs);
        safeCall(ctx.refreshRuns);
        safeCall(ctx.refreshHeader);
        safeCall(ctx.refreshJobs);
        safeCall(ctx.refreshTail);
      } else {
        // IDLE: max once per 10s, and only conditional refreshes in refresh funcs.
        safeCall(ctx.refreshRuns);
        safeCall(ctx.refreshHeader);
        safeCall(ctx.refreshJobs);
      }

      scheduleNext(mode === "ACTIVE" ? intervalActiveMs : intervalIdleMs);
    }

    function setVisible(v) {
      visible = !!v;
      if (!visible) {
        clearTimer();
        safeCall(ctx?.pauseLiveStream);
        return;
      }
      scheduleNext(0);
    }

    function install(newCtx) {
      ctx = newCtx || null;
      scheduleNext(0);
    }

    function pokeSoon() {
      if (!visible) return;
      scheduleNext(0);
    }

    return { install: install, setVisible: setVisible, pokeSoon: pokeSoon };
  }

  function ensureAutoRefresh(jobs, hooks) {
    hooks = hooks || {};
    try {
      const getLiveJobId = (typeof hooks.getLiveJobId === "function")
        ? hooks.getLiveJobId
        : (() => "");
      const openLiveStream = (typeof hooks.openLiveStream === "function")
        ? hooks.openLiveStream
        : noop;
      const closeLiveStream = (typeof hooks.closeLiveStream === "function")
        ? hooks.closeLiveStream
        : noop;
      const pokeSoon = (typeof hooks.pokeSoon === "function")
        ? hooks.pokeSoon
        : noop;

      const id = String(getLiveJobId() || "");
      let st = "";
      if (id && jobs && jobs.length) {
        const j = jobs.find((x) => String(x.job_id || "") === id) || null;
        st = j ? String(j.status || "") : "";
      }

      if (st === "running" || st === "queued") {
        openLiveStream(id);
        pokeSoon();
      } else {
        closeLiveStream();
      }
    } catch (e) {
      if (FT) FT.report(e, "refresh.ensureAutoRefresh");
    }
  }


  function installSafe() {
    var tokenClient = createTokenClient();
    var dom = createDomGuard();
    var sched = createScheduler();

    window.PatchHubRefreshPolicy = {
      ensureAutoRefresh: ensureAutoRefresh,
      tokenGetJson: tokenClient.tokenGetJson,
      getToken: tokenClient.getToken,
      setHtmlIfChanged: dom.setHtmlIfChanged,
      setTextIfChanged: dom.setTextIfChanged,
      install: sched.install,
      setVisible: sched.setVisible,
      pokeSoon: sched.pokeSoon,
    };
  }

  try {
    installSafe();
  } catch (e) {
    if (FT) FT.report(e, "refresh.install");
    window.PatchHubRefreshPolicy = {
      tokenGetJson: () => Promise.resolve({ stale: false, data: null }),
      getToken: () => "",
      setHtmlIfChanged: () => false,
      setTextIfChanged: () => false,
      install: noop,
      setVisible: noop,
      pokeSoon: noop,
    };
  }
})();
