(function () {
  "use strict";

  function _section(title, body, el, text) {
    const wrap = el("div", "flowSidebarSection");
    const head = el("div", "flowSidebarSectionHead");
    head.appendChild(text("div", "flowSidebarSectionTitle", title));
    wrap.appendChild(head);
    if (body) wrap.appendChild(body);
    return wrap;
  }

  function buildSidebarSections(ctx) {
    const flowSidebar = ctx && ctx.flowSidebar;
    const stepPanel = ctx && ctx.stepPanel;
    const transitionsPanel = ctx && ctx.transitionsPanel;
    const rightCol = ctx && ctx.rightCol;
    const clear = ctx && ctx.clear;
    const el = ctx && ctx.el;
    const text = ctx && ctx.text;

    if (!flowSidebar || !stepPanel || !transitionsPanel || !rightCol) return;

    clear(flowSidebar);
    flowSidebar.appendChild(_section("Step Details", stepPanel, el, text));
    flowSidebar.appendChild(_section("Transitions", transitionsPanel, el, text));
    flowSidebar.appendChild(_section("Step Palette", rightCol, el, text));

    return {};
  }

  // Backward-compatible alias. Tabs are forbidden in the consolidated Flow Editor.
  function buildSidebarTabs(ctx) {
    return buildSidebarSections(ctx);
  }

  function clearSidebar(state) {
    state.selected = null;
    try {
      window.dispatchEvent(
        new CustomEvent("am2:wd:selected", {
          detail: { step_id: null },
        })
      );
    } catch (e) {
      // ignore
    }
  }

  function renderSidebar(state, stepId) {
    state.selected = stepId || null;
    try {
      window.dispatchEvent(
        new CustomEvent("am2:wd:selected", {
          detail: { step_id: state.selected },
        })
      );
    } catch (e) {
      // ignore
    }
  }

  window.AM2WDSidebar = {
    buildSidebarSections: buildSidebarSections,
    buildSidebarTabs: buildSidebarTabs,
    clearSidebar: clearSidebar,
    renderSidebar: renderSidebar,
  };
})();
