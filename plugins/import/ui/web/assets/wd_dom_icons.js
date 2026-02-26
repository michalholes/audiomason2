(function () {
  "use strict";

  function svgIcon(name, cls, title) {
    const ns = "http://www.w3.org/2000/svg";
    const svg = document.createElementNS(ns, "svg");
    svg.setAttribute("viewBox", "0 0 24 24");
    svg.setAttribute("width", "16");
    svg.setAttribute("height", "16");
    svg.setAttribute("aria-hidden", "true");
    if (cls) svg.setAttribute("class", cls);

    if (title) {
      const t = document.createElementNS(ns, "title");
      t.textContent = String(title);
      svg.appendChild(t);
    }

    const p = document.createElementNS(ns, "path");

    if (name === "lock") {
      p.setAttribute(
        "d",
        "M17 10V8a5 5 0 0 0-10 0v2H6a2 2 0 0 0-2 2v7a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-7a2 2 0 0 0-2-2h-1Zm-8 0V8a3 3 0 0 1 6 0v2H9Z"
      );
    } else if (name === "trash") {
      p.setAttribute(
        "d",
        "M9 3h6l1 2h4v2h-2l-1 14a2 2 0 0 1-2 2H9a2 2 0 0 1-2-2L6 7H4V5h4l1-2Zm0 4 1 14h4l1-14H9Zm2 2h2v10h-2V9Z"
      );
    } else if (name === "check") {
      p.setAttribute("d", "M9 16.2 4.8 12l-1.4 1.4L9 19 21 7l-1.4-1.4z");
    } else if (name === "search") {
      p.setAttribute(
        "d",
        "M10 2a8 8 0 1 0 4.9 14.3l4.4 4.4 1.4-1.4-4.4-4.4A8 8 0 0 0 10 2Zm0 2a6 6 0 1 1 0 12 6 6 0 0 1 0-12Z"
      );
    } else if (name === "grip") {
      p.setAttribute(
        "d",
        "M9 5a1 1 0 1 1-2 0 1 1 0 0 1 2 0Zm0 7a1 1 0 1 1-2 0 1 1 0 0 1 2 0Zm0 7a1 1 0 1 1-2 0 1 1 0 0 1 2 0Zm8-14a1 1 0 1 1-2 0 1 1 0 0 1 2 0Zm0 7a1 1 0 1 1-2 0 1 1 0 0 1 2 0Zm0 7a1 1 0 1 1-2 0 1 1 0 0 1 2 0Z"
      );
    } else if (name === "required") {
      p.setAttribute(
        "d",
        "M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20Zm1 5v6h-2V7h2Zm0 8v2h-2v-2h2Z"
      );
    }

    svg.appendChild(p);
    return svg;
  }

  window.AM2WDDomIcons = { svgIcon: svgIcon };
})();
