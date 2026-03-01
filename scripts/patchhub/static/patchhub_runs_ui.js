(() => {
  var FT = (window.PatchHubFT || null);

  function el(id) {
    return document.getElementById(String(id));
  }

  function bindRunsList(container, getRuns, onSelect) {
    var node = (typeof container === "string") ? el(container) : container;
    if (!node) return;
    if (node.__phBound) return;
    node.__phBound = true;

    node.addEventListener("click", (e) => {
      try {
        const t = e?.target ?? null;
        if (!t) return;
        const nameNode = t.closest?.(".runitem .name") ?? null;
        if (!nameNode) return;
        const item = nameNode.parentElement;
        if (!item) return;
        const idx = Number.parseInt(item.getAttribute("data-idx") ?? "-1", 10);
        if (!Number.isFinite(idx) || idx < 0) return;

        const runs = (typeof getRuns === "function") ? getRuns() : [];
        if (!runs || idx >= runs.length) return;

        if (typeof onSelect === "function") {
          onSelect(runs[idx]);
        }
      } catch (err) {
        if (FT) FT.report(err, "runs.click");
      }
    });
  }

  function installSafe() {
    window.PatchHubRunsUI = {
      bindRunsList: bindRunsList,
    };
  }

  try {
    installSafe();
  } catch (e) {
    if (FT) FT.report(e, "runs.install");
    window.PatchHubRunsUI = { bindRunsList: () => {} };
  }
})();
