(() => {
  function ensureBanner() {
    var id = "patchhubFaultBanner";
    var node = document.getElementById(id);
    if (node) return node;

    node = document.createElement("div");
    node.id = id;
    node.style.display = "none";
    node.style.position = "fixed";
    node.style.top = "0";
    node.style.left = "0";
    node.style.right = "0";
    node.style.zIndex = "9999";
    node.style.padding = "8px 12px";
    node.style.background = "#5b0000";
    node.style.color = "#fff";
    node.style.fontFamily = "system-ui, -apple-system, Segoe UI, Roboto, sans-serif";
    node.style.fontSize = "13px";
    node.style.lineHeight = "1.35";
    node.style.whiteSpace = "pre-wrap";

    function attach() {
      try {
        if (!document.body) return;
        if (document.getElementById(id)) return;
        document.body.appendChild(node);
      } catch {
        // best-effort
      }
    }

    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", attach);
    } else {
      attach();
    }

    return node;
  }

  var faults = [];

  function renderBanner() {
    var node = ensureBanner();
    if (!node) return;

    if (!faults.length) {
      node.style.display = "none";
      node.textContent = "";
      return;
    }

    node.style.display = "block";
    var head = "PatchHub degraded mode: ";
    node.textContent = `${head}${faults.join("\n")}`;
  }

  function normErr(err) {
    if (!err) return "";
    if (typeof err === "string") return err;
    var msg = "";
    try {
      msg = String(err.message || err);
    } catch {
      msg = "(unprintable error)";
    }
    var name = "";
    try {
      name = String(err.name || "");
    } catch {
      name = "";
    }
    if (name && msg && !msg.startsWith(name)) return `${name}: ${msg}`;
    return msg || name || "(error)";
  }

  function addFault(line) {
    line = String(line || "").trim();
    if (!line) return;
    if (faults.includes(line)) return;
    faults.push(line);
    renderBanner();
  }

  function report(err, context) {
    var ctx = String(context || "").trim();
    var msg = normErr(err);
    var line = ctx ? `${ctx}: ${msg}` : msg;
    addFault(line);
    try {
      // eslint-disable-next-line no-console
      console.error("PatchHub fault", { context: ctx, error: err });
    } catch {
      // best-effort
    }
  }

  function getGlobal(name, fallback) {
    name = String(name || "").trim();
    if (!name) return fallback;
    if (Object.hasOwn(window, name)) return window[name];
    addFault(`Missing module: ${name}`);
    return fallback;
  }

  function installGlobalHandlers() {
    try {
      window.addEventListener("error", (e) => {
        try {
          const msg = e?.message ? String(e.message) : "window.error";
          report(e?.error ?? msg, "window.error");
        } catch {
          // best-effort
        }
      });
    } catch {
      // best-effort
    }

    try {
      window.addEventListener("unhandledrejection", (e) => {
        try {
          report(e?.reason ?? "unhandledrejection", "unhandledrejection");
        } catch {
          // best-effort
        }
      });
    } catch {
      // best-effort
    }
  }

  installGlobalHandlers();

  window.PatchHubFT = {
    getGlobal: getGlobal,
    report: report,
  };
})();
