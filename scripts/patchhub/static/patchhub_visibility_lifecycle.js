(() => {
  function safeCall1(fn, a1) {
    try {
      if (typeof fn === "function") {
        fn(a1);
      }
    } catch {
      // best-effort
    }
  }

  function install(ctx) {
    var FT = (window.PatchHubFT ?? null);
    var RP = FT ? FT.getGlobal("PatchHubRefreshPolicy", null) : (window.PatchHubRefreshPolicy ?? null);

    function onVisibility() {
      var isVisible = !document.hidden;
      safeCall1(RP?.setVisible, isVisible);
    }

    try {
      document.addEventListener("visibilitychange", onVisibility);
    } catch {
      // best-effort
    }

    // Install scheduler context once; visibility only gates it.
    safeCall1(RP?.install, ctx);
    onVisibility();
  }

  window.PatchHubVisibilityLifecycle = {
    install: install,
  };
})();
