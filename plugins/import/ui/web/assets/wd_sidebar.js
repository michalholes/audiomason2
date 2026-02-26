(function () {
  "use strict";

  function buildSidebarTabs(ctx) {
    const flowSidebar = ctx && ctx.flowSidebar;
    const stepPanel = ctx && ctx.stepPanel;
    const transitionsPanel = ctx && ctx.transitionsPanel;
    const rightCol = ctx && ctx.rightCol;
    const state = ctx && ctx.state;
    const clear = ctx && ctx.clear;
    const el = ctx && ctx.el;
    const text = ctx && ctx.text;
    const renderTransitions = ctx && ctx.renderTransitions;

    if (!flowSidebar || !stepPanel) return;

    const tabBar = el("div", "flowRightTabs");
    const btnDetails = text("button", "flowRightTab", "Step Details");
    const btnTrans = text("button", "flowRightTab", "Transitions");
    const btnPalette = text("button", "flowRightTab", "Step Palette");
    btnDetails.type = "button";
    btnTrans.type = "button";
    btnPalette.type = "button";

    const panelDetails = el("div", "flowRightPanel");
    panelDetails.dataset.tab = "details";
    const panelTrans = el("div", "flowRightPanel");
    panelTrans.dataset.tab = "transitions";
    const panelPalette = el("div", "flowRightPanel");
    panelPalette.dataset.tab = "palette";

    panelDetails.appendChild(stepPanel);
    panelTrans.appendChild(transitionsPanel);
    panelPalette.appendChild(rightCol);

    tabBar.appendChild(btnDetails);
    tabBar.appendChild(btnTrans);
    tabBar.appendChild(btnPalette);

    clear(flowSidebar);
    flowSidebar.appendChild(tabBar);
    flowSidebar.appendChild(panelDetails);
    flowSidebar.appendChild(panelTrans);
    flowSidebar.appendChild(panelPalette);

    function setTab(name) {
      state.rightTab = name;
      btnDetails.classList.toggle("is-active", name === "details");
      btnTrans.classList.toggle("is-active", name === "transitions");
      btnPalette.classList.toggle("is-active", name === "palette");
      panelDetails.classList.toggle("is-active", name === "details");
      panelTrans.classList.toggle("is-active", name === "transitions");
      panelPalette.classList.toggle("is-active", name === "palette");
      if (name === "transitions" && renderTransitions) renderTransitions();
    }

    btnDetails.addEventListener("click", () => setTab("details"));
    btnTrans.addEventListener("click", () => setTab("transitions"));
    btnPalette.addEventListener("click", () => setTab("palette"));

    setTab(state.rightTab || "details");

    return { setTab: setTab };
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
    buildSidebarTabs: buildSidebarTabs,
    clearSidebar: clearSidebar,
    renderSidebar: renderSidebar,
  };
})();
