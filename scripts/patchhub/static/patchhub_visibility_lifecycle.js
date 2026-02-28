(function () {
  function safeClearTimer(ctx, key) {
    try {
      if (ctx && ctx[key]) {
        clearInterval(ctx[key]);
      }
    } catch (e) {
      // best-effort
    }
    try {
      if (ctx) {
        ctx[key] = null;
      }
    } catch (e2) {
      // best-effort
    }
  }

  function safeCall(fn) {
    try {
      if (typeof fn === "function") {
        fn();
      }
    } catch (e) {
      // best-effort
    }
  }

  function safeCall1(fn, a1) {
    try {
      if (typeof fn === "function") {
        fn(a1);
      }
    } catch (e) {
      // best-effort
    }
  }

  function pause(ctx) {
    safeClearTimer(ctx, "autoRefreshTimer");
    safeClearTimer(ctx, "autofillTimer");
    safeClearTimer(ctx, "patchStatTimer");
    safeClearTimer(ctx, "jobsTailTimer");
    safeClearTimer(ctx, "headerTimer");
    safeCall(ctx && ctx.closeLiveStream);
  }

  function resume(ctx) {
    if (!ctx) return;

    if (!ctx.patchStatTimer) {
      ctx.patchStatTimer = setInterval(function () {
        safeCall(ctx.tickMissingPatchClear);
      }, 1000);
    }

    if (!ctx.jobsTailTimer) {
      ctx.jobsTailTimer = setInterval(function () {
        safeCall(ctx.refreshJobs);
        safeCall1(ctx.refreshTail, ctx.tailLines);
      }, 2000);
    }

    if (!ctx.headerTimer) {
      ctx.headerTimer = setInterval(function () {
        safeCall(ctx.refreshHeader);
      }, 5000);
    }

    safeCall(ctx.startAutofillPolling);
    safeCall(ctx.refreshJobs);
    safeCall1(ctx.refreshTail, ctx.tailLines);
    safeCall(ctx.refreshHeader);
  }

  function install(ctx) {
    function onVisibility() {
      if (document.hidden) {
        pause(ctx);
      } else {
        resume(ctx);
      }
    }

    try {
      document.addEventListener("visibilitychange", onVisibility);
    } catch (e) {
      // best-effort
    }

    onVisibility();
  }

  window.PatchHubVisibilityLifecycle = {
    install: install,
    pause: pause,
    resume: resume,
  };
})();
