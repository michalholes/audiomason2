(function () {
  "use strict";

  function clear(node) {
    while (node && node.firstChild) node.removeChild(node.firstChild);
  }

  function renderPalette(opts) {
    const mount = opts && opts.mount;
    const items = (opts && opts.items) || [];
    const state = (opts && opts.state) || {};
    const el = (opts && opts.el) || function () {};
    const text = (opts && opts.text) || function () {};

    if (!mount) return;
    clear(mount);

    const header = el("div", "wdPaletteHeader");
    header.appendChild(text("div", "wdPaletteTitle", "Step Palette"));
    mount.appendChild(header);

    const searchWrap = el("div", "wdPaletteSearch");
    const search = el("input", "wdPaletteSearchInput");
    search.type = "search";
    search.placeholder = "Search";
    searchWrap.appendChild(search);
    mount.appendChild(searchWrap);

    const list = el("div", "wdPaletteGroups");
    mount.appendChild(list);

    function matches(it, q) {
      if (!q) return true;
      const s = (
        String((it && it.step_id) || "") +
        " " +
        String((it && it.displayName) || "") +
        " " +
        String((it && it.title) || "")
      )
        .toLowerCase()
        .trim();
      return s.indexOf(q.toLowerCase().trim()) >= 0;
    }

    function renderList() {
      clear(list);
      const q = String(search.value || "");
      (Array.isArray(items) ? items : []).forEach(function (it) {
        if (!matches(it, q)) return;
        const sid = String(it && it.step_id ? it.step_id : "");
        if (!sid) return;

        const row = el("div", "wdPaletteItem");
        const meta = el("div", "wdPaletteMeta");
        meta.appendChild(text("div", "wdPaletteItemId", sid));
        meta.appendChild(
          text("div", "wdPaletteItemTitle", String(it.displayName || it.title || sid))
        );

        const btn = text("button", "btn btnSmall", "Add");
        btn.type = "button";
        btn.disabled = !(state.canAdd && state.canAdd(sid));
        btn.classList.toggle("is-disabled", btn.disabled);
        btn.addEventListener("click", function () {
          state.addStep && state.addStep(sid);
        });

        row.appendChild(meta);
        row.appendChild(btn);
        list.appendChild(row);
      });
    }

    search.addEventListener("input", function () {
      renderList();
    });

    renderList();
  }

  window.AM2WDPaletteRender = {
    renderPalette: renderPalette,
  };
})();
